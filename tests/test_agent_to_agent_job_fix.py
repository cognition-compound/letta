"""
Test to verify that the agent-to-agent messaging fix properly creates jobs.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch


@pytest.mark.asyncio
async def test_process_agent_creates_job():
    """Test that _process_agent now creates a job before running the agent step."""
    
    from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
    
    # Create mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock(id="user-123")
    
    # Mock job creation
    mock_job_manager.create_job_async = AsyncMock(return_value=Mock(id="run-12345678"))
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
        mock_agent_instance.step = AsyncMock(return_value=Mock(messages=[]))
        
        # Call _process_agent directly
        result = await executor._process_agent(
            agent_id="target-agent-456",
            message="[Message from agent 'source-123'] Test message",
            source_agent_id="source-123"
        )
        
        # Verify job was created
        mock_job_manager.create_job_async.assert_called_once()
        
        # Verify the job metadata
        call_args = mock_job_manager.create_job_async.call_args
        created_job = call_args[1]['pydantic_job']
        assert created_job.metadata['job_type'] == 'agent_to_agent_message'
        assert created_job.metadata['target_agent_id'] == 'target-agent-456'
        assert created_job.metadata['source_agent_id'] == 'source-123'
        
        # Verify job status was updated to running and then completed
        assert mock_job_manager.safe_update_job_status_async.call_count >= 2
        
        # Verify the agent step was called
        MockLettaAgent.assert_called_once_with(
            agent_id="target-agent-456",
            message_manager=mock_message_manager,
            agent_manager=mock_agent_manager,
            block_manager=mock_block_manager,
            job_manager=mock_job_manager,
            passage_manager=mock_passage_manager,
            actor=mock_actor,
        )
        mock_agent_instance.step.assert_called_once()
        
        # Verify result includes job_id
        assert 'job_id' in result
        assert result['job_id'] == "run-12345678"


@pytest.mark.asyncio
async def test_send_message_to_agent_is_async():
    """Test that send_message_to_agent_async returns immediately (fire-and-forget)."""
    
    from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
    
    # Create mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock(id="user-123")
    
    # Create the executor
    executor = LettaMultiAgentToolExecutor(
        message_manager=mock_message_manager,
        agent_manager=mock_agent_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor,
    )
    
    # Create a mock agent state
    mock_agent_state = Mock(id="source-agent-123")
    
    # Track if _process_agent is called
    process_agent_called = False
    
    async def mock_process_agent(*args, **kwargs):
        nonlocal process_agent_called
        await asyncio.sleep(1)  # Simulate slow processing
        process_agent_called = True
        return {"agent_id": "target", "response": ["OK"]}
    
    # Replace _process_agent with our mock
    executor._process_agent = mock_process_agent
    
    # Call send_message_to_agent_async
    result = await executor.send_message_to_agent_async(
        agent_state=mock_agent_state,
        message="Test message",
        other_agent_id="target-agent-456"
    )
    
    # Should return immediately
    assert result == "Successfully sent message"
    assert not process_agent_called  # Should not have completed yet
    
    # Wait for background task to complete
    await asyncio.sleep(1.5)
    assert process_agent_called  # Now it should be done