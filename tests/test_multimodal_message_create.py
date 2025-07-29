"""Test multimodal message creation"""

import pytest
from letta.schemas.message import MessageCreate
from letta.schemas.enums import MessageRole


def test_string_content():
    """Test that simple string content still works"""
    message = MessageCreate(
        role=MessageRole.user,
        content="This is a simple text message"
    )
    assert message.content == "This is a simple text message"
    assert isinstance(message.content, str)


def test_multimodal_content():
    """Test that multimodal content with text and image works"""
    content = [
        {"type": "text", "text": "Can you see this image?"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "TEST_BASE64_DATA"
            }
        }
    ]
    
    message = MessageCreate(
        role=MessageRole.user,
        content=content
    )
    
    assert isinstance(message.content, list)
    assert len(message.content) == 2
    assert message.content[0].type.value == "text"
    assert message.content[0].text == "Can you see this image?"
    assert message.content[1].type.value == "image"
    assert message.content[1].source.type.value == "base64"
    assert message.content[1].source.media_type == "image/jpeg"


def test_multimodal_content_camelcase_error():
    """Test that using camelCase field names fails validation as expected"""
    content = [
        {"type": "text", "text": "Can you see this image?"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "mediaType": "image/jpeg",  # Wrong field name
                "data": "TEST_BASE64_DATA"
            }
        }
    ]
    
    with pytest.raises(ValueError):
        MessageCreate(
            role=MessageRole.user,
            content=content
        )


def test_multiple_images():
    """Test that multiple images in one message work"""
    content = [
        {"type": "text", "text": "Here are two images:"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "IMAGE1_BASE64"
            }
        },
        {"type": "text", "text": "And the second one:"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "IMAGE2_BASE64"
            }
        }
    ]
    
    message = MessageCreate(
        role=MessageRole.user,
        content=content
    )
    
    assert isinstance(message.content, list)
    assert len(message.content) == 4
    assert sum(1 for part in message.content if part.type.value == "image") == 2
    assert sum(1 for part in message.content if part.type.value == "text") == 2