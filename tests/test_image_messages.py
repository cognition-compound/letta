"""
Tests for image message functionality in Letta

This test suite covers:
- ImageContent class creation and validation
- Multimodal message parsing from OpenAI format
- Message conversion to OpenAI, Anthropic, and Google AI formats
- Message block integration for preserving image content
- Edge cases and error handling
"""

from datetime import datetime, timezone
from typing import List
from uuid import uuid4

import pytest

from letta.schemas.enums import MessageRole
from letta.schemas.letta_message import UserMessage
from letta.schemas.letta_message_content import (
    ImageContent,
    LettaMessageContentUnion,
    LettaUserMessageContentUnion,
    MessageContentType,
    TextContent,
)
from letta.schemas.message import Message
from letta.schemas.openai.chat_completion_request import ContentPart, ImageUrlContentPart, TextContentPart
from letta.schemas.openai.chat_completion_request import UserMessage as OpenAIUserMessage


class TestImageContent:
    """Test the ImageContent class and its properties"""

    def test_create_image_content_with_base64_url(self):
        """Test creating ImageContent with base64 data URL"""
        base64_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD..."
        img_content = ImageContent(image_url=base64_url, detail="high")

        assert img_content.type == MessageContentType.image
        assert img_content.image_url == base64_url
        assert img_content.detail == "high"

    def test_create_image_content_with_http_url(self):
        """Test creating ImageContent with HTTP URL"""
        http_url = "https://example.com/image.jpg"
        img_content = ImageContent(image_url=http_url)

        assert img_content.type == MessageContentType.image
        assert img_content.image_url == http_url
        assert img_content.detail == "auto"  # default value

    def test_create_image_content_with_detail_levels(self):
        """Test creating ImageContent with different detail levels"""
        url = "https://example.com/image.jpg"

        for detail in ["low", "high", "auto"]:
            img_content = ImageContent(image_url=url, detail=detail)
            assert img_content.detail == detail

    def test_image_content_type_discriminator(self):
        """Test that ImageContent has correct type for discriminator"""
        img_content = ImageContent(image_url="test.jpg")
        assert img_content.type.value == "image"

    def test_image_content_in_union_types(self):
        """Test that ImageContent works in union types"""
        img_content = ImageContent(image_url="test.jpg")
        text_content = TextContent(text="Hello")

        # Test in user message content union
        user_contents: List[LettaUserMessageContentUnion] = [text_content, img_content]
        assert len(user_contents) == 2

        # Test in general message content union
        general_contents: List[LettaMessageContentUnion] = [text_content, img_content]
        assert len(general_contents) == 2


class TestMultimodalMessageCreation:
    """Test creating messages with both text and image content"""

    def test_create_user_message_with_text_and_image(self):
        """Test creating a user message with both text and image"""
        message = Message(
            role=MessageRole.user,
            content=[
                TextContent(text="Can you describe this image?"),
                ImageContent(image_url="data:image/jpeg;base64,abc123", detail="high"),
            ],
        )

        assert message.role == MessageRole.user
        assert len(message.content) == 2
        assert isinstance(message.content[0], TextContent)
        assert isinstance(message.content[1], ImageContent)
        assert message.content[0].text == "Can you describe this image?"
        assert message.content[1].image_url == "data:image/jpeg;base64,abc123"

    def test_create_message_with_multiple_images(self):
        """Test creating a message with multiple images"""
        message = Message(
            role=MessageRole.user,
            content=[
                TextContent(text="Compare these images:"),
                ImageContent(image_url="data:image/jpeg;base64,img1", detail="high"),
                ImageContent(image_url="data:image/jpeg;base64,img2", detail="low"),
            ],
        )

        assert len(message.content) == 3
        assert isinstance(message.content[0], TextContent)
        assert isinstance(message.content[1], ImageContent)
        assert isinstance(message.content[2], ImageContent)
        assert message.content[1].detail == "high"
        assert message.content[2].detail == "low"

    def test_create_message_with_only_image(self):
        """Test creating a message with only image content"""
        message = Message(
            role=MessageRole.user,
            content=[ImageContent(image_url="https://example.com/image.jpg")],
        )

        assert len(message.content) == 1
        assert isinstance(message.content[0], ImageContent)


class TestOpenAIFormatParsing:
    """Test parsing messages from OpenAI format"""

    def test_parse_openai_multimodal_message(self):
        """Test parsing OpenAI multimodal message format"""
        openai_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,xyz789", "detail": "low"}},
            ],
        }

        message = Message.dict_to_message("test-agent", openai_msg)

        assert message.role == MessageRole.user
        assert len(message.content) == 2

        # Check text content
        text_content = message.content[0]
        assert isinstance(text_content, TextContent)
        assert text_content.text == "What's in this image?"

        # Check image content
        img_content = message.content[1]
        assert isinstance(img_content, ImageContent)
        assert img_content.image_url == "data:image/jpeg;base64,xyz789"
        assert img_content.detail == "low"

    def test_parse_openai_string_image_url(self):
        """Test parsing OpenAI message with string image URL"""
        openai_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this"},
                {"type": "image_url", "image_url": "https://example.com/image.jpg"},  # String format
            ],
        }

        message = Message.dict_to_message("test-agent", openai_msg)

        assert len(message.content) == 2
        img_content = message.content[1]
        assert isinstance(img_content, ImageContent)
        assert img_content.image_url == "https://example.com/image.jpg"
        assert img_content.detail == "auto"  # default when not specified

    def test_parse_openai_text_only_message(self):
        """Test parsing OpenAI text-only message still works"""
        openai_msg = {"role": "user", "content": "Hello, this is a text message"}

        message = Message.dict_to_message("test-agent", openai_msg)

        assert message.role == MessageRole.user
        assert len(message.content) == 1
        assert isinstance(message.content[0], TextContent)
        assert message.content[0].text == "Hello, this is a text message"


class TestOpenAIFormatConversion:
    """Test converting messages to OpenAI format"""

    def test_convert_multimodal_message_to_openai(self):
        """Test converting multimodal message to OpenAI format"""
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="Describe this image"), ImageContent(image_url="data:image/jpeg;base64,abc123", detail="high")],
        )

        openai_msg = message.to_openai_dict()

        assert openai_msg["role"] == "user"
        assert isinstance(openai_msg["content"], list)
        assert len(openai_msg["content"]) == 2

        # Check text part
        text_part = openai_msg["content"][0]
        assert text_part["type"] == "text"
        assert text_part["text"] == "Describe this image"

        # Check image part
        img_part = openai_msg["content"][1]
        assert img_part["type"] == "image_url"
        assert img_part["image_url"]["url"] == "data:image/jpeg;base64,abc123"
        assert img_part["image_url"]["detail"] == "high"

    def test_convert_text_only_message_to_openai(self):
        """Test converting text-only message to OpenAI format"""
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="Hello world")],
        )

        openai_msg = message.to_openai_dict()

        assert openai_msg["role"] == "user"
        assert isinstance(openai_msg["content"], str)
        assert openai_msg["content"] == "Hello world"

    def test_convert_assistant_multimodal_to_openai(self):
        """Test converting assistant message with images to OpenAI format"""
        message = Message(
            role=MessageRole.assistant,
            content=[TextContent(text="I can see the image shows"), ImageContent(image_url="data:image/jpeg;base64,response_img")],
        )

        openai_msg = message.to_openai_dict()

        assert openai_msg["role"] == "assistant"
        assert isinstance(openai_msg["content"], list)
        assert len(openai_msg["content"]) == 2


class TestAnthropicFormatConversion:
    """Test converting messages to Anthropic format"""

    def test_convert_multimodal_message_to_anthropic(self):
        """Test converting multimodal message to Anthropic format"""
        message = Message(
            role=MessageRole.user, content=[TextContent(text="Analyze this image"), ImageContent(image_url="data:image/jpeg;base64,abc123")]
        )

        anthropic_msg = message.to_anthropic_dict()

        assert anthropic_msg["role"] == "user"
        assert isinstance(anthropic_msg["content"], list)
        assert len(anthropic_msg["content"]) == 2

        # Check text part
        text_part = anthropic_msg["content"][0]
        assert text_part["type"] == "text"
        assert text_part["text"] == "Analyze this image"

        # Check image part
        img_part = anthropic_msg["content"][1]
        assert img_part["type"] == "image"
        assert img_part["source"]["type"] == "base64"
        assert img_part["source"]["data"] == "abc123"

    def test_convert_text_only_message_to_anthropic(self):
        """Test converting text-only message to Anthropic format"""
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="Hello Claude")],
        )

        anthropic_msg = message.to_anthropic_dict()

        assert anthropic_msg["role"] == "user"
        assert isinstance(anthropic_msg["content"], str)
        assert anthropic_msg["content"] == "Hello Claude"

    def test_convert_png_image_to_anthropic_with_correct_mime_type(self):
        """Test that Anthropic conversion correctly parses PNG MIME type from data URL"""
        message = Message(
            role=MessageRole.user, 
            content=[
                TextContent(text="Look at this PNG image"),
                ImageContent(image_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==")
            ]
        )

        anthropic_msg = message.to_anthropic_dict()
        
        assert len(anthropic_msg["content"]) == 2
        img_part = anthropic_msg["content"][1]
        assert img_part["type"] == "image"
        assert img_part["source"]["media_type"] == "image/png"  # Should correctly parse PNG
        assert img_part["source"]["data"] == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

    def test_convert_webp_image_to_anthropic_with_correct_mime_type(self):
        """Test that Anthropic conversion correctly parses WebP MIME type from data URL"""
        message = Message(
            role=MessageRole.user,
            content=[ImageContent(image_url="data:image/webp;base64,UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA")]
        )

        anthropic_msg = message.to_anthropic_dict()
        
        img_part = anthropic_msg["content"][0]
        assert img_part["source"]["media_type"] == "image/webp"  # Should correctly parse WebP


class TestGoogleAIFormatConversion:
    """Test converting messages to Google AI format"""

    def test_convert_multimodal_message_to_google_ai(self):
        """Test converting multimodal message to Google AI format"""
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="What do you see in this image?"), ImageContent(image_url="data:image/jpeg;base64,xyz789")],
        )

        google_msg = message.to_google_ai_dict()

        assert google_msg["role"] == "user"
        assert isinstance(google_msg["parts"], list)
        assert len(google_msg["parts"]) == 2

        # Check text part
        text_part = google_msg["parts"][0]
        assert "text" in text_part
        assert text_part["text"] == "What do you see in this image?"

        # Check image part
        img_part = google_msg["parts"][1]
        assert "inline_data" in img_part
        assert img_part["inline_data"]["mime_type"] == "image/jpeg"
        assert img_part["inline_data"]["data"] == "xyz789"

    def test_convert_image_url_to_google_ai_fallback(self):
        """Test converting HTTP image URL to Google AI format falls back to placeholder on failure"""
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="Check this image"), ImageContent(image_url="https://invalid-domain-that-should-not-exist.invalid/image.jpg")],
        )

        # Should fall back to text placeholder when fetch fails
        google_msg = message.to_google_ai_dict()

        img_part = google_msg["parts"][1]
        assert "text" in img_part
        assert "Failed to load image" in img_part["text"]
        
    def test_convert_unknown_scheme_to_google_ai(self):
        """Test converting unknown URL scheme to Google AI format creates placeholder"""
        message = Message(
            role=MessageRole.user,
            content=[ImageContent(image_url="ftp://example.com/image.jpg")],
        )

        google_msg = message.to_google_ai_dict()

        img_part = google_msg["parts"][0]
        assert "text" in img_part
        assert "Image: ftp://example.com/image.jpg" in img_part["text"]


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error scenarios"""

    def test_empty_image_url(self):
        """Test handling of empty image URL"""
        # Empty string is actually allowed by pydantic, just not very useful
        img_content = ImageContent(image_url="")
        assert img_content.image_url == ""

    def test_message_with_no_content(self):
        """Test message with empty content list"""
        message = Message(
            role=MessageRole.user,
            content=[],
        )

        # Should raise error for empty content in user messages
        with pytest.raises(AssertionError):
            message.to_openai_dict()

    def test_parse_openai_message_with_unknown_content_type(self):
        """Test parsing OpenAI message with unknown content type"""
        openai_msg = {
            "role": "user",
            "content": [{"type": "text", "text": "Hello"}, {"type": "unknown_type", "data": "some data"}],  # Unknown type
        }

        # Should skip unknown types and continue parsing
        message = Message.dict_to_message("test-agent", openai_msg)
        assert len(message.content) == 1  # Only text content should be parsed
        assert isinstance(message.content[0], TextContent)

    def test_image_content_with_invalid_detail_level(self):
        """Test ImageContent with custom detail level (should still work)"""
        img_content = ImageContent(image_url="test.jpg", detail="custom")  # Not in standard low/high/auto
        assert img_content.detail == "custom"

    def test_multimodal_message_text_extraction(self):
        """Test that multimodal messages handle text extraction for legacy code"""
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="Main text content"), ImageContent(image_url="test.jpg")],
        )

        # Test to_letta_messages conversion handles multimodal content
        letta_messages = message.to_letta_messages()
        assert len(letta_messages) > 0


class TestMessageBlockIntegration:
    """Test that multimodal messages work properly with message blocks."""

    def test_multimodal_message_to_letta_messages_preserves_images(self):
        """Test that converting multimodal Message to LettaMessage preserves image content."""
        # Create a multimodal message with text and image
        text_content = TextContent(text="Can you see this image?")
        image_content = ImageContent(
            image_url="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...",
            detail="high"
        )
        
        message = Message(
            id=uuid4(),
            role=MessageRole.user,
            content=[text_content, image_content],
            created_at=datetime.now(timezone.utc),
        )

        # Convert to LettaMessage format
        letta_messages = message.to_letta_messages()

        # Should have one UserMessage with preserved multimodal content
        assert len(letta_messages) == 1
        assert isinstance(letta_messages[0], UserMessage)
        
        # Content should be the original multimodal content, not just text
        assert letta_messages[0].content == [text_content, image_content]
        assert len(letta_messages[0].content) == 2
        
        # Check that both text and image are preserved
        assert isinstance(letta_messages[0].content[0], TextContent)
        assert isinstance(letta_messages[0].content[1], ImageContent)
        assert letta_messages[0].content[0].text == "Can you see this image?"
        assert letta_messages[0].content[1].image_url == "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ..."

    def test_image_only_message_to_letta_messages(self):
        """Test that image-only messages are properly converted."""
        # Create an image-only message
        image_content = ImageContent(
            image_url="https://example.com/image.jpg", detail="low"
        )
        
        message = Message(
            id=uuid4(),
            role=MessageRole.user,
            content=[image_content],
            created_at=datetime.now(timezone.utc),
        )

        # Convert to LettaMessage format
        letta_messages = message.to_letta_messages()

        # Should have one UserMessage with preserved image content
        assert len(letta_messages) == 1
        assert isinstance(letta_messages[0], UserMessage)
        
        # Content should be the original image content
        assert letta_messages[0].content == [image_content]
        assert len(letta_messages[0].content) == 1
        assert isinstance(letta_messages[0].content[0], ImageContent)
        assert letta_messages[0].content[0].image_url == "https://example.com/image.jpg"


class TestBackwardsCompatibility:
    """Test that existing functionality still works"""

    def test_text_only_messages_unchanged(self):
        """Test that existing text-only messages work exactly as before"""
        # Create old-style message
        message = Message(
            role=MessageRole.user,
            content=[TextContent(text="Hello world")],
        )

        # All format conversions should work as before
        openai_msg = message.to_openai_dict()
        anthropic_msg = message.to_anthropic_dict()
        google_msg = message.to_google_ai_dict()

        assert openai_msg["content"] == "Hello world"
        assert anthropic_msg["content"] == "Hello world"
        assert google_msg["parts"][0]["text"] == "Hello world"

    def test_parse_simple_openai_string_content(self):
        """Test parsing simple string content from OpenAI format"""
        openai_msg = {"role": "user", "content": "Simple text message"}

        message = Message.dict_to_message("test-agent", openai_msg)

        assert len(message.content) == 1
        assert isinstance(message.content[0], TextContent)
        assert message.content[0].text == "Simple text message"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
