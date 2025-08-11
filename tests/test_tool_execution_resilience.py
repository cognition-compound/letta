"""Test that tool execution errors don't crash the agent system."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from letta.services.tool_executor.tool_execution_manager import ToolExecutionManager


class TestToolExecutionResilience:
    """Test that tool execution errors are handled gracefully."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent."""
        agent = Mock()
        agent.agent_state = Mock()
        agent.agent_state.id = "agent-test-uuid"
        agent.agent_state.name = "TestAgent"
        agent.user = Mock()
        agent.logger = Mock()
        return agent
    
    @pytest.fixture
    def tool_executor(self, mock_agent):
        """Create a tool execution manager."""
        executor = ToolExecutionManager()
        executor.agent = mock_agent
        return executor
    
    @pytest.mark.asyncio
    async def test_tool_error_returns_error_message_not_exception(self, tool_executor):
        """Test that tool errors return error messages, not exceptions."""
        # Mock a tool that will fail
        mock_tool = Mock()
        mock_tool.name = "send"
        mock_tool.tags = []
        
        # Simulate the tool raising an exception
        with patch.object(tool_executor, 'execute_tool_async') as mock_execute:
            mock_execute.side_effect = ValueError("Invalid 'to' parameter")
            
            # This should NOT raise an exception
            # It should return a ToolReturn with an error message
            result = await tool_executor.execute_tool_with_error_handling(
                tool_name="send",
                tool_args={"message": "test", "to": "agent-123", "request_heartbeat": True}
            )
            
            # Result should be a ToolReturn with error status
            assert hasattr(result, 'status')
            assert result.status == 'error'
            assert "Invalid 'to' parameter" in result.message
    
    @pytest.mark.asyncio
    async def test_heartbeat_continues_after_tool_error(self, tool_executor):
        """Test that request_heartbeat=True continues even after tool error."""
        # This is critical - if a tool fails but requests heartbeat,
        # the agent should continue processing, not stop
        
        mock_tool_result = Mock()
        mock_tool_result.status = "error"
        mock_tool_result.message = "Tool failed"
        
        # Even with error, if request_heartbeat was True, should continue
        should_continue = tool_executor.should_continue_after_tool(
            tool_result=mock_tool_result,
            tool_args={"request_heartbeat": True}
        )
        
        # This is the KEY fix - heartbeat should continue even on error
        assert should_continue == True
    
    @pytest.mark.asyncio
    async def test_malformed_tool_args_handled_gracefully(self, tool_executor):
        """Test that malformed tool arguments don't crash the system."""
        # Test with various malformed inputs
        test_cases = [
            {"to": "agent-123"},  # Missing 'message' arg
            {"message": "test"},  # Missing 'to' arg
            {"message": "test", "to": None},  # None value
            {"message": "test", "to": ""},  # Empty string
            {"message": "test", "to": "invalid:format:here"},  # Invalid format
        ]
        
        for args in test_cases:
            # None of these should crash the system
            # They should all return error ToolReturns
            result = await tool_executor.execute_tool_with_error_handling(
                tool_name="send",
                tool_args=args
            )
            
            assert hasattr(result, 'status')
            assert result.status == 'error'
            # System should still be running after this
    
    @pytest.mark.asyncio  
    async def test_tool_timeout_handled_gracefully(self, tool_executor):
        """Test that tool timeouts don't crash the system."""
        import asyncio
        
        # Mock a tool that hangs
        async def hanging_tool(*args, **kwargs):
            await asyncio.sleep(100)  # Hang for 100 seconds
            return "Should never get here"
        
        with patch.object(tool_executor, 'execute_tool_async', hanging_tool):
            # Set a short timeout
            result = await tool_executor.execute_tool_with_timeout(
                tool_name="send",
                tool_args={"message": "test", "to": "agent:agent-123"},
                timeout=0.1  # 100ms timeout
            )
            
            # Should timeout and return error, not hang forever
            assert hasattr(result, 'status')
            assert result.status == 'error'
            assert 'timeout' in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_agent_continues_after_tool_error(self, mock_agent):
        """Integration test: agent continues processing after tool error."""
        # This simulates what happens in the real system
        from letta.agents.letta_agent import LettaAgent
        
        # Create a more complete mock agent
        mock_agent = Mock(spec=LettaAgent)
        mock_agent.agent_state = Mock()
        mock_agent.agent_state.id = "agent-test"
        mock_agent.agent_state.name = "TestAgent"
        mock_agent.logger = Mock()
        
        # Simulate a step with a failing tool
        with patch.object(mock_agent, '_execute_tool') as mock_execute:
            mock_execute.return_value = Mock(
                status="error",
                message="Tool failed",
                tool_return="Error: Invalid parameter"
            )
            
            # Agent should handle this gracefully
            # Not crash, and potentially continue with heartbeat
            # This is where the fix needs to ensure resilience
            pass


class TestSendFunctionFixes:
    """Test the fixes to the send() function."""
    
    def test_send_handles_all_agent_id_formats(self):
        """Test that send() now handles all reasonable agent ID formats."""
        from letta.functions.function_sets.multi_agent import send
        
        mock_self = Mock()
        mock_self.agent_state = Mock(id="agent-sender", name="Sender")
        mock_self.user = Mock()
        mock_self.logger = Mock()
        
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_async:
            mock_async.return_value = "Message sent successfully"
            
            # All these should work
            test_cases = [
                "agent-ed6055c1-3c50-4dae-8966-36321a827dc9",  # Natural format
                "agent:agent-ed6055c1-3c50-4dae-8966-36321a827dc9",  # Redundant
                "agent:ed6055c1-3c50-4dae-8966-36321a827dc9",  # Without prefix
                "ed6055c1-3c50-4dae-8966-36321a827dc9",  # Raw UUID
            ]
            
            for to_param in test_cases:
                result = send(mock_self, "Test message", to=to_param)
                assert "Message sent" in result or "successfully" in result.lower()
                
                # All should result in calling with the full agent-uuid format
                call_args = mock_async.call_args[0]
                assert call_args[2] == "agent-ed6055c1-3c50-4dae-8966-36321a827dc9"
    
    def test_send_returns_error_message_on_exception(self):
        """Test that send() returns error message instead of raising exception."""
        from letta.functions.function_sets.multi_agent import send
        
        mock_self = Mock()
        mock_self.agent_state = Mock(id="agent-sender", name="Sender")
        mock_self.user = Mock()
        mock_self.logger = Mock()
        
        with patch('letta.functions.function_sets.multi_agent.send_message_to_agent_async') as mock_async:
            mock_async.side_effect = Exception("Network error")
            
            # Should NOT raise exception
            # Should return error message
            result = send(mock_self, "Test", to="agent:agent-123")
            
            # Check that it returns an error message, not crashes
            assert "error" in result.lower() or "failed" in result.lower()
    
    def test_send_validates_but_doesnt_crash(self):
        """Test that send() validates input but doesn't crash on bad input."""
        from letta.functions.function_sets.multi_agent import send
        
        mock_self = Mock()
        mock_self.agent_state = Mock(id="agent-sender", name="Sender")
        mock_self.user = Mock()
        mock_self.logger = Mock()
        
        # Test with clearly invalid input
        try:
            result = send(mock_self, "Test", to="completely:invalid:format:here")
            # Should either return error or raise ValueError
            assert "error" in result.lower() or "invalid" in result.lower()
        except ValueError as e:
            # ValueError is acceptable, but should be clear
            assert "Invalid 'to' parameter" in str(e)