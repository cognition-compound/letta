"""
Test to verify SDK compatibility with organization_id field.
This test simulates the exact scenario described in the error message.
"""

import pytest
import uuid
from datetime import datetime

from letta.schemas.message import Message, MessageCreate
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent


def test_sdk_message_with_organization_id():
    """
    Test that simulates the exact SDK scenario causing the error:
    "Message" object has no field "organization_id"
    """
    # This simulates the exact data that an SDK client (like @letta-ai/letta-client@0.1.164) 
    # would send when creating an async message
    sdk_message_data = {
        "id": f"message-{uuid.uuid4()}",
        "role": MessageRole.system,
        "content": [{"type": "text", "text": "Test message from SDK"}],
        "agent_id": "agent-b37f29c9-a9ea-48a2-84d7-a8166cbcaa71",
        "organization_id": "org-456",  # This field was causing the error
        "created_at": datetime.now(),
        "_created_by_id": "user-123",
        "_last_updated_by_id": "user-123",
    }
    
    # Convert content to proper format
    sdk_message_data["content"] = [TextContent(text="Test message from SDK")]
    
    # Before the fix, this would raise:
    # ValueError: "Message" object has no field "organization_id"
    try:
        message = Message(**sdk_message_data)
        
        # Verify the message was created successfully
        assert message.id == sdk_message_data["id"]
        assert message.role == MessageRole.system
        assert message.agent_id == "agent-b37f29c9-a9ea-48a2-84d7-a8166cbcaa71"
        assert message.organization_id == "org-456"  # Should be accessible but ignored
        
        print("✅ SDK message with organization_id was accepted successfully")
        
    except Exception as e:
        pytest.fail(f"SDK message should be accepted, but got error: {e}")


def test_message_create_with_organization_id():
    """
    Test that MessageCreate (used in request bodies) accepts organization_id.
    """
    # This simulates data from a request body in the API
    request_data = {
        "role": MessageRole.user,
        "content": "Test message from SDK client",
        "organization_id": "org-456",  # SDK clients include this
        "sender_id": "user-123",
    }
    
    try:
        message_create = MessageCreate(**request_data)
        
        # Verify the message was created successfully
        assert message_create.role == MessageRole.user
        assert message_create.content == "Test message from SDK client"
        assert message_create.organization_id == "org-456"
        
        print("✅ MessageCreate with organization_id was accepted successfully")
        
    except Exception as e:
        pytest.fail(f"MessageCreate should accept organization_id, but got error: {e}")


def test_async_message_serialization():
    """
    Test that messages can be serialized/deserialized in async processing.
    """
    # Create a message like an SDK would
    original_data = {
        "role": MessageRole.user,
        "content": [TextContent(text="Async message test")],
        "agent_id": "agent-123",
        "organization_id": "org-456",  # From SDK
    }
    
    # Create the message
    message = Message(**original_data)
    
    # Serialize (like what happens in async processing)
    serialized = message.model_dump()
    
    # Deserialize (like what happens when processing the async job)
    deserialized = Message(**serialized)
    
    # Verify the round trip worked
    assert deserialized.role == MessageRole.user
    assert deserialized.agent_id == "agent-123"
    assert deserialized.organization_id == "org-456"
    
    print("✅ Async message serialization/deserialization works")


if __name__ == "__main__":
    test_sdk_message_with_organization_id()
    test_message_create_with_organization_id()
    test_async_message_serialization()
    print("🎉 All SDK compatibility tests passed!")