"""Test for broadcast message fix - ensuring correct agent IDs are used."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor


@pytest.mark.asyncio
async def test_broadcast_message_uses_correct_agent_ids():
    """Test that broadcast messages are sent to the correct agent IDs."""
    
    # Create mock dependencies
    mock_agent_manager = AsyncMock()
    mock_message_manager = AsyncMock()
    mock_block_manager = AsyncMock()
    mock_job_manager = AsyncMock()
    mock_passage_manager = AsyncMock()
    mock_actor = MagicMock()
    mock_actor.id = "test-user-id"
    
    # Create executor
    executor = LettaMultiAgentToolExecutor(
        agent_manager=mock_agent_manager,
        message_manager=mock_message_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor
    )
    
    # Create sender agent state mock
    sender_agent_state = MagicMock()
    sender_agent_state.id = "sender-agent-id"
    sender_agent_state.name = "Sender Agent"
    sender_agent_state.tags = ["sender"]
    sender_agent_state.tools = []
    
    # Create matching agents
    matching_agents = []
    for i in range(1, 4):
        agent = MagicMock()
        agent.id = f"agent-{i}"
        agent.name = f"Agent {i}"
        agent.tags = ["test-tag"]
        agent.tools = []
        matching_agents.append(agent)
    
    # Mock the agent manager to return matching agents
    mock_agent_manager.list_agents_matching_tags_async.return_value = matching_agents
    
    # Mock job creation
    mock_run = MagicMock()
    mock_run.id = "test-job-id"
    mock_job_manager.create_job_async = AsyncMock(return_value=mock_run)
    mock_job_manager.safe_update_job_status_async = AsyncMock()
    
    # Track which agent IDs _process_agent was called with
    process_agent_calls = []
    
    async def mock_process_agent(agent_id, message, source_agent_id=None):
        process_agent_calls.append({
            "agent_id": agent_id,
            "message": message,
            "source_agent_id": source_agent_id
        })
        return {
            "agent_id": agent_id,
            "response": ["Test response"],
            "job_id": "test-job-id"
        }
    
    # Patch _process_agent to track calls
    with patch.object(executor, '_process_agent', new=mock_process_agent):
        # Execute broadcast
        result = await executor.send_message_to_agents_matching_tags_async(
            agent_state=sender_agent_state,
            message="Test broadcast message",
            match_all=["test-tag"],
            match_some=[]
        )
    
    # Verify the agent manager was called correctly
    mock_agent_manager.list_agents_matching_tags_async.assert_called_once_with(
        actor=mock_actor,
        match_all=["test-tag"],
        match_some=[]
    )
    
    # Verify _process_agent was called with the correct agent IDs
    assert len(process_agent_calls) == 3, f"Expected 3 calls, got {len(process_agent_calls)}"
    
    # Check each call has the correct agent ID (not the sender's ID)
    called_agent_ids = [call["agent_id"] for call in process_agent_calls]
    expected_agent_ids = ["agent-1", "agent-2", "agent-3"]
    
    assert sorted(called_agent_ids) == sorted(expected_agent_ids), \
        f"Expected agent IDs {expected_agent_ids}, got {called_agent_ids}"
    
    # Verify all calls have the correct source_agent_id (sender's ID)
    for call in process_agent_calls:
        assert call["source_agent_id"] == "sender-agent-id", \
            f"Expected source_agent_id to be 'sender-agent-id', got {call['source_agent_id']}"
        
        # Verify the message format
        expected_prefix = "[Broadcast message from agent 'sender-agent-id']"
        assert call["message"].startswith(expected_prefix), \
            f"Message should start with '{expected_prefix}', got: {call['message']}"
    
    print("✅ All broadcast message tests passed!")


@pytest.mark.asyncio
async def test_broadcast_message_empty_matching_agents():
    """Test that broadcast returns empty list when no agents match."""
    
    # Create mock dependencies
    mock_agent_manager = AsyncMock()
    mock_message_manager = AsyncMock()
    mock_block_manager = AsyncMock()
    mock_job_manager = AsyncMock()
    mock_passage_manager = AsyncMock()
    mock_actor = MagicMock()
    mock_actor.id = "test-user-id"
    
    # Create executor
    executor = LettaMultiAgentToolExecutor(
        agent_manager=mock_agent_manager,
        message_manager=mock_message_manager,
        block_manager=mock_block_manager,
        job_manager=mock_job_manager,
        passage_manager=mock_passage_manager,
        actor=mock_actor
    )
    
    # Create sender agent state mock
    sender_agent_state = MagicMock()
    sender_agent_state.id = "sender-agent-id"
    sender_agent_state.name = "Sender Agent"
    sender_agent_state.tags = ["sender"]
    sender_agent_state.tools = []
    
    # Mock the agent manager to return no matching agents
    mock_agent_manager.list_agents_matching_tags_async.return_value = []
    
    # Execute broadcast
    result = await executor.send_message_to_agents_matching_tags_async(
        agent_state=sender_agent_state,
        message="Test broadcast message",
        match_all=["non-existent-tag"],
        match_some=[]
    )
    
    # Verify the result is an empty list string
    assert result == "[]", f"Expected '[]', got '{result}'"
    
    print("✅ Empty broadcast test passed!")


if __name__ == "__main__":
    asyncio.run(test_broadcast_message_uses_correct_agent_ids())
    asyncio.run(test_broadcast_message_empty_matching_agents())