"""
Test edge cases in the summarizer that could cause it to fail or hang.

This test validates that the summarizer can handle:
1. Incomplete tool calls (call without response)
2. Orphaned responses (response without call) 
3. Malformed tool_call_ids
4. Tool pairs at trim boundaries
"""

import pytest
import asyncio
import os
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from letta.schemas.message import Message
from letta.schemas.enums import MessageRole
from letta.services.summarizer.summarizer import Summarizer
from letta.schemas.agent import AgentState
from letta.schemas.llm_config import LLMConfig


# Use real OpenAI for testing if available
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class TestSummarizerEdgeCases:
    """Test edge cases that could break the summarizer."""
    
    @pytest.fixture
    def mock_agent_state(self):
        """Create a mock agent state."""
        return AgentState(
            id="test-agent",
            name="test-agent",
            llm_config=LLMConfig(
                model="gpt-4o-mini",
                context_window=2000,  # Small window to trigger summarization
                model_endpoint_type="openai"
            )
        )
    
    @pytest.fixture
    def mock_managers(self):
        """Create mock managers for testing."""
        return {
            "agent_manager": AsyncMock(),
            "message_manager": AsyncMock(),
            "passage_manager": AsyncMock(),
            "user": MagicMock(id="test-user")
        }
    
    def create_tool_call_message(self, call_id: str, tool_name: str = "archival_memory_search") -> Message:
        """Create a tool call message."""
        return Message(
            id=f"msg-call-{call_id}",
            role=MessageRole.assistant,
            created_at=datetime.now(timezone.utc),
            agent_id="test-agent",
            content=[{
                "type": "tool_call",
                "tool_call": {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": '{"query": "test"}'
                    }
                }
            }]
        )
    
    def create_tool_response_message(self, call_id: str, content: str = "Result") -> Message:
        """Create a tool response message."""
        return Message(
            id=f"msg-resp-{call_id}",
            role=MessageRole.tool,
            created_at=datetime.now(timezone.utc),
            agent_id="test-agent",
            content=[{
                "type": "function_call_output",
                "function_call_output": {
                    "tool_call_id": call_id,
                    "output": content
                }
            }]
        )
    
    def create_user_message(self, content: str) -> Message:
        """Create a user message."""
        return Message(
            id=f"msg-user-{content[:10]}",
            role=MessageRole.user,
            created_at=datetime.now(timezone.utc),
            agent_id="test-agent",
            content=[{"type": "text", "text": content}]
        )
    
    @pytest.mark.asyncio
    async def test_incomplete_tool_call_at_boundary(self, mock_agent_state, mock_managers):
        """Test summarizer with incomplete tool call (call without response) at trim boundary."""
        # Create a conversation with an incomplete tool call at the end
        messages = [
            self.create_user_message("Hello"),
            self.create_tool_call_message("call_1", "archival_memory_search"),
            self.create_tool_response_message("call_1", "Search result 1"),
            self.create_user_message("Tell me more"),
            self.create_tool_call_message("call_2", "archival_memory_insert"),
            self.create_tool_response_message("call_2", "Inserted successfully"),
            self.create_user_message("What about the other thing?"),
            self.create_tool_call_message("call_3", "send"),  # Incomplete - no response!
            # No response for call_3 - this is the edge case
        ]
        
        summarizer = Summarizer(
            agent_state=mock_agent_state,
            agent_manager=mock_managers["agent_manager"],
            message_manager=mock_managers["message_manager"],
            passage_manager=mock_managers["passage_manager"],
            user=mock_managers["user"]
        )
        
        # Mock the LLM response for summarization
        mock_managers["agent_manager"].update_agent_memory_async = AsyncMock()
        
        with patch.object(summarizer, '_summarize_messages_with_llm', new_callable=AsyncMock) as mock_summarize:
            mock_summarize.return_value = "Summary of conversation"
            
            # This should not crash despite incomplete tool call
            try:
                trimmed_messages, summary_created = await summarizer.summarize(
                    messages_to_summarize=messages,
                    preserve_last_N_messages=3,
                    force=True
                )
                
                # Should handle the incomplete tool call gracefully
                assert trimmed_messages is not None
                assert len(trimmed_messages) <= len(messages)
                
                # The incomplete tool call should be handled - either kept or removed
                # but shouldn't cause a crash
                print(f"✅ Handled incomplete tool call. Trimmed to {len(trimmed_messages)} messages")
                
            except Exception as e:
                pytest.fail(f"Summarizer failed on incomplete tool call: {e}")
    
    @pytest.mark.asyncio  
    async def test_orphaned_response_at_boundary(self, mock_agent_state, mock_managers):
        """Test summarizer with orphaned tool response at trim boundary."""
        # Create a conversation where a tool response exists without its call
        messages = [
            self.create_user_message("Hello"),
            # Missing tool call for "call_orphan"!
            self.create_tool_response_message("call_orphan", "Orphaned response"),  # Orphaned!
            self.create_user_message("Continue"),
            self.create_tool_call_message("call_1", "archival_memory_search"),
            self.create_tool_response_message("call_1", "Search result"),
        ]
        
        summarizer = Summarizer(
            agent_state=mock_agent_state,
            agent_manager=mock_managers["agent_manager"],
            message_manager=mock_managers["message_manager"],
            passage_manager=mock_managers["passage_manager"],
            user=mock_managers["user"]
        )
        
        with patch.object(summarizer, '_summarize_messages_with_llm', new_callable=AsyncMock) as mock_summarize:
            mock_summarize.return_value = "Summary of conversation"
            
            # This should handle the orphaned response gracefully
            try:
                trimmed_messages, summary_created = await summarizer.summarize(
                    messages_to_summarize=messages,
                    preserve_last_N_messages=2,
                    force=True
                )
                
                assert trimmed_messages is not None
                
                # Should not include orphaned response without its call
                orphaned_responses = [
                    msg for msg in trimmed_messages
                    if msg.role == MessageRole.tool and 
                    "call_orphan" in str(msg.content)
                ]
                
                if orphaned_responses:
                    print(f"⚠️ Orphaned response kept in trimmed messages")
                else:
                    print(f"✅ Orphaned response correctly removed")
                    
            except Exception as e:
                pytest.fail(f"Summarizer failed on orphaned response: {e}")
    
    @pytest.mark.asyncio
    async def test_malformed_tool_call_id(self, mock_agent_state, mock_managers):
        """Test summarizer with malformed tool_call_id."""
        messages = [
            self.create_user_message("Hello"),
            Message(
                id="msg-malformed",
                role=MessageRole.assistant,
                created_at=datetime.now(timezone.utc),
                agent_id="test-agent",
                content=[{
                    "type": "tool_call",
                    "tool_call": {
                        "id": None,  # Malformed - None instead of string!
                        "type": "function",
                        "function": {
                            "name": "archival_memory_search",
                            "arguments": '{"query": "test"}'
                        }
                    }
                }]
            ),
            self.create_user_message("Continue"),
        ]
        
        summarizer = Summarizer(
            agent_state=mock_agent_state,
            agent_manager=mock_managers["agent_manager"],
            message_manager=mock_managers["message_manager"],
            passage_manager=mock_managers["passage_manager"],
            user=mock_managers["user"]
        )
        
        with patch.object(summarizer, '_summarize_messages_with_llm', new_callable=AsyncMock) as mock_summarize:
            mock_summarize.return_value = "Summary"
            
            try:
                trimmed_messages, _ = await summarizer.summarize(
                    messages_to_summarize=messages,
                    preserve_last_N_messages=1,
                    force=True
                )
                
                assert trimmed_messages is not None
                print(f"✅ Handled malformed tool_call_id gracefully")
                
            except Exception as e:
                pytest.fail(f"Summarizer crashed on malformed tool_call_id: {e}")
    
    @pytest.mark.asyncio
    async def test_circular_adjustment_prevention(self, mock_agent_state, mock_managers):
        """Test that trim adjustment doesn't create infinite loops."""
        # Create a pathological case with many interleaved tool calls
        messages = []
        for i in range(20):
            messages.append(self.create_user_message(f"Message {i}"))
            messages.append(self.create_tool_call_message(f"call_{i}"))
            if i % 3 == 0:  # Some calls don't have responses
                messages.append(self.create_tool_response_message(f"call_{i}"))
        
        summarizer = Summarizer(
            agent_state=mock_agent_state,
            agent_manager=mock_managers["agent_manager"],
            message_manager=mock_managers["message_manager"],
            passage_manager=mock_managers["passage_manager"],
            user=mock_managers["user"]
        )
        
        with patch.object(summarizer, '_summarize_messages_with_llm', new_callable=AsyncMock) as mock_summarize:
            mock_summarize.return_value = "Summary"
            
            # Should complete without hanging
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Summarizer appears to be in infinite loop!")
            
            # Set a 5 second timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)
            
            try:
                trimmed_messages, _ = await summarizer.summarize(
                    messages_to_summarize=messages,
                    preserve_last_N_messages=5,
                    force=True
                )
                signal.alarm(0)  # Cancel alarm
                
                assert trimmed_messages is not None
                print(f"✅ No infinite loop detected. Trimmed to {len(trimmed_messages)} messages")
                
            except TimeoutError:
                signal.alarm(0)
                pytest.fail("Summarizer got stuck in infinite loop during trim adjustment!")
            except Exception as e:
                signal.alarm(0)
                pytest.fail(f"Summarizer failed: {e}")
    
    @pytest.mark.skipif(not OPENAI_API_KEY, reason="OpenAI API key not available")
    @pytest.mark.asyncio
    async def test_real_summarization_with_broken_pairs(self, mock_agent_state, mock_managers):
        """Test with real OpenAI API to see actual summarization behavior."""
        from letta.llm_api.openai_client import OpenAIClient
        
        # Create conversation with broken tool pairs
        messages = [
            self.create_user_message("Let's test the system"),
            self.create_tool_call_message("call_1", "archival_memory_search"),
            # Missing response for call_1!
            self.create_user_message("Did that work?"),
            self.create_tool_response_message("call_2", "Response without call"),  # Orphaned!
            self.create_user_message("Please continue"),
            self.create_tool_call_message("call_3", "send"),
            self.create_tool_response_message("call_3", "Message sent"),
        ]
        
        # Use real OpenAI client
        client = OpenAIClient(
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1"
        )
        
        summarizer = Summarizer(
            agent_state=mock_agent_state,
            agent_manager=mock_managers["agent_manager"],
            message_manager=mock_managers["message_manager"],
            passage_manager=mock_managers["passage_manager"],
            user=mock_managers["user"]
        )
        
        # Patch the client to use real OpenAI
        with patch.object(summarizer, 'llm_client', client):
            mock_managers["agent_manager"].update_agent_memory_async = AsyncMock()
            
            try:
                print("\n🔬 Testing with real OpenAI API...")
                trimmed_messages, summary_created = await summarizer.summarize(
                    messages_to_summarize=messages,
                    preserve_last_N_messages=2,
                    force=True
                )
                
                print(f"✅ Real summarization completed successfully")
                print(f"   Original messages: {len(messages)}")
                print(f"   Trimmed messages: {len(trimmed_messages)}")
                print(f"   Summary created: {summary_created}")
                
                # Check if broken pairs were handled
                for msg in trimmed_messages:
                    if msg.role == MessageRole.tool:
                        content = str(msg.content)
                        if "call_1" in content:
                            print(f"   ⚠️ Found response for incomplete call_1")
                        if "call_2" in content:
                            print(f"   ⚠️ Found orphaned response call_2")
                
            except Exception as e:
                pytest.fail(f"Real OpenAI summarization failed: {e}")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])