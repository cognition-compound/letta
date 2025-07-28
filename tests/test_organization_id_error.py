"""
Test to reproduce the organization_id error from SDK clients.

This test simulates the error that occurs when an SDK client sends a message
with an organization_id field that the marshmallow schema doesn't expect.
"""

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import uuid

# Ensure database pooling is disabled for tests
os.environ["LETTA_DISABLE_SQLALCHEMY_POOLING"] = "true"

from letta.schemas.message import Message, MessageCreate, MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.schemas.agent import AgentState, CreateAgent
from letta.schemas.block import CreateBlock
from letta.schemas.user import User
from letta.serialize_schemas.marshmallow_message import SerializedMessageSchema
from letta.orm.message import Message as MessageModel
from letta.server.server import SyncServer
from letta.config import LettaConfig
from marshmallow import ValidationError


@pytest.fixture(scope="module")
def server():
    """Create a test server instance."""
    config = LettaConfig.load()
    config.save()
    server = SyncServer()
    return server


@pytest.fixture
async def default_organization(server: SyncServer):
    """Fixture to create and return the default organization."""
    yield await server.organization_manager.create_default_organization_async()


@pytest.fixture
async def default_user(server: SyncServer, default_organization):
    """Fixture to create and return the default user within the default organization."""
    user = await server.user_manager.create_default_actor_async(org_id=default_organization.id)
    yield user


@pytest.fixture
async def test_agents(server: SyncServer, default_user):
    """Create two test agents for async messaging."""
    agent1 = await server.create_agent_async(
        request=CreateAgent(
            name="agent1",
            memory_blocks=[
                CreateBlock(
                    label="persona",
                    value="You are agent 1, a helpful assistant.",
                ),
            ],
            model="openai/gpt-4o-mini",
            embedding="openai/text-embedding-3-small",
        ),
        actor=default_user,
    )
    
    agent2 = await server.create_agent_async(
        request=CreateAgent(
            name="agent2",
            memory_blocks=[
                CreateBlock(
                    label="persona",
                    value="You are agent 2, a collaborative assistant.",
                ),
            ],
            model="openai/gpt-4o-mini",
            embedding="openai/text-embedding-3-small",
        ),
        actor=default_user,
    )
    
    yield [agent1, agent2]
    
    # Cleanup
    await server.agent_manager.delete_agent_async(agent1.id, default_user)
    await server.agent_manager.delete_agent_async(agent2.id, default_user)


@pytest.mark.asyncio
async def test_organization_id_error_reproduction(server: SyncServer, default_user, test_agents):
    """
    Test that reproduces the organization_id error when SDK sends messages with organization_id field.
    """
    agent1, agent2 = test_agents
    
    # Simulate what the SDK client sends - a message with organization_id field
    message_data_with_org_id = {
        "id": f"message-{uuid.uuid4()}",
        "role": MessageRole.system,
        "content": [{"type": "text", "text": "Test message from SDK"}],
        "agent_id": agent2.id,
        "organization_id": default_user.organization_id,  # This field causes the error
        "created_at": "2025-01-28T12:00:00Z",
        "model": "gpt-4o-mini",
        "name": None,
        "tool_calls": None,
        "tool_call_id": None,
        "step_id": None,
        "otid": None,
        "tool_returns": None,
        "group_id": None,
        "sender_id": agent1.id,
        "batch_item_id": None,
        "is_err": None,
    }
    
    # Test marshmallow deserialization with organization_id field
    schema = SerializedMessageSchema(actor=default_user)
    
    # This should raise an error with the current implementation
    with pytest.raises(ValidationError) as exc_info:
        # Try to load the message data with organization_id
        schema.load(message_data_with_org_id)
    
    # Verify the error matches what we see in staging
    error_str = str(exc_info.value)
    assert "object has no field" in error_str.lower() or "unknown field" in error_str.lower()
    

@pytest.mark.asyncio
async def test_organization_id_backward_compatibility(server: SyncServer, default_user, test_agents):
    """
    Test that MessageCreate accepts organization_id for backward compatibility.
    """
    # Test that MessageCreate accepts organization_id without error
    message_create = MessageCreate(
        role=MessageRole.user,
        content="Test message",
        organization_id="some-org-id",  # This should be ignored
    )
    
    # Should not raise an error
    assert message_create.role == MessageRole.user
    assert message_create.content == "Test message"
    
    # Verify organization_id is not in the dumped data when to_orm=True
    dumped = message_create.model_dump(to_orm=True)
    assert "organization_id" not in dumped


