"""Test that send() checkpoint logic doesn't cause context loss."""

import pytest
from letta.schemas.enums import MessageRole
from letta.schemas.message import Message
from letta.schemas.letta_message_content import TextContent
from letta.services.summarizer.enums import SummarizationMode
from letta.services.summarizer.summarizer import Summarizer


def create_send_tool_call_message(message_id, call_id, message_text):
    """Helper to create a message with send tool call."""
    from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall as OpenAIToolCall
    from openai.types.chat.chat_completion_message_function_tool_call import Function as OpenAIFunction
    import json
    
    tool_call = OpenAIToolCall(
        id=call_id,
        function=OpenAIFunction(
            name="send",
            arguments=json.dumps({"message": message_text, "to": "user"})
        ),
        type="function"
    )
    
    return Message(
        role=MessageRole.assistant,
        tool_calls=[tool_call],
        id=message_id,
    )


def test_send_checkpoint_no_context_loss():
    """Verify that recent send() calls don't trigger aggressive eviction."""
    
    # Create messages with a send() call
    messages = [
        Message(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant")],
            id="message-00000001",
        ),
        Message(
            role=MessageRole.user,
            content=[TextContent(text="Hello")],
            id="message-00000002",
        ),
        create_send_tool_call_message("message-00000003", "call_test123", "Hello there!"),
        Message(
            role=MessageRole.tool,
            content=[TextContent(text='{"status": "OK"}')],
            tool_call_id="call_test123",
            id="message-00000004",
        ),
    ]
    
    # Create summarizer with low buffer limit to trigger logic
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,  # No summarizer agent for this test
        message_buffer_limit=10,
        message_buffer_min=3
    )
    
    # This should NOT evict everything
    result, was_summarized = summarizer._static_buffer_summarization(
        messages[:2], messages[2:], force=False
    )
    
    # Should keep at least message_buffer_min messages
    assert len(result) >= 3, f"Expected at least 3 messages, got {len(result)}"
    
    # Should include the system message
    assert result[0].role == MessageRole.system, "First message should be system message"
    
    # The bug would have caused result to be nearly empty
    # With the fix, we should have reasonable context preserved
    assert len(result) == 4, f"Expected all 4 messages to be kept, got {len(result)}"


def test_send_checkpoint_with_force():
    """Test that force=True with send() checkpoints works correctly."""
    
    # Create a longer conversation with multiple send() calls
    messages = [
        Message(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant")],
            id="message-00000001",
        ),
    ]
    
    # Add 20 message pairs (user + assistant with send)
    for i in range(20):
        messages.append(Message(
            role=MessageRole.user,
            content=[TextContent(text=f"Message {i}")],
            id=f"message-{i*2+2:08d}",
        ))
        messages.append(create_send_tool_call_message(
            f"message-{i*2+3:08d}",
            f"call_test{i}",
            f"Response {i}"
        ))
    
    # Create summarizer with settings that would trigger trimming
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=10,
        message_buffer_min=5
    )
    
    # Force summarization
    result, was_summarized = summarizer._static_buffer_summarization(
        messages[:-2], messages[-2:], force=True
    )
    
    # Should have summarized
    assert was_summarized is True
    
    # Should keep system message plus message_buffer_min messages
    assert len(result) >= 6, f"Expected at least 6 messages (system + 5), got {len(result)}"
    
    # System message should be preserved
    assert result[0].role == MessageRole.system
    
    # Should have used a send() checkpoint (logged in the function)
    # The most recent messages should be preserved
    assert result[-1].id == messages[-1].id, "Most recent message should be preserved"


def test_no_send_checkpoints_fallback():
    """Test that when no send() calls exist, standard trimming is used."""
    
    # Create messages WITHOUT send() calls
    messages = [
        Message(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant")],
            id="message-00000001",
        ),
    ]
    
    # Add regular message pairs without send()
    for i in range(10):
        messages.append(Message(
            role=MessageRole.user,
            content=[TextContent(text=f"Question {i}")],
            id=f"message-{i*2+2:08d}",
        ))
        messages.append(Message(
            role=MessageRole.assistant,
            content=[TextContent(text=f"Answer {i}")],
            id=f"message-{i*2+3:08d}",
        ))
    
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=10,
        message_buffer_min=4
    )
    
    # Force summarization
    result, was_summarized = summarizer._static_buffer_summarization(
        messages[:-2], messages[-2:], force=True
    )
    
    # Should use standard trimming since no send() checkpoints
    assert was_summarized is True
    assert len(result) >= 5, f"Expected at least 5 messages (system + 4), got {len(result)}"
    assert result[0].role == MessageRole.system
    
    # Should keep the most recent messages
    assert result[-1].id == messages[-1].id


if __name__ == "__main__":
    test_send_checkpoint_no_context_loss()
    test_send_checkpoint_with_force()
    test_no_send_checkpoints_fallback()
    print("All tests passed!")