# Multimodal Message API Instructions

## Overview  
To send messages with images to Letta agents, you can use either the SDK types or raw REST API calls. This guide covers both approaches.

**Important:** The REST API uses Letta's internal message format, which differs from OpenAI's format. Use the SDK for the most convenient experience, or follow the exact format shown in the REST API examples below.

## SDK Usage (Recommended)

### Installation
```bash
pip install letta-client
```

### Using the Letta Client SDK
```python
from letta_client import Letta, MessageCreate
from letta_client.types import TextContent, ImageContent, Base64Image, UrlImage

# Initialize client
client = Letta(base_url="http://localhost:8283")

# Create message with image
messages = [
    MessageCreate(
        role="user",
        content=[
            TextContent(text="What do you see in this image?"),
            ImageContent(source=Base64Image(
                data="<base64_encoded_image_data>",
                media_type="image/jpeg"
            ))
        ]
    )
]

# Send to agent
response = client.agents.messages.create(
    agent_id="your-agent-id",
    messages=messages
)
```

### SDK Content Types

#### Text Content
```python
from letta_client.types import TextContent

text_content = TextContent(text="Your message here")
```

#### Image Content with Base64 Data
```python
from letta_client.types import ImageContent, Base64Image

image_content = ImageContent(
    source=Base64Image(
        data="<base64_encoded_image_data>",
        media_type="image/jpeg",
        detail="high"  # Optional: "low", "high", or "auto"
    )
)
```

#### Image Content with URL
```python
from letta_client.types import ImageContent, UrlImage

image_content = ImageContent(
    source=UrlImage(url="https://example.com/image.jpg")
)
```

## Raw REST API Format

### Endpoint
```
POST /v1/agents/{agent_id}/messages
```

### Headers
```
Content-Type: application/json
Authorization: Bearer <your-token>
```

### Body Structure (Letta Internal Format)
```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",  
          "text": "Can you describe what you see in this image?"
        },
        {
          "type": "image",
          "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "/9j/4AAQSkZJRgABAQEAAAAAAAD...",
            "detail": "high"
          }
        }
      ]
    }
  ]
}
```

### REST API Content Types

#### Text Content
```json
{
  "type": "text",
  "text": "Your text message here"
}
```

#### Image Content
```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/jpeg",
    "data": "<base64_encoded_image_data>",
    "detail": "high"
  }
}
```

#### Image Content with URL
```json
{
  "type": "image",
  "source": {
    "type": "url",
    "url": "https://example.com/image.jpg"
  }
}
```

## Image Details

### Supported Formats
- **JPEG** (`.jpg`, `.jpeg`)
- **PNG** (`.png`) 
- **GIF** (`.gif`)
- **WebP** (`.webp`)

### Image URL Formats
1. **Base64 Data URLs** (Recommended):
   ```
   data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD...
   ```

2. **HTTP/HTTPS URLs**:
   ```
   https://example.com/image.jpg
   ```

### Detail Levels
- `"low"` - Basic analysis, lower cost
- `"high"` - Detailed analysis, higher cost  
- `"auto"` - Provider decides (default)

## Complete Examples

### SDK Examples

#### Single Image with Text
```python
from letta_client import Letta, MessageCreate
from letta_client.types import TextContent, ImageContent, Base64Image
import base64

# Initialize client
client = Letta(base_url="http://localhost:8283")

# Read and encode image
with open("screenshot.png", "rb") as f:
    image_data = base64.b64encode(f.read()).decode('utf-8')

# Create message
messages = [
    MessageCreate(
        role="user",
        content=[
            TextContent(text="What's in this screenshot?"),
            ImageContent(source=Base64Image(
                data=image_data,
                media_type="image/png",
                detail="auto"
            ))
        ]
    )
]

# Send to agent
response = client.agents.messages.create(agent_id="agent-id", messages=messages)
```

