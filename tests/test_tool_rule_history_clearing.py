"""Test that tool rule history is cleared after summarization to prevent infinite loops."""

import pytest
from letta.schemas.enums import MessageRole
from letta.schemas.message import Message
from letta.schemas.letta_message_content import TextContent
from letta.schemas.tool_rule import ContinueToolRule
from letta.helpers.tool_rule_solver import ToolRulesSolver
from letta.services.summarizer.enums import SummarizationMode
from letta.services.summarizer.summarizer import Summarizer


def create_tool_call_message(message_id, call_id, tool_name, message_text="test"):
    """Helper to create a message with tool call."""
    from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall as OpenAIToolCall
    from openai.types.chat.chat_completion_message_function_tool_call import Function as OpenAIFunction
    import json
    
    tool_call = OpenAIToolCall(
        id=call_id,
        function=OpenAIFunction(
            name=tool_name,
            arguments=json.dumps({"message": message_text}) if tool_name == "send" else json.dumps({})
        ),
        type="function"
    )
    
    return Message(
        role=MessageRole.assistant,
        tool_calls=[tool_call],
        id=message_id,
    )


def test_tool_rule_history_cleared_after_summarization():
    """Test that tool call history is cleared after summarization to break infinite loops."""
    
    # Create a continue tool rule for session_todo_get
    continue_rule = ContinueToolRule(tool_name="session_todo_get")
    tool_rules_solver = ToolRulesSolver(tool_rules=[continue_rule])
    
    # Simulate the agent calling session_todo_get
    tool_rules_solver.register_tool_call("session_todo_get")
    
    # Verify the tool is marked as a continue tool
    assert tool_rules_solver.is_continue_tool("session_todo_get")
    
    # Verify the tool was recorded in history
    assert "session_todo_get" in tool_rules_solver.tool_call_history
    
    # Simulate what happens after summarization - tool history should be cleared
    tool_rules_solver.clear_tool_history()
    
    # After clearing, the history should be empty
    assert len(tool_rules_solver.tool_call_history) == 0
    
    # The continue rule should still exist but not apply to past calls
    assert tool_rules_solver.is_continue_tool("session_todo_get")


def test_tool_rule_solver_state_reset():
    """Test that ToolRulesSolver properly resets state when cleared."""
    
    # Create rules for various scenarios
    continue_rule = ContinueToolRule(tool_name="session_todo_get")
    tool_rules_solver = ToolRulesSolver(tool_rules=[continue_rule])
    
    # Register multiple tool calls to build history
    tool_rules_solver.register_tool_call("session_todo_get")
    tool_rules_solver.register_tool_call("send")
    tool_rules_solver.register_tool_call("session_todo_get")  # Called again
    
    # Verify history is populated
    assert len(tool_rules_solver.tool_call_history) == 3
    assert tool_rules_solver.tool_call_history == ["session_todo_get", "send", "session_todo_get"]
    
    # Clear and verify reset
    tool_rules_solver.clear_tool_history()
    assert len(tool_rules_solver.tool_call_history) == 0
    
    # Rules should still work for new calls
    tool_rules_solver.register_tool_call("session_todo_get")
    assert tool_rules_solver.is_continue_tool("session_todo_get")
    assert len(tool_rules_solver.tool_call_history) == 1


if __name__ == "__main__":
    test_tool_rule_history_cleared_after_summarization()
    test_tool_rule_solver_state_reset()
    print("All tests passed!")