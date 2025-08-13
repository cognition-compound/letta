import asyncio
import os
from typing import Any, Dict, List, Optional

from letta.log import get_logger
from letta.otel.tracing import trace_method, tracer
from letta.schemas.agent import AgentState
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message import AssistantMessage
from letta.schemas.letta_message_content import TextContent
from letta.schemas.message import MessageCreate
from letta.schemas.sandbox_config import SandboxConfig
from letta.schemas.tool import Tool
from letta.schemas.tool_execution_result import ToolExecutionResult
from letta.schemas.user import User
from letta.services.tool_executor.tool_executor_base import ToolExecutor

logger = get_logger(__name__)


class LettaMultiAgentToolExecutor(ToolExecutor):
    """Executor for LETTA multi-agent core tools."""

    @trace_method
    async def execute(
        self,
        function_name: str,
        function_args: dict,
        tool: Tool,
        actor: User,
        agent_state: Optional[AgentState] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        sandbox_env_vars: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        assert agent_state is not None, "Agent state is required for multi-agent tools"
        function_map = {
            "send_message_to_agent_async": self.send_message_to_agent_async,
            "send_message_to_agents_matching_tags": self.send_message_to_agents_matching_tags_async,
            "send": self.send,
        }

        if function_name not in function_map:
            raise ValueError(f"Unknown function: {function_name}")

        # Execute the appropriate function
        function_args_copy = function_args.copy()  # Make a copy to avoid modifying the original
        function_response = await function_map[function_name](agent_state, **function_args_copy)
        return ToolExecutionResult(
            status="success",
            func_return=function_response,
        )

    async def send_message_to_agents_matching_tags_async(
        self, agent_state: AgentState, message: str, match_all: List[str], match_some: List[str]
    ) -> str:
        # Find matching agents
        matching_agents = await self.agent_manager.list_agents_matching_tags_async(
            actor=self.actor, match_all=match_all, match_some=match_some
        )
        if not matching_agents:
            return str([])

        augmented_message = f"[Broadcast message from agent '{agent_state.id}'] {message}"

        tasks = [
            asyncio.create_task(self._process_agent(agent_id=matched_agent.id, message=augmented_message, source_agent_id=agent_state.id)) for matched_agent in matching_agents
        ]
        results = await asyncio.gather(*tasks)
        return str(results)

    @trace_method
    async def _process_agent(self, agent_id: str, message: str, source_agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Process agent message by creating a job and running it in the background."""
        from letta.schemas.run import Run
        from letta.schemas.enums import JobStatus
        from letta.agents.letta_agent import LettaAgent
        
        # Log and validate agent_id
        logger.debug(f"_process_agent called with agent_id={agent_id!r} (type: {type(agent_id).__name__})")
        
        # Defensive check
        if isinstance(agent_id, list):
            logger.warning(f"agent_id was passed as a list {agent_id}, extracting first element")
            if len(agent_id) == 0:
                raise ValueError("agent_id list is empty")
            agent_id = agent_id[0]

        try:
            # Create a job for tracking the agent message processing
            run = Run(
                user_id=self.actor.id,
                status=JobStatus.created,
                metadata={
                    "job_type": "agent_to_agent_message",
                    "target_agent_id": agent_id,
                    "source_agent_id": source_agent_id or "unknown",
                }
            )
            run = await self.job_manager.create_job_async(pydantic_job=run, actor=self.actor)
            
            # Business Flow Event: Agent message processing job created
            logger.info("Agent message processing job created", extra={
                "event": "agent_message_job_created",
                "job_id": run.id,
                "source_agent_id": source_agent_id or "unknown",
                "target_agent_id": agent_id,
                "message_summary": message[:100] + "..." if len(message) > 100 else message,
                "workflow_type": "agent_to_agent_communication"
            })
            
            # Update job status to running
            await self.job_manager.safe_update_job_status_async(
                job_id=run.id,
                new_status=JobStatus.running,
                actor=self.actor,
            )
            
            logger.info("Agent message processing job started", extra={
                "event": "agent_message_job_running",
                "job_id": run.id,
                "target_agent_id": agent_id
            })
            
            # Create and run the agent
            letta_agent = LettaAgent(
                agent_id=agent_id,
                message_manager=self.message_manager,
                agent_manager=self.agent_manager,
                block_manager=self.block_manager,
                job_manager=self.job_manager,
                passage_manager=self.passage_manager,
                actor=self.actor,
            )

            # Use system role for agent-to-agent messages
            # Now that we've migrated to the Responses API, system messages work correctly
            # without breaking tool call ID tracking (verified in test_responses_api_system_messages.py)
            letta_response = await letta_agent.step([MessageCreate(role=MessageRole.system, content=[TextContent(text=message)])])
            messages = letta_response.messages

            send_message_content = [message.content for message in messages if isinstance(message, AssistantMessage)]
            
            # Update job status to completed
            await self.job_manager.safe_update_job_status_async(
                job_id=run.id,
                new_status=JobStatus.completed,
                actor=self.actor,
            )
            
            # Business Flow Event: Agent message processing completed successfully
            response_summary = str(send_message_content)[:200] if send_message_content else "No response content"
            logger.info("Agent message processing completed successfully", extra={
                "event": "agent_message_job_completed",
                "job_id": run.id,
                "target_agent_id": agent_id,
                "source_agent_id": source_agent_id or "unknown",
                "response_summary": response_summary,
                "response_count": len(send_message_content),
                "workflow_status": "success"
            })

            return {
                "agent_id": agent_id,
                "response": send_message_content if send_message_content else ["<no response>"],
                "job_id": run.id,
            }

        except Exception as e:
            # Business Flow Event: Agent message processing failed
            logger.error("Agent message processing failed", extra={
                "event": "agent_message_job_failed",
                "job_id": run.id if 'run' in locals() else "unknown",
                "target_agent_id": agent_id,
                "source_agent_id": source_agent_id or "unknown",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "workflow_status": "failed"
            })
            
            # Try to update job status to failed if we created one
            if 'run' in locals():
                try:
                    await self.job_manager.safe_update_job_status_async(
                        job_id=run.id,
                        new_status=JobStatus.failed,
                        actor=self.actor,
                    )
                except:
                    pass  # Ignore errors in error handling
            return {
                "agent_id": agent_id,
                "error": str(e),
                "type": type(e).__name__,
            }

    async def send_message_to_agent_async(self, agent_state: AgentState, message: str, other_agent_id: str) -> str:
        """Send message to agent without waiting for response."""
        
        # Log the agent_id being used for debugging
        logger.debug(f"send_message_to_agent_async called with other_agent_id={other_agent_id!r} (type: {type(other_agent_id).__name__})")
        
        # Defensive check: ensure other_agent_id is a string
        if isinstance(other_agent_id, list):
            logger.warning(f"other_agent_id was passed as a list {other_agent_id}, extracting first element")
            if len(other_agent_id) == 0:
                raise ValueError("other_agent_id list is empty")
            other_agent_id = other_agent_id[0]

        # Build the prefixed system message
        prefixed = f"[Message from agent '{agent_state.id}'] {message}"

        task = asyncio.create_task(self._process_agent(agent_id=other_agent_id, message=prefixed, source_agent_id=agent_state.id))

        task.add_done_callback(lambda t: (logger.error(f"Async send_message task failed: {t.exception()}") if t.exception() else None))

        return "Successfully sent message"

    async def send(self, agent_state: AgentState, message: str, to: str) -> str:
        """Universal message sending function with explicit routing."""
        # Business Flow Event: Message routing decision
        logger.info("Agent message routing", extra={
            "event": "agent_message_route",
            "source_agent_id": agent_state.id,
            "source_agent_name": agent_state.name,
            "routing_target": to,
            "message_summary": message[:100] + "..." if len(message) > 100 else message,
            "routing_type": "user" if to == "user" else to.split(":")[0] if ":" in to else "unknown"
        })

        if to == "user":
            # For user messages, just return the success message
            # The actual message delivery is handled by the streaming interfaces
            # which look for the tool name and extract the message parameter
            logger.info("Message sent to user", extra={
                "event": "message_to_user",
                "source_agent_id": agent_state.id,
                "message_summary": message[:100] + "..." if len(message) > 100 else message
            })
            return "Message sent to user"

        elif to.startswith("agent:"):
            agent_id = to.split(":", 1)[1]
            logger.info("Agent-to-agent communication initiated", extra={
                "event": "agent_to_agent_message_start",
                "source_agent_id": agent_state.id,
                "target_agent_id": agent_id,
                "message_summary": message[:100] + "..." if len(message) > 100 else message
            })
            return await self.send_message_to_agent_async(agent_state, message, agent_id)

        elif to.startswith("group:"):
            # TODO: Implement group messaging in executor
            return "Message sent to group"

        elif to.startswith("broadcast:"):
            tag = to.split(":", 1)[1]
            result = await self.send_message_to_agents_matching_tags_async(agent_state, message, match_all=[tag], match_some=[])
            # Parse the result to get count
            try:
                results = eval(result)  # Safe since we control the format
                return f"Message broadcasted to {len(results)} agents with tag '{tag}'"
            except:
                return f"Message broadcasted to agents with tag '{tag}'"

        else:
            raise ValueError(f"Invalid 'to' parameter: {to}. Must be 'user', 'agent:<id>', 'group:<id>', or 'broadcast:<tag>'")
