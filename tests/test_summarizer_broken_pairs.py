"""
Test to reproduce summarizer failures when hitting context window limit with broken tool pairs.

The hypothesis: Our fix to keep tool call/response pairs together can fail on edge cases:
1. Infinite adjustment loops
2. Index out of bounds
3. Malformed tool calls
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.services.summarizer.summarizer import Summarizer
from letta.services.summarizer.enums import SummarizationMode
from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall as OpenAIToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function as OpenAIFunction
import json


class TestSummarizerBrokenPairs:
    """Test cases for summarizer failures with broken tool pairs."""
    
    def test_adjustment_with_multiple_orphaned_responses(self):
        """Test case where multiple orphaned responses could cause index issues."""
        messages = []
        
        # System message (index 0)
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System prompt")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool call 1 (index 1) - will be evicted
        messages.append(Message(
            id="message-00000001",
            role=MessageRole.assistant,
            content=[TextContent(text="Calling tool 1")],
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id="call_1",
                function=OpenAIFunction(name="test", arguments="{}"),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # User message (index 2) - potential trim boundary
        messages.append(Message(
            id="message-00000002",
            role=MessageRole.user,
            content=[TextContent(text="User input")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool response 1 (index 3) - orphaned!
        messages.append(Message(
            id="message-00000003",
            role=MessageRole.tool,
            content=[TextContent(text="Response 1")],
            agent_id="test",
            tool_call_id="call_1",
            name="test",
            created_at=datetime.now()
        ))
        
        # Tool call 2 (index 4) - will be kept
        messages.append(Message(
            id="message-00000004",
            role=MessageRole.assistant,
            content=[TextContent(text="Calling tool 2")],
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id="call_2",
                function=OpenAIFunction(name="test2", arguments="{}"),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # Tool response 2 (index 5) - paired, should be kept
        messages.append(Message(
            id="message-00000005",
            role=MessageRole.tool,
            content=[TextContent(text="Response 2")],
            agent_id="test",
            tool_call_id="call_2",
            name="test2",
            created_at=datetime.now()
        ))
        
        # Create summarizer
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=10,
            message_buffer_min=3
        )
        
        # Test the adjustment function
        target_trim_index = 2  # Would evict tool call 1 but keep its response
        adjusted_index = summarizer._adjust_trim_index_for_tool_pairs(messages, target_trim_index)
        
        # Should adjust backwards to include tool call 1
        assert adjusted_index < target_trim_index, f"Should adjust backwards but got {adjusted_index}"
        
        # Verify no orphaned responses in adjusted result
        for i in range(adjusted_index, len(messages)):
            msg = messages[i]
            if msg.role == MessageRole.tool and msg.tool_call_id:
                # Check that its tool call is also in the kept messages
                found_call = False
                for j in range(adjusted_index, len(messages)):
                    check_msg = messages[j]
                    if check_msg.role == MessageRole.assistant and check_msg.tool_calls:
                        for tc in check_msg.tool_calls:
                            if tc.id == msg.tool_call_id:
                                found_call = True
                                break
                    if found_call:
                        break
                assert found_call, f"Orphaned response at index {i} with tool_call_id {msg.tool_call_id}"
    
    def test_adjustment_boundary_edge_case(self):
        """Test adjustment when it would go beyond message boundaries."""
        messages = []
        
        # System message (index 0)
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # All tool calls and responses - no user messages to use as boundaries!
        for i in range(1, 10):
            # Tool call
            messages.append(Message(
                id=f"message-{i*2-1:08x}",
                role=MessageRole.assistant,
                content=[TextContent(text=f"Call {i}")],
                agent_id="test",
                tool_calls=[OpenAIToolCall(
                    id=f"call_{i}",
                    function=OpenAIFunction(name="test", arguments="{}"),
                    type="function"
                )],
                created_at=datetime.now()
            ))
            # Tool response
            messages.append(Message(
                id=f"message-{i*2:08x}",
                role=MessageRole.tool,
                content=[TextContent(text=f"Response {i}")],
                agent_id="test",
                tool_call_id=f"call_{i}",
                name="test",
                created_at=datetime.now()
            ))
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=10,
            message_buffer_min=3
        )
        
        # Test adjustment with no user message boundaries
        target_trim_index = 10  # Middle of the messages
        adjusted_index = summarizer._adjust_trim_index_for_tool_pairs(messages, target_trim_index)
        
        # Should handle the lack of user boundaries gracefully
        assert 0 < adjusted_index < len(messages), f"Adjusted index {adjusted_index} out of bounds"
    
    def test_malformed_tool_call_id(self):
        """Test with None or empty tool_call_id."""
        messages = []
        
        # System message
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool call with empty ID
        messages.append(Message(
            id="message-00000001",
            role=MessageRole.assistant,
            content=[TextContent(text="Call")],
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id="",  # Empty ID!
                function=OpenAIFunction(name="test", arguments="{}"),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # User message
        messages.append(Message(
            id="message-00000002",
            role=MessageRole.user,
            content=[TextContent(text="User")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool response with None tool_call_id
        messages.append(Message(
            id="message-00000003",
            role=MessageRole.tool,
            content=[TextContent(text="Response")],
            agent_id="test",
            tool_call_id=None,  # None ID!
            name="test",
            created_at=datetime.now()
        ))
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=10,
            message_buffer_min=3
        )
        
        # Should not crash on malformed IDs
        try:
            adjusted_index = summarizer._adjust_trim_index_for_tool_pairs(messages, 2)
            assert adjusted_index >= 0, "Should return valid index"
        except Exception as e:
            pytest.fail(f"Should handle malformed IDs gracefully but crashed: {e}")
    
    def test_circular_dependency_scenario(self):
        """Test a scenario that could cause circular adjustment."""
        messages = []
        
        # System
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool call A (index 1)
        messages.append(Message(
            id="message-00000001",
            role=MessageRole.assistant,
            content=[TextContent(text="Call A")],
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id="call_A",
                function=OpenAIFunction(name="test", arguments="{}"),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # User (index 2) - initial trim boundary
        messages.append(Message(
            id="message-00000002",
            role=MessageRole.user,
            content=[TextContent(text="User 1")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool response A (index 3) - would be orphaned
        messages.append(Message(
            id="message-00000003",
            role=MessageRole.tool,
            content=[TextContent(text="Response A")],
            agent_id="test",
            tool_call_id="call_A",
            name="test",
            created_at=datetime.now()
        ))
        
        # Tool call B (index 4)
        messages.append(Message(
            id="message-00000004",
            role=MessageRole.assistant,
            content=[TextContent(text="Call B")],
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id="call_B",
                function=OpenAIFunction(name="test2", arguments="{}"),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # User (index 5) - potential adjusted boundary
        messages.append(Message(
            id="message-00000005",
            role=MessageRole.user,
            content=[TextContent(text="User 2")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Tool response B (index 6)
        messages.append(Message(
            id="message-00000006",
            role=MessageRole.tool,
            content=[TextContent(text="Response B")],
            agent_id="test",
            tool_call_id="call_B",
            name="test2",
            created_at=datetime.now()
        ))
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=10,
            message_buffer_min=3
        )
        
        # Test that adjustment doesn't create circular logic
        target_trim_index = 2
        adjusted_index = summarizer._adjust_trim_index_for_tool_pairs(messages, target_trim_index)
        
        # Should make a decision and stick with it
        assert adjusted_index >= 1, "Should not adjust to before system message"
        assert adjusted_index < len(messages), "Should not adjust beyond message list"
        
        # Run adjustment again on the adjusted index - should be stable
        re_adjusted = summarizer._adjust_trim_index_for_tool_pairs(messages, adjusted_index)
        assert re_adjusted == adjusted_index, f"Adjustment not stable: {adjusted_index} -> {re_adjusted}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])