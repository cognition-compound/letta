# Multimodal Messages - Quick Reference

A concise reference for Letta's multimodal message support.

## Basic Usage

### Creating Image Messages

```python
from letta.schemas.letta_message_content import TextContent, ImageContent
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole

# Single image with text
message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="What's in this image?"),
        ImageContent(image_url="data:image/jpeg;base64,...", detail="high")
    ]
)
```

### Using with Letta Client

```python
from letta_client import MessageCreate

response = client.agents.messages.create(
    agent_id=agent.id,
    messages=[MessageCreate(
        role="user",
        content=[
            TextContent(text="Analyze this chart"),
            ImageContent(image_url="https://example.com/chart.png")
        ]
    )]
)
```

## Image Content Options

### ImageContent Parameters

```python
ImageContent(
    image_url="...",        # Required: URL or base64 data URL
    detail="auto"           # Optional: "low", "high", "auto" (default)
)
```

### Detail Levels

| Level | Use Case | Cost | Quality |
|-------|----------|------|---------|
| `"low"` | Simple images, OCR | Lower | Basic |
| `"high"` | Complex charts, detailed analysis | Higher | High |
| `"auto"` | Provider optimized | Variable | Balanced |

### Image URL Formats

```python
# Base64 data URL (recommended)
ImageContent(image_url="data:image/jpeg;base64,/9j/4AAQ...")

# HTTP/HTTPS URL
ImageContent(image_url="https://example.com/image.jpg")
```

## Code Snippets

### Image File to Base64

```python
import base64

def image_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
        # Detect MIME type based on extension
        if file_path.lower().endswith('.png'):
            return f"data:image/png;base64,{encoded}"
        else:
            return f"data:image/jpeg;base64,{encoded}"

# Usage
image_url = image_to_base64("screenshot.png")
content = ImageContent(image_url=image_url, detail="high")
```

### Multiple Images

```python
# Compare multiple images
content = [TextContent(text="Compare these products:")]
for i, image_path in enumerate(["product1.jpg", "product2.jpg"]):
    image_url = image_to_base64(image_path)
    content.append(ImageContent(image_url=image_url, detail="high"))

message = Message(role=MessageRole.user, content=content)
```

### Image Analysis

```python
def analyze_image(image_path: str, question: str):
    return Message(
        role=MessageRole.user,
        content=[
            TextContent(text=question),
            ImageContent(image_url=image_to_base64(image_path), detail="high")
        ]
    )

# Usage
message = analyze_image("chart.png", "What trends do you see in this data?")
```

## Provider Support

### OpenAI (GPT-4 Vision)

```python
# Models: gpt-4o, gpt-4o-mini, gpt-4-vision-preview
# Limits: 20 images/message, 20MB total
{
    "model": "gpt-4o",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this"},
                {
                    "type": "image_url", 
                    "image_url": {
                        "url": "data:image/jpeg;base64,...",
                        "detail": "high"
                    }
                }
            ]
        }
    ]
}
```

### Anthropic (Claude Vision)

```python
# Models: claude-3-5-sonnet, claude-3-5-haiku, claude-3-opus
# Limits: 5 images/message, 100MB total, base64 only
{
    "model": "claude-3-5-sonnet",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg", 
                        "data": "base64_data"
                    }
                }
            ]
        }
    ]
}
```

### Google AI (Gemini)

```python
# Models: gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp  
# Limits: 30MB per file
{
    "model": "gemini-1.5-pro",
    "contents": [
        {
            "role": "user",
            "parts": [
                {"text": "What's this?"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": "base64_data"
                    }
                }
            ]
        }
    ]
}
```

## Message Conversion

### To OpenAI Format

```python
message = Message(role=MessageRole.user, content=[...])
openai_dict = message.to_openai_dict()
```

### To Anthropic Format

```python
anthropic_dict = message.to_anthropic_dict()
```

### To Google AI Format  

```python
google_dict = message.to_google_ai_dict()
```

### From OpenAI Format

```python
openai_msg = {"role": "user", "content": [...]}
message = Message.dict_to_message("agent-id", openai_msg)
```

## Common Patterns

### Image + Text Analysis

```python
def create_analysis_message(image_path: str, prompt: str):
    return Message(
        role=MessageRole.user,
        content=[
            TextContent(text=prompt),
            ImageContent(
                image_url=image_to_base64(image_path),
                detail="high"
            )
        ]
    )
```

### Batch Image Processing

```python
def process_image_batch(image_paths: list, instruction: str):
    content = [TextContent(text=instruction)]
    
    for path in image_paths:
        content.append(ImageContent(
            image_url=image_to_base64(path),
            detail="auto"
        ))
    
    return Message(role=MessageRole.user, content=content)
```

### Error Handling

```python
try:
    message = Message(
        role=MessageRole.user,
        content=[
            TextContent(text="Analyze this"),
            ImageContent(image_url="invalid-url")
        ]
    )
except ValueError as e:
    print(f"Invalid image URL: {e}")

try:
    openai_dict = message.to_openai_dict()
except AssertionError as e:
    print(f"Conversion failed: {e}")
```

## Best Practices

### ✅ Do
- Use base64 data URLs for reliability
- Set appropriate detail levels for cost optimization
- Validate image formats before processing
- Handle errors gracefully
- Resize large images before encoding

### ❌ Don't
- Send extremely large images (>20MB)
- Use HTTP URLs without fallback handling
- Ignore provider-specific limits
- Send sensitive information in images
- Forget to handle conversion errors

## Quick Troubleshooting

| Error | Solution |
|-------|----------|
| "Image too large" | Resize before encoding |
| "Invalid image format" | Convert to JPEG/PNG |
| "Unsupported model" | Use vision-capable model |
| "Base64 decode error" | Validate data URL format |
| "Empty content" | Add TextContent or check content list |

## File Size Optimization

```python
from PIL import Image
import io
import base64

def optimize_image(image_path: str, max_size=(1024, 1024), quality=85):
    with Image.open(image_path) as img:
        # Resize if needed
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Save optimized
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        
        # Encode
        encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded}"
```

---

**Complete Documentation:**
- [Full Guide](MULTIMODAL_MESSAGES.md) - Comprehensive documentation
- [API Reference](MULTIMODAL_API_REFERENCE.md) - Detailed API docs
- [Test Examples](../tests/test_image_messages.py) - Working code examples