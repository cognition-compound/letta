"""
Tests for enhanced inter-agent messaging with clean context formatting.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List

from letta.functions.function_sets.multi_agent import (
    send_message_to_agent_and_wait_for_reply,
    send_message_to_agent_async,
    send_message_to_agents_matching_tags,
    send,
)
from letta.schemas.message import MessageCreate
from letta.schemas.enums import MessageRole


class TestEnhancedMessaging:
    """Test suite for enhanced inter-agent messaging functions."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = Mock()
        agent.agent_state = Mock()
        agent.agent_state.id = "test-agent-123"
        agent.agent_state.name = "TestAgent"
        agent.user = Mock()
        agent.user.organization_id = "test-org"
        agent.logger = Mock()
        return agent

    @pytest.fixture
    def mock_server(self):
        """Create a mock server for testing."""
        with patch("letta.functions.function_sets.multi_agent.get_letta_server") as mock_get_server:
            server = Mock()
            mock_get_server.return_value = server
            yield server

    def test_send_message_to_agent_and_wait_for_reply_clean_format(self, mock_agent):
        """Test that send_message_to_agent_and_wait_for_reply uses clean message format."""
        with patch("letta.functions.function_sets.multi_agent.execute_send_message_to_agent") as mock_execute:
            mock_execute.return_value = "Test response"

            # Call the function
            result = send_message_to_agent_and_wait_for_reply(mock_agent, "Hello other agent!", "other-agent-456")

            # Verify the function was called
            mock_execute.assert_called_once()

            # Check the messages format
            messages = mock_execute.call_args[1]["messages"]
            assert len(messages) == 2

            # Check system message with clean sender context
            assert messages[0].role == MessageRole.system
            assert messages[0].content == '[Message from: Agent "TestAgent" (ID: test-agent-123)]'

            # Check user message with clean content
            assert messages[1].role == MessageRole.user
            assert messages[1].content == "Hello other agent!"
            assert messages[1].name == "TestAgent"
            assert messages[1].sender_id == "test-agent-123"

            assert result == "Test response"

    def test_send_message_to_agent_async_clean_format(self, mock_agent):
        """Test that send_message_to_agent_async uses clean message format."""
        with patch("letta.functions.function_sets.multi_agent.fire_and_forget_send_to_agent") as mock_fire_forget:
            # Call the function
            result = send_message_to_agent_async(mock_agent, "Async notification", "other-agent-789")

            # Verify the function was called
            mock_fire_forget.assert_called_once()

            # Check the messages format
            messages = mock_fire_forget.call_args[1]["messages"]
            assert len(messages) == 2

            # Check system message with clean sender context
            assert messages[0].role == MessageRole.system
            assert messages[0].content == '[Message from: Agent "TestAgent" (ID: test-agent-123)]'

            # Check user message with clean content
            assert messages[1].role == MessageRole.user
            assert messages[1].content == "Async notification"
            assert messages[1].name == "TestAgent"
            assert messages[1].sender_id == "test-agent-123"

            assert result == "Message sent successfully"

    def test_send_message_to_agents_matching_tags_clean_format(self, mock_agent, mock_server):
        """Test that send_message_to_agents_matching_tags uses clean message format."""
        # Mock matching agents
        mock_agent_state = Mock()
        mock_agent_state.id = "matched-agent-1"
        mock_server.agent_manager.list_agents_matching_tags.return_value = [mock_agent_state]

        # Mock loaded agent
        loaded_agent = Mock()
        loaded_agent.logger = Mock()
        mock_server.load_agent.return_value = loaded_agent

        # Mock step response
        usage_stats = Mock()
        usage_stats.steps_messages = []
        loaded_agent.step.return_value = usage_stats

        with patch("letta.functions.function_sets.multi_agent.extract_send_message_from_steps_messages") as mock_extract:
            mock_extract.return_value = ["Response from matched agent"]

            # Call the function
            results = send_message_to_agents_matching_tags(
                mock_agent, "Broadcast message", match_all=["important"], match_some=["urgent", "critical"]
            )

            # Verify step was called with clean messages
            loaded_agent.step.assert_called_once()
            messages = loaded_agent.step.call_args[1]["input_messages"]
            assert len(messages) == 2

            # Check system message with clean sender context
            assert messages[0].role == MessageRole.system
            assert messages[0].content == '[Message from: Agent "TestAgent" (ID: test-agent-123)]'

            # Check user message with clean content
            assert messages[1].role == MessageRole.user
            assert messages[1].content == "Broadcast message"
            assert messages[1].name == "TestAgent"
            assert messages[1].sender_id == "test-agent-123"

            assert len(results) == 1

    def test_universal_send_to_user(self, mock_agent):
        """Test universal send function routing to user."""
        with patch("letta.functions.function_sets.base.send_message") as mock_send_message:
            result = send(mock_agent, "Hello user!", to="user")

            mock_send_message.assert_called_once_with(mock_agent, "Hello user!")
            assert result == "Message sent to user"

    def test_universal_send_to_agent_sync(self, mock_agent):
        """Test universal send function routing to agent synchronously."""
        with patch("letta.functions.function_sets.multi_agent.send_message_to_agent_and_wait_for_reply") as mock_send_sync:
            mock_send_sync.return_value = "Agent response"

            result = send(mock_agent, "Need info", to="agent:other-agent-123", wait_for_reply=True)

            mock_send_sync.assert_called_once_with(mock_agent, "Need info", "other-agent-123")
            assert result == "Agent response"

    def test_universal_send_to_agent_async(self, mock_agent):
        """Test universal send function routing to agent asynchronously."""
        with patch("letta.functions.function_sets.multi_agent.send_message_to_agent_async") as mock_send_async:
            mock_send_async.return_value = "Message sent successfully"

            result = send(mock_agent, "FYI", to="agent:other-agent-456", wait_for_reply=False)

            mock_send_async.assert_called_once_with(mock_agent, "FYI", "other-agent-456")
            assert result == "Message sent successfully"

    def test_universal_send_to_group(self, mock_agent):
        """Test universal send function routing to group."""
        with patch("letta.functions.function_sets.multi_agent.send_message_to_all_agents_in_group") as mock_send_group:
            mock_send_group.return_value = ["Response 1", "Response 2"]

            result = send(mock_agent, "Group update", to="group:my-group")

            mock_send_group.assert_called_once_with(mock_agent, "Group update")
            assert result == "Message sent to 2 agents in group"

    def test_universal_send_broadcast(self, mock_agent):
        """Test universal send function broadcasting by tag."""
        with patch("letta.functions.function_sets.multi_agent.send_message_to_agents_matching_tags") as mock_broadcast:
            mock_broadcast.return_value = ["Response 1", "Response 2", "Response 3"]

            result = send(mock_agent, "Alert!", to="broadcast:critical")

            mock_broadcast.assert_called_once_with(mock_agent, "Alert!", match_all=["critical"], match_some=[])
            assert result == "Message broadcasted to 3 agents with tag 'critical'"

    def test_universal_send_invalid_target(self, mock_agent):
        """Test universal send function with invalid target."""
        with pytest.raises(ValueError) as exc_info:
            send(mock_agent, "Test", to="invalid:target")

        assert "Invalid 'to' parameter" in str(exc_info.value)
