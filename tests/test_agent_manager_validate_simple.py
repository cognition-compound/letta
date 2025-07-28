"""Simple unit test for the _validate_agent_exists_async method."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from letta.orm.errors import NoResultFound
from letta.schemas.user import User as PydanticUser
from letta.services.agent_manager import AgentManager


@pytest.mark.asyncio
async def test_validate_agent_exists_async_success():
    """Test _validate_agent_exists_async when agent exists and user has access."""
    # Create mock session and result
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=True)
    
    # Make execute return an awaitable
    async def async_execute(*args, **kwargs):
        return mock_result
    mock_session.execute = AsyncMock(side_effect=async_execute)
    
    # Create test data
    agent_manager = AgentManager()
    agent_id = "test-agent-id"
    user = PydanticUser(
        id="user-12345678-1234-5678-1234-567812345678",
        name="test-user",
        organization_id="org-12345678-1234-5678-1234-567812345678"
    )
    
    # Should not raise any exception
    await agent_manager._validate_agent_exists_async(mock_session, agent_id, user)
    
    # Verify the query was executed
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_validate_agent_exists_async_not_found():
    """Test _validate_agent_exists_async when agent doesn't exist or user doesn't have access."""
    # Create mock session and result
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=False)
    
    # Make execute return an awaitable
    async def async_execute(*args, **kwargs):
        return mock_result
    mock_session.execute = AsyncMock(side_effect=async_execute)
    
    # Create test data
    agent_manager = AgentManager()
    agent_id = "non-existent-agent-id"
    user = PydanticUser(
        id="user-12345678-1234-5678-1234-567812345678",
        name="test-user",
        organization_id="org-12345678-1234-5678-1234-567812345678"
    )
    
    # Should raise NoResultFound
    with pytest.raises(NoResultFound, match=f"Agent '{agent_id}' not found"):
        await agent_manager._validate_agent_exists_async(mock_session, agent_id, user)
    
    # Verify the query was executed
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_validate_agent_exists_async_query_structure():
    """Test that _validate_agent_exists_async builds the correct query."""
    # Create mock session
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=True)
    
    # Capture the actual query
    captured_query = None
    async def capture_execute(query):
        nonlocal captured_query
        captured_query = query
        return mock_result
    
    mock_session.execute = AsyncMock(side_effect=capture_execute)
    
    # Create test data
    agent_manager = AgentManager()
    agent_id = "test-agent-id"
    user = PydanticUser(
        id="user-12345678-1234-5678-1234-567812345678",
        name="test-user", 
        organization_id="org-12345678-1234-5678-1234-567812345678"
    )
    
    # Execute the method
    await agent_manager._validate_agent_exists_async(mock_session, agent_id, user)
    
    # Verify a query was captured
    assert captured_query is not None
    
    # Convert query to string to check its structure
    query_str = str(captured_query)
    
    # Check that the query includes the expected conditions
    assert "EXISTS" in query_str
    assert "agents.id" in query_str
    assert "agents.organization_id" in query_str
    assert "agents.is_deleted" in query_str