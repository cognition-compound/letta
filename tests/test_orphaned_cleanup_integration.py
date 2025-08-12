"""
Test for the one-time orphaned tool response cleanup that runs on startup.
This verifies that agents with orphaned tool responses get cleaned properly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, create_autospec
from letta.server.rest_api.app import cleanup_orphaned_tool_responses
from letta.schemas.agent import AgentState
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole
from letta.schemas.openai.chat_completion_response import ToolCall, FunctionCall


@pytest.mark.asyncio
async def test_cleanup_orphaned_tool_responses():
    """Test that orphaned tool responses are removed from agent message_ids"""
    
    # Create mock server with managers
    server = MagicMock()
    server.default_user = MagicMock()
    server.agent_manager = AsyncMock()
    server.message_manager = AsyncMock()
    
    # Create a mock agent with message IDs
    mock_agent = MagicMock()
    mock_agent.id = "agent-123"
    mock_agent.name = "Test Agent"
    mock_agent.message_ids = ["msg-1", "msg-2", "msg-3", "msg-4", "msg-5"]
    
    # Create mock messages with an orphaned tool response
    # Note: Each mock message needs an 'id' attribute for the fixed implementation
    mock_messages = [
        # System message
        MagicMock(id="msg-1", role=MessageRole.system, content="System prompt"),
        
        # Assistant message with tool call
        MagicMock(
            id="msg-2",
            role=MessageRole.assistant,
            content="Calling a tool",
            tool_calls=[
                MagicMock(id="call-valid-123", function=MagicMock(name="test_tool"))
            ]
        ),
        
        # Tool response for the valid tool call
        MagicMock(
            id="msg-3",
            role=MessageRole.tool,
            tool_call_id="call-valid-123",
            content="Tool response"
        ),
        
        # ORPHANED tool response (no corresponding tool call)
        MagicMock(
            id="msg-4",
            role=MessageRole.tool,
            tool_call_id="call-orphaned-456",  # This ID doesn't exist
            content="Orphaned response"
        ),
        
        # Normal assistant message
        MagicMock(
            id="msg-5",
            role=MessageRole.assistant,
            content="Regular message"
        ),
    ]
    
    # Set up the mock returns
    server.agent_manager.list_agents_async.return_value = [mock_agent]
    server.message_manager.get_messages_by_ids_async.return_value = mock_messages
    
    # Run the cleanup
    await cleanup_orphaned_tool_responses(server, worker_id=1)
    
    # Verify the agent's message_ids were updated to remove the orphaned response
    server.agent_manager.set_in_context_messages_async.assert_called_once_with(
        agent_id="agent-123",
        message_ids=["msg-1", "msg-2", "msg-3", "msg-5"],  # msg-4 (orphaned) removed
        actor=server.default_user
    )


@pytest.mark.asyncio
async def test_cleanup_no_orphans():
    """Test that agents without orphaned responses are not modified"""
    
    # Create mock server
    server = MagicMock()
    server.default_user = MagicMock()
    server.agent_manager = AsyncMock()
    server.message_manager = AsyncMock()
    
    # Create a mock agent with valid messages
    mock_agent = MagicMock()
    mock_agent.id = "agent-456"
    mock_agent.name = "Clean Agent"
    mock_agent.message_ids = ["msg-1", "msg-2", "msg-3"]
    
    # Create messages with no orphans
    mock_messages = [
        MagicMock(id="msg-1", role=MessageRole.system, content="System"),
        MagicMock(
            id="msg-2",
            role=MessageRole.assistant,
            content="With tool",
            tool_calls=[MagicMock(id="call-123", function=MagicMock(name="tool"))]
        ),
        MagicMock(
            id="msg-3",
            role=MessageRole.tool,
            tool_call_id="call-123",
            content="Valid response"
        ),
    ]
    
    server.agent_manager.list_agents_async.return_value = [mock_agent]
    server.message_manager.get_messages_by_ids_async.return_value = mock_messages
    
    # Run the cleanup
    await cleanup_orphaned_tool_responses(server, worker_id=1)
    
    # Verify no update was made (no orphans found)
    server.agent_manager.set_in_context_messages_async.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_multiple_orphans():
    """Test cleanup of multiple orphaned tool responses"""
    
    server = MagicMock()
    server.default_user = MagicMock()
    server.agent_manager = AsyncMock()
    server.message_manager = AsyncMock()
    
    mock_agent = MagicMock()
    mock_agent.id = "agent-789"
    mock_agent.name = "Multi Orphan Agent"
    mock_agent.message_ids = ["msg-1", "msg-2", "msg-3", "msg-4", "msg-5"]
    
    # Create messages with multiple orphaned tool responses
    mock_messages = [
        MagicMock(id="msg-1", role=MessageRole.system, content="System"),
        
        # First orphaned response
        MagicMock(
            id="msg-2",
            role=MessageRole.tool,
            tool_call_id="orphan-1",
            content="Orphan 1"
        ),
        
        # Assistant message without tool calls
        MagicMock(
            id="msg-3",
            role=MessageRole.assistant,
            content="No tools"
        ),
        
        # Second orphaned response  
        MagicMock(
            id="msg-4",
            role=MessageRole.tool,
            tool_call_id="orphan-2",
            content="Orphan 2"
        ),
        
        # User message
        MagicMock(
            id="msg-5",
            role=MessageRole.user,
            content="User input"
        ),
    ]
    
    server.agent_manager.list_agents_async.return_value = [mock_agent]
    server.message_manager.get_messages_by_ids_async.return_value = mock_messages
    
    # Run the cleanup
    await cleanup_orphaned_tool_responses(server, worker_id=1)
    
    # Both orphaned responses should be removed
    server.agent_manager.set_in_context_messages_async.assert_called_once_with(
        agent_id="agent-789",
        message_ids=["msg-1", "msg-3", "msg-5"],  # msg-2 and msg-4 removed
        actor=server.default_user
    )


@pytest.mark.asyncio
async def test_cleanup_handles_errors_gracefully():
    """Test that cleanup continues even if one agent fails"""
    
    server = MagicMock()
    server.default_user = MagicMock()
    server.agent_manager = AsyncMock()
    server.message_manager = AsyncMock()
    
    # Create two agents
    agent1 = MagicMock()
    agent1.id = "agent-error"
    agent1.name = "Error Agent"
    agent1.message_ids = ["msg-1"]
    
    agent2 = MagicMock()
    agent2.id = "agent-ok"
    agent2.name = "OK Agent"
    agent2.message_ids = ["msg-2", "msg-3"]
    
    server.agent_manager.list_agents_async.return_value = [agent1, agent2]
    
    # First agent will error, second will have an orphan
    async def get_messages_side_effect(message_ids, actor):
        if message_ids == ["msg-1"]:
            raise Exception("Database error")
        else:
            return [
                MagicMock(id="msg-2", role=MessageRole.system, content="System"),
                MagicMock(
                    id="msg-3",
                    role=MessageRole.tool,
                    tool_call_id="orphan",
                    content="Orphan"
                ),
            ]
    
    server.message_manager.get_messages_by_ids_async.side_effect = get_messages_side_effect
    
    # Run cleanup - should not raise despite first agent error
    await cleanup_orphaned_tool_responses(server, worker_id=1)
    
    # Second agent should still be cleaned
    server.agent_manager.set_in_context_messages_async.assert_called_once_with(
        agent_id="agent-ok",
        message_ids=["msg-2"],  # Orphan removed
        actor=server.default_user
    )