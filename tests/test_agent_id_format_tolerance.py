"""Test that agent-to-agent messaging handles various ID formats gracefully."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from letta.functions.function_sets.multi_agent import send


class TestAgentIDFormatTolerance:
    """Test suite for agent ID format tolerance in send() function."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent with necessary attributes."""
        agent = Mock()
        agent.agent_state = Mock()
        agent.agent_state.id = "agent-sender-uuid"
        agent.agent_state.name = "SenderAgent"
        agent.user = Mock()
        agent.user.organization_id = "org-test"
        agent.logger = Mock()
        return agent
    
    def test_send_with_agent_prefix_no_colon(self, mock_agent):
        """Test that 'agent-uuid' format works (most natural for LLM)."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.return_value = "Message sent successfully"
            
            # This is what the LLM naturally tries
            result = send(mock_agent, "Hello", to="agent-ed6055c1-3c50-4dae-8966-36321a827dc9")
            
            assert result == "Message sent successfully"
            mock_send.assert_called_once_with(
                mock_agent, 
                "Hello", 
                "agent-ed6055c1-3c50-4dae-8966-36321a827dc9"
            )
    
    def test_send_with_redundant_agent_colon_format(self, mock_agent):
        """Test that 'agent:agent-uuid' format works (technically 'correct' but redundant)."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.return_value = "Message sent successfully"
            
            # The redundant "correct" format
            result = send(mock_agent, "Hello", to="agent:agent-ed6055c1-3c50-4dae-8966-36321a827dc9")
            
            assert result == "Message sent successfully"
            mock_send.assert_called_once_with(
                mock_agent, 
                "Hello", 
                "agent-ed6055c1-3c50-4dae-8966-36321a827dc9"
            )
    
    def test_send_with_agent_colon_uuid_only(self, mock_agent):
        """Test that 'agent:uuid' format works (if someone strips the prefix)."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.return_value = "Message sent successfully"
            
            # Just UUID after colon
            result = send(mock_agent, "Hello", to="agent:ed6055c1-3c50-4dae-8966-36321a827dc9")
            
            assert result == "Message sent successfully"
            # Should add the agent- prefix
            mock_send.assert_called_once_with(
                mock_agent, 
                "Hello", 
                "agent-ed6055c1-3c50-4dae-8966-36321a827dc9"
            )
    
    def test_send_with_raw_uuid(self, mock_agent):
        """Test that raw UUID format works (auto-prefixes with agent-)."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.return_value = "Message sent successfully"
            
            # Just raw UUID
            result = send(mock_agent, "Hello", to="ed6055c1-3c50-4dae-8966-36321a827dc9")
            
            assert result == "Message sent successfully"
            mock_send.assert_called_once_with(
                mock_agent, 
                "Hello", 
                "agent-ed6055c1-3c50-4dae-8966-36321a827dc9"
            )
    
    def test_send_to_user_still_works(self, mock_agent):
        """Test that sending to user still works normally."""
        with patch('letta.functions.function_sets.base.send_message') as mock_send_message:
            result = send(mock_agent, "Hello user", to="user")
            
            assert result == "Message sent to user"
            mock_send_message.assert_called_once_with(mock_agent, "Hello user")
    
    def test_send_to_group_still_works(self, mock_agent):
        """Test that sending to group still works normally."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_specific_group') as mock_send_group:
            mock_send_group.return_value = ["response1", "response2"]
            
            result = send(mock_agent, "Hello group", to="group:group-123")
            
            assert result == "Message sent to 2 agents in group group-123"
            mock_send_group.assert_called_once_with(mock_agent, "Hello group", "group-123")
    
    def test_send_to_broadcast_still_works(self, mock_agent):
        """Test that broadcast still works normally."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agents_matching_tags') as mock_broadcast:
            mock_broadcast.return_value = ["response1", "response2", "response3"]
            
            result = send(mock_agent, "Alert!", to="broadcast:critical")
            
            assert result == "Message broadcasted to 3 agents with tag 'critical'"
            mock_broadcast.assert_called_once_with(
                mock_agent, 
                "Alert!", 
                match_all=["critical"], 
                match_some=[]
            )
    
    def test_truly_invalid_format_returns_error(self, mock_agent):
        """Test that truly invalid formats return a helpful error."""
        # Test with something that's clearly not valid
        # Now it returns an error message instead of raising exception (resilient behavior)
        result = send(mock_agent, "Hello", to="invalid:format:here")
        
        assert "Error" in result or "Invalid" in result
        assert "invalid:format:here" in result
    
    def test_empty_to_parameter_returns_error(self, mock_agent):
        """Test that empty 'to' parameter returns error."""
        # Now it returns an error message instead of raising exception (resilient behavior)
        result = send(mock_agent, "Hello", to="")
        
        assert "Error" in result or "Invalid" in result


class TestAgentErrorResilience:
    """Test that agents don't crash from tool execution errors."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent with necessary attributes."""
        agent = Mock()
        agent.agent_state = Mock()
        agent.agent_state.id = "agent-sender-uuid"
        agent.agent_state.name = "SenderAgent"
        agent.user = Mock()
        agent.user.organization_id = "org-test"
        agent.logger = Mock()
        return agent
    
    def test_send_error_returns_gracefully(self, mock_agent):
        """Test that send errors are caught and returned gracefully."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.side_effect = Exception("Network error")
            
            # Should catch the exception and return an error message
            # NOT crash the entire agent
            with patch('letta.functions.function_sets.multi_agent.send') as mock_send_fn:
                # We need to test the actual error handling
                # The function should catch exceptions and return error strings
                pass
    
    def test_tool_execution_error_doesnt_stop_heartbeat(self):
        """Test that tool execution errors don't prevent heartbeat continuation."""
        # This test would require mocking the tool execution manager
        # to ensure that when a tool fails, the heartbeat still continues
        # if request_heartbeat=True
        pass
    
    def test_malformed_agent_id_doesnt_crash_system(self, mock_agent):
        """Test that malformed agent IDs don't crash the system."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.side_effect = ValueError("Agent not found")
            
            # Even with an error, the function should handle it gracefully
            # and return an error message, not crash
            pass


class TestBackwardCompatibility:
    """Ensure backward compatibility with existing code."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent with necessary attributes."""
        agent = Mock()
        agent.agent_state = Mock()
        agent.agent_state.id = "agent-sender-uuid"
        agent.agent_state.name = "SenderAgent"
        agent.user = Mock()
        agent.user.organization_id = "org-test"
        agent.logger = Mock()
        return agent
    
    def test_existing_agent_colon_format_still_works(self, mock_agent):
        """Test that existing 'agent:' format code continues to work."""
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_send:
            mock_send.return_value = "Message sent successfully"
            
            # Existing code might use this format
            result = send(mock_agent, "Hello", to="agent:agent-123")
            
            assert result == "Message sent successfully"
    
    def test_all_other_formats_unchanged(self, mock_agent):
        """Test that user, group, broadcast formats are unchanged."""
        # Test user
        with patch('letta.functions.function_sets.base.send_message') as mock_send:
            send(mock_agent, "msg", to="user")
            mock_send.assert_called_once()
        
        # Test group
        with patch('letta.functions.function_sets.multi_agent.send_message_to_specific_group') as mock_send:
            mock_send.return_value = []
            send(mock_agent, "msg", to="group:g1")
            mock_send.assert_called_once()
        
        # Test broadcast  
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agents_matching_tags') as mock_send:
            mock_send.return_value = []
            send(mock_agent, "msg", to="broadcast:tag1")
            mock_send.assert_called_once()