"""
End-to-end tests for agent communication via streaming endpoints.

These tests reproduce the exact production failure scenario:
- Agent tries to send message to another agent via streaming endpoint
- Should not crash with "Unhandled LLM error: 'type'" or "missing 2 required positional arguments"
"""

import json
import os
import pytest
import time
from typing import List, Dict, Any
from letta_client import Letta
from letta_client.types import LettaMessageUnion, MessageCreate, UserMessage

from letta.config import LettaConfig
from letta.server.server import SyncServer
from letta.schemas.llm_config import LLMConfig


class TestAgentCommunicationStreamingEndpoint:
    """End-to-end tests for the streaming endpoint that was failing in production."""

    @pytest.fixture(scope="class")
    def server(self):
        """Set up test server."""
        config = LettaConfig()
        server = SyncServer(config)
        return server

    @pytest.fixture(scope="class") 
    def client(self, server):
        """Set up test client."""
        return Letta(
            base_url="http://localhost:8283",
            token=server.password,
        )

    @pytest.fixture
    def llm_config(self):
        """LLM config for testing."""
        return LLMConfig(
            model="gpt-4o-mini",
            model_endpoint_type="openai",
            context_window=128000,
        )

    def test_send_tool_via_streaming_endpoint_does_not_crash(self, client: Letta, llm_config: LLMConfig):
        """
        Test the exact production failure scenario.
        
        Bug: Streaming endpoint crashed with "Unhandled LLM error: 'type'" when agent used send tool
        Root cause: Schema corruption + indentation bug in convert_to_structured_output
        """
        # Create two agents for communication
        sender_agent = client.create_agent(
            name="sender_agent",
            llm_config=llm_config,
            description="Agent that sends messages to other agents"
        )
        
        receiver_agent = client.create_agent(
            name="receiver_agent", 
            llm_config=llm_config,
            description="Agent that receives messages from other agents"
        )
        
        try:
            # The exact scenario that was failing in production:
            # Agent tries to send a message to another agent via the streaming endpoint
            
            # Create a message that should trigger the send tool
            user_message = MessageCreate(
                role="user",
                text=f"Please send a message 'Hello from sender!' to agent {receiver_agent.id} using the send tool"
            )
            
            # This is the exact endpoint that was failing: /v1/agents/{agent_id}/messages/stream
            # The streaming=True parameter triggers the streaming endpoint
            response = client.send_message(
                agent_id=sender_agent.id,
                message=user_message,
                streaming=True  # This triggers the streaming endpoint that was crashing
            )
            
            # If we get here without an exception, the bug is fixed
            assert response is not None
            
            # Verify the response contains messages
            messages = []
            if hasattr(response, '__iter__'):
                # Streaming response
                for chunk in response:
                    if hasattr(chunk, 'messages'):
                        messages.extend(chunk.messages)
            else:
                # Non-streaming response
                if hasattr(response, 'messages'):
                    messages = response.messages
            
            # Should have received some messages (at least acknowledgment of send)
            assert len(messages) > 0, "Agent should have responded to the send request"
            
            # Look for evidence that send tool was called successfully
            response_text = ""
            for msg in messages:
                if hasattr(msg, 'text'):
                    response_text += msg.text + " "
            
            # Should not contain error messages about missing arguments
            error_indicators = [
                "missing 2 required positional arguments",
                "Unhandled LLM error",
                "KeyError: 'type'",
                "tool execution failed"
            ]
            
            for error in error_indicators:
                assert error.lower() not in response_text.lower(), f"Response contains error: {error}"
            
        finally:
            # Clean up
            try:
                client.delete_agent(sender_agent.id)
                client.delete_agent(receiver_agent.id)  
            except:
                pass  # Ignore cleanup errors

    def test_send_tool_with_various_targets(self, client: Letta, llm_config: LLMConfig):
        """
        Test send tool with different target formats to ensure schema is preserved.
        
        The schema corruption bug affected all send tool calls, not just agent-to-agent.
        """
        agent = client.create_agent(
            name="multi_sender_agent",
            llm_config=llm_config, 
            description="Agent that can send to various targets"
        )
        
        target_formats = [
            "user",  # Send to user
            f"agent:{agent.id}",  # Send to specific agent  
            "broadcast:urgent",  # Broadcast to tag
        ]
        
        try:
            for target in target_formats:
                user_message = MessageCreate(
                    role="user", 
                    text=f"Please use the send tool to send 'Test message' to '{target}'"
                )
                
                # Should not crash regardless of target format
                response = client.send_message(
                    agent_id=agent.id,
                    message=user_message,
                    streaming=True
                )
                
                # Collect response messages
                messages = []
                if hasattr(response, '__iter__'):
                    for chunk in response:
                        if hasattr(chunk, 'messages'):
                            messages.extend(chunk.messages)
                else:
                    if hasattr(response, 'messages'):
                        messages = response.messages
                
                assert len(messages) > 0, f"Agent should respond to send request for target: {target}"
                
                # Should not contain tool execution errors
                response_text = " ".join(msg.text for msg in messages if hasattr(msg, 'text'))
                assert "tool execution failed" not in response_text.lower(), f"Send tool failed for target: {target}"
                
        finally:
            try:
                client.delete_agent(agent.id)
            except:
                pass

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="Requires OpenAI API key")
    def test_production_scenario_exact_reproduction(self, client: Letta):
        """
        Reproduce the exact production scenario that was failing.
        
        This test mimics the exact curl request and agent setup from production.
        """
        # Use production-like LLM config
        production_llm_config = LLMConfig(
            model="gpt-4o-mini",
            model_endpoint_type="openai", 
            context_window=128000,
        )
        
        # Create agent similar to production setup
        agent = client.create_agent(
            name="production_test_agent",
            llm_config=production_llm_config,
            description="Agent reproducing production failure scenario"
        )
        
        try:
            # The exact type of message that was causing crashes
            message = MessageCreate(
                role="user",
                text="I need you to coordinate with other agents. Send a status update to agent-12345 using the send function."
            )
            
            # This should not raise any of the production errors:
            # - "Unhandled LLM error: 'type'" 
            # - "missing 2 required positional arguments: 'message' and 'to'"
            # - KeyError in convert_to_structured_output
            
            start_time = time.time()
            
            response = client.send_message(
                agent_id=agent.id,
                message=message,
                streaming=True  # Critical: this is the streaming endpoint that was failing
            )
            
            end_time = time.time()
            
            # Should complete within reasonable time (not hang due to errors)
            assert end_time - start_time < 30, "Request took too long, may indicate error handling issues"
            
            # Should get a response without crashing
            messages = []
            if hasattr(response, '__iter__'):
                for chunk in response:
                    if hasattr(chunk, 'messages'):
                        messages.extend(chunk.messages)
            
            assert len(messages) > 0, "Should receive response messages"
            
            # Verify no critical errors in response
            full_response = " ".join(
                msg.text for msg in messages 
                if hasattr(msg, 'text') and msg.text
            )
            
            critical_errors = [
                "Unhandled LLM error",
                "KeyError: 'type'", 
                "missing 2 required positional arguments",
                "convert_to_structured_output",
                "tool execution manager error"
            ]
            
            for error in critical_errors:
                assert error not in full_response, f"Critical error found in response: {error}"
                
        finally:
            try:
                client.delete_agent(agent.id)
            except:
                pass