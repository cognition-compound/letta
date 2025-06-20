# Code Style and Conventions

## Code Formatting
- **Black** - Line length 140 characters
- **isort** - Import sorting with black profile
- **autoflake** - Remove unused imports and variables
- **Pre-commit hooks** enforce formatting

## Type Checking
- **Pyright** for static type analysis
- **Pydantic v2** for data validation and serialization
- Type hints required throughout codebase

## Architecture Patterns
- **Service Layer Pattern** - Business logic in service managers
  - `AgentManager` - Agent lifecycle and state management
  - `MessageManager` - Message persistence and retrieval  
  - `ToolManager` - Tool registration and execution
  - `BlockManager` - Memory block operations

- **Database Patterns**
  - SQLAlchemy ORM models in `letta/orm/`
  - All changes require Alembic migrations
  - Async operations throughout
  - Proper relationship modeling with cascading deletes

- **API Design**
  - RESTful endpoints following OpenAPI standards
  - Consistent error handling with proper HTTP status codes
  - Streaming responses for real-time agent interactions
  - OpenAI-compatible endpoints

## Testing Strategy
- Unit tests for core logic
- Integration tests for API endpoints
- SDK tests for client library
- Test markers control execution scope