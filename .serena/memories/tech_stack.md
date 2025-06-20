# Tech Stack

## Core Technologies
- **Python 3.10-3.13** - Primary language
- **Poetry** - Dependency management and packaging
- **FastAPI + Uvicorn** - REST API server
- **SQLAlchemy 2.0** with async support for ORM
- **PostgreSQL + pgvector** for production database
- **Pydantic v2** - Data validation
- **Alembic** - Database migrations
- **Typer** - CLI framework

## Key Dependencies
- **LLM Providers**: OpenAI, Anthropic, Google AI, Mistral
- **Database**: PostgreSQL (production), SQLite (development)
- **Testing**: pytest, pytest-asyncio
- **Code Quality**: black, isort, pyright, autoflake, pre-commit
- **Async**: asyncio, uvloop, aiomultiprocess
- **Other**: httpx, pyyaml, jinja2, nltk, composio-core

## Optional Extras
- `dev` - Development tools (black, pyright, isort, etc.)
- `server` - FastAPI server components
- `postgres` - PostgreSQL support
- `cloud-tool-sandbox` - E2B sandbox support