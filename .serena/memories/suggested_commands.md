# Suggested Commands

## Environment Setup
```bash
# Install all dependencies with extras
poetry install --all-extras

# Install development dependencies
poetry install -E dev -E server -E postgres
```

## Database Operations
```bash
# Set PostgreSQL URI
export LETTA_PG_URI="postgresql://letta:letta@localhost:5432/letta"

# Run migrations
alembic upgrade head

# Reset database (development)
alembic downgrade base && alembic upgrade head
```

## Running the Application
```bash
# Start Letta server
poetry run letta server

# Start CLI interface
poetry run letta run

# Docker development
docker compose -f dev-compose.yaml up

# Production Docker
docker compose up
```

## Testing
```bash
# Run all tests
poetry run pytest

# Run specific test markers
poetry run pytest -m "not async_client_test"
poetry run pytest -m "openai_basic" 
poetry run pytest -m "local_sandbox"

# Run single test file
poetry run pytest tests/test_client.py
```

## Code Quality (Run after completing tasks)
```bash
# Format code
poetry run black letta/ tests/ --line-length 140
poetry run isort letta/ tests/

# Type checking
poetry run pyright

# Pre-commit hooks
poetry run pre-commit run --all-files
```