"""
Test to verify that agent-to-agent messages properly create jobs.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
from letta.schemas.agent import AgentState
from letta.schemas.run import Run
from letta.schemas.enums import JobStatus
from letta.schemas.llm_config import LLMConfig
from letta.schemas.embedding_config import EmbeddingConfig
from letta.schemas.memory import Memory, Block


@pytest.mark.asyncio
async def test_agent_to_agent_creates_job():
    """Test that sending a message to another agent creates a proper job."""
    
    # Create mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock(id="user-123")
    
    # Create mock job
    mock_run = Run(
        id="run-12345678",
        user_id="user-123",
        status=JobStatus.created,
        metadata={}
    )
    
    # Setup job manager mocks
    mock_job_manager.create_job_async = AsyncMock(return_value=mock_run)
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
    
    # Create mock agent state
    source_agent_state = AgentState(
        id="source-agent-123",
        name="Source Agent",
        user_id="user-123",
        tools=[],
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        llm_config=LLMConfig(
            model="gpt-4",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=8192,
        ),
        embedding_config=EmbeddingConfig(
            embedding_model="text-embedding-ada-002",
            embedding_endpoint_type="openai",
            embedding_endpoint="https://api.openai.com/v1",
            embedding_dim=1536,
        ),
        memory=Memory(blocks=[]),
    )
    
    # Mock the LettaAgent and its step method
    with patch('letta.services.tool_executor.multi_agent_tool_executor.LettaAgent') as MockLettaAgent:
        mock_agent_instance = MockLettaAgent.return_value
        mock_agent_instance.step = AsyncMock(return_value=Mock(messages=[]))
        
        # Test sending a message
        result = await executor.send_message_to_agent_async(
            agent_state=source_agent_state,
            message="Test message",
            other_agent_id="target-agent-456"
        )
        
        # Verify the result
        assert result == "Successfully sent message"
        
        # Wait a bit for the background task to start
        await asyncio.sleep(0.1)
        
        # Verify job was created
        mock_job_manager.create_job_async.assert_called_once()
        call_args = mock_job_manager.create_job_async.call_args
        created_job = call_args[1]['pydantic_job']
        
        assert created_job.metadata['job_type'] == 'agent_to_agent_message'
        assert created_job.metadata['target_agent_id'] == 'target-agent-456'
        assert created_job.metadata['source_agent_id'] == 'source-agent-123'
        
        # Verify job status was updated to running
        await asyncio.sleep(0.1)  # Give time for async operations
        assert mock_job_manager.safe_update_job_status_async.called


@pytest.mark.asyncio  
async def test_agent_to_agent_handles_errors():
    """Test that errors in agent-to-agent messaging are handled properly."""
    
    # Create mock managers
    mock_message_manager = Mock()
    mock_agent_manager = Mock()
    mock_block_manager = Mock()
    mock_job_manager = Mock()
    mock_passage_manager = Mock()
    mock_actor = Mock(id="user-123")
    
    # Create mock job
    mock_run = Run(
        id="run-abcdef12",
        user_id="user-123",
        status=JobStatus.created,
        metadata={}
    )
    
    # Setup job manager mocks
    mock_job_manager.create_job_async = AsyncMock(return_value=mock_run)
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
    
    # Create mock agent state
    source_agent_state = AgentState(
        id="source-agent-789",
        name="Source Agent",
        user_id="user-123",
        tools=[],
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        llm_config=LLMConfig(
            model="gpt-4",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=8192,
        ),
        embedding_config=EmbeddingConfig(
            embedding_model="text-embedding-ada-002",
            embedding_endpoint_type="openai",
            embedding_endpoint="https://api.openai.com/v1",
            embedding_dim=1536,
        ),
        memory=Memory(blocks=[]),
    )
    
    # Mock the LettaAgent to raise an error
    with patch('letta.services.tool_executor.multi_agent_tool_executor.LettaAgent') as MockLettaAgent:
        mock_agent_instance = MockLettaAgent.return_value
        mock_agent_instance.step = AsyncMock(side_effect=Exception("Test error"))
        
        # Test sending a message
        result = await executor.send_message_to_agent_async(
            agent_state=source_agent_state,
            message="Test message that will fail",
            other_agent_id="target-agent-999"
        )
        
        # Verify the immediate result is still success (fire-and-forget)
        assert result == "Successfully sent message"
        
        # Wait for the background task to process
        await asyncio.sleep(0.2)
        
        # Verify job was created
        mock_job_manager.create_job_async.assert_called_once()
        
        # Verify job status was updated to failed
        calls = mock_job_manager.safe_update_job_status_async.call_args_list
        # Should have at least one call with failed status
        failed_call_found = False
        for call in calls:
            if call[1].get('new_status') == JobStatus.failed:
                failed_call_found = True
                break
        assert failed_call_found, "Job should have been marked as failed"