#### Multiple Images
```python
from letta_client import MessageCreate
from letta_client.types import TextContent, ImageContent, Base64Image, UrlImage

messages = [
    MessageCreate(
        role="user", 
        content=[
            TextContent(text="Compare these two charts:"),
            ImageContent(source=Base64Image(
                data="<chart1_base64_data>",
                media_type="image/jpeg",
                detail="high"
            )),
            TextContent(text="vs"),
            ImageContent(source=UrlImage(url="https://example.com/chart2.png"))
        ]
    )
]
```

#### Image from URL
```python
from letta_client import MessageCreate
from letta_client.types import TextContent, ImageContent, UrlImage

messages = [
    MessageCreate(
        role="user",
        content=[
            TextContent(text="Analyze this chart"),
            ImageContent(source=UrlImage(url="https://example.com/chart.png"))
        ]
    )
]
```

### REST API Examples

#### Single Image with Text
```json
{
  "messages": [
    {
      "role": "user", 
      "content": [
        {
          "type": "text",
          "text": "What's in this screenshot?"
        },
        {
          "type": "image",
          "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "iVBORw0KGgoAAAANSUhEUgAA...",
            "detail": "auto"
          }
        }
      ]
    }
  ]
}
```

#### Multiple Images
```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text", 
          "text": "Compare these two charts:"
        },
        {
          "type": "image",
          "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "<chart1_data>",
            "detail": "high"
          }
        },
        {
          "type": "text",
          "text": "vs"
        },
        {
          "type": "image",
          "source": {
            "type": "url",
            "url": "https://example.com/chart2.png"
          }
        }
      ]
    }
  ]
}
```

#### Text-Only (Legacy Format Still Supported)
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ]
}
```

## Converting Images to Base64

### JavaScript/TypeScript
```javascript
function imageToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Usage
const base64Image = await imageToBase64(imageFile);
// Result: "data:image/jpeg;base64,/9j/4AAQ..."
```

### Python
```python
import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode('utf-8')
        
    # Detect image type
    if image_path.lower().endswith('.png'):
        mime_type = 'image/png'
    elif image_path.lower().endswith(('.jpg', '.jpeg')):
        mime_type = 'image/jpeg'
    else:
        mime_type = 'image/jpeg'  # default
        
    return f"data:{mime_type};base64,{encoded}"
```

### curl Example
```bash
curl -X POST "https://your-letta-server.com/v1/agents/{agent_id}/messages/async" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-token" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text", 
            "text": "What do you see in this image?"
          },
          {
            "type": "image",
            "source": {
              "type": "base64",
              "media_type": "image/jpeg",
              "data": "/9j/4AAQSkZJRgABAQEAAAAAAAD...",
              "detail": "high"
            }
          }
        ]
      }
    ]
  }'
```

## Error Handling

### Common Errors
- **400 Bad Request**: Invalid content format or missing required fields
- **413 Payload Too Large**: Image exceeds size limits (typically 20MB)
- **422 Unprocessable Entity**: Invalid base64 encoding or unsupported image format

### Validation Requirements
1. **Content array must not be empty**
2. **Each content part must have a valid `type`**
3. **Image URLs must not be empty strings**
4. **Base64 data must be properly formatted**

## Best Practices

### Image Optimization
- **Resize large images** before encoding (max 2048px recommended)
- **Use JPEG for photos**, PNG for graphics with transparency
- **Compress images** to reduce payload size while maintaining quality

### Performance Tips
- **Use `"detail": "low"`** for simple images to reduce cost and latency
- **Batch related images** in a single message when possible
- **Cache base64 encoded images** on client side to avoid re-encoding

### Security Considerations
- **Validate image files** before encoding
- **Limit file sizes** to prevent large payloads
- **Sanitize file names** and paths
- **Use HTTPS** for external image URLs

While the SDK provides OpenAI-compatible interface, the REST API uses Letta's internal format for maximum flexibility and performance.