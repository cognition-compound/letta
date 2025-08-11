# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Letta** (previously MemGPT) is an open-source framework for building stateful agents with advanced reasoning capabilities and transparent long-term memory. It provides a white-box, model-agnostic platform for creating AI agents that persist memory across conversations.

### Key Features
- **Stateful Agents**: Agents maintain memory across conversations using a sophisticated block-based memory system
- **Multi-Provider LLM Support**: Works with OpenAI, Anthropic, Google, and local LLMs
- **Tool Execution**: Sandboxed tool execution with built-in and custom tools
- **Multi-Agent Communication**: Agents can communicate with each other asynchronously
- **Production Ready**: Enterprise-grade logging, observability, and deployment options

## Quick Start

### Prerequisites
- Python 3.12+
- Poetry for dependency management
- PostgreSQL (for production)
- Docker (optional)

### Basic Setup
```bash
# Clone and install
poetry install -E dev -E server -E postgres

# Set up database
export LETTA_PG_URI="postgresql://letta:letta@localhost:5432/letta"
alembic upgrade head

# Start server
poetry run letta server
```

### Essential Commands
```bash
# Testing
poetry run pytest                    # Run all tests
poetry run pytest -m openai_basic    # Run specific marker

# Code quality
poetry run black letta/ tests/ --line-length 140
poetry run isort letta/ tests/
poetry run pyright

# Docker
docker compose -f dev-compose.yaml up  # Development stack
docker build -t letta:latest .         # Build image
```

## Architecture Overview

### Core Components
- **Server** (`letta/server/`) - FastAPI REST API with WebSocket support
- **Agents** (`letta/agents/`) - Core agent implementations (LettaAgent, VoiceAgent, etc.)
- **Services** (`letta/services/`) - Business logic layer (managers for agents, tools, etc.)
- **ORM** (`letta/orm/`) - SQLAlchemy models for persistence
- **LLM Integration** (`letta/llm_api/`) - Multi-provider LLM clients

### Key Technologies
- **FastAPI + Uvicorn** for REST API server
- **SQLAlchemy 2.0** with async support for ORM
- **PostgreSQL + pgvector** for production database
- **Pydantic v2** for data validation
- **Alembic** for database migrations
- **Poetry** for dependency management
- **Docker + tini** for containerized deployment with proper init system
- **GitHub Actions** for automated CI/CD and image publishing

### Memory System
Letta uses a sophisticated block-based memory system:
- **Core Memory** - Essential agent information (persona, human details)
- **Recall Memory** - Conversation history with semantic search
- **Archival Memory** - Long-term storage with vector embeddings
- **Block Management** - Structured memory components with identity linking

### Tool Execution
- **Sandboxed execution** via local sandbox or E2B cloud sandbox
- **Built-in tools** for memory management, file operations, multi-agent coordination
- **External integrations** via Composio and MCP (Model Context Protocol)
- **Schema validation** using Pydantic for all tool definitions

### Multi-Provider LLM Support
The system abstracts LLM interactions through:
- Unified client interface in `llm_client_base.py`
- Provider-specific implementations (OpenAI, Anthropic, Google, local LLMs)
- Streaming support with proper token counting and context management
- Function calling standardization across providers

## Development Patterns

### Service Layer Pattern
All business logic goes through service managers:
- `AgentManager` - Agent lifecycle and state management  
- `MessageManager` - Message persistence and retrieval
- `ToolManager` - Tool registration and execution
- `BlockManager` - Memory block operations

### Database Patterns
- Use SQLAlchemy ORM models in `letta/orm/`
- All database changes require Alembic migrations
- Async database operations throughout
- Proper relationship modeling with cascading deletes

### API Design
- RESTful endpoints following OpenAPI standards
- Consistent error handling with proper HTTP status codes
- Streaming responses for real-time agent interactions
- OpenAI-compatible endpoints for chat completions

### Logging and Observability
- **Modern logging system** with OpenTelemetry integration
- **Performance optimized** with lazy evaluation and async processing
- **Security features** including automatic sensitive data sanitization
- **Standard OTEL configuration** via environment variables
- **Log locations**: `~/.letta/logs/` (with rotation and retention)

## Key Environment Variables

