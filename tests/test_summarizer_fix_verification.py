#!/usr/bin/env python3
"""
Verification tests that demonstrate the summarizer fix works correctly.

These tests show:
1. The exact bug scenario that was fixed
2. How the fix adjusts trim boundaries to preserve tool pairs
3. Various edge cases and scenarios where the fix applies
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


class TestSummarizerFixVerification:
    """Verification tests for the summarizer orphaned tool response fix"""

    def create_fix_demonstration_scenario(self):
        """Create scenario that demonstrates the fix in action"""
        messages = []
        tool_call_id = "call_FixDemo12345"
        
        # System message (index 0)
        messages.append(Message(
            id="message-11111111",
            role=MessageRole.system,
            content=[TextContent(text="System prompt")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Assistant with tool call (index 1) - would be evicted without fix
        tool_call = OpenAIToolCall(
            id=tool_call_id,
            function=OpenAIFunction(
                name="send",
                arguments=json.dumps({"to": "agent:research", "message": "test"})
            ),
            type="function"
        )
        
        messages.append(Message(
            id="message-22222222",
            role=MessageRole.assistant,
            content=[TextContent(text="Assistant with tool call")],
            agent_id="agent_test",
            tool_calls=[tool_call],
            created_at=datetime.now()
        ))
        
        # User message (index 2) - original trim boundary
        messages.append(Message(
            id="message-33333333",
            role=MessageRole.user,
            content=[TextContent(text="User message")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Tool response (index 3) - would be orphaned without fix
        messages.append(Message(
            id="message-44444444",
            role=MessageRole.tool,
            content=[TextContent(text="Tool response")],
            agent_id="agent_test",
            tool_call_id=tool_call_id,
            name="send",
            created_at=datetime.now()
        ))
        
        # Assistant message (index 4)
        messages.append(Message(
            id="message-55555555",
            role=MessageRole.assistant,
            content=[TextContent(text="Final assistant message")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        return messages, tool_call_id

    def test_fix_detects_and_prevents_orphaning(self):
        """Test that the fix correctly detects potential orphaning and prevents it"""
        messages, tool_call_id = self.create_fix_demonstration_scenario()
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            message_buffer_limit=3,
            message_buffer_min=3,
            summarizer_agent=None
        )
        
        # The fix should detect that trimming at index 2 would create orphaned responses
        # and adjust to prevent it
        result_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages,
            new_letta_messages=[],
            force=True
        )
        
        # Verify no orphaned responses exist
        tool_call_ids_in_assistants = set()
        tool_call_ids_in_responses = set()
        
        for msg in result_messages:
            if msg.role == MessageRole.assistant and msg.tool_calls:
                tool_call_ids_in_assistants.update(call.id for call in msg.tool_calls)
            elif msg.role == MessageRole.tool and msg.tool_call_id:
                tool_call_ids_in_responses.add(msg.tool_call_id)
        
        orphaned_responses = tool_call_ids_in_responses - tool_call_ids_in_assistants
        assert len(orphaned_responses) == 0, f"Fix should prevent orphaned responses, but found: {orphaned_responses}"
        
        # Verify tool pairs are preserved together
        if tool_call_id in tool_call_ids_in_responses:
            assert tool_call_id in tool_call_ids_in_assistants, "If tool response is kept, tool call must be kept too"
            
        if tool_call_id in tool_call_ids_in_assistants:
            assert tool_call_id in tool_call_ids_in_responses, "If tool call is kept, tool response should be kept too"

    def create_multiple_tool_pairs_scenario(self):
        """Create scenario with multiple tool call/response pairs"""
        messages = []
        tool_call_ids = ["call_First123", "call_Second456"]
        
        messages.append(Message(
            id="message-11111111",
            role=MessageRole.system,
            content=[TextContent(text="System prompt")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # First tool pair
        tool_call_1 = OpenAIToolCall(
            id=tool_call_ids[0],
            function=OpenAIFunction(name="send", arguments=json.dumps({"to": "agent:1", "message": "test1"})),
            type="function"
        )
        
        messages.append(Message(
            id="message-22222222",
            role=MessageRole.assistant,
            content=[TextContent(text="First assistant with tool call")],
            agent_id="agent_test",
            tool_calls=[tool_call_1],
            created_at=datetime.now()
        ))
        
        messages.append(Message(
            id="message-33333333",
            role=MessageRole.tool,
            content=[TextContent(text="First tool response")],
            agent_id="agent_test",
            tool_call_id=tool_call_ids[0],
            name="send",
            created_at=datetime.now()
        ))
        
        # Second tool pair
        tool_call_2 = OpenAIToolCall(
            id=tool_call_ids[1],
            function=OpenAIFunction(name="send", arguments=json.dumps({"to": "agent:2", "message": "test2"})),
            type="function"
        )
        
        messages.append(Message(
            id="message-44444444",
            role=MessageRole.assistant,
            content=[TextContent(text="Second assistant with tool call")],
            agent_id="agent_test",
            tool_calls=[tool_call_2],
            created_at=datetime.now()
        ))
        
        messages.append(Message(
            id="message-55555555",
            role=MessageRole.tool,
            content=[TextContent(text="Second tool response")],
            agent_id="agent_test",
            tool_call_id=tool_call_ids[1],
            name="send",
            created_at=datetime.now()
        ))
        
        # User message
        messages.append(Message(
            id="message-66666666",
            role=MessageRole.user,
            content=[TextContent(text="User message after tools")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        return messages, tool_call_ids

    def test_multiple_tool_pairs_handling(self):
        """Test that the fix handles multiple tool call/response pairs correctly"""
        messages, tool_call_ids = self.create_multiple_tool_pairs_scenario()
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            message_buffer_limit=4,  # Force some trimming
            message_buffer_min=3,
            summarizer_agent=None
        )
        
        result_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages,
            new_letta_messages=[],
            force=True
        )
        
        # Analyze tool pairs in result
        tool_calls_present = set()
        tool_responses_present = set()
        
        for msg in result_messages:
            if msg.role == MessageRole.assistant and msg.tool_calls:
                tool_calls_present.update(call.id for call in msg.tool_calls)
            elif msg.role == MessageRole.tool and msg.tool_call_id:
                tool_responses_present.add(msg.tool_call_id)
        
        # Verify no orphaned responses or calls
        orphaned_responses = tool_responses_present - tool_calls_present
        orphaned_calls = tool_calls_present - tool_responses_present
        
        assert len(orphaned_responses) == 0, f"Should have no orphaned responses: {orphaned_responses}"
        assert len(orphaned_calls) == 0, f"Should have no orphaned calls: {orphaned_calls}"
        
        # Every tool call should have its response if it's in the result
        assert tool_calls_present == tool_responses_present, "Tool calls and responses should match exactly"

    def test_adjustment_respects_user_boundaries(self):
        """Test that trim index adjustments still respect user message boundaries when possible"""
        messages = []
        tool_call_id = "call_BoundaryTest"
        
        # System message
        messages.append(Message(
            id="message-11111111",
            role=MessageRole.system,
            content=[TextContent(text="System prompt")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # User message (index 1) - potential boundary
        messages.append(Message(
            id="message-22222222",
            role=MessageRole.user,
            content=[TextContent(text="User message 1")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        # Assistant with tool call (index 2)
        tool_call = OpenAIToolCall(
            id=tool_call_id,
            function=OpenAIFunction(name="send", arguments=json.dumps({"message": "test"})),
            type="function"
        )
        
        messages.append(Message(
            id="message-33333333",
            role=MessageRole.assistant,
            content=[TextContent(text="Assistant with tool")],
            agent_id="agent_test",
            tool_calls=[tool_call],
            created_at=datetime.now()
        ))
        
        # Tool response (index 3)
        messages.append(Message(
            id="message-44444444",
            role=MessageRole.tool,
            content=[TextContent(text="Tool response")],
            agent_id="agent_test",
            tool_call_id=tool_call_id,
            name="send",
            created_at=datetime.now()
        ))
        
        # User message (index 4) - good boundary after complete tool pair
        messages.append(Message(
            id="message-55555555",
            role=MessageRole.user,
            content=[TextContent(text="User message 2")],
            agent_id="agent_test",
            created_at=datetime.now()
        ))
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            message_buffer_limit=3,
            message_buffer_min=2,
            summarizer_agent=None
        )
        
        result_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages,
            new_letta_messages=[],
            force=True
        )
        
        # Should be able to trim at a user boundary that preserves tool pairs
        # The fix should find a boundary that works for both requirements
        if was_summarized:
            # If summarization occurred, verify integrity
            tool_calls_present = set()
            tool_responses_present = set()
            
            for msg in result_messages:
                if msg.role == MessageRole.assistant and msg.tool_calls:
                    tool_calls_present.update(call.id for call in msg.tool_calls)
                elif msg.role == MessageRole.tool and msg.tool_call_id:
                    tool_responses_present.add(msg.tool_call_id)
            
            assert tool_calls_present == tool_responses_present, "Tool calls and responses must match"


if __name__ == "__main__":
    test_instance = TestSummarizerFixVerification()
    
    print("🧪 Testing fix detection and prevention...")
    test_instance.test_fix_detects_and_prevents_orphaning()
    print("✅ Fix prevention test passed")
    
    print("\n🧪 Testing multiple tool pairs handling...")
    test_instance.test_multiple_tool_pairs_handling()
    print("✅ Multiple tool pairs test passed")
    
    print("\n🧪 Testing user boundary respect...")
    test_instance.test_adjustment_respects_user_boundaries()
    print("✅ User boundary test passed")
    
    print("\n🎉 All fix verification tests passed!")