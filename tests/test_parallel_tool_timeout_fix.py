"""Test that individual tool timeouts don't affect other tools in parallel execution."""

import asyncio
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from letta.schemas.openai.chat_completion_response import ToolCall, FunctionCall
from letta.schemas.parallel_tool_call import ParallelToolCallConfig
from letta.schemas.tool import Tool
from letta.orm.enums import ToolType
from letta.services.tool_executor.tool_execution_manager import ToolExecutionManager


class TestParallelToolTimeoutFix:
    """Test that individual tool timeouts work correctly in parallel execution."""

    @pytest.fixture
    def mock_managers(self):
        """Create mock managers for testing."""
        return {
            "message_manager": MagicMock(),
            "agent_manager": MagicMock(),
            "block_manager": MagicMock(),
            "job_manager": MagicMock(),
            "passage_manager": MagicMock(),
            "actor": MagicMock(),
        }

    @pytest.fixture
    def tool_executor(self, mock_managers):
        """Create a ToolExecutionManager instance."""
        return ToolExecutionManager(**mock_managers)

    @pytest.fixture
    def mock_agent_state(self):
        """Create a mock agent state with tools."""
        agent_state = MagicMock()
        agent_state.tools = [
            Tool(
                name="fast_tool",
                tool_type=ToolType.CUSTOM,
                json_schema={"name": "fast_tool", "parameters": {"type": "object", "properties": {}}},
                source_code='def fast_tool():\n    """Fast tool for testing."""\n    pass',
            ),
            Tool(
                name="slow_tool",
                tool_type=ToolType.CUSTOM,
                json_schema={"name": "slow_tool", "parameters": {"type": "object", "properties": {}}},
                source_code='def slow_tool():\n    """Slow tool for testing."""\n    pass',
            ),
            Tool(
                name="hanging_tool",
                tool_type=ToolType.CUSTOM,
                json_schema={"name": "hanging_tool", "parameters": {"type": "object", "properties": {}}},
                source_code='def hanging_tool():\n    """Hanging tool for testing."""\n    pass',
            ),
        ]
        return agent_state

    @pytest.mark.asyncio
    async def test_individual_tool_timeout(self, tool_executor, mock_agent_state):
        """Test that one tool timing out doesn't affect other tools."""
        
        # Create mock tool calls
        tool_calls = [
            ToolCall(
                id="call_1",
                function=FunctionCall(name="fast_tool", arguments="{}"),
            ),
            ToolCall(
                id="call_2",
                function=FunctionCall(name="slow_tool", arguments="{}"),
            ),
            ToolCall(
                id="call_3",
                function=FunctionCall(name="hanging_tool", arguments="{}"),
            ),
        ]

        # Mock execute_tool_async to simulate different execution times
        async def mock_execute_tool(function_name, **kwargs):
            if function_name == "fast_tool":
                # Fast tool completes in 0.1 seconds
                await asyncio.sleep(0.1)
                result = MagicMock()
                result.success_flag = True
                result.func_return = "Fast tool completed"
                result.status = "success"
                return result
            elif function_name == "slow_tool":
                # Slow tool completes in 2 seconds
                await asyncio.sleep(2)
                result = MagicMock()
                result.success_flag = True
                result.func_return = "Slow tool completed"
                result.status = "success"
                return result
            elif function_name == "hanging_tool":
                # Hanging tool would take 30 seconds (will timeout)
                await asyncio.sleep(30)
                result = MagicMock()
                result.success_flag = True
                result.func_return = "Should not reach here"
                result.status = "success"
                return result

        tool_executor.execute_tool_async = mock_execute_tool

        # Configure with 5 second timeout per tool
        config = ParallelToolCallConfig(
            enabled=True,
            timeout_per_tool_seconds=5.0,  # 5 second timeout per tool
            max_concurrent_tools=10,
        )

        # Execute tools in parallel
        start_time = time.time()
        result = await tool_executor.execute_tools_parallel_async(
            tool_calls=tool_calls,
            agent_state=mock_agent_state,
            config=config,
        )
        execution_time = time.time() - start_time

        # Verify results
        assert len(result.results) == 3
        
        # Fast tool should succeed
        fast_result = result.results[0]
        assert fast_result.tool_call.function.name == "fast_tool"
        assert fast_result.execution_result.status == "success"
        assert "Fast tool completed" in fast_result.execution_result.func_return
        
        # Slow tool should succeed (2s < 5s timeout)
        slow_result = result.results[1]
        assert slow_result.tool_call.function.name == "slow_tool"
        assert slow_result.execution_result.status == "success"
        assert "Slow tool completed" in slow_result.execution_result.func_return
        
        # Hanging tool should timeout
        hanging_result = result.results[2]
        assert hanging_result.tool_call.function.name == "hanging_tool"
        assert hanging_result.execution_result.status == "error"
        assert "timed out after 5" in hanging_result.execution_result.func_return
        
        # Total execution should be around 5 seconds (not 30+ or 40 seconds)
        assert execution_time < 6  # Allow some overhead
        assert execution_time > 4  # Should wait for timeout
        
        # Verify counts
        assert result.successful_count == 2  # fast and slow succeeded
        assert result.failed_count == 1  # hanging timed out

    @pytest.mark.asyncio
    async def test_all_tools_timeout_independently(self, tool_executor, mock_agent_state):
        """Test that multiple tools can timeout independently."""
        
        # Create tool calls that will all timeout at different times
        tool_calls = [
            ToolCall(
                id=f"call_{i}",
                function=FunctionCall(name="slow_tool", arguments="{}"),
            )
            for i in range(3)
        ]

        # Mock execute_tool_async to simulate all tools hanging
        async def mock_execute_tool(function_name, **kwargs):
            await asyncio.sleep(30)  # All tools hang for 30 seconds
            result = MagicMock()
            result.success_flag = True
            result.func_return = "Should not reach"
            result.status = "success"
            return result

        tool_executor.execute_tool_async = mock_execute_tool

        # Configure with 2 second timeout
        config = ParallelToolCallConfig(
            enabled=True,
            timeout_per_tool_seconds=2.0,
            max_concurrent_tools=10,
        )

        # Execute tools
        start_time = time.time()
        result = await tool_executor.execute_tools_in_parallel(
            tool_calls=tool_calls,
            agent_state=mock_agent_state,
            config=config,
        )
        execution_time = time.time() - start_time

        # All tools should timeout
        assert result.failed_count == 3
        assert result.successful_count == 0
        
        # Each result should show timeout error
        for tool_result in result.results:
            assert tool_result.execution_result.status == "error"
            assert "timed out after 2" in tool_result.execution_result.func_return
        
        # Total execution should be around 2 seconds (not 6 seconds if sequential)
        assert execution_time < 3
        assert execution_time > 1.5

    @pytest.mark.asyncio  
    async def test_mixed_success_and_timeout(self, tool_executor, mock_agent_state):
        """Test mixture of successful and timed out tools."""
        
        # Create 5 tool calls
        tool_calls = [
            ToolCall(
                id=f"call_{i}",
                function=FunctionCall(name="fast_tool" if i % 2 == 0 else "hanging_tool", arguments="{}"),
            )
            for i in range(5)
        ]

        # Mock execute_tool_async
        async def mock_execute_tool(function_name, **kwargs):
            if function_name == "fast_tool":
                await asyncio.sleep(0.5)
                result = MagicMock()
                result.success_flag = True
                result.func_return = "Fast completed"
                result.status = "success"
                return result
            else:
                await asyncio.sleep(30)  # Will timeout
                result = MagicMock()
                result.success_flag = True
                result.func_return = "Should not reach"
                result.status = "success"
                return result

        tool_executor.execute_tool_async = mock_execute_tool

        config = ParallelToolCallConfig(
            enabled=True,
            timeout_per_tool_seconds=3.0,
            max_concurrent_tools=10,
        )

        # Execute
        result = await tool_executor.execute_tools_in_parallel(
            tool_calls=tool_calls,
            agent_state=mock_agent_state,
            config=config,
        )

        # Check results - 3 fast tools succeed, 2 hanging tools timeout
        assert result.successful_count == 3
        assert result.failed_count == 2
        
        # Verify alternating pattern
        for i, tool_result in enumerate(result.results):
            if i % 2 == 0:
                # Fast tool
                assert tool_result.execution_result.status == "success"
            else:
                # Hanging tool
                assert tool_result.execution_result.status == "error"
                assert "timed out" in tool_result.execution_result.func_return