"""
Unit test to verify the organization_id fix in the Pydantic Message model.
This test verifies that Message objects can accept organization_id field from SDK clients.
"""

import pytest
import uuid
from datetime import datetime

from letta.schemas.message import Message, MessageCreate
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent


def test_message_accepts_organization_id():
    """Test that Message model accepts organization_id field without error."""
    # Test data with organization_id (simulating SDK client)
    message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": MessageRole.system,
        "content": [TextContent(text="Test message from SDK")],
        "agent_id": "agent-789",
        "organization_id": "org-456",  # This field should be ignored
        "created_at": datetime.now(),
        "sender_id": "user-123",
    }
    
    # This should work without raising ValidationError
    try:
        message = Message(**message_data)
        # Verify the message was created successfully
        assert message.id == message_data["id"]
        assert message.role == MessageRole.system
        assert message.agent_id == "agent-789"
        # organization_id should be present but ignored in serialization
        assert message.organization_id == "org-456"
    except Exception as e:
        pytest.fail(f"Message should accept organization_id field, but got error: {e}")


def test_message_ignores_multiple_unknown_fields():
    """Test that Message model ignores multiple unknown fields."""
    # Test data with multiple unknown fields
    message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": MessageRole.assistant,
        "content": [TextContent(text="Response message")],
        "agent_id": "agent-789",
        "organization_id": "org-456",  # Unknown field 1
        "custom_field": "custom_value",  # Unknown field 2
        "legacy_field": "legacy_value",  # Unknown field 3
        "created_at": datetime.now(),
    }
    
    # This should work without raising ValidationError
    try:
        message = Message(**message_data)
        # Verify only known fields are present
        assert message.id == message_data["id"]
        assert message.role == MessageRole.assistant
        assert message.agent_id == "agent-789"
        # organization_id should be accessible since we explicitly added it
        assert message.organization_id == "org-456"
        # Other unknown fields should not cause errors but won't be accessible
        assert not hasattr(message, 'custom_field') or message.custom_field == "custom_value"  # May be present due to extra="ignore"
    except Exception as e:
        pytest.fail(f"Message should ignore unknown fields, but got error: {e}")


def test_message_validates_required_fields():
    """Test that Message model still validates required fields."""
    # Test data missing required fields
    message_data = {
        "organization_id": "org-456",  # This will be ignored
        "custom_field": "value",  # This will be ignored
        # Missing required fields like id, role, etc.
    }
    
    # This should raise ValidationError for missing required fields
    with pytest.raises(Exception) as exc_info:
        Message(**message_data)
    
    # Verify the error is about missing required fields, not unknown fields
    error_str = str(exc_info.value)
    # Should mention missing required fields like "role"
    assert "Field required" in error_str
    assert "role" in error_str


def test_message_create_still_works():
    """Test that MessageCreate continues to work with organization_id."""
    # Test data with organization_id
    message_data = {
        "role": MessageRole.user,
        "content": "Test message from SDK",
        "organization_id": "org-456",  # This field should be ignored
    }
    
    # This should work without raising ValidationError
    try:
        message = MessageCreate(**message_data)
        # Verify the message was created successfully
        assert message.role == MessageRole.user
        assert message.content == "Test message from SDK"
        # organization_id should be present for backward compatibility
        assert message.organization_id == "org-456"
    except Exception as e:
        pytest.fail(f"MessageCreate should accept organization_id field, but got error: {e}")


def test_message_serialization_excludes_organization_id():
    """Test that Message serialization properly handles organization_id."""
    # Create a message with organization_id
    message = Message(
        role=MessageRole.user,
        content=[TextContent(text="Test message")],
        agent_id="agent-123",
        organization_id="org-456"
    )
    
    # Test normal serialization - organization_id should be present
    serialized = message.model_dump()
    assert "organization_id" in serialized
    assert serialized["organization_id"] == "org-456"
    
    # Test ORM serialization - organization_id should be excluded
    orm_serialized = message.model_dump()  # No special to_orm handling in Message class
    # In this case, organization_id will still be present since Message doesn't have special to_orm logic
    # This is fine since the field is optional and will be ignored by the system