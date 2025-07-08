from typing import List, Optional, Set
from pydantic import BaseModel, Field

from letta.schemas.letta_stop_reason import LettaStopReason
from letta.schemas.openai.chat_completion_response import ToolCall
from letta.schemas.tool_execution_result import ToolExecutionResult


class ParallelToolCallResult(BaseModel):
    """Result of a single tool call execution within a parallel batch."""

    tool_call_id: str = Field(..., description="Unique identifier for this tool call")
    tool_call: ToolCall = Field(..., description="The original tool call that was executed")
    execution_result: ToolExecutionResult = Field(..., description="Result of the tool execution")
    execution_time_ms: float = Field(..., description="Time taken to execute this tool call in milliseconds")
    error: Optional[str] = Field(None, description="Error message if execution failed, None if successful")

    @property
    def success_flag(self) -> bool:
        """Returns True if the tool call executed successfully."""
        return self.execution_result.success_flag and self.error is None


class ParallelExecutionSummary(BaseModel):
    """Summary of a parallel tool call execution batch."""

    results: List[ParallelToolCallResult] = Field(..., description="Results of all tool calls in the batch")
    total_execution_time_ms: float = Field(..., description="Total time for parallel execution in milliseconds")
    successful_count: int = Field(..., description="Number of successfully executed tool calls")
    failed_count: int = Field(..., description="Number of failed tool call executions")
    continue_stepping: bool = Field(..., description="Whether the agent should continue stepping after these tool calls")
    stop_reason: Optional[LettaStopReason] = Field(None, description="Reason for stopping execution, if any")

    @property
    def total_count(self) -> int:
        """Returns the total number of tool calls executed."""
        return len(self.results)

    @property
    def success_rate(self) -> float:
        """Returns the success rate as a percentage (0-100)."""
        if self.total_count == 0:
            return 0.0
        return (self.successful_count / self.total_count) * 100.0

    @property
    def has_errors(self) -> bool:
        """Returns True if any tool calls failed."""
        return self.failed_count > 0


class ParallelToolCallConfig(BaseModel):
    """Configuration for parallel tool call execution."""

    enabled: bool = Field(default=True, description="Whether parallel tool calling is enabled")
    max_concurrent_tools: int = Field(default=5, description="Maximum number of tool calls to execute concurrently")
    timeout_per_tool_seconds: float = Field(default=30.0, description="Timeout for individual tool execution in seconds")
    allow_memory_tools_parallel: bool = Field(
        default=False, description="Whether to allow memory operation tools to run in parallel (conservative default)"
    )
    memory_operation_tools: Set[str] = Field(
        default_factory=lambda: {
            "core_memory_append",
            "core_memory_replace",
            "memory_rethink",
            "memory_replace",
            "memory_append",
        },
        description="Set of tool names that perform memory operations",
    )

    def is_memory_tool(self, tool_name: str) -> bool:
        """Check if a tool is considered a memory operation tool."""
        return tool_name in self.memory_operation_tools

    def should_execute_sequentially(self, tool_names: List[str]) -> bool:
        """
        Determine if tools should be executed sequentially based on configuration.

        Returns True if any tool is a memory operation and parallel memory tools are disabled.
        """
        if not self.enabled:
            return True

        if not self.allow_memory_tools_parallel:
            return any(self.is_memory_tool(name) for name in tool_names)

        return False
