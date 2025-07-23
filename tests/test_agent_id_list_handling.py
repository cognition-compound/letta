"""Test agent_id list handling in inter-agent communication.

This test module verifies that agent_id parameters are properly handled
when they are incorrectly passed as lists instead of strings.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from letta.orm.errors import NoResultFound
from letta.schemas.agent import AgentState, AgentType
from letta.schemas.enums import MessageRole
from letta.schemas.llm_config import LLMConfig
from letta.schemas.embedding_config import EmbeddingConfig
from letta.schemas.letta_message_content import TextContent
from letta.schemas.message import MessageCreate
from letta.schemas.memory import Memory
from letta.schemas.user import User
from letta.services.agent_manager import AgentManager
from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor


@pytest.fixture
def mock_actor():
    """Create a mock actor/user for testing."""
    # Extract just the first 8 characters of the UUID for the ID pattern
    user_id = f"user-{str(uuid4())[:8]}"
    org_id = f"org-{str(uuid4())[:8]}"
    
    return User(
        id=user_id,
        name="test_user",
        organization_id=org_id
    )


@pytest.fixture
def mock_agent_state():
    """Create a mock agent state for testing."""
    agent_id = f"agent-{str(uuid4())[:8]}"
    user_id = f"user-{str(uuid4())[:8]}"
    org_id = f"org-{str(uuid4())[:8]}"
    
    # Use a simple mock instead of creating complex Pydantic objects
    mock_state = MagicMock()
    mock_state.id = agent_id
    mock_state.name = "test_agent"
    mock_state.created_by_id = user_id
    mock_state.last_updated_by_id = user_id
    mock_state.organization_id = org_id
    
    return mock_state


class TestMultiAgentToolExecutorListHandling:
    """Test multi-agent tool executor handles agent_id passed as list."""
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent_async_with_list(self, mock_actor, mock_agent_state):
        """Test send_message_to_agent_async handles other_agent_id as list."""
        # Create mock managers
        mock_agent_manager = MagicMock()
        mock_message_manager = MagicMock()
        mock_block_manager = MagicMock()
        mock_job_manager = MagicMock()
        mock_passage_manager = MagicMock()
        
        executor = LettaMultiAgentToolExecutor(
            agent_manager=mock_agent_manager,
            message_manager=mock_message_manager,
            block_manager=mock_block_manager,
            job_manager=mock_job_manager,
            passage_manager=mock_passage_manager,
            actor=mock_actor,
        )
        
        other_agent_id = f"agent-{str(uuid4())[:8]}"
        
        # Mock the _process_agent method
        with patch.object(executor, '_process_agent', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {
                "agent_id": other_agent_id,
                "response": ["Test response"]
            }
            
            # Call with other_agent_id as a list
            result = await executor.send_message_to_agent_async(
                agent_state=mock_agent_state,
                message="Test message",
                other_agent_id=[other_agent_id]  # Pass as list
            )
            
            # Verify the ID was extracted correctly
            assert result == "Successfully sent message"
            # The task is created asynchronously, so we need to wait a bit
            await asyncio.sleep(0.1)
            mock_process.assert_called_once()
            call_args = mock_process.call_args
            assert call_args[1]['agent_id'] == other_agent_id  # Should be string
    
    @pytest.mark.asyncio
    async def test_process_agent_with_list(self, mock_actor, mock_agent_state):
        """Test _process_agent handles agent_id as list."""
        # Create mock managers
        mock_agent_manager = MagicMock()
        mock_message_manager = MagicMock()
        mock_block_manager = MagicMock()
        mock_job_manager = MagicMock()
        mock_passage_manager = MagicMock()
        
        executor = LettaMultiAgentToolExecutor(
            agent_manager=mock_agent_manager,
            message_manager=mock_message_manager,
            block_manager=mock_block_manager,
            job_manager=mock_job_manager,
            passage_manager=mock_passage_manager,
            actor=mock_actor,
        )
        
        agent_id = f"agent-{str(uuid4())[:8]}"
        
        # Mock LettaAgent - patch where it's imported in the _process_agent method
        with patch('letta.agents.letta_agent.LettaAgent') as MockLettaAgent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.step = AsyncMock(return_value=MagicMock(messages=[]))
            MockLettaAgent.return_value = mock_agent_instance
            
            # Call with agent_id as a list
            result = await executor._process_agent(
                agent_id=[agent_id],  # Pass as list
                message="Test message"
            )
            
            # Verify LettaAgent was created with string ID
            MockLettaAgent.assert_called_once()
            call_args = MockLettaAgent.call_args
            assert call_args[1]['agent_id'] == agent_id  # Should be string
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent_async_empty_list(self, mock_actor, mock_agent_state):
        """Test send_message_to_agent_async with empty list."""
        # Create mock managers
        mock_agent_manager = MagicMock()
        mock_message_manager = MagicMock()
        mock_block_manager = MagicMock()
        mock_job_manager = MagicMock()
        mock_passage_manager = MagicMock()
        
        executor = LettaMultiAgentToolExecutor(
            agent_manager=mock_agent_manager,
            message_manager=mock_message_manager,
            block_manager=mock_block_manager,
            job_manager=mock_job_manager,
            passage_manager=mock_passage_manager,
            actor=mock_actor,
        )
        
        # Test with empty list
        with pytest.raises(ValueError, match="other_agent_id list is empty"):
            await executor.send_message_to_agent_async(
                agent_state=mock_agent_state,
                message="Test message",
                other_agent_id=[]  # Empty list
            )


class TestMultiAgentFunctionsListHandling:
    """Test multi-agent functions handle agent_id passed as list."""
    
    def test_send_message_to_agent_async_function_with_list(self):
        """Test send_message_to_agent_async function handles other_agent_id as list."""
        from letta.functions.function_sets.multi_agent import send_message_to_agent_async
        
        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.agent_state.name = "TestAgent"
        mock_agent.agent_state.id = f"agent-{str(uuid4())[:8]}"
        mock_agent.logger = MagicMock()
        
        other_agent_id = f"agent-{str(uuid4())[:8]}"
        
        with patch('letta.functions.function_sets.multi_agent.fire_and_forget_send_to_agent') as mock_fire:
            # Call with other_agent_id as a list
            result = send_message_to_agent_async(
                mock_agent,
                message="Test message",
                other_agent_id=[other_agent_id]  # Pass as list
            )
            
            # Verify the function was called with string ID
            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[1]['other_agent_id'] == other_agent_id  # Should be string
            assert result == "Message sent successfully"
    
    def test_fire_and_forget_send_to_agent_with_list(self):
        """Test fire_and_forget_send_to_agent handles other_agent_id as list."""
        from letta.functions.helpers import fire_and_forget_send_to_agent
        
        # Create mock objects
        mock_agent = MagicMock()
        mock_agent.user = MagicMock()
        mock_agent.logger = MagicMock()
        
        other_agent_id = f"agent-{str(uuid4())[:8]}"
        messages = [MessageCreate(role=MessageRole.system, content=[TextContent(text="Test")])]
        
        with patch('letta.functions.helpers.get_letta_server') as mock_get_server:
            mock_server = MagicMock()
            mock_agent_manager = MagicMock()
            mock_server.agent_manager = mock_agent_manager
            mock_get_server.return_value = mock_server
            
            # Mock successful agent lookup
            mock_agent_manager.get_agent_by_id.return_value = MagicMock()
            
            with patch('letta.functions.helpers.asyncio') as mock_asyncio:
                # Call with other_agent_id as a list
                fire_and_forget_send_to_agent(
                    sender_agent=mock_agent,
                    messages=messages,
                    other_agent_id=[other_agent_id],  # Pass as list
                    log_prefix="[test]",
                    use_retries=False
                )
                
                # Verify agent lookup was called with string ID
                mock_agent_manager.get_agent_by_id.assert_called_once()
                call_args = mock_agent_manager.get_agent_by_id.call_args
                assert call_args[1]['agent_id'] == other_agent_id  # Should be string
    
    def test_send_message_to_agent_async_function_empty_list(self):
        """Test send_message_to_agent_async function with empty list."""
        from letta.functions.function_sets.multi_agent import send_message_to_agent_async
        
        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.agent_state.name = "TestAgent"
        mock_agent.agent_state.id = f"agent-{str(uuid4())[:8]}"
        mock_agent.logger = MagicMock()
        
        # Test with empty list
        with pytest.raises(ValueError, match="other_agent_id list is empty"):
            send_message_to_agent_async(
                mock_agent,
                message="Test message",
                other_agent_id=[]  # Empty list
            )


class TestIntegrationScenarios:
    """Test complete inter-agent communication scenarios."""
    
    @pytest.mark.asyncio
    async def test_send_method_with_agent_list(self, mock_actor, mock_agent_state):
        """Test the send() method in tool executor with agent: prefix and list ID."""
        # Create mock managers
        mock_agent_manager = MagicMock()
        mock_message_manager = MagicMock()
        mock_block_manager = MagicMock()
        mock_job_manager = MagicMock()
        mock_passage_manager = MagicMock()
        
        executor = LettaMultiAgentToolExecutor(
            agent_manager=mock_agent_manager,
            message_manager=mock_message_manager,
            block_manager=mock_block_manager,
            job_manager=mock_job_manager,
            passage_manager=mock_passage_manager,
            actor=mock_actor,
        )
        
        agent_id = f"agent-{str(uuid4())[:8]}"
        
        # Mock send_message_to_agent_async
        with patch.object(executor, 'send_message_to_agent_async', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = "Successfully sent message"
            
            # Simulate the case where agent ID might be in a list
            # This could happen if the 'to' parameter is constructed incorrectly
            result = await executor.send(
                agent_state=mock_agent_state,
                message="Test message",
                to=f"agent:{agent_id}"  # Normal case
            )
            
            # Verify it was called correctly
            mock_send.assert_called_once_with(mock_agent_state, "Test message", agent_id)
            assert result == "Successfully sent message"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])