import asyncio
import json
import uuid
from typing import List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from letta.schemas.agent import AgentState
from letta.schemas.llm_config import LLMConfig
from letta.schemas.openai.chat_completion_response import FunctionCall, ToolCall
from letta.schemas.parallel_tool_call import (
    ParallelExecutionSummary,
    ParallelToolCallConfig,
    ParallelToolCallResult,
)
from letta.schemas.tool import Tool
from letta.schemas.tool_execution_result import ToolExecutionResult
from letta.schemas.user import User
from letta.services.tool_executor.tool_categorizer import ToolCategorizer, ToolSafetyProfile
from letta.services.tool_executor.tool_execution_manager import ToolExecutionManager


@pytest.fixture
def sample_user():
    """Create a sample user for testing."""
    return User(
        id=f"user-{uuid.uuid4()}",
        organization_id=f"org-{uuid.uuid4()}",
        name="test_user",
    )


@pytest.fixture
def sample_tool_calls():
    """Create sample tool calls for testing."""
    return [
        ToolCall(
            id="call_1",
            type="function",
            function=FunctionCall(
                name="send_message",
                arguments='{"message": "Hello World"}'
            )
        ),
        ToolCall(
            id="call_2", 
            type="function",
            function=FunctionCall(
                name="core_memory_append",
                arguments='{"content": "Important fact"}'
            )
        ),
        ToolCall(
            id="call_3",
            type="function", 
            function=FunctionCall(
                name="list_files",
                arguments='{"query": "test.py"}'
            )
        )
    ]


@pytest.fixture
def sample_tools():
    """Create sample tools for testing."""
    return [
        Tool(
            id=f"tool-{uuid.uuid4()}",
            name="send_message",
            description="Send a message",
            tool_type="letta_core",
            json_schema={"type": "object"},
            return_char_limit=1000,
        ),
        Tool(
            id=f"tool-{uuid.uuid4()}",
            name="core_memory_append", 
            description="Append to core memory",
            tool_type="letta_memory_core",
            json_schema={"type": "object"},
            return_char_limit=1000,
        ),
        Tool(
            id=f"tool-{uuid.uuid4()}",
            name="list_files",
            description="List files",
            tool_type="letta_files_core", 
            json_schema={"type": "object"},
            return_char_limit=1000,
        )
    ]


@pytest.fixture  
def sample_agent_state(sample_tools):
    """Create a sample agent state for testing."""
    return AgentState(
        id=f"agent-{uuid.uuid4()}",
        name="test_agent",
        timezone="UTC",
        tools=sample_tools,
        llm_config=LLMConfig(
            model="gpt-4o-mini",
            model_endpoint_type="openai",
            context_window=128000,
        ),
        tool_exec_environment_variables=[],
    )


