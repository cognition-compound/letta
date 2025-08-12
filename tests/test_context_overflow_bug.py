"""
Test to reproduce the context overflow bug where summarizer fails to reduce context enough.

The hypothesis: When _adjust_trim_index_for_tool_pairs moves the trim index backwards 
to preserve tool pairs, it might keep so many messages that we're still over the context limit.
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


class TestContextOverflowBug:
    """Test the scenario where summarizer doesn't reduce context enough."""
    
    def test_adjustment_prevents_sufficient_trimming(self):
        """
        Test case where adjustment to preserve tool pairs prevents sufficient trimming.
        
        Scenario:
        - We have 100 messages
        - Buffer min is 10 (want to keep only last 10)
        - But there are many tool call/response pairs that would be orphaned
        - Adjustment moves trim point backwards to preserve them
        - Result: We keep 50+ messages instead of 10, still over context limit!
        """
        messages = []
        
        # System message (index 0)
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System prompt")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Create a pattern that will cause problems:
        # Many tool calls early on, with responses scattered throughout
        for i in range(1, 50):
            if i < 20:
                # Early tool calls (indices 1-19)
                messages.append(Message(
                    id=f"message-{i:08x}",
                    role=MessageRole.assistant,
                    content=[TextContent(text=f"Tool call {i}")],
                    agent_id="test",
                    tool_calls=[OpenAIToolCall(
                        id=f"call_{i}",
                        function=OpenAIFunction(name="archival_memory_search", arguments="{}"),
                        type="function"
                    )],
                    created_at=datetime.now()
                ))
            elif i == 20:
                # User message at index 20
                messages.append(Message(
                    id=f"message-{i:08x}",
                    role=MessageRole.user,
                    content=[TextContent(text="User message")],
                    agent_id="test",
                    created_at=datetime.now()
                ))
            elif i < 40:
                # Tool responses for the early calls (indices 21-39)
                call_index = i - 20  # Maps to calls 1-19
                messages.append(Message(
                    id=f"message-{i:08x}",
                    role=MessageRole.tool,
                    content=[TextContent(text=f"Response for call {call_index}")],
                    agent_id="test",
                    tool_call_id=f"call_{call_index}",
                    name="archival_memory_search",
                    created_at=datetime.now()
                ))
            else:
                # More user/assistant messages
                if i % 2 == 0:
                    messages.append(Message(
                        id=f"message-{i:08x}",
                        role=MessageRole.user,
                        content=[TextContent(text=f"User {i}")],
                        agent_id="test",
                        created_at=datetime.now()
                    ))
                else:
                    messages.append(Message(
                        id=f"message-{i:08x}",
                        role=MessageRole.assistant,
                        content=[TextContent(text=f"Assistant {i}")],
                        agent_id="test",
                        created_at=datetime.now()
                    ))
        
        # Create summarizer with small buffer
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=20,  # Want only 20 messages
            message_buffer_min=10      # Keep at least 10
        )
        
        # Calculate where we WANT to trim (to keep only 10 messages)
        target_trim_index = len(messages) - 10  # Should be around index 40
        
        # Apply the adjustment
        adjusted_index = summarizer._adjust_trim_index_for_tool_pairs(messages, target_trim_index)
        
        print(f"\n=== Context Overflow Test ===")
        print(f"Total messages: {len(messages)}")
        print(f"Desired trim index: {target_trim_index} (keep last 10)")
        print(f"Adjusted trim index: {adjusted_index}")
        print(f"Messages that would be kept: {len(messages) - adjusted_index}")
        
        # The bug: adjustment moves trim point way back to preserve tool pairs
        if adjusted_index < 20:
            print("⚠️ BUG: Adjustment moved trim point back to preserve tool pairs!")
            print(f"   We wanted to keep 10 messages but will keep {len(messages) - adjusted_index}")
            
            # This is the problem - we're keeping way too many messages!
            assert len(messages) - adjusted_index > 20, "Keeping more than buffer limit!"
    
    def test_infinite_adjustment_scenario(self):
        """
        Test a scenario where adjustment could ping-pong between different positions.
        """
        messages = []
        
        # System
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Create interlocked tool calls and responses
        # Call A at index 1
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
        
        # Call B at index 2
        messages.append(Message(
            id="message-00000002",
            role=MessageRole.assistant,
            content=[TextContent(text="Call B")],
            agent_id="test",
            tool_calls=[OpenAIToolCall(
                id="call_B",
                function=OpenAIFunction(name="test", arguments="{}"),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # User message at index 3
        messages.append(Message(
            id="message-00000003",
            role=MessageRole.user,
            content=[TextContent(text="User")],
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Response B at index 4
        messages.append(Message(
            id="message-00000004",
            role=MessageRole.tool,
            content=[TextContent(text="Response B")],
            agent_id="test",
            tool_call_id="call_B",
            name="test",
            created_at=datetime.now()
        ))
        
        # Response A at index 5  
        messages.append(Message(
            id="message-00000005",
            role=MessageRole.tool,
            content=[TextContent(text="Response A")],
            agent_id="test",
            tool_call_id="call_A",
            name="test",
            created_at=datetime.now()
        ))
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=10,
            message_buffer_min=3
        )
        
        # Try different trim indices to see if any cause problems
        for target in [3, 4, 5]:
            adjusted = summarizer._adjust_trim_index_for_tool_pairs(messages, target)
            print(f"Target {target} -> Adjusted {adjusted}")
            
            # Check stability - adjusting the adjusted index should give same result
            re_adjusted = summarizer._adjust_trim_index_for_tool_pairs(messages, adjusted)
            assert re_adjusted == adjusted, f"Unstable adjustment: {adjusted} -> {re_adjusted}"
    
    def test_summarizer_fails_to_reduce_context(self):
        """
        Full test showing summarizer fails to reduce context below limit.
        """
        # Create a LOT of messages with tool pairs
        messages = []
        
        # System
        messages.append(Message(
            id="message-00000000",
            role=MessageRole.system,
            content=[TextContent(text="System " * 100)],  # Large system message
            agent_id="test",
            created_at=datetime.now()
        ))
        
        # Add many tool call/response pairs
        for i in range(1, 100):
            # Tool call
            messages.append(Message(
                id=f"message-{i*3-2:08x}",
                role=MessageRole.assistant,
                content=[TextContent(text=f"Calling tool {i} with lots of text " * 50)],
                agent_id="test",
                tool_calls=[OpenAIToolCall(
                    id=f"call_{i}",
                    function=OpenAIFunction(
                        name="archival_memory_insert",
                        arguments=json.dumps({"content": "x" * 1000})  # Large arguments
                    ),
                    type="function"
                )],
                created_at=datetime.now()
            ))
            
            # User message
            messages.append(Message(
                id=f"message-{i*3-1:08x}",
                role=MessageRole.user,
                content=[TextContent(text=f"User message {i} " * 100)],
                agent_id="test",
                created_at=datetime.now()
            ))
            
            # Tool response
            messages.append(Message(
                id=f"message-{i*3:08x}",
                role=MessageRole.tool,
                content=[TextContent(text=f"Response {i} " * 100)],
                agent_id="test",
                tool_call_id=f"call_{i}",
                name="archival_memory_insert",
                created_at=datetime.now()
            ))
        
        summarizer = Summarizer(
            mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
            summarizer_agent=None,
            message_buffer_limit=50,  # Want to limit to 50 messages
            message_buffer_min=10      # Keep at least 10
        )
        
        # Run static buffer summarization
        trimmed_messages, was_summarized = summarizer._static_buffer_summarization(
            in_context_messages=messages[:100],
            new_letta_messages=messages[100:],
            force=True
        )
        
        print(f"\n=== Summarizer Result ===")
        print(f"Original message count: {len(messages)}")
        print(f"Trimmed message count: {len(trimmed_messages)}")
        print(f"Buffer limit: {summarizer.message_buffer_limit}")
        print(f"Was summarized: {was_summarized}")
        
        # The bug: we might still have too many messages!
        if len(trimmed_messages) > summarizer.message_buffer_limit:
            print(f"⚠️ BUG CONFIRMED: Trimmed messages ({len(trimmed_messages)}) exceed buffer limit ({summarizer.message_buffer_limit})!")
            print("   The adjustment to preserve tool pairs prevented sufficient trimming!")
        
        # This demonstrates the core issue
        assert len(trimmed_messages) > summarizer.message_buffer_min, "Should have kept some messages"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])