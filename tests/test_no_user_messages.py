"""
Test case where there are no user messages to use as trim boundaries.
"""

import pytest
from datetime import datetime
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.services.summarizer.summarizer import Summarizer
from letta.services.summarizer.enums import SummarizationMode
from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall as OpenAIToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function as OpenAIFunction


def test_no_user_messages_for_boundary():
    """Test when there are no user messages available for trim boundary."""
    
    messages = []
    
    # System message
    messages.append(Message(
        id="message-00000000",
        role=MessageRole.system,
        content=[TextContent(text="System")],
        agent_id="test",
        created_at=datetime.now()
    ))
    
    # User message early on
    messages.append(Message(
        id="message-00000001",
        role=MessageRole.user,
        content=[TextContent(text="Initial user message")],
        agent_id="test",
        created_at=datetime.now()
    ))
    
    # Then ONLY assistant and tool messages (no more user messages!)
    for i in range(2, 20):
        if i % 2 == 0:
            # Assistant with tool call
            messages.append(Message(
                id=f"message-{i:08x}",
                role=MessageRole.assistant,
                content=[TextContent(text=f"Assistant {i}")],
                agent_id="test",
                tool_calls=[OpenAIToolCall(
                    id=f"call_{i}",
                    function=OpenAIFunction(name="test", arguments="{}"),
                    type="function"
                )],
                created_at=datetime.now()
            ))
        else:
            # Tool response
            messages.append(Message(
                id=f"message-{i:08x}",
                role=MessageRole.tool,
                content=[TextContent(text=f"Response {i}")],
                agent_id="test",
                tool_call_id=f"call_{i-1}",
                name="test",
                created_at=datetime.now()
            ))
    
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=10,
        message_buffer_min=3  # Want to keep last 3
    )
    
    print(f"\n=== No User Messages Test ===")
    print(f"Total messages: {len(messages)}")
    print(f"Last user message at index: 1")
    print(f"Messages after that are all assistant/tool")
    
    # Run summarization with clear=True (simulating context overflow)
    trimmed, was_summarized = summarizer._static_buffer_summarization(
        in_context_messages=messages,
        new_letta_messages=[],
        force=True,
        clear=True  # This sets retain_count to 2
    )
    
    print(f"\nAfter summarization:")
    print(f"  Trimmed message count: {len(trimmed)}")
    print(f"  Message roles: {[m.role for m in trimmed]}")
    
    # The problem: the while loop looking for user message might have gone too far
    if len(trimmed) <= 2:  # Only system + maybe 1 other
        print("🔴 BUG: Agent left with almost no context!")
        print("   The search for user message boundary went too far!")
    
    # Check if we have a functional context
    has_user_msg = any(m.role == MessageRole.user for m in trimmed)
    has_assistant_msg = any(m.role == MessageRole.assistant for m in trimmed)
    
    if not has_user_msg or not has_assistant_msg:
        print("🔴 CRITICAL: Missing essential message types for agent to function!")
    
    return trimmed


def test_all_tool_messages_at_end():
    """Test when all the recent messages are tool calls/responses."""
    
    messages = []
    
    # System
    messages.append(Message(
        id="message-00000000",
        role=MessageRole.system,
        content=[TextContent(text="System")],
        agent_id="test",
        created_at=datetime.now()
    ))
    
    # One user message
    messages.append(Message(
        id="message-00000001",
        role=MessageRole.user,
        content=[TextContent(text="Do many things")],
        agent_id="test",
        created_at=datetime.now()
    ))
    
    # Then a long chain of tool calls and responses
    for i in range(2, 100, 2):
        # Tool call
        messages.append(Message(
            id=f"message-{i:08x}",
            role=MessageRole.assistant,
            content=[TextContent(text="")],  # Empty content, just tool call
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id=f"call_{i}",
                function=OpenAIFunction(
                    name="archival_memory_insert",
                    arguments='{"content": "data"}'
                ),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # Tool response
        messages.append(Message(
            id=f"message-{i+1:08x}",
            role=MessageRole.tool,
            content=[TextContent(text="Inserted")],
            agent_id="test",
            tool_call_id=f"call_{i}",
            name="archival_memory_insert",
            created_at=datetime.now()
        ))
    
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=50,
        message_buffer_min=10
    )
    
    print(f"\n=== All Tool Messages Test ===")
    print(f"Total messages: {len(messages)}")
    print(f"Last 98 messages are all tool calls/responses")
    
    # This should trigger the issue
    trimmed, was_summarized = summarizer._static_buffer_summarization(
        in_context_messages=messages,
        new_letta_messages=[],
        force=True,
        clear=True
    )
    
    print(f"\nAfter summarization:")
    print(f"  Trimmed message count: {len(trimmed)}")
    
    # Count message types
    user_count = sum(1 for m in trimmed if m.role == MessageRole.user)
    assistant_count = sum(1 for m in trimmed if m.role == MessageRole.assistant)
    tool_count = sum(1 for m in trimmed if m.role == MessageRole.tool)
    
    print(f"  User messages: {user_count}")
    print(f"  Assistant messages: {assistant_count}")
    print(f"  Tool messages: {tool_count}")
    
    if user_count == 0:
        print("🔴 BUG: No user messages in context - agent cannot understand user intent!")
    
    return trimmed


if __name__ == "__main__":
    print("Testing edge cases with no user message boundaries...")
    test_no_user_messages_for_boundary()
    test_all_tool_messages_at_end()