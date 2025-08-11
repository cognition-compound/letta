"""Test to reproduce the heartbeat bug in parallel tool execution."""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import List

from letta.schemas.agent import AgentState
from letta.schemas.openai.chat_completion_response import ToolCall, FunctionCall
from letta.schemas.parallel_tool_call import ParallelToolCallConfig
from letta.schemas.tool import Tool
from letta.schemas.tool_execution_result import ToolExecutionResult
from letta.orm.enums import ToolType
from letta.services.tool_executor.tool_execution_manager import ToolExecutionManager


@pytest.mark.asyncio
async def test_heartbeat_lost_in_parallel_execution():
    """Test that heartbeat requests are properly handled in parallel tool execution."""
    
    # Setup mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock()
    
    # Create tool execution manager
    manager = ToolExecutionManager(
        message_manager=mock_message_manager,
        agent_manager=mock_agent_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor,
    )
    
    # Create test tools
    test_tool = Tool(
        name="test_tool",
        description="Test tool",
        source_code="def test_tool(arg1: str = None) -> str:\n    return 'success'",
        tool_type=ToolType.CUSTOM,
        json_schema={
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "Test argument"}
                },
                "required": []
            }
        },
        return_char_limit=1000,
    )
    
    # Create agent state with tools
    agent_state = AgentState(
        id="test-agent",
        name="Test Agent",
        tools=[test_tool],
    )
    
    # Create tool calls - one WITH heartbeat, one WITHOUT
    tool_call_with_heartbeat = ToolCall(
        id="call_1",
        function=FunctionCall(
            name="test_tool",
            arguments='{"arg1": "value1", "request_heartbeat": true}'
        )
    )
    
    tool_call_without_heartbeat = ToolCall(
        id="call_2",
        function=FunctionCall(
            name="test_tool",
            arguments='{"arg1": "value2", "request_heartbeat": false}'
        )
    )
    
    # Mock the execute_tool_async to return success
    async def mock_execute_tool(function_name, function_args, tool, step_id=None):
        return ToolExecutionResult(
            status="success",
            func_return="Tool executed successfully",
        )
    
    manager.execute_tool_async = AsyncMock(side_effect=mock_execute_tool)
    
    # Test 1: Tool WITH heartbeat should result in continue_stepping=True
    config = ParallelToolCallConfig()
    summary = await manager.execute_tools_parallel_async(
        tool_calls=[tool_call_with_heartbeat],
        agent_state=agent_state,
        config=config,
    )
    
    # BUG: This will PASS currently because continue_stepping is set to True for ANY success
    # But it's set for the WRONG reason - not because of heartbeat!
    assert summary.continue_stepping == True, "Tool with heartbeat should continue stepping"
    
    # Test 2: Tool WITHOUT heartbeat should result in continue_stepping=False
    summary = await manager.execute_tools_parallel_async(
        tool_calls=[tool_call_without_heartbeat],
        agent_state=agent_state,
        config=config,
    )
    
    # BUG: This will FAIL currently because continue_stepping is ALWAYS True for success!
    assert summary.continue_stepping == False, "Tool without heartbeat should NOT continue stepping"
    
    # Test 3: Multiple tools - only continue if ANY has heartbeat
    summary = await manager.execute_tools_parallel_async(
        tool_calls=[tool_call_without_heartbeat, tool_call_with_heartbeat],
        agent_state=agent_state,
        config=config,
    )
    
    assert summary.continue_stepping == True, "Should continue if ANY tool requests heartbeat"


@pytest.mark.asyncio
async def test_heartbeat_handling_with_failures():
    """Test heartbeat handling when some tools fail."""
    
    # Setup mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock()
    
    manager = ToolExecutionManager(
        message_manager=mock_message_manager,
        agent_manager=mock_agent_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor,
    )
    
    # Create test tools
    test_tool = Tool(
        name="test_tool",
        description="Test tool",
        source_code="def test_tool(arg1: str = None) -> str:\n    return 'success'",
        tool_type=ToolType.CUSTOM,
        json_schema={
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "Test argument"}
                },
                "required": []
            }
        },
        return_char_limit=1000,
    )
    
    agent_state = AgentState(
        id="test-agent",
        name="Test Agent",
        tools=[test_tool],
    )
    
    # Tool that fails but requests heartbeat
    tool_call_fail_with_heartbeat = ToolCall(
        id="call_1",
        function=FunctionCall(
            name="test_tool",
            arguments='{"request_heartbeat": true, "will_fail": true}'
        )
    )
    
    # Mock to make this tool fail
    async def mock_execute_tool_with_failure(function_name, function_args, tool, step_id=None):
        if function_args.get("will_fail"):
            return ToolExecutionResult(
                status="error",
                func_return="Tool failed",
            )
        return ToolExecutionResult(
            status="success",
            func_return="Tool succeeded",
        )
    
    manager.execute_tool_async = AsyncMock(side_effect=mock_execute_tool_with_failure)
    
    config = ParallelToolCallConfig()
    summary = await manager.execute_tools_parallel_async(
        tool_calls=[tool_call_fail_with_heartbeat],
        agent_state=agent_state,
        config=config,
    )
    
    # Failed tools with heartbeat should NOT continue stepping
    # (heartbeat only matters for successful tools)
    assert summary.continue_stepping == False, "Failed tools should not trigger continuation even with heartbeat"


if __name__ == "__main__":
    # Run the tests
    asyncio.run(test_heartbeat_lost_in_parallel_execution())
    asyncio.run(test_heartbeat_handling_with_failures())
    print("Tests completed - they will likely fail due to the bug!")