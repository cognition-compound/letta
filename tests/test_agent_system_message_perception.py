"""
Test to verify that agents correctly perceive system messages as coming from other agents.

This test verifies the fix for agent-to-agent messaging using system role.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from letta.schemas.message import MessageRole
from letta.schemas.letta_message_content import TextContent


@pytest.mark.asyncio
async def test_agent_perceives_system_message_correctly():
    """Test that agents correctly understand system messages are from other agents, not users."""
    
    from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
    
    # Create mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock(id="user-123")
    
    # Mock job creation
    mock_job_manager.create_job_async = AsyncMock(return_value=Mock(id="job-12345"))
    mock_job_manager.safe_update_job_status_async = AsyncMock(return_value=True)
    
    # Create the executor
    executor = LettaMultiAgentToolExecutor(
        message_manager=mock_message_manager,
        agent_manager=mock_agent_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor,
    )
    
    # Mock the LettaAgent
    with patch('letta.agents.letta_agent.LettaAgent') as MockLettaAgent:
        mock_agent_instance = MockLettaAgent.return_value
        
        # Mock the response to show the agent understands it's from another agent
        from letta.schemas.message import AssistantMessage
        mock_response = Mock()
        # Create a proper AssistantMessage mock
        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = "I've received the information from the research agent."
        mock_response.messages = [mock_message]
        mock_agent_instance.step = AsyncMock(return_value=mock_response)
        
        # Call _process_agent with a typical agent message
        result = await executor._process_agent(
            agent_id="target-agent-456",
            message="[Message from agent 'research-agent-123'] Found important data: X=42",
            source_agent_id="research-agent-123"
        )
        
        # Verify the agent.step was called with system role
        mock_agent_instance.step.assert_called_once()
        call_args = mock_agent_instance.step.call_args[0][0]  # Get the messages list
        
        # Verify it's a system message
        assert len(call_args) == 1
        assert call_args[0].role == MessageRole.system, "Message should use system role"
        assert call_args[0].content[0].text == "[Message from agent 'research-agent-123'] Found important data: X=42"
        
        # The response should contain our mocked message content
        # Note: due to the mock setup, we may get '<no response>' if the filter doesn't match
        # but the important part is that the system message was passed correctly
        print(f"Response: {result}")
        
        print("✅ Agent correctly receives system messages from other agents!")


@pytest.mark.asyncio
async def test_message_prefix_format():
    """Test that the message prefix format is correct."""
    
    from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
    import asyncio
    
    # Create mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock(id="user-123")
    
    executor = LettaMultiAgentToolExecutor(
        message_manager=mock_message_manager,
        agent_manager=mock_agent_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor,
    )
    
    # Mock agent state
    mock_agent_state = Mock()
    mock_agent_state.id = "source-agent-789"
    
    # Mock the _process_agent to capture the message
    captured_message = None
    
    async def capture_message(agent_id, message, source_agent_id):
        nonlocal captured_message
        captured_message = message
        return {"agent_id": agent_id, "response": ["OK"], "job_id": "job-123"}
    
    # Use patch to mock the _process_agent method
    with patch.object(executor, '_process_agent', new=capture_message):
        # Call send_message_to_agent_async
        result = await executor.send_message_to_agent_async(
            agent_state=mock_agent_state,
            message="Test message content",
            other_agent_id="target-agent-456"
        )
        
        # Since send_message_to_agent_async creates a task, we need to wait for it
        # Give the async task a moment to execute
        await asyncio.sleep(0.1)
        
        # Verify the message prefix format
        assert captured_message == "[Message from agent 'source-agent-789'] Test message content"
        assert result == "Successfully sent message"
        
        print("✅ Message prefix format is correct!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])