# Letta Documentation

This directory contains technical documentation for Letta development and advanced features.

## Core Documentation

### 🎯 Quick References
- **[Multimodal Messages Quick Reference](MULTIMODAL_QUICK_REFERENCE.md)** - Fast reference for image message features

### 📚 Comprehensive Guides  
- **[Multimodal Messages Guide](MULTIMODAL_MESSAGES.md)** - Complete guide to text + image messages
- **[Multimodal API Reference](MULTIMODAL_API_REFERENCE.md)** - Detailed API documentation for multimodal features

### 🔧 Development Guides
- **[Agent Types](AGENT_TYPES.md)** - Different agent implementations and use cases
- **[Proactive Messaging](PROACTIVE_MESSAGING.md)** - Background agent communication
- **[Sleeptime Agent Migration](MIGRATE_TO_SLEEPTIME.md)** - Upgrading to sleeptime agents

### 📁 File Processing
- **[File Processing Architecture](FILE_PROCESSING_ARCHITECTURE.md)** - How file ingestion works
- **[File Tools Reference](FILE_TOOLS_REFERENCE.md)** - Available file manipulation tools

### 🛠️ Development & Troubleshooting
- **[Troubleshooting Lessons](TROUBLESHOOTING_LESSONS.md)** - Common issues and debugging patterns
- **[Documentation Updates](UPDATE_DOCS.md)** - How to update documentation

## Feature Overview

### 🖼️ Multimodal Messages (NEW)
Support for messages containing both text and images, enabling:
- Image analysis and description
- Chart and document processing  
- Visual question answering
- Multi-image comparison

**Quick Start:**
```python
from letta.schemas.letta_message_content import TextContent, ImageContent

message = Message(
    role=MessageRole.user,
    content=[
        TextContent(text="What's in this image?"),
        ImageContent(image_url="data:image/jpeg;base64,...", detail="high")
    ]
)
```

### 🤖 Agent Types
- **LettaAgent** - Standard conversational agent
- **VoiceAgent** - Speech-enabled agent
- **SleeptimeAgent** - Background processing agent
- **EphemeralAgent** - Temporary agents without persistence

### 📂 File Processing
- Document ingestion (PDF, TXT, MD, etc.)
- Automatic chunking and embedding
- File search and retrieval tools
- Content-aware processing

### 🔗 Tool Integration
- Built-in memory management tools
- File manipulation tools
- Multi-agent coordination tools
- External tool integration via Composio and MCP

## Getting Started

### For Users
1. Start with the **[Multimodal Quick Reference](MULTIMODAL_QUICK_REFERENCE.md)** for image messages
2. Review **[Agent Types](AGENT_TYPES.md)** to choose the right agent
3. Check **[File Tools Reference](FILE_TOOLS_REFERENCE.md)** for file operations

### For Developers  
1. Read **[File Processing Architecture](FILE_PROCESSING_ARCHITECTURE.md)** for system understanding
2. Use **[Troubleshooting Lessons](TROUBLESHOOTING_LESSONS.md)** for debugging guidance
3. Follow **[Documentation Updates](UPDATE_DOCS.md)** for contributing docs

## Support

- **Issues**: Report bugs or request features on GitHub
- **Documentation**: Contribute improvements via pull requests
- **Community**: Join discussions in the Letta community

---

**Note**: This documentation covers advanced features and development topics. For basic usage, see the main README and examples directory.