"""
Test to verify that the Message model can handle internal organization_id assignment.
This reproduces the exact scenario that was causing the error in production.
"""

import pytest
import uuid
from unittest.mock import Mock

from letta.schemas.message import Message, MessageCreate
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.schemas.user import User
from letta.agents.helpers import create_input_messages


def test_internal_organization_id_assignment():
    """
    Test the exact scenario from letta/agents/helpers.py:280 where organization_id is assigned:
    
    for message in messages:
        message.organization_id = actor.organization_id
    """
    # Create a Message like convert_message_creates_to_messages would
    message = Message(
        role=MessageRole.user,
        content=[TextContent(text="Test message")],
        agent_id="agent-123"
    )
    
    # Simulate the assignment that happens in create_input_messages
    # This is the line that was causing the error before the fix
    message.organization_id = "org-456"
    
    # This should work now with our fix
    assert message.organization_id == "org-456"
    assert message.role == MessageRole.user
    assert message.agent_id == "agent-123"
    
    # Test serialization/deserialization (what happens in async processing)
    serialized = message.model_dump()
    assert "organization_id" in serialized
    assert serialized["organization_id"] == "org-456"
    
    # Deserialize (this was failing before the fix)
    deserialized = Message(**serialized)
    assert deserialized.organization_id == "org-456"
    assert deserialized.role == MessageRole.user
    assert deserialized.agent_id == "agent-123"
    
    print("✅ Internal organization_id assignment and serialization works")


def test_create_input_messages_with_organization_id():
    """
    Test the actual create_input_messages function that assigns organization_id.
    """
    # Create test data
    input_messages = [
        MessageCreate(
            role=MessageRole.user,
            content="Test message from user"
        )
    ]
    
    # Create a mock actor with organization_id
    mock_actor = Mock(spec=User)
    mock_actor.organization_id = "org-789"
    
    # This should not fail anymore
    try:
        result_messages = create_input_messages(
            input_messages=input_messages,
            agent_id="agent-456",
            timezone="UTC",
            actor=mock_actor
        )
        
        # Verify the organization_id was assigned
        assert len(result_messages) == 1
        assert result_messages[0].organization_id == "org-789"
        assert result_messages[0].role == MessageRole.user
        
        print("✅ create_input_messages with organization_id assignment works")
        
    except Exception as e:
        pytest.fail(f"create_input_messages should handle organization_id assignment: {e}")


def test_message_serialization_in_async_context():
    """
    Test message serialization/deserialization that happens in async processing.
    """
    # Create a message with organization_id like the system does internally
    original_message = Message(
        role=MessageRole.system,
        content=[TextContent(text="System message")],
        agent_id="agent-789",
        organization_id="org-456"  # Assigned internally by the system
    )
    
    # Simulate what happens in async processing - messages get serialized and deserialized
    
    # Step 1: Serialize (like when storing in job queue or passing between processes)
    serialized_data = original_message.model_dump()
    
    # Step 2: Deserialize (like when processing async job)
    # This was failing before our fix
    try:
        restored_message = Message(**serialized_data)
        
        # Verify the message was restored correctly
        assert restored_message.organization_id == "org-456"
        assert restored_message.role == MessageRole.system
        assert restored_message.agent_id == "agent-789"
        
        print("✅ Message async serialization/deserialization works")
        
    except Exception as e:
        pytest.fail(f"Message async processing should work: {e}")


if __name__ == "__main__":
    test_internal_organization_id_assignment()
    test_create_input_messages_with_organization_id()
    test_message_serialization_in_async_context()
    print("🎉 All internal organization_id assignment tests passed!")