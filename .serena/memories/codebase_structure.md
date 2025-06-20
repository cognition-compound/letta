# Codebase Structure

## Root Directory
- `letta/` - Main package source code
- `tests/` - Test suite with pytest configuration
- `docs/` - Documentation
- `alembic/` - Database migration scripts
- `examples/` - Example usage and demos
- `scripts/` - Utility scripts

## Core Letta Package (`letta/`)
- `agents/` - Agent implementations (LettaAgent, VoiceAgent, etc.)
- `server/` - FastAPI REST API server
- `services/` - Business logic layer (managers)
- `orm/` - SQLAlchemy models for persistence
- `llm_api/` - Multi-provider LLM clients
- `cli/` - Command-line interface
- `schemas/` - Pydantic data models
- `functions/` - Built-in tool functions
- `interfaces/` - Communication interfaces
- `client/` - SDK client implementation
- `types/` - Type definitions

## Configuration Files
- `pyproject.toml` - Poetry dependencies and project config
- `alembic.ini` - Database migration configuration
- `.pre-commit-config.yaml` - Code quality hooks
- `pytest.ini` - Test configuration
- `docker-compose.yaml` / `dev-compose.yaml` - Container orchestration

## Key Entry Points
- `letta/main.py` - CLI application entry point
- `letta/server/rest_api/app.py` - FastAPI server
- `letta/agent.py` - Core agent implementation