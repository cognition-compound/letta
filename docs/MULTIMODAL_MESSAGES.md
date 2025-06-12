# Multimodal Messages in Letta

This document describes Letta's support for multimodal messages, including images alongside text content. This feature enables agents to process and respond to visual information, unlocking new capabilities for computer vision, document analysis, and multimodal AI applications.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Message Format](#message-format)
- [Image Content Types](#image-content-types)
- [API Reference](#api-reference)
- [Provider Support](#provider-support)
- [Code Examples](#code-examples)
- [Migration Guide](#migration-guide)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

Letta now supports multimodal messages that can contain both text and images. This allows agents to:

- **Analyze images** sent by users
- **Process visual documents** like charts, diagrams, and screenshots
- **Understand multimodal content** with context from both text and images
- **Generate responses** based on visual input

### Key Features

✅ **Multiple image formats** - JPEG, PNG, GIF, WebP support  
✅ **Base64 and URL** - Support for both base64 data URLs and HTTP(S) image URLs  
✅ **Detail levels** - Control image processing fidelity (low/high/auto)  
✅ **Provider compatibility** - Works with OpenAI, Anthropic, and Google AI  
✅ **Backwards compatibility** - Existing text-only messages continue to work  
✅ **Comprehensive testing** - Full test suite ensures reliability  

## Quick Start

### 1. Basic Image Message

```python
from letta.schemas.letta_message_content import TextContent, ImageContent
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole

# Create a message with text and image
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="Can you describe what you see in this image?"),
        ImageContent(
            image_url="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD...",
            detail="high"
        )
    ]
)
```

### 2. Using with Letta Client

```python
from letta_client import MessageCreate
from letta.schemas.letta_message_content import TextContent, ImageContent

# Send multimodal message to agent
response = client.agents.messages.create(
    agent_id=agent.id,
    messages=[MessageCreate(
        role="user",
        content=[
            TextContent(text="Analyze this chart and summarize the trends"),
            ImageContent(image_url="https://example.com/chart.png")
        ]
    )]
)
```

### 3. Multiple Images

```python
# Message with multiple images for comparison
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="Compare these two product images:"),
        ImageContent(image_url="data:image/jpeg;base64,product1_data...", detail="high"),
        ImageContent(image_url="data:image/jpeg;base64,product2_data...", detail="high")
    ]
)
```

## Message Format

### Content Structure

Multimodal messages use a **content array** instead of a simple string:

```python
# Old format (still supported)
message = Message(
    role=MessageRole.user,
    content=[TextContent(text="Hello world")]
)

# New multimodal format
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="Look at this image:"),
        ImageContent(image_url="...", detail="auto")
    ]
)
```

### Content Types

| Type | Purpose | Fields |
|------|---------|--------|
| `TextContent` | Text messages | `text: str` |
| `ImageContent` | Images | `image_url: str`, `detail: str` |
| `ToolCallContent` | Tool calls | `id: str`, `name: str`, `input: dict` |
| `ToolReturnContent` | Tool results | `tool_call_id: str`, `content: str`, `is_error: bool` |

### JSON Schema

```json
{
  "content": [
    {
      "type": "text",
      "text": "Describe this image:"
    },
    {
      "type": "image",
      "image_url": "data:image/jpeg;base64,/9j/4AAQ...",
      "detail": "high"
    }
  ]
}
```

## Image Content Types

### Supported Image Formats

- **JPEG** (`.jpg`, `.jpeg`) - Most common, good compression
- **PNG** (`.png`) - Lossless, supports transparency  
- **GIF** (`.gif`) - Animated images (first frame used)
- **WebP** (`.webp`) - Modern format with excellent compression

### Image URL Formats

#### 1. Base64 Data URLs ⭐ Recommended

```python
ImageContent(
    image_url="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD...",
    detail="high"
)
```

**Advantages:**
- No external dependencies
- Works offline
- Guaranteed availability
- No CORS issues

#### 2. HTTP/HTTPS URLs

```python
ImageContent(
    image_url="https://example.com/images/chart.png",
    detail="auto"
)
```

**Considerations:**
- Must be publicly accessible
- Subject to rate limiting
- May require authentication headers
- Network dependent

### Detail Levels

Control image processing quality and cost:

| Detail | Use Case | Processing | Cost |
|--------|----------|------------|------|
| `"low"` | Simple images, OCR | Low resolution | Lower |
| `"high"` | Complex images, charts | High resolution | Higher |
| `"auto"` | Automatic selection | Provider decides | Variable |

```python
# For detailed analysis
ImageContent(image_url="...", detail="high")

# For basic recognition  
ImageContent(image_url="...", detail="low")

# Let the provider decide
ImageContent(image_url="...", detail="auto")  # Default
```

## API Reference

### ImageContent Class

```python
class ImageContent(MessageContent):
    type: Literal["image"] = "image"
    image_url: str  # Required: Image URL or base64 data URL
    detail: Optional[str] = "auto"  # Optional: "low", "high", or "auto"
```

#### Properties

- **`type`** - Always `"image"` for type discrimination
- **`image_url`** - Image URL or base64 data URL (required)
- **`detail`** - Processing detail level (optional, default: `"auto"`)

#### Methods

Inherits from `MessageContent` base class:

- **`model_dump()`** - Serialize to dictionary
- **`model_validate()`** - Create from dictionary

### Message Class Updates

#### New Multimodal Support

```python
class Message(BaseMessage):
    content: Optional[List[LettaMessageContentUnion]] = None
    # ... other fields
```

#### Conversion Methods

- **`to_openai_dict()`** - Convert to OpenAI Chat Completions format
- **`to_anthropic_dict()`** - Convert to Anthropic Messages format  
- **`to_google_ai_dict()`** - Convert to Google AI format
- **`dict_to_message()`** - Parse from OpenAI format

## Provider Support

### OpenAI GPT-4 Vision Models

**Supported Models:**
- `gpt-4o`
- `gpt-4o-mini` 
- `gpt-4-vision-preview`

**Format:**
```json
{
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
```

**Limitations:**
- Max 20 images per message
- 20MB total size limit
- Base64 encoding adds ~33% size overhead

### Anthropic Claude Vision Models

**Supported Models:**
- `claude-3-5-sonnet`
- `claude-3-5-haiku`
- `claude-3-opus`

**Format:**
```json
{
  "role": "user", 
  "content": [
    {"type": "text", "text": "Analyze this image"},
    {
      "type": "image",
      "source": {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": "base64_image_data"
      }
    }
  ]
}
```

**Limitations:**
- Base64 data URLs only (HTTP URLs not supported)
- Max 5 images per message
- 100MB total size limit

### Google AI Gemini Models

**Supported Models:**
- `gemini-1.5-pro`
- `gemini-1.5-flash`
- `gemini-2.0-flash-exp`

**Format:**
```json
{
  "role": "user",
  "parts": [
    {"text": "What do you see?"},
    {
      "inline_data": {
        "mime_type": "image/jpeg",
        "data": "base64_image_data"
      }
    }
  ]
}
```

**Limitations:**
- Base64 data preferred
- HTTP URLs converted to placeholders
- 30MB per file limit

## Code Examples

### 1. Basic Image Analysis

```python
from letta.schemas.letta_message_content import TextContent, ImageContent
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole

# Read image file and encode as base64
import base64

with open("screenshot.png", "rb") as f:
    image_data = base64.b64encode(f.read()).decode('utf-8')
    data_url = f"data:image/png;base64,{image_data}"

# Create multimodal message
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="Please analyze this screenshot and tell me what application is running"),
        ImageContent(image_url=data_url, detail="high")
    ]
)

# Convert to OpenAI format for API call
openai_message = message.to_openai_dict()
```

### 2. Document Processing

```python
# Process multiple document pages
pages = ["page1.jpg", "page2.jpg", "page3.jpg"]
content = [TextContent(text="Summarize this multi-page document:")]

for i, page_file in enumerate(pages):
    with open(page_file, "rb") as f:
        page_data = base64.b64encode(f.read()).decode('utf-8')
        content.append(ImageContent(
            image_url=f"data:image/jpeg;base64,{page_data}",
            detail="high"
        ))

message = Message(role=MessageRole.user, content=content)
```

### 3. Chart Analysis

```python
# Analyze charts with different detail levels
def analyze_chart(chart_url: str, complexity: str = "auto"):
    detail_level = {
        "simple": "low",
        "complex": "high", 
        "auto": "auto"
    }[complexity]
    
    message = Message(
        role=MessageRole.user,
        content=[
            TextContent(text=f"Analyze this {complexity} chart and extract key insights:"),
            ImageContent(image_url=chart_url, detail=detail_level)
        ]
    )
    
    return message

# Usage
simple_chart = analyze_chart("https://example.com/pie-chart.png", "simple")
complex_chart = analyze_chart("https://example.com/multi-axis-chart.png", "complex")
```

### 4. Image Comparison

```python
def compare_images(image1_url: str, image2_url: str, comparison_task: str):
    """Compare two images for specific task"""
    message = Message(
        role=MessageRole.user,
        content=[
            TextContent(text=f"Compare these two images for {comparison_task}:"),
            ImageContent(image_url=image1_url, detail="high"),
            ImageContent(image_url=image2_url, detail="high"),
            TextContent(text="Please highlight the key differences and similarities.")
        ]
    )
    return message

# Usage examples
before_after = compare_images(
    "data:image/jpeg;base64,before_image...",
    "data:image/jpeg;base64,after_image...", 
    "changes in product design"
)

ab_test = compare_images(
    "https://example.com/version-a.png",
    "https://example.com/version-b.png",
    "user interface effectiveness"
)
```

### 5. Using with Letta Client

```python
from letta_client import Letta, MessageCreate
from letta.schemas.letta_message_content import TextContent, ImageContent

# Initialize client
client = Letta(base_url="http://localhost:8283")

# Create agent with vision capabilities
agent = client.agents.create(
    name="Vision Assistant",
    persona="You are an expert at analyzing images and visual content.",
    llm_config={
        "model": "gpt-4o",  # Vision-capable model
        "context_window": 128000
    }
)

# Send multimodal message
def send_image_message(agent_id: str, text: str, image_path: str):
    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
        # Detect image type
        if image_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif image_path.lower().endswith(('.jpg', '.jpeg')):
            mime_type = 'image/jpeg'
        else:
            mime_type = 'image/jpeg'  # Default
        
        data_url = f"data:{mime_type};base64,{image_data}"
    
    # Send message
    response = client.agents.messages.create(
        agent_id=agent_id,
        messages=[MessageCreate(
            role="user",
            content=[
                TextContent(text=text),
                ImageContent(image_url=data_url, detail="high")
            ]
        )]
    )
    
    return response

# Usage
response = send_image_message(
    agent.id,
    "What type of chart is this and what does it show?",
    "sales_chart.png"
)
```

### 6. Streaming with Images

```python
# Stream responses for multimodal messages
def stream_image_analysis(agent_id: str, image_url: str, question: str):
    message = MessageCreate(
        role="user",
        content=[
            TextContent(text=question),
            ImageContent(image_url=image_url, detail="high")
        ]
    )
    
    # Stream the response
    stream = client.agents.messages.create_stream(
        agent_id=agent_id,
        messages=[message]
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()  # New line after streaming

# Usage
stream_image_analysis(
    agent.id,
    "data:image/jpeg;base64,chart_data...",
    "Explain the trends shown in this time series chart"
)
```

## Migration Guide

### From Text-Only Messages

#### Before (Text Only)
```python
# Old way - string content
message = Message(
    role=MessageRole.user,
    content="Hello, can you help me?"
)

# Or with content array (still works)
message = Message(
    role=MessageRole.user,
    content=[TextContent(text="Hello, can you help me?")]
)
```

#### After (Multimodal Ready)
```python
# New way - always use content array for consistency
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="Hello, can you help me analyze this image?"),
        ImageContent(image_url="data:image/jpeg;base64,...", detail="auto")
    ]
)
```

### Updating Existing Code

#### 1. Message Creation
```python
# OLD: Direct string assignment
message.content = "Hello world"

# NEW: Use content array
message.content = [TextContent(text="Hello world")]
```

#### 2. Content Access
```python
# OLD: Direct string access
text = message.content

# NEW: Extract from content array
text_parts = [c.text for c in message.content if isinstance(c, TextContent)]
text = text_parts[0] if text_parts else ""
```

#### 3. API Calls
```python
# OLD: String content in API calls
{
    "role": "user",
    "content": "Analyze this data"
}

# NEW: Content array for multimodal
{
    "role": "user", 
    "content": [
        {"type": "text", "text": "Analyze this data"},
        {"type": "image_url", "image_url": {"url": "...", "detail": "high"}}
    ]
}
```

### Backwards Compatibility

✅ **Existing text-only messages continue to work**  
✅ **String content automatically converted to TextContent**  
✅ **All existing APIs maintain compatibility**  
✅ **No breaking changes to public interfaces**

### Breaking Changes

❌ **None** - This is a fully backwards-compatible addition

## Best Practices

### 🖼️ Image Selection

**DO:**
- Use high-quality, well-lit images
- Ensure text in images is clearly readable
- Crop to focus on relevant content
- Use appropriate image formats (JPEG for photos, PNG for graphics)

**DON'T:**
- Send extremely large images (>20MB)
- Use blurry or low-contrast images
- Include sensitive information in images
- Send duplicate or redundant images

### 💰 Cost Optimization

**Image Size Management:**
```python
# Use appropriate detail levels
ImageContent(image_url="...", detail="low")   # Cheaper, basic analysis
ImageContent(image_url="...", detail="high")  # More expensive, detailed analysis
ImageContent(image_url="...", detail="auto")  # Provider optimized
```

**Batch Processing:**
```python
# Process related images together
content = [TextContent(text="Analyze these related charts:")]
for chart_url in chart_urls:
    content.append(ImageContent(image_url=chart_url, detail="low"))
```

### 🔒 Security Considerations

**Image Data Handling:**
- **Validate image formats** before processing
- **Sanitize file names** and paths
- **Limit image sizes** to prevent DoS attacks
- **Use HTTPS URLs** for external images
- **Avoid sensitive information** in images

**Base64 Encoding:**
```python
import base64
import mimetypes

def safe_encode_image(file_path: str) -> str:
    """Safely encode image with validation"""
    # Validate file exists and is readable
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Image file not found: {file_path}")
    
    # Check file size (limit to 20MB)
    file_size = os.path.getsize(file_path)
    if file_size > 20 * 1024 * 1024:
        raise ValueError(f"Image too large: {file_size} bytes")
    
    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith('image/'):
        raise ValueError(f"Invalid image type: {mime_type}")
    
    # Encode safely
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
        return f"data:{mime_type};base64,{encoded}"
```

### 🚀 Performance Tips

**Image Optimization:**
```python
from PIL import Image
import io
import base64

def optimize_image(image_path: str, max_size: tuple = (1024, 1024), quality: int = 85) -> str:
    """Optimize image for better performance"""
    with Image.open(image_path) as img:
        # Resize if too large
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Save optimized version
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        
        # Encode as base64
        encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded}"
```

**Caching Strategies:**
```python
import hashlib
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_image_analysis(image_hash: str, question: str):
    """Cache image analysis results"""
    # Implementation depends on your caching strategy
    pass

def get_image_hash(image_data: bytes) -> str:
    """Generate hash for image caching"""
    return hashlib.md5(image_data).hexdigest()
```

## Troubleshooting

### Common Issues

#### 1. "Image too large" errors

**Problem:** Image exceeds provider size limits

**Solution:**
```python
# Resize image before encoding
from PIL import Image

def resize_image(image_path: str, max_dimension: int = 2048) -> str:
    with Image.open(image_path) as img:
        # Calculate new size maintaining aspect ratio
        width, height = img.size
        if max(width, height) > max_dimension:
            ratio = max_dimension / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Save and encode
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded}"
```

#### 2. "Unsupported image format" errors

**Problem:** Image format not supported by provider

**Solution:**
```python
def convert_to_supported_format(image_path: str) -> str:
    """Convert any image to JPEG format"""
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=90)
        
        encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded}"
```

#### 3. Base64 encoding issues

**Problem:** Invalid base64 data or encoding errors

**Solution:**
```python
import base64

def validate_base64_image(data_url: str) -> bool:
    """Validate base64 image data URL"""
    try:
        # Check format
        if not data_url.startswith('data:image/'):
            return False
        
        # Extract base64 part
        header, data = data_url.split(',', 1)
        
        # Validate base64
        decoded = base64.b64decode(data, validate=True)
        
        # Check if it's a valid image
        from PIL import Image
        import io
        Image.open(io.BytesIO(decoded))
        
        return True
    except Exception:
        return False
```

#### 4. Provider-specific issues

**OpenAI Issues:**
```python
# Check model supports vision
VISION_MODELS = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-vision-preview']

def validate_openai_config(llm_config: dict):
    if llm_config.get('model') not in VISION_MODELS:
        raise ValueError(f"Model {llm_config['model']} doesn't support images")
```

**Anthropic Issues:**
```python
# Ensure base64 format for Claude
def ensure_anthropic_format(image_url: str) -> str:
    if image_url.startswith('http'):
        # Download and convert to base64
        import requests
        response = requests.get(image_url)
        encoded = base64.b64encode(response.content).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded}"
    return image_url
```

### Debug Information

**Enable debug logging:**
```python
import logging

# Enable debug logging for image processing
logging.getLogger('letta.schemas.message').setLevel(logging.DEBUG)
logging.getLogger('letta.llm_api').setLevel(logging.DEBUG)
```

**Message inspection:**
```python
# Debug message format conversion
def debug_message_conversion(message: Message):
    print("Original message:")
    print(f"Content parts: {len(message.content)}")
    for i, part in enumerate(message.content):
        print(f"  Part {i}: {type(part).__name__}")
        if isinstance(part, ImageContent):
            print(f"    URL length: {len(part.image_url)}")
            print(f"    Detail: {part.detail}")
    
    print("\nOpenAI format:")
    openai_dict = message.to_openai_dict()
    print(f"Content type: {type(openai_dict['content'])}")
    if isinstance(openai_dict['content'], list):
        print(f"Content parts: {len(openai_dict['content'])}")
```

### Performance Monitoring

**Track image processing metrics:**
```python
import time
from functools import wraps

def monitor_image_processing(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        # Log processing time
        print(f"Image processing took {end_time - start_time:.2f} seconds")
        return result
    return wrapper

@monitor_image_processing
def process_multimodal_message(message: Message):
    # Your processing logic here
    pass
```

---

## Support

For additional help with multimodal messages:

1. **Check the [test suite](../tests/test_image_messages.py)** for working examples
2. **Review [provider documentation](#provider-support)** for specific limitations
3. **Use debug logging** to troubleshoot conversion issues
4. **Optimize images** before processing to reduce costs and improve performance

The multimodal message system is designed to be robust and backwards-compatible while enabling powerful new AI capabilities with visual understanding.