@pytest.mark.asyncio
async def test_async_message_flow_with_organization_id(server: SyncServer, default_user, test_agents):
    """
    Test the actual async message flow with organization_id to reproduce the real-world error.
    """
    agent1, agent2 = test_agents
    
    # Mock the tool executor to intercept the message processing
    from letta.services.tool_executor.multi_agent_tool_executor import LettaMultiAgentToolExecutor
    
    with patch.object(LettaMultiAgentToolExecutor, '_process_agent') as mock_process:
        # Create a mock that simulates SDK sending message with organization_id
        async def mock_process_with_org_id(agent_id: str, message: str):
            # Simulate the SDK creating a message with organization_id
            message_with_org_id = {
                "role": MessageRole.system,
                "content": [{"type": "text", "text": message}],
                "organization_id": default_user.organization_id,
                "agent_id": agent_id,
            }
            
            # This would normally be where the error occurs
            # when marshmallow tries to deserialize the message
            schema = SerializedMessageSchema(actor=default_user)
            
            try:
                # This should fail with current implementation
                schema.load(message_with_org_id)
                return {"agent_id": agent_id, "response": ["Message processed"]}
            except ValidationError as e:
                return {"agent_id": agent_id, "error": str(e), "type": "ValidationError"}
        
        mock_process.side_effect = mock_process_with_org_id
        
        # Create the tool executor
        executor = LettaMultiAgentToolExecutor(
            agent_manager=server.agent_manager,
            message_manager=server.message_manager,
            block_manager=server.block_manager,
            job_manager=server.job_manager,
            passage_manager=server.passage_manager,
            actor=default_user,
        )
        
        # Send async message from agent1 to agent2
        result = await executor.send_message_to_agent_async(
            agent_state=agent1,
            message="Hello from agent1",
            other_agent_id=agent2.id,
        )
        
        assert result == "Successfully sent message"
        
        # Wait for async processing
        import asyncio
        await asyncio.sleep(0.5)
        
        # Verify the mock was called
        mock_process.assert_called_once()
        
        # Check the result - it should have failed with ValidationError
        call_result = await mock_process.return_value
        assert "error" in call_result
        assert call_result["type"] == "ValidationError"


@pytest.mark.asyncio
async def test_fix_marshmallow_schema_organization_id():
    """
    Test the proposed fix for marshmallow schema to handle organization_id.
    """
    # Create a mock user
    mock_user = Mock(spec=User)
    mock_user.id = "user-123"
    mock_user.organization_id = "org-456"
    
    # Test data with organization_id
    message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": "system",
        "content": [{"type": "text", "text": "Test message"}],
        "agent_id": "agent-789",
        "organization_id": "org-456",  # Extra field that should be ignored
        "created_at": "2025-01-28T12:00:00Z",
        "_created_by_id": "user-123",
        "_last_updated_by_id": "user-123",
    }
    
    # Create a patched version of SerializedMessageSchema with the fix
    class FixedSerializedMessageSchema(SerializedMessageSchema):
        class Meta(SerializedMessageSchema.Meta):
            unknown = "exclude"  # This is the fix - ignore unknown fields
    
    # Test with the fixed schema
    fixed_schema = FixedSerializedMessageSchema(actor=mock_user)
    
    # This should now work without errors
    try:
        result = fixed_schema.load(message_data)
        # If we get here, the fix works
        assert True
    except ValidationError:
        pytest.fail("Fixed schema should have handled organization_id field")


@pytest.mark.asyncio 
async def test_message_pydantic_model_with_extra_fields():
    """
    Test that the Message Pydantic model can handle extra fields with the fix.
    """
    # Import the Message model
    from letta.schemas.message import Message
    from pydantic import ConfigDict
    
    # Create a modified Message class with the fix
    class FixedMessage(Message):
        model_config = ConfigDict(extra="ignore")  # Allow extra fields
    
    # Test creating a message with extra fields
    message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": MessageRole.system,
        "content": [TextContent(text="Test message")],
        "agent_id": "agent-123",
        "organization_id": "org-456",  # Extra field
        "some_other_field": "value",  # Another extra field
    }
    
    # This should work with the fixed model
    try:
        fixed_message = FixedMessage(**message_data)
        assert fixed_message.agent_id == "agent-123"
        assert fixed_message.role == MessageRole.system
        # Extra fields should be ignored
        assert not hasattr(fixed_message, "organization_id")
        assert not hasattr(fixed_message, "some_other_field")
    except Exception as e:
        pytest.fail(f"Fixed Message model should have handled extra fields: {e}")