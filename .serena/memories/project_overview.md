# Project Overview

**Letta** (previously MemGPT) is an open-source framework for building stateful agents with advanced reasoning capabilities and transparent long-term memory. It provides a white-box, model-agnostic platform for creating AI agents that persist memory across conversations.

## Key Features
- **Stateful agents** with persistent memory across conversations
- **Multi-provider LLM support** (OpenAI, Anthropic, Google, local LLMs)  
- **Advanced memory system** with core memory, recall memory, and archival memory
- **Tool execution** via sandboxed environments
- **REST API** with FastAPI and WebSocket support
- **Agent Development Environment (ADE)** - web interface for managing agents
- **Multi-agent coordination** capabilities

## Architecture
- **Server** (`letta/server/`) - FastAPI REST API with WebSocket support
- **Agents** (`letta/agents/`) - Core agent implementations
- **Services** (`letta/services/`) - Business logic layer
- **ORM** (`letta/orm/`) - SQLAlchemy models for persistence
- **LLM Integration** (`letta/llm_api/`) - Multi-provider LLM clients

The system uses a sophisticated block-based memory system and supports external integrations via Composio and MCP (Model Context Protocol).