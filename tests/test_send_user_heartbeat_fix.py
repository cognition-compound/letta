"""
Test to verify that send(to="user") with request_heartbeat=true doesn't cause duplicate responses.

This test verifies the fix for the critical bug where agents would send duplicate responses
when using send(to="user", request_heartbeat=true).
"""

import pytest
from unittest.mock import Mock, patch
from letta.agents.letta_agent import LettaAgent
from letta.services.tool_executor.tool_execution_manager import ToolExecutionManager
from letta.schemas.parallel_tool_call import ParallelToolCallResult
from letta.schemas.tool_execution_result import ToolExecutionResult
from letta.schemas.openai.chat_completion_response import ToolCall as OpenAIToolCall, FunctionCall as OpenAIFunctionCall
import json
import asyncio


@pytest.mark.asyncio
async def test_send_to_user_no_heartbeat_continuation():
    """Test that send(to='user') never triggers heartbeat continuation in parallel execution."""
    
    # Create a mock tool execution manager
    manager = ToolExecutionManager(
        message_manager=Mock(),
        agent_manager=Mock(),
        block_manager=Mock(),
        job_manager=Mock(),
        passage_manager=Mock(),
        actor=Mock(),
    )
    
    # Create a tool call for send(to="user") with heartbeat=true
    tool_call = OpenAIToolCall(
        id="test_call_1",
        function=OpenAIFunctionCall(
            name="send",
            arguments=json.dumps({
                "message": "Test message to user",
                "to": "user",
                "request_heartbeat": True  # This should be ignored
            })
        )
    )
    
    # Mock the execute_tool_async to return success
    async def mock_execute_tool(*args, **kwargs):
        return ToolExecutionResult(
            status="success",
            func_return="Message sent to user"
        )
    
    manager.execute_tool_async = mock_execute_tool
    
    # Mock agent state with send tool
    agent_state = Mock()
    tool = Mock()
    tool.name = "send"
    agent_state.tools = [tool]
    
    # Execute the tool call
    result = await manager._execute_single_tool_call(
        tool_call=tool_call,
        agent_state=agent_state,
        config=Mock(),
        agent_step_span=None,
        step_id="test_step"
    )
    
    # Verify that heartbeat_requested is False despite request_heartbeat=true in args
    assert result.heartbeat_requested is False, "send(to='user') should force heartbeat=False"
    assert result.execution_result.success_flag is True
    assert result.execution_result.func_return == "Message sent to user"


@pytest.mark.asyncio
async def test_send_to_agent_preserves_heartbeat():
    """Test that send(to='agent:X') preserves heartbeat request."""
    
    # Create a mock tool execution manager
    manager = ToolExecutionManager(
        message_manager=Mock(),
        agent_manager=Mock(),
        block_manager=Mock(),
        job_manager=Mock(),
        passage_manager=Mock(),
        actor=Mock(),
    )
    
    # Create a tool call for send(to="agent:X") with heartbeat=true
    tool_call = OpenAIToolCall(
        id="test_call_2",
        function=OpenAIFunctionCall(
            name="send",
            arguments=json.dumps({
                "message": "Test message to agent",
                "to": "agent:other_agent_id",
                "request_heartbeat": True  # This should be preserved
            })
        )
    )
    
    # Mock the execute_tool_async to return success
    async def mock_execute_tool(*args, **kwargs):
        return ToolExecutionResult(
            status="success",
            func_return="Successfully sent message"
        )
    
    manager.execute_tool_async = mock_execute_tool
    
    # Mock agent state with send tool
    agent_state = Mock()
    tool = Mock()
    tool.name = "send"
    agent_state.tools = [tool]
    
    # Execute the tool call
    result = await manager._execute_single_tool_call(
        tool_call=tool_call,
        agent_state=agent_state,
        config=Mock(),
        agent_step_span=None,
        step_id="test_step"
    )
    
    # Verify that heartbeat_requested is True for agent-to-agent messages
    assert result.heartbeat_requested is True, "send(to='agent:X') should preserve heartbeat request"
    assert result.execution_result.success_flag is True


def test_decide_continuation_send_to_user():
    """Test that _decide_continuation forces heartbeat=False for send(to='user') in sequential execution."""
    
    # Create a mock agent
    agent = LettaAgent(
        agent_id="test_agent",
        message_manager=Mock(),
        agent_manager=Mock(),
        block_manager=Mock(),
        job_manager=Mock(),
        passage_manager=Mock(),
        actor=Mock(),
    )
    
    # Mock agent state and tool rules solver
    agent_state = Mock()
    agent_state.tools = []
    tool_rules_solver = Mock()
    tool_rules_solver.is_terminal_tool.return_value = False
    tool_rules_solver.has_children_tools.return_value = False
    tool_rules_solver.is_continue_tool.return_value = False
    tool_rules_solver.get_uncalled_required_tools.return_value = []
    
    # Test send(to="user") with heartbeat request
    continue_stepping, heartbeat_reason, stop_reason = agent._decide_continuation(
        agent_state=agent_state,
        request_heartbeat=True,  # This should be ignored
        tool_call_name="send",
        tool_rule_violated=False,
        tool_rules_solver=tool_rules_solver,
        is_final_step=False,
        tool_args={"to": "user", "message": "Test"}
    )
    
    # Verify that continuation is False despite request_heartbeat=True
    assert continue_stepping is False, "send(to='user') should not trigger continuation"
    assert heartbeat_reason is None
    
    # Test send(to="agent:X") with heartbeat request  
    continue_stepping, heartbeat_reason, stop_reason = agent._decide_continuation(
        agent_state=agent_state,
        request_heartbeat=True,  # This should be preserved
        tool_call_name="send",
        tool_rule_violated=False,
        tool_rules_solver=tool_rules_solver,
        is_final_step=False,
        tool_args={"to": "agent:other_id", "message": "Test"}
    )
    
    # Verify that continuation is True for agent-to-agent messages
    assert continue_stepping is True, "send(to='agent:X') should preserve heartbeat request"

