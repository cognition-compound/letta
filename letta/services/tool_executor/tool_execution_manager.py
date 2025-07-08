import asyncio
import traceback
import uuid
from typing import Any, Dict, List, Optional, Type

from opentelemetry.trace import Span

from letta.constants import FUNCTION_RETURN_VALUE_TRUNCATED
from letta.helpers.datetime_helpers import AsyncTimer
from letta.log import get_logger
from letta.orm.enums import ToolType
from letta.otel.context import get_ctx_attributes
from letta.otel.metric_registry import MetricRegistry
from letta.otel.tracing import trace_method
from letta.schemas.agent import AgentState
from letta.schemas.openai.chat_completion_response import ToolCall
from letta.schemas.parallel_tool_call import ParallelExecutionSummary, ParallelToolCallConfig, ParallelToolCallResult
from letta.schemas.sandbox_config import SandboxConfig
from letta.schemas.tool import Tool
from letta.schemas.tool_execution_result import ToolExecutionResult
from letta.schemas.user import User
from letta.services.agent_manager import AgentManager
from letta.services.block_manager import BlockManager
from letta.services.job_manager import JobManager
from letta.services.message_manager import MessageManager
from letta.services.passage_manager import PassageManager
from letta.services.tool_executor.builtin_tool_executor import LettaBuiltinToolExecutor
from letta.services.tool_executor.composio_tool_executor import ExternalComposioToolExecutor
from letta.services.tool_executor.core_tool_executor import LettaCoreToolExecutor
from letta.services.tool_executor.files_tool_executor import LettaFileToolExecutor
from letta.services.tool_executor.mcp_tool_executor import ExternalMCPToolExecutor
from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
from letta.services.tool_executor.tool_executor import SandboxToolExecutor
from letta.services.tool_executor.tool_executor_base import ToolExecutor
from letta.utils import get_friendly_error_msg


class ToolExecutorFactory:
    """Factory for creating appropriate tool executors based on tool type."""

    _executor_map: Dict[ToolType, Type[ToolExecutor]] = {
        ToolType.LETTA_CORE: LettaCoreToolExecutor,
        ToolType.LETTA_MEMORY_CORE: LettaCoreToolExecutor,
        ToolType.LETTA_SLEEPTIME_CORE: LettaCoreToolExecutor,
        ToolType.LETTA_MULTI_AGENT_CORE: LettaMultiAgentToolExecutor,
        ToolType.LETTA_BUILTIN: LettaBuiltinToolExecutor,
        ToolType.LETTA_FILES_CORE: LettaFileToolExecutor,
        ToolType.EXTERNAL_COMPOSIO: ExternalComposioToolExecutor,
        ToolType.EXTERNAL_MCP: ExternalMCPToolExecutor,
    }

    @classmethod
    def get_executor(
        cls,
        tool_type: ToolType,
        message_manager: MessageManager,
        agent_manager: AgentManager,
        block_manager: BlockManager,
        job_manager: JobManager,
        passage_manager: PassageManager,
        actor: User,
    ) -> ToolExecutor:
        """Get the appropriate executor for the given tool type."""
        executor_class = cls._executor_map.get(tool_type, SandboxToolExecutor)
        return executor_class(
            message_manager=message_manager,
            agent_manager=agent_manager,
            block_manager=block_manager,
            job_manager=job_manager,
            passage_manager=passage_manager,
            actor=actor,
        )


class ToolExecutionManager:
    """Manager class for tool execution operations."""

    def __init__(
        self,
        message_manager: MessageManager,
        agent_manager: AgentManager,
        block_manager: BlockManager,
        job_manager: JobManager,
        passage_manager: PassageManager,
        actor: User,
        agent_state: Optional[AgentState] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        sandbox_env_vars: Optional[Dict[str, Any]] = None,
    ):
        self.message_manager = message_manager
        self.agent_manager = agent_manager
        self.block_manager = block_manager
        self.job_manager = job_manager
        self.passage_manager = passage_manager
        self.agent_state = agent_state
        self.logger = get_logger(__name__)
        self.actor = actor
        self.sandbox_config = sandbox_config
        self.sandbox_env_vars = sandbox_env_vars

    @trace_method
    async def execute_tool_async(
        self, function_name: str, function_args: dict, tool: Tool, step_id: str | None = None
    ) -> ToolExecutionResult:
        """
        Execute a tool asynchronously and persist any state changes.
        """
        status = "error"  # set as default for tracking purposes
        try:
            executor = ToolExecutorFactory.get_executor(
                tool.tool_type,
                message_manager=self.message_manager,
                agent_manager=self.agent_manager,
                block_manager=self.block_manager,
                job_manager=self.job_manager,
                passage_manager=self.passage_manager,
                actor=self.actor,
            )

            def _metrics_callback(exec_time_ms: int, exc):
                return MetricRegistry().tool_execution_time_ms_histogram.record(
                    exec_time_ms, dict(get_ctx_attributes(), **{"tool.name": tool.name})
                )

            async with AsyncTimer(callback_func=_metrics_callback):
                result = await executor.execute(
                    function_name, function_args, tool, self.actor, self.agent_state, self.sandbox_config, self.sandbox_env_vars
                )
            status = result.status

            # trim result
            return_str = str(result.func_return)
            if len(return_str) > tool.return_char_limit:
                # TODO: okay that this become a string?
                result.func_return = FUNCTION_RETURN_VALUE_TRUNCATED(return_str, len(return_str), tool.return_char_limit)
            return result

        except Exception as e:
            status = "error"
            self.logger.error(f"Error executing tool {function_name}: {str(e)}")
            error_message = get_friendly_error_msg(
                function_name,
                type(e).__name__,
                str(e),
            )
            return ToolExecutionResult(
                status="error",
                func_return=error_message,
                stderr=[traceback.format_exc()],
            )
        finally:
            metric_attrs = {"tool.name": tool.name, "tool.execution_success": status == "success"}
            if status == "error" and step_id:
                metric_attrs["step.id"] = step_id
            MetricRegistry().tool_execution_counter.add(1, dict(get_ctx_attributes(), **metric_attrs))

    @trace_method
    async def execute_tools_parallel_async(
        self,
        tool_calls: List[ToolCall],
        agent_state: AgentState,
        config: ParallelToolCallConfig,
        agent_step_span: Optional[Span] = None,
        step_id: str | None = None,
    ) -> ParallelExecutionSummary:
        """
        Execute multiple tool calls in parallel and return a summary of results.
        
        Args:
            tool_calls: List of tool calls to execute
            agent_state: Current agent state containing available tools
            config: Configuration for parallel execution
            agent_step_span: Optional span for tracing
            step_id: Optional step identifier
            
        Returns:
            ParallelExecutionSummary with results of all tool executions
        """
        if not tool_calls:
            return ParallelExecutionSummary(
                results=[],
                total_execution_time_ms=0.0,
                successful_count=0,
                failed_count=0,
                continue_stepping=False,
                stop_reason=None,
            )

        # Check if we should execute sequentially instead
        tool_names = [tc.function.name for tc in tool_calls]
        if config.should_execute_sequentially(tool_names):
            self.logger.info(f"Executing {len(tool_calls)} tools sequentially due to configuration")
            return await self._execute_tools_sequentially(tool_calls, agent_state, config, agent_step_span, step_id)

        self.logger.info(f"Executing {len(tool_calls)} tools in parallel")
        
        # Prepare individual tool execution tasks
        tasks = []
        start_time = asyncio.get_event_loop().time()
        
        for tool_call in tool_calls[:config.max_concurrent_tools]:  # Respect concurrency limit
            task = self._execute_single_tool_call(tool_call, agent_state, config, agent_step_span, step_id)
            tasks.append(task)

        # Execute all tools in parallel with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=config.timeout_per_tool_seconds * len(tasks),  # Allow extra time for parallel execution
            )
        except asyncio.TimeoutError:
            self.logger.error(f"Parallel tool execution timed out after {config.timeout_per_tool_seconds * len(tasks)} seconds")
            results = [Exception("Execution timed out") for _ in tasks]

        # Calculate execution time
        end_time = asyncio.get_event_loop().time()
        total_execution_time_ms = (end_time - start_time) * 1000

        # Process results
        parallel_results = []
        successful_count = 0
        failed_count = 0
        continue_stepping = False

        for i, result in enumerate(results):
            tool_call = tool_calls[i]
            
            if isinstance(result, Exception):
                # Handle exception case
                error_result = ParallelToolCallResult(
                    tool_call_id=tool_call.id or f"call_{uuid.uuid4().hex[:8]}",
                    tool_call=tool_call,
                    execution_result=ToolExecutionResult(
                        status="error",
                        func_return=f"Tool execution failed: {str(result)}",
                        stderr=[traceback.format_exc()],
                    ),
                    execution_time_ms=0.0,
                    error=str(result),
                )
                parallel_results.append(error_result)
                failed_count += 1
            elif isinstance(result, ParallelToolCallResult):
                # Handle successful result
                parallel_results.append(result)
                if result.success_flag:
                    successful_count += 1
                    # Check if any tool requested heartbeat (continue stepping)
                    if hasattr(result.execution_result, 'func_return'):
                        continue_stepping = True  # Conservative approach - continue if any tool succeeded
                else:
                    failed_count += 1

        # Log metrics for parallel execution
        if agent_step_span:
            agent_step_span.add_event(
                name="parallel_tool_execution_completed",
                attributes={
                    "total_tools": len(tool_calls),
                    "successful_tools": successful_count,
                    "failed_tools": failed_count,
                    "total_duration_ms": total_execution_time_ms,
                    "parallel_execution": True,
                },
            )

        # Record metrics
        for result in parallel_results:
            metric_attrs = {
                "tool.name": result.tool_call.function.name,
                "tool.execution_success": result.success_flag,
                "parallel_execution": True,
            }
            if not result.success_flag and step_id:
                metric_attrs["step.id"] = step_id
            MetricRegistry().tool_execution_counter.add(1, dict(get_ctx_attributes(), **metric_attrs))

        return ParallelExecutionSummary(
            results=parallel_results,
            total_execution_time_ms=total_execution_time_ms,
            successful_count=successful_count,
            failed_count=failed_count,
            continue_stepping=continue_stepping,
            stop_reason=None,
        )

    async def _execute_single_tool_call(
        self,
        tool_call: ToolCall,
        agent_state: AgentState,
        config: ParallelToolCallConfig,
        agent_step_span: Optional[Span] = None,
        step_id: str | None = None,
    ) -> ParallelToolCallResult:
        """Execute a single tool call and return wrapped result."""
        import uuid
        from letta.agents.helpers import _safe_load_tool_call_str, _pop_heartbeat

        tool_call_id = tool_call.id or f"call_{uuid.uuid4().hex[:8]}"
        tool_name = tool_call.function.name
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Find the tool in agent state
            target_tool = next((x for x in agent_state.tools if x.name == tool_name), None)
            if not target_tool:
                raise ValueError(f"Tool {tool_name} not found in agent state")

            # Parse tool arguments
            tool_args = _safe_load_tool_call_str(tool_call.function.arguments)
            _pop_heartbeat(tool_args)  # Remove heartbeat from args

            # Execute the tool
            execution_result = await self.execute_tool_async(
                function_name=tool_name,
                function_args=tool_args,
                tool=target_tool,
                step_id=step_id,
            )

            end_time = asyncio.get_event_loop().time()
            execution_time_ms = (end_time - start_time) * 1000

            return ParallelToolCallResult(
                tool_call_id=tool_call_id,
                tool_call=tool_call,
                execution_result=execution_result,
                execution_time_ms=execution_time_ms,
                error=None if execution_result.success_flag else execution_result.func_return,
            )

        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            execution_time_ms = (end_time - start_time) * 1000
            
            self.logger.error(f"Error executing tool {tool_name} in parallel: {str(e)}")
            
            error_result = ToolExecutionResult(
                status="error",
                func_return=get_friendly_error_msg(
                    tool_name,
                    type(e).__name__,
                    str(e),
                ),
                stderr=[traceback.format_exc()],
            )

            return ParallelToolCallResult(
                tool_call_id=tool_call_id,
                tool_call=tool_call,
                execution_result=error_result,
                execution_time_ms=execution_time_ms,
                error=str(e),
            )

    async def _execute_tools_sequentially(
        self,
        tool_calls: List[ToolCall],
        agent_state: AgentState,
        config: ParallelToolCallConfig,
        agent_step_span: Optional[Span] = None,
        step_id: str | None = None,
    ) -> ParallelExecutionSummary:
        """Execute tools sequentially when parallel execution is not safe."""
        start_time = asyncio.get_event_loop().time()
        results = []
        successful_count = 0
        failed_count = 0
        continue_stepping = False

        for tool_call in tool_calls:
            result = await self._execute_single_tool_call(tool_call, agent_state, config, agent_step_span, step_id)
            results.append(result)
            
            if result.success_flag:
                successful_count += 1
                continue_stepping = True  # Continue if any tool succeeded
            else:
                failed_count += 1

        end_time = asyncio.get_event_loop().time()
        total_execution_time_ms = (end_time - start_time) * 1000

        return ParallelExecutionSummary(
            results=results,
            total_execution_time_ms=total_execution_time_ms,
            successful_count=successful_count,
            failed_count=failed_count,
            continue_stepping=continue_stepping,
            stop_reason=None,
        )