class TestParallelToolCallConfig:
    """Test the ParallelToolCallConfig configuration system."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ParallelToolCallConfig()
        assert config.enabled is True
        assert config.max_concurrent_tools == 5
        assert config.timeout_per_tool_seconds == 30.0
        assert config.allow_memory_tools_parallel is False
        assert "core_memory_append" in config.memory_operation_tools
    
    def test_is_memory_tool(self):
        """Test memory tool detection."""
        config = ParallelToolCallConfig()
        assert config.is_memory_tool("core_memory_append") is True
        assert config.is_memory_tool("send_message") is False
        assert config.is_memory_tool("list_files") is False
    
    def test_should_execute_sequentially(self):
        """Test sequential execution decision logic."""
        config = ParallelToolCallConfig()
        
        # Should execute sequentially when disabled
        config.enabled = False
        assert config.should_execute_sequentially(["send_message"]) is True
        
        # Should execute sequentially when memory tools present and not allowed
        config.enabled = True
        config.allow_memory_tools_parallel = False
        assert config.should_execute_sequentially(["send_message", "core_memory_append"]) is True
        
        # Should execute in parallel when no memory tools
        assert config.should_execute_sequentially(["send_message", "list_files"]) is False
        
        # Should execute in parallel when memory tools allowed
        config.allow_memory_tools_parallel = True
        assert config.should_execute_sequentially(["send_message", "core_memory_append"]) is False


class TestToolCategorizer:
    """Test the ToolCategorizer functionality."""
    
    def test_categorize_memory_tool(self, sample_tools):
        """Test categorization of memory tools."""
        categorizer = ToolCategorizer()
        memory_tool = next(t for t in sample_tools if t.name == "core_memory_append")
        
        profile = categorizer.categorize_tool(memory_tool)
        assert profile == ToolSafetyProfile.MEMORY_OPERATION
    
    def test_categorize_communication_tool(self, sample_tools):
        """Test categorization of communication tools."""
        categorizer = ToolCategorizer()
        comm_tool = next(t for t in sample_tools if t.name == "send_message")
        
        profile = categorizer.categorize_tool(comm_tool)
        assert profile == ToolSafetyProfile.COMMUNICATION
    
    def test_categorize_file_tool(self, sample_tools):
        """Test categorization of file tools."""
        categorizer = ToolCategorizer()
        file_tool = next(t for t in sample_tools if t.name == "list_files")
        
        profile = categorizer.categorize_tool(file_tool)
        assert profile == ToolSafetyProfile.FILE_OPERATION
    
    def test_categorize_tools_batch(self, sample_tools):
        """Test batch categorization of tools."""
        categorizer = ToolCategorizer()
        result = categorizer.categorize_tools(sample_tools)
        
        assert "core_memory_append" in result.memory_tools
        assert "send_message" in result.communication_tools
        assert "list_files" in result.file_tools
        assert len(result.recommended_execution_order) > 0
    
    def test_is_safe_for_parallel_execution(self, sample_tools):
        """Test parallel execution safety analysis."""
        categorizer = ToolCategorizer()
        
        # Should be unsafe with memory tools when not allowed
        safe_tools = [t for t in sample_tools if t.name != "core_memory_append"]
        memory_tools = [t for t in sample_tools if t.name == "core_memory_append"]
        
        is_safe, unsafe_tools = categorizer.is_safe_for_parallel_execution(
            safe_tools, allow_memory_parallel=False
        )
        assert is_safe is True
        assert len(unsafe_tools) == 0
        
        is_safe, unsafe_tools = categorizer.is_safe_for_parallel_execution(
            sample_tools, allow_memory_parallel=False
        )
        assert is_safe is False
        assert "core_memory_append" in unsafe_tools
    
    def test_detect_tool_conflicts(self, sample_tools):
        """Test tool conflict detection."""
        categorizer = ToolCategorizer()
        
        # Create multiple memory tools
        memory_tools = [t for t in sample_tools if t.name == "core_memory_append"] * 2
        conflicts = categorizer.detect_tool_conflicts(memory_tools)
        
        assert len(conflicts) > 0
        assert any("memory" in conflict[2].lower() for conflict in conflicts)


class TestParallelToolExecution:
    """Test the parallel tool execution functionality."""
    
    @pytest.mark.asyncio
    async def test_parallel_execution_summary_creation(self, sample_tool_calls):
        """Test creation of parallel execution summary."""
        results = []
        for i, tool_call in enumerate(sample_tool_calls):
            result = ParallelToolCallResult(
                tool_call_id=tool_call.id,
                tool_call=tool_call,
                execution_result=ToolExecutionResult(
                    status="success",
                    func_return=f"Result {i}"
                ),
                execution_time_ms=100.0 + i * 10,
                error=None
            )
            results.append(result)
        
        summary = ParallelExecutionSummary(
            results=results,
            total_execution_time_ms=250.0,
            successful_count=3,
            failed_count=0,
            continue_stepping=True,
            stop_reason=None
        )
        
        assert summary.total_count == 3
        assert summary.success_rate == 100.0
        assert summary.has_errors is False
    
    @pytest.mark.asyncio
    async def test_parallel_execution_with_failures(self, sample_tool_calls):
        """Test parallel execution with some failures."""
        results = []
        for i, tool_call in enumerate(sample_tool_calls):
            status = "success" if i < 2 else "error"
            result = ParallelToolCallResult(
                tool_call_id=tool_call.id,
                tool_call=tool_call,
                execution_result=ToolExecutionResult(
                    status=status,
                    func_return=f"Result {i}" if status == "success" else "Error occurred"
                ),
                execution_time_ms=100.0 + i * 10,
                error="Test error" if status == "error" else None
            )
            results.append(result)
        
        summary = ParallelExecutionSummary(
            results=results,
            total_execution_time_ms=250.0,
            successful_count=2,
            failed_count=1,
            continue_stepping=True,
            stop_reason=None
        )
        
        assert summary.total_count == 3
        assert abs(summary.success_rate - 66.67) < 0.01  # approximately 
        assert summary.has_errors is True
    
    @pytest.mark.asyncio
    @patch("letta.services.tool_executor.tool_execution_manager.ToolExecutorFactory.get_executor")
    async def test_tool_execution_manager_parallel(self, mock_get_executor, sample_user, sample_agent_state, sample_tool_calls):
        """Test ToolExecutionManager parallel execution."""
        # Mock the executor
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ToolExecutionResult(
            status="success",
            func_return="Test result"
        )
        mock_get_executor.return_value = mock_executor
        
        # Create mock managers
        message_manager = AsyncMock()
        agent_manager = AsyncMock()
        block_manager = AsyncMock()
        job_manager = AsyncMock()
        passage_manager = AsyncMock()
        
        # Create tool execution manager
        manager = ToolExecutionManager(
            message_manager=message_manager,
            agent_manager=agent_manager,
            block_manager=block_manager,
            job_manager=job_manager,
            passage_manager=passage_manager,
            actor=sample_user,
            agent_state=sample_agent_state,
        )
        
        config = ParallelToolCallConfig()
        
        # Test parallel execution
        summary = await manager.execute_tools_parallel_async(
            tool_calls=sample_tool_calls,
            agent_state=sample_agent_state,
            config=config,
        )
        
        assert isinstance(summary, ParallelExecutionSummary)
        assert summary.total_count == len(sample_tool_calls)
    
    @pytest.mark.asyncio
    async def test_empty_tool_calls_list(self, sample_user, sample_agent_state):
        """Test handling of empty tool calls list."""
        # Create mock managers
        message_manager = AsyncMock()
        agent_manager = AsyncMock()
        block_manager = AsyncMock()
        job_manager = AsyncMock()
        passage_manager = AsyncMock()
        
        manager = ToolExecutionManager(
            message_manager=message_manager,
            agent_manager=agent_manager,
            block_manager=block_manager,
            job_manager=job_manager,
            passage_manager=passage_manager,
            actor=sample_user,
            agent_state=sample_agent_state,
        )
        
        config = ParallelToolCallConfig()
        
        summary = await manager.execute_tools_parallel_async(
            tool_calls=[],
            agent_state=sample_agent_state,
            config=config,
        )
        
        assert summary.total_count == 0
        assert summary.successful_count == 0
        assert summary.failed_count == 0


class TestParallelToolCallResult:
    """Test the ParallelToolCallResult functionality."""
    
    def test_success_flag_with_successful_result(self, sample_tool_calls):
        """Test success flag with successful execution."""
        result = ParallelToolCallResult(
            tool_call_id="test_id",
            tool_call=sample_tool_calls[0],
            execution_result=ToolExecutionResult(
                status="success",
                func_return="Test result"
            ),
            execution_time_ms=100.0,
            error=None
        )
        
        assert result.success_flag is True
    
    def test_success_flag_with_failed_result(self, sample_tool_calls):
        """Test success flag with failed execution."""
        result = ParallelToolCallResult(
            tool_call_id="test_id",
            tool_call=sample_tool_calls[0],
            execution_result=ToolExecutionResult(
                status="error",
                func_return="Error occurred"
            ),
            execution_time_ms=100.0,
            error="Test error"
        )
        
        assert result.success_flag is False
    
    def test_success_flag_with_execution_success_but_error_message(self, sample_tool_calls):
        """Test success flag when execution succeeds but error is present."""
        result = ParallelToolCallResult(
            tool_call_id="test_id",
            tool_call=sample_tool_calls[0],
            execution_result=ToolExecutionResult(
                status="success",
                func_return="Test result"
            ),
            execution_time_ms=100.0,
            error="Some warning message"  # Error message present but execution was successful
        )
        
        assert result.success_flag is False  # Should be False due to error message


@pytest.mark.asyncio 
class TestConfigurationManagement:
    """Test configuration management and environment variables."""
    
    def test_environment_variable_parsing(self):
        """Test environment variable parsing for parallel tool calls."""
        config = ParallelToolCallConfig()
        
        # Test default values
        assert config.enabled is True
        assert config.max_concurrent_tools == 5
        
        # Test custom values
        custom_config = ParallelToolCallConfig(
            enabled=False,
            max_concurrent_tools=10,
            timeout_per_tool_seconds=60.0
        )
        
        assert custom_config.enabled is False
        assert custom_config.max_concurrent_tools == 10
        assert custom_config.timeout_per_tool_seconds == 60.0
    
    @patch.dict("os.environ", {"LETTA_ENABLE_PARALLEL_TOOL_CALLS": "false"})
    def test_environment_variable_override(self):
        """Test that environment variables properly override defaults."""
        import os
        
        # Simulate the logic from the LLM clients
        enable_parallel = os.getenv("LETTA_ENABLE_PARALLEL_TOOL_CALLS", "true").lower() == "true"
        assert enable_parallel is False
    
    @patch.dict("os.environ", {"LETTA_ENABLE_PARALLEL_TOOL_CALLS": "true"})
    def test_environment_variable_enable(self):
        """Test that environment variables can enable parallel execution."""
        import os
        
        enable_parallel = os.getenv("LETTA_ENABLE_PARALLEL_TOOL_CALLS", "true").lower() == "true"
        assert enable_parallel is True


if __name__ == "__main__":
    pytest.main([__file__])