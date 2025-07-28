"""
Unit test to verify the organization_id fix in marshmallow schema.
This test can be run without docker/postgres.
"""

import pytest
from unittest.mock import Mock
import uuid

from letta.schemas.user import User
from letta.serialize_schemas.marshmallow_message import SerializedMessageSchema
from marshmallow import ValidationError


def test_marshmallow_ignores_organization_id():
    """Test that SerializedMessageSchema ignores organization_id field."""
    # Create a mock user
    mock_user = Mock(spec=User)
    mock_user.id = "user-123"
    mock_user.organization_id = "org-456"
    
    # Create schema instance
    schema = SerializedMessageSchema(actor=mock_user)
    
    # Test data with organization_id (simulating SDK client)
    message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": "system",
        "content": [{"type": "text", "text": "Test message from SDK"}],
        "agent_id": "agent-789",
        "organization_id": "org-456",  # This field should be ignored
        "created_at": "2025-01-28T12:00:00Z",
        "_created_by_id": "user-123",
        "_last_updated_by_id": "user-123",
        "organization": "org-456",  # This is excluded in Meta
    }
    
    # This should work without raising ValidationError
    try:
        result = schema.load(message_data)
        # Verify the message was loaded successfully
        assert hasattr(result, 'id')
        assert hasattr(result, 'role')
        assert hasattr(result, 'agent_id')
        # organization_id should not be in the loaded object
        assert not hasattr(result, 'organization_id')
    except ValidationError as e:
        pytest.fail(f"Schema should ignore organization_id field, but got error: {e}")


def test_marshmallow_ignores_multiple_unknown_fields():
    """Test that SerializedMessageSchema ignores multiple unknown fields."""
    # Create a mock user
    mock_user = Mock(spec=User)
    mock_user.id = "user-123"
    mock_user.organization_id = "org-456"
    
    # Create schema instance
    schema = SerializedMessageSchema(actor=mock_user)
    
    # Test data with multiple unknown fields
    message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": "assistant",
        "content": [{"type": "text", "text": "Response message"}],
        "agent_id": "agent-789",
        "organization_id": "org-456",  # Unknown field 1
        "custom_field": "custom_value",  # Unknown field 2
        "legacy_field": "legacy_value",  # Unknown field 3
        "created_at": "2025-01-28T12:00:00Z",
        "_created_by_id": "user-123",
        "_last_updated_by_id": "user-123",
    }
    
    # This should work without raising ValidationError
    try:
        result = schema.load(message_data)
        # Verify only known fields are loaded
        assert hasattr(result, 'id')
        assert hasattr(result, 'role')
        assert hasattr(result, 'agent_id')
        # Unknown fields should not be present
        assert not hasattr(result, 'organization_id')
        assert not hasattr(result, 'custom_field')
        assert not hasattr(result, 'legacy_field')
    except ValidationError as e:
        pytest.fail(f"Schema should ignore unknown fields, but got error: {e}")


def test_marshmallow_validates_required_fields():
    """Test that SerializedMessageSchema still validates required fields."""
    # Create a mock user
    mock_user = Mock(spec=User)
    mock_user.id = "user-123"
    mock_user.organization_id = "org-456"
    
    # Create schema instance
    schema = SerializedMessageSchema(actor=mock_user)
    
    # Test data missing required fields
    message_data = {
        "organization_id": "org-456",  # This will be ignored
        "custom_field": "value",  # This will be ignored
        # Missing required fields like id, role, etc.
    }
    
    # This should raise ValidationError for missing required fields
    with pytest.raises(ValidationError) as exc_info:
        schema.load(message_data)
    
    # Verify the error is about missing required fields, not unknown fields
    error_dict = exc_info.value.messages
    assert "id" in error_dict or "_schema" in error_dict
    # organization_id should not be in the error messages
    assert "organization_id" not in str(error_dict)