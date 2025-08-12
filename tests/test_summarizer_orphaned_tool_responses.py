#!/usr/bin/env python3
"""
Test for critical bug where conversation summarizer creates orphaned tool responses.

BUG: The static buffer summarization can preserve tool responses while evicting their 
corresponding tool calls, creating orphaned tool responses that reference non-existent 
tool call IDs. This breaks conversation flow and confuses LLMs.

Root Cause: The trimming logic in _static_buffer_summarization only considers user 
messages as boundary points, ignoring tool call/response relationships.
"""

import json
import pytest
from datetime import datetime
from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall as OpenAIToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function as OpenAIFunction

from letta.schemas.message import Message
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.services.summarizer.summarizer import Summarizer
from letta.services.summarizer.enums import SummarizationMode


class TestSummarizerOrphanedToolResponses:
    """Test cases for the orphaned tool response bug in summarizer"""

    def create_orphaning_scenario(self):
        """
        Create a conversation that reproduces the orphaned tool response bug.
        
        With retain_count=3 and 5 messages:
        - target_trim_index = max(1, 5-3) = 2  
        - User message at index 2 becomes trim boundary
        - Tool call (index 1) gets EVICTED
        - Tool response (index 3) gets KEPT
        - Result: Orphaned tool response!
        """
        messages = []
        tool_call_id = "call_Wqo6GWjx6FTCahmQcloMUDng"
        
        # System message (index 0 - always preserved)
        messages.append(Message(
            id="message-11111111",
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful AI assistant.")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Assistant with tool call (index 1) - WILL BE EVICTED
        tool_call = OpenAIToolCall(
            id=tool_call_id,
            function=OpenAIFunction(
                name="send",
                arguments=json.dumps({
                    "to": "agent:research", 
                    "message": "Research AI safety",
                    "request_heartbeat": True
                })
            ),
            type="function"
        )
        
        messages.append(Message(
            id="message-22222222",
            role=MessageRole.assistant,
            content=[TextContent(text="I'll research AI safety for you.")],
            agent_id="agent_test",
            tool_calls=[tool_call],
            created_at=datetime.now()
        ))
        
        # User message (index 2) - becomes trim boundary
        messages.append(Message(
            id="message-33333333",
            role=MessageRole.user,
            content=[TextContent(text="User message at trim boundary")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Tool response (index 3) - WILL BE KEPT and ORPHANED!
        messages.append(Message(
            id="message-44444444",
            role=MessageRole.tool,
            content=[TextContent(text="Message sent successfully to research agent.")],
            agent_id="agent_test",
            tool_call_id=tool_call_id,  # References evicted tool call!
            name="send",
            created_at=datetime.now()
        ))
        
        # Assistant message (index 4)
        messages.append(Message(
            id="message-55555555",
            role=MessageRole.assistant,
            content=[TextContent(text="I'll wait for the research results.")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        return messages, tool_call_id

    def test_orphaned_tool_response_bug_is_fixed(self):
        """Test that the fix prevents orphaned tool responses by adjusting trim boundaries"""
        messages, tool_call_id = self.create_orphaning_scenario()
        
        # Create summarizer with settings that would have triggered the bug
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            message_buffer_limit=3,  # This would normally force summarization
            message_buffer_min=3,    # Keep 3 messages
            summarizer_agent=None
        )
        
        # Run summarization
        result_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages,
            new_letta_messages=[],
            force=True
        )
        
        # The fix should prevent summarization when it would create orphaned responses
        # Instead of blindly trimming, it should preserve message integrity
        
        # Analyze the result for orphaned tool responses
        tool_call_ids_in_assistants = set()
        tool_call_ids_in_responses = set()
        
        for msg in result_messages:
            if msg.role == MessageRole.assistant and msg.tool_calls:
                tool_call_ids_in_assistants.update(call.id for call in msg.tool_calls)
            elif msg.role == MessageRole.tool and msg.tool_call_id:
                tool_call_ids_in_responses.add(msg.tool_call_id)
        
        orphaned_responses = tool_call_ids_in_responses - tool_call_ids_in_assistants
        
        # FIXED: After the fix, there should be NO orphaned responses
        # The fix should prevent tool call/response pairs from being split
        if len(orphaned_responses) > 0:
            print(f"🚨 BUG STILL EXISTS: Found {len(orphaned_responses)} orphaned tool responses: {orphaned_responses}")
            # For debugging - let's see what the result looks like
            print("Result messages:")
            for i, msg in enumerate(result_messages):
                if msg.role == MessageRole.assistant and msg.tool_calls:
                    print(f"  {i}: assistant with tool_call (id: {msg.tool_calls[0].id})")
                elif msg.role == MessageRole.tool:
                    print(f"  {i}: tool response (tool_call_id: {msg.tool_call_id})")
                else:
                    print(f"  {i}: {msg.role.value}")
        else:
            print(f"✅ BUG FIXED: No orphaned tool responses found after fix")
            
        # After fix: Should have NO orphaned responses
        assert len(orphaned_responses) == 0, f"Fixed summarizer should not create orphaned responses, but found: {orphaned_responses}"

    def create_valid_scenario(self):
        """Create a conversation where tool calls and responses stay together"""
        messages = []
        tool_call_id = "call_ValidScenario123"
        
        # System message
        messages.append(Message(
            id="message-11111111",
            role=MessageRole.system,
            content=[TextContent(text="System prompt")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Old user message (will be evicted)
        messages.append(Message(
            id="message-22222222",
            role=MessageRole.user,
            content=[TextContent(text="Old user message")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Recent user message (trim boundary)
        messages.append(Message(
            id="message-33333333",
            role=MessageRole.user,
            content=[TextContent(text="Recent user message")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Assistant with tool call (will be kept)
        tool_call = OpenAIToolCall(
            id=tool_call_id,
            function=OpenAIFunction(
                name="send",
                arguments=json.dumps({"to": "agent:research", "message": "test"})
            ),
            type="function"
        )
        
        messages.append(Message(
            id="message-44444444",
            role=MessageRole.assistant,
            content=[TextContent(text="Assistant with tool call")],
            agent_id="agent_test",
            tool_calls=[tool_call],
            created_at=datetime.now()
        ))
        
        # Tool response (will be kept with its tool call)
        messages.append(Message(
            id="message-55555555",
            role=MessageRole.tool,
            content=[TextContent(text="Tool response")],
            agent_id="agent_test",
            tool_call_id=tool_call_id,
            name="send",
            created_at=datetime.now()
        ))
        
        return messages, tool_call_id

    def test_valid_tool_call_response_preserved(self):
        """Test that tool calls and responses are preserved together when possible"""
        messages, tool_call_id = self.create_valid_scenario()
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            message_buffer_limit=3,
            message_buffer_min=3,
            summarizer_agent=None
        )
        
        result_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages,
            new_letta_messages=[],
            force=True
        )
        
        # Check that tool call and response are both present or both absent
        tool_call_ids_in_assistants = set()
        tool_call_ids_in_responses = set()
        
        for msg in result_messages:
            if msg.role == MessageRole.assistant and msg.tool_calls:
                tool_call_ids_in_assistants.update(call.id for call in msg.tool_calls)
            elif msg.role == MessageRole.tool and msg.tool_call_id:
                tool_call_ids_in_responses.add(msg.tool_call_id)
        
        orphaned_responses = tool_call_ids_in_responses - tool_call_ids_in_assistants
        missing_responses = tool_call_ids_in_assistants - tool_call_ids_in_responses
        
        assert len(orphaned_responses) == 0, f"Found orphaned responses: {orphaned_responses}"
        assert len(missing_responses) == 0, f"Found tool calls without responses: {missing_responses}"

    def test_fixed_summarizer_preserves_tool_pairs(self):
        """Test that the fixed summarizer preserves tool call/response pairs"""
        messages, tool_call_id = self.create_orphaning_scenario()
        
        # Use the fixed summarizer with the same settings that caused the bug
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            message_buffer_limit=3,  # Same settings as the bug reproduction
            message_buffer_min=3,
            summarizer_agent=None
        )
        
        result_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages,
            new_letta_messages=[],
            force=True
        )
        
        # After fix: No orphaned responses should exist
        tool_call_ids_in_assistants = set()
        tool_call_ids_in_responses = set()
        
        for msg in result_messages:
            if msg.role == MessageRole.assistant and msg.tool_calls:
                tool_call_ids_in_assistants.update(call.id for call in msg.tool_calls)
            elif msg.role == MessageRole.tool and msg.tool_call_id:
                tool_call_ids_in_responses.add(msg.tool_call_id)
        
        orphaned_responses = tool_call_ids_in_responses - tool_call_ids_in_assistants
        assert len(orphaned_responses) == 0, f"Fixed summarizer should not create orphaned responses, but found: {orphaned_responses}"


if __name__ == "__main__":
    # Run the bug reproduction test directly
    test_instance = TestSummarizerOrphanedToolResponses()
    
    print("🧪 Testing orphaned tool response bug...")
    try:
        test_instance.test_orphaned_tool_response_bug()
        print("✅ Bug test passed - orphaned responses confirmed")
    except AssertionError as e:
        print(f"❌ Bug test failed: {e}")
    
    print("\n🧪 Testing valid scenario...")
    try:
        test_instance.test_valid_tool_call_response_preserved()
        print("✅ Valid scenario test passed - no orphaned responses")
    except AssertionError as e:
        print(f"❌ Valid scenario test failed: {e}")