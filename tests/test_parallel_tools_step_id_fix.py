"""Test that step_id is handled correctly with NoopStepManager to avoid foreign key constraint violations."""

import pytest
from letta.server.rest_api.utils import create_letta_messages_from_llm_response
from letta.schemas.user import User
from letta.services.tool_executor.tool_execution_manager import ToolExecutionResult
from letta.services.step_manager import NoopStepManager
from letta.agents.helpers import generate_step_id
from letta.schemas.openai.chat_completion_response import UsageStatistics


def test_create_messages_with_none_step_id():
    """Test that messages are created without step_id when step_id is None."""
    
    # Create a test user
    actor = User(
        id="user-12345678",
        organization_id="org-12345678",
        name="Test User"
    )
    
    # Create a tool execution result
    tool_execution_result = ToolExecutionResult(
        status="success",
        func_return="Tool executed successfully",
        stdout=[],
        stderr=[]
    )
    
    # Call the function with step_id=None (as would happen with NoopStepManager)
    messages = create_letta_messages_from_llm_response(
        agent_id="agent-12345678",
        model="gpt-4",
        function_name="test_tool",
        function_arguments={"arg": "value"},
        tool_execution_result=tool_execution_result,
        tool_call_id="call_123",
        function_call_success=True,
        function_response="Success",
        timezone="UTC",
        actor=actor,
        continue_stepping=False,
        step_id=None  # This is what happens with NoopStepManager
    )
    
    # Verify that messages don't have step_id set
    for message in messages:
        assert message.step_id is None, f"Expected step_id to be None, but got {message.step_id}"
    
    print("✅ Test passed: Messages created without step_id when using None")


def test_create_messages_with_valid_step_id():
    """Test that messages are created with step_id when step_id is provided."""
    
    # Create a test user
    actor = User(
        id="user-12345678",
        organization_id="org-12345678",
        name="Test User"
    )
    
    # Create a tool execution result
    tool_execution_result = ToolExecutionResult(
        status="success",
        func_return="Tool executed successfully",
        stdout=[],
        stderr=[]
    )
    
    # Generate a step ID (as would happen with a real StepManager)
    step_id = generate_step_id()
    
    # Call the function with a valid step_id
    messages = create_letta_messages_from_llm_response(
        agent_id="agent-12345678",
        model="gpt-4",
        function_name="test_tool",
        function_arguments={"arg": "value"},
        tool_execution_result=tool_execution_result,
        tool_call_id="call_123",
        function_call_success=True,
        function_response="Success",
        timezone="UTC",
        actor=actor,
        continue_stepping=False,
        step_id=step_id  # This is what happens with a real StepManager
    )
    
    # Verify that messages have step_id set
    for message in messages:
        assert message.step_id == step_id, f"Expected step_id to be {step_id}, but got {message.step_id}"
    
    print(f"✅ Test passed: Messages created with step_id {step_id}")


def test_noop_step_manager_returns_none():
    """Test that NoopStepManager's log_step returns None."""
    
    step_manager = NoopStepManager()
    
    # Mock the required parameters
    actor = User(
        id="user-12345678",
        organization_id="org-12345678",
        name="Test User"
    )
    
    # Call log_step (should return None)
    usage = UsageStatistics(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15
    )
    
    result = step_manager.log_step(
        actor=actor,
        agent_id="agent-123",
        provider_name="openai",
        provider_category="llm",
        model="gpt-4",
        model_endpoint="https://api.openai.com/v1",
        context_window_limit=8192,
        usage=usage,
        step_id="step-123"
    )
    
    assert result is None, f"Expected NoopStepManager.log_step to return None, but got {result}"
    
    print("✅ Test passed: NoopStepManager returns None")


if __name__ == "__main__":
    test_create_messages_with_none_step_id()
    test_create_messages_with_valid_step_id()
    test_noop_step_manager_returns_none()
    print("\n✅ All tests passed!")