# Multimodal Messages API Reference

This document provides detailed API reference for Letta's multimodal message system, including all classes, methods, and data structures.

## Table of Contents

- [Core Classes](#core-classes)
- [Content Types](#content-types)
- [Message Class](#message-class)
- [OpenAI Integration](#openai-integration)
- [Type Definitions](#type-definitions)
- [Validation Rules](#validation-rules)
- [Error Handling](#error-handling)

## Core Classes

### MessageContentType

Enumeration of all supported content types.

```python
class MessageContentType(str, Enum):
    text = "text"
    image = "image"  # NEW: Image content type
    tool_call = "tool_call"
    tool_return = "tool_return"
    reasoning = "reasoning"
    redacted_reasoning = "redacted_reasoning"
    omitted_reasoning = "omitted_reasoning"
```

### MessageContent

Base class for all message content types.

```python
class MessageContent(BaseModel):
    type: MessageContentType = Field(..., description="The type of the message.")
```

**Properties:**
- `type` (MessageContentType): Content type discriminator

## Content Types

### TextContent

Represents text content in messages.

```python
class TextContent(MessageContent):
    type: Literal[MessageContentType.text] = Field(
        MessageContentType.text, 
        description="The type of the message."
    )
    text: str = Field(..., description="The text content of the message.")
```

**Properties:**
- `type` (Literal["text"]): Always "text"
- `text` (str): The text content

**Example:**
```python
text_content = TextContent(text="Hello, world!")
```

### ImageContent

**NEW:** Represents image content in messages.

```python
class ImageContent(MessageContent):
    type: Literal[MessageContentType.image] = Field(
        MessageContentType.image, 
        description="The type of the message."
    )
    image_url: str = Field(
        ..., 
        description="The image URL or base64 data URL (e.g., 'data:image/jpeg;base64,...')."
    )
    detail: Optional[str] = Field(
        "auto", 
        description="Image detail level for vision models: 'low', 'high', or 'auto'."
    )
```

**Properties:**
- `type` (Literal["image"]): Always "image"
- `image_url` (str): Image URL or base64 data URL (**required**)
- `detail` (Optional[str]): Detail level, defaults to "auto"

**Valid Detail Levels:**
- `"low"` - Low resolution processing (faster, cheaper)
- `"high"` - High resolution processing (slower, more expensive)
- `"auto"` - Provider decides based on image characteristics

**Supported Image Formats:**
- JPEG (`image/jpeg`)
- PNG (`image/png`)
- GIF (`image/gif`)
- WebP (`image/webp`)

**URL Formats:**

1. **Base64 Data URL (Recommended):**
   ```python
   ImageContent(
       image_url="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA...",
       detail="high"
   )
   ```

2. **HTTP/HTTPS URL:**
   ```python
   ImageContent(
       image_url="https://example.com/image.jpg",
       detail="auto"
   )
   ```

**Example:**
```python
# Base64 encoded image
image_content = ImageContent(
    image_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    detail="high"
)

# HTTP URL
image_content = ImageContent(
    image_url="https://example.com/chart.png",
    detail="auto"
)
```

## Message Class

### Updated Message Schema

```python
class Message(BaseMessage):
    # Core fields
    role: MessageRole = Field(..., description="The role of the participant.")
    content: Optional[List[LettaMessageContentUnion]] = Field(
        None, 
        description="The content of the message."
    )
    
    # ... other fields remain unchanged
```

**Key Changes:**
- `content` is now a list of content objects instead of a string
- Supports multiple content types in a single message
- Maintains backwards compatibility with text-only messages

### Content Union Types

```python
# User message content (text + images)
LettaUserMessageContentUnion = Annotated[
    Union[TextContent, ImageContent],
    Field(discriminator="type")
]

# All message content types  
LettaMessageContentUnion = Annotated[
    Union[
        TextContent, 
        ImageContent,           # NEW
        ToolCallContent, 
        ToolReturnContent, 
        ReasoningContent, 
        RedactedReasoningContent, 
        OmittedReasoningContent
    ],
    Field(discriminator="type")
]
```

### Message Methods

#### Conversion Methods

##### `to_openai_dict()` → `dict`

Convert message to OpenAI Chat Completions format.

**Returns:**
- For single text content: `{"role": "user", "content": "text"}`
- For multimodal content: `{"role": "user", "content": [...]}`

**Example:**
```python
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="Describe this image:"),
        ImageContent(image_url="data:image/jpeg;base64,...", detail="high")
    ]
)

openai_dict = message.to_openai_dict()
# {
#   "role": "user",
#   "content": [
#     {"type": "text", "text": "Describe this image:"},
#     {
#       "type": "image_url",
#       "image_url": {
#         "url": "data:image/jpeg;base64,...",
#         "detail": "high"
#       }
#     }
#   ]
# }
```

##### `to_anthropic_dict()` → `dict`

Convert message to Anthropic Messages format.

**Returns:**
- For single text content: `{"role": "user", "content": "text"}`
- For multimodal content: `{"role": "user", "content": [...]}`

**Example:**
```python
anthropic_dict = message.to_anthropic_dict()
# {
#   "role": "user", 
#   "content": [
#     {"type": "text", "text": "Describe this image:"},
#     {
#       "type": "image",
#       "source": {
#         "type": "base64",
#         "media_type": "image/jpeg",
#         "data": "base64_data_without_prefix"
#       }
#     }
#   ]
# }
```

##### `to_google_ai_dict()` → `dict`

Convert message to Google AI format.

**Returns:**
- `{"role": "user", "parts": [...]}`

**Example:**
```python
google_dict = message.to_google_ai_dict()
# {
#   "role": "user",
#   "parts": [
#     {"text": "Describe this image:"},
#     {
#       "inline_data": {
#         "mime_type": "image/jpeg",
#         "data": "base64_data_without_prefix"
#       }
#     }
#   ]
# }
```

#### Parsing Methods

##### `dict_to_message(agent_id: str, openai_message_dict: dict)` → `Message`

**Static method** to parse OpenAI format into Message object.

**Parameters:**
- `agent_id` (str): Agent identifier
- `openai_message_dict` (dict): OpenAI message format

**Returns:**
- `Message`: Parsed message object

**Supported Input Formats:**

1. **String content:**
   ```python
   openai_dict = {
       "role": "user",
       "content": "Hello world"
   }
   message = Message.dict_to_message("agent-123", openai_dict)
   ```

2. **Multimodal content array:**
   ```python
   openai_dict = {
       "role": "user",
       "content": [
           {"type": "text", "text": "What's in this image?"},
           {
               "type": "image_url",
               "image_url": {
                   "url": "data:image/jpeg;base64,...",
                   "detail": "high"
               }
           }
       ]
   }
   message = Message.dict_to_message("agent-123", openai_dict)
   ```

3. **String image URL format:**
   ```python
   openai_dict = {
       "role": "user", 
       "content": [
           {"type": "text", "text": "Analyze this"},
           {
               "type": "image_url",
               "image_url": "https://example.com/image.jpg"  # String format
           }
       ]
   }
   message = Message.dict_to_message("agent-123", openai_dict)
   ```

**Error Handling:**
- Invalid content types are skipped with warning
- Malformed image URLs result in validation errors
- Missing required fields raise `ValueError`

## OpenAI Integration

### Chat Completion Request Schema

Updated OpenAI-compatible request schemas with multimodal support.

#### Content Part Types

```python
class TextContentPart(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ImageUrlContentPart(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: Union[str, Dict[str, Any]]

ContentPart = Union[TextContentPart, ImageUrlContentPart]
```

#### Message Types

```python
class UserMessage(BaseModel):
    content: Union[str, List[ContentPart]]  # NEW: Supports multimodal content
    role: str = "user"
    name: Optional[str] = None

class AssistantMessage(BaseModel):
    content: Optional[Union[str, List[ContentPart]]] = None  # NEW: Multimodal support
    role: str = "assistant"
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
```

### Chat Completion Examples

#### Text-only Request (Backwards Compatible)

```python
{
    "model": "gpt-4o",
    "messages": [
        {
            "role": "user",
            "content": "Hello, how are you?"
        }
    ]
}
```

#### Multimodal Request

```python
{
    "model": "gpt-4o", 
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What's happening in this image?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,/9j/4AAQ...",
                        "detail": "high"
                    }
                }
            ]
        }
    ]
}
```

## Type Definitions

### Union Types

```python
from typing import Union, List, Literal, Optional
from pydantic import BaseModel, Field
```

### Content Discriminated Union

```python
LettaMessageContentUnion = Annotated[
    Union[
        TextContent,
        ImageContent,
        ToolCallContent,
        ToolReturnContent, 
        ReasoningContent,
        RedactedReasoningContent,
        OmittedReasoningContent
    ],
    Field(discriminator="type")
]
```

The discriminator ensures proper type resolution based on the `type` field.

### JSON Schema Generation

```python
def create_letta_message_content_union_schema():
    return {
        "oneOf": [
            {"$ref": "#/components/schemas/TextContent"},
            {"$ref": "#/components/schemas/ImageContent"},  # NEW
            {"$ref": "#/components/schemas/ToolCallContent"},
            {"$ref": "#/components/schemas/ToolReturnContent"},
            {"$ref": "#/components/schemas/ReasoningContent"},
            {"$ref": "#/components/schemas/RedactedReasoningContent"},
            {"$ref": "#/components/schemas/OmittedReasoningContent"},
        ],
        "discriminator": {
            "propertyName": "type",
            "mapping": {
                "text": "#/components/schemas/TextContent",
                "image": "#/components/schemas/ImageContent",  # NEW
                "tool_call": "#/components/schemas/ToolCallContent",
                "tool_return": "#/components/schemas/ToolReturnContent",
                "reasoning": "#/components/schemas/ReasoningContent",
                "redacted_reasoning": "#/components/schemas/RedactedReasoningContent",
                "omitted_reasoning": "#/components/schemas/OmittedReasoningContent",
            },
        },
    }
```

## Validation Rules

### ImageContent Validation

```python
from pydantic import field_validator
import re

class ImageContent(MessageContent):
    # ... field definitions ...
    
    @field_validator('image_url')
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        """Validate image URL format"""
        if not v:
            raise ValueError("image_url cannot be empty")
        
        # Check for data URL format
        data_url_pattern = r'^data:image/(jpeg|jpg|png|gif|webp);base64,[A-Za-z0-9+/=]+$'
        if v.startswith('data:'):
            if not re.match(data_url_pattern, v):
                raise ValueError("Invalid data URL format")
        # Check for HTTP(S) URL format  
        elif v.startswith(('http://', 'https://')):
            # Basic URL validation
            if not re.match(r'^https?://.+\..+', v):
                raise ValueError("Invalid HTTP URL format")
        else:
            raise ValueError("image_url must be data URL or HTTP(S) URL")
        
        return v
    
    @field_validator('detail')
    @classmethod
    def validate_detail(cls, v: Optional[str]) -> str:
        """Validate detail level"""
        if v is None:
            return "auto"
        
        valid_details = ["low", "high", "auto"]
        if v not in valid_details:
            # Allow custom detail levels but warn
            import warnings
            warnings.warn(f"Non-standard detail level: {v}")
        
        return v
```

### Message Content Validation

```python
class Message(BaseMessage):
    # ... field definitions ...
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: Optional[List[LettaMessageContentUnion]]) -> Optional[List[LettaMessageContentUnion]]:
        """Validate message content"""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("content must be a list")
        
        # Check for at least one content item for user messages
        if len(v) == 0:
            import warnings
            warnings.warn("Empty content list may cause issues with some providers")
        
        # Validate image count for specific providers
        image_count = sum(1 for item in v if isinstance(item, ImageContent))
        if image_count > 20:  # OpenAI limit
            warnings.warn(f"High image count ({image_count}) may exceed provider limits")
        
        return v
```

## Error Handling

### Custom Exceptions

```python
class MultimodalError(Exception):
    """Base exception for multimodal message errors"""
    pass

class ImageValidationError(MultimodalError):
    """Raised when image content validation fails"""
    pass

class ProviderNotSupportedError(MultimodalError):
    """Raised when provider doesn't support multimodal content"""
    pass

class ImageSizeLimitError(MultimodalError):
    """Raised when image exceeds size limits"""
    pass
```

### Error Examples

```python
try:
    # Invalid image URL
    ImageContent(image_url="not-a-valid-url")
except ValueError as e:
    print(f"Validation error: {e}")

try:
    # Empty content for user message
    message = Message(role=MessageRole.user, content=[])
    openai_dict = message.to_openai_dict()
except AssertionError as e:
    print(f"Conversion error: {e}")

try:
    # Malformed OpenAI message
    Message.dict_to_message("agent-123", {"role": "user", "content": None})
except ValueError as e:
    print(f"Parsing error: {e}")
```

### Validation Helper Functions

```python
def validate_multimodal_message(message: Message) -> List[str]:
    """Validate multimodal message and return warnings"""
    warnings = []
    
    if not message.content:
        warnings.append("Message has no content")
        return warnings
    
    text_count = sum(1 for c in message.content if isinstance(c, TextContent))
    image_count = sum(1 for c in message.content if isinstance(c, ImageContent))
    
    if text_count == 0 and image_count > 0:
        warnings.append("Image-only message may not work with all providers")
    
    if image_count > 10:
        warnings.append(f"High image count ({image_count}) may impact performance")
    
    # Check image sizes (if base64)
    for content in message.content:
        if isinstance(content, ImageContent) and content.image_url.startswith('data:'):
            # Estimate size from base64 length
            base64_part = content.image_url.split(',')[1]
            estimated_size = len(base64_part) * 3 / 4  # Base64 overhead
            if estimated_size > 20 * 1024 * 1024:  # 20MB
                warnings.append(f"Large image detected (est. {estimated_size/1024/1024:.1f}MB)")
    
    return warnings

# Usage
message = Message(role=MessageRole.user, content=[...])
warnings = validate_multimodal_message(message)
for warning in warnings:
    print(f"Warning: {warning}")
```

### Provider Compatibility Checks

```python
def check_provider_compatibility(message: Message, provider: str) -> bool:
    """Check if message is compatible with specific provider"""
    if not message.content:
        return True
    
    image_count = sum(1 for c in message.content if isinstance(c, ImageContent))
    
    if provider.lower() == "openai":
        return image_count <= 20
    elif provider.lower() == "anthropic":
        return image_count <= 5
    elif provider.lower() == "google":
        return image_count <= 30
    else:
        return image_count == 0  # Conservative default

# Usage
if not check_provider_compatibility(message, "anthropic"):
    raise ProviderNotSupportedError("Too many images for Anthropic")
```

---

## Summary

The multimodal message API extends Letta's message system with:

✅ **ImageContent class** for representing images  
✅ **Enhanced Message class** supporting mixed content  
✅ **Provider-specific conversion** methods  
✅ **Comprehensive validation** and error handling  
✅ **Backwards compatibility** with existing text messages  
✅ **Type-safe discriminated unions** for content types  

The API is designed to be intuitive, type-safe, and compatible with existing Letta workflows while enabling powerful new multimodal AI capabilities.