```bash
# Database (required for production)
LETTA_PG_URI="postgresql://user:pass@host:port/db"

# LLM Providers
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."

# Server Configuration
HOST="0.0.0.0"
PORT="8283"
LETTA_SERVER_PASSWORD="password"  # For secure mode

# Development
LETTA_LOG_LEVEL="DEBUG"
LETTA_DEBUG="true"

# OpenTelemetry (standard OTEL vars)
OTEL_SERVICE_NAME="letta-server"
OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
OTEL_TRACES_EXPORTER="otlp"

# Database Connection Pool (to reduce connections)
LETTA_PG_POOL_SIZE="10"
LETTA_PG_MAX_OVERFLOW="5"

# Parallel Tool Calls
LETTA_ENABLE_PARALLEL_TOOL_CALLS="true"  # Enable parallel tool execution (default: true)
```

## Docker Deployment

- **Optimized image**: Multi-stage build with `python:3.12-slim` base
- **External PostgreSQL required**: No embedded database in Docker image
- **Container registry**: `ghcr.io/letta-ai/letta:latest` (auto-published)
- **Health checks**: Built-in at `/v1/health`
- **Development**: Use `docker compose -f dev-compose.yaml up`

## Testing Strategy

### Test Types
- **Unit tests**: Core logic in services and agents
- **Integration tests**: API endpoints and database operations  
- **SDK tests**: Client library functionality
- **Sandbox tests**: Tool execution environments
- **Provider tests**: LLM integrations (requires API keys)

### Test Markers
- `openai_basic` - Tests requiring OpenAI API
- `local_sandbox` - Local tool sandbox tests  
- `e2b_sandbox` - Cloud sandbox tests
- `async_client_test` - Async client tests (skipped by default)

## Key Features

### Custom Fork Features
- **Unified send() function**: Single API for all agent messaging (user, agent-to-agent, group, broadcast)
- **Async-only agent communication**: All inter-agent messaging is fire-and-forget
- **Multimodal support**: Messages can contain both text and images
- **Modern logging**: OpenTelemetry integration with standard configuration
- **File tools**: Built-in tools for file operations (open_file, search_files, grep, etc.)
- **Parallel tool execution**: Concurrent execution of multiple tools from a single LLM response for 2-5x performance gains

### Notable Capabilities
- **Agent-to-agent messaging**: Agents communicate asynchronously without blocking
- **File processing**: Type-aware chunking for code, markdown, HTML, JSON
- **Distributed scheduling**: Leader election for multi-instance deployments
- **Source metadata API**: Aggregated file statistics at organization level

## Common Issues

### Parallel Tool Execution
- **Configuration**: Control via `LETTA_ENABLE_PARALLEL_TOOL_CALLS` environment variable
- **Default**: Enabled (`"true"`) - set to `"false"` to disable
- **Memory safety**: Memory operation tools executed sequentially by default
- **Performance**: 2-5x speedup for multi-tool workflows
- **Troubleshooting**: If issues arise, disable with `export LETTA_ENABLE_PARALLEL_TOOL_CALLS="false"`

## Documentation Structure

### Key Documentation Files
- `current_progress.md` - Active development tracking
- `docs/UNIFIED_SEND_IMPLEMENTATION.md` - Agent messaging architecture
- `docs/MULTIMODAL_*.md` - Image support documentation
- `docs/FILE_PROCESSING_ARCHITECTURE.md` - File handling system
- `docs/DATABASE_CONNECTION_POOLING_ANALYSIS.md` - DB optimization
- `docs/PARALLEL_TOOL_CALLS_IMPLEMENTATION_PLAN.md` - Parallel tool execution architecture

## Development Philosophy
- **No backwards compatibility concerns** - We can break things if needed
- **Focus on core functionality** - Not on edge cases or fallbacks
- **Document discoveries** - Update current_progress.md as you learn

## Fork Maintenance

### Branch Strategy
- **dev branch**: Contains our custom fork changes
- **main branch**: Synced with upstream Letta repository

### Merging Upstream Changes
1. Review upstream changes thoroughly
2. Test compatibility with custom features
3. Preserve our enhancements:
   - Unified send() function
   - Async-only messaging
   - Custom logging system
   - Docker optimizations
4. Update documentation as needed

### Key Custom Changes to Preserve
- `letta/tools/multi_agent.py` - Unified send() implementation
- `letta/schemas/message.py` - Message conversion logic
- `letta/log/` - Modern logging system
- `Dockerfile` - Optimized build configuration

## Behaviour Expectations
- **NEVER push to git without explicit permission**: Always ask before running `git push`. Only commit locally.
- **No backwards compatibility**: We can break things if needed
- **Reproduce bugs**: When analysing issues, **ALWAYS** reproduce them by creating a (failing) test case in the test suite as very first step.
- **Document discoveries**: Update @current_progress.md as you learn new things. **ALWAYS** Review and compact existing entries as you learn more about the system.
- **NEVER** use inline imports - group all imports at the top of the file.