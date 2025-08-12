"""
Test to prove the trim index can be pushed beyond message bounds.
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


def test_trim_index_beyond_bounds():
    """Test that adjustment can push trim index beyond message bounds."""
    
    messages = []
    
    # System message
    messages.append(Message(
        id="message-00000000",
        role=MessageRole.system,
        content=[TextContent(text="System")],
        agent_id="test",
        created_at=datetime.now()
    ))
    
    # Tool call at index 1 (will be evicted)
    messages.append(Message(
        id="message-00000001",
        role=MessageRole.assistant,
        content=[TextContent(text="Call")],
        agent_id="test",
        tool_calls=[OpenAIToolCall(
            id="call_1",
            function=OpenAIFunction(name="test", arguments="{}"),
            type="function"
        )],
        created_at=datetime.now()
    ))
    
    # User message at index 2 (trim boundary)
    messages.append(Message(
        id="message-00000002",
        role=MessageRole.user,
        content=[TextContent(text="User")],
        agent_id="test",
        created_at=datetime.now()
    ))
    
    # Tool response at index 3 (orphaned - references evicted call)
    messages.append(Message(
        id="message-00000003",
        role=MessageRole.tool,
        content=[TextContent(text="Response")],
        agent_id="test",
        tool_call_id="call_1",
        name="test",
        created_at=datetime.now()
    ))
    
    # Nothing else after the orphaned response!
    
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=10,
        message_buffer_min=2  # Want to keep 2 messages
    )
    
    # Target trim index would be 2 (to keep last 2 messages: indices 2 and 3)
    target_trim_index = len(messages) - 2  # = 4 - 2 = 2
    
    # The adjustment function will:
    # 1. Find orphaned response at index 3
    # 2. See its tool call at index 1 would be evicted
    # 3. Try to adjust forward to exclude the orphaned response
    # 4. Push trim index to 4 (past the end of messages!)
    
    adjusted_index = summarizer._adjust_trim_index_for_tool_pairs(messages, target_trim_index)
    
    print(f"\n=== Trim Beyond Bounds Test ===")
    print(f"Total messages: {len(messages)}")
    print(f"Target trim index: {target_trim_index}")
    print(f"Adjusted trim index: {adjusted_index}")
    
    if adjusted_index >= len(messages):
        print("🔴 BUG CONFIRMED: Trim index pushed beyond message bounds!")
        print(f"   This would result in NO messages in context (except system)")
        print("   Agent would be effectively broken!")
    
    # Now test what happens in actual summarization
    trimmed, was_summarized = summarizer._static_buffer_summarization(
        in_context_messages=messages,
        new_letta_messages=[],
        force=True
    )
    
    print(f"\nAfter summarization:")
    print(f"  Trimmed message count: {len(trimmed)}")
    print(f"  Message roles: {[m.role for m in trimmed]}")
    
    # The bug: we might have only system message left!
    if len(trimmed) == 1 and trimmed[0].role == MessageRole.system:
        print("🔴 CRITICAL: Agent left with only system message - cannot function!")
        
    # This is the core issue
    assert len(trimmed) > 1, "Agent must have more than just system message to function"


if __name__ == "__main__":
    test_trim_index_beyond_bounds()