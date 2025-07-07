# Letta Testing Guide

This guide explains the pytest marker system used in the Letta test suite to help developers run specific subsets of tests efficiently.

## Test Categorization Markers

The test suite uses the following markers to categorize tests:

### Core Categorization Markers

- **`@pytest.mark.unit`** - Pure unit tests with no external dependencies, database access, or network calls
  - Tests that only use in-memory objects and mocks
  - Fast execution (typically < 1 second)
  - No filesystem operations except temp files
  
- **`@pytest.mark.integration`** - Integration tests that require:
  - Database access (PostgreSQL or SQLite)
  - External service connections
  - Complex setup/teardown procedures
  - Multiple component interactions
  
- **`@pytest.mark.database`** - Tests specifically requiring database access
  - Tests that create/read/update/delete database records
  - Tests using SQLAlchemy models and sessions
  - Always used together with `@pytest.mark.integration`
  
- **`@pytest.mark.external_api`** - Tests that make external API calls
  - Tests requiring API keys (OpenAI, Anthropic, etc.)
  - Tests that connect to external services
  - May fail if API keys are not configured
  
- **`@pytest.mark.slow`** - Tests taking more than 5 seconds to execute
  - Long-running integration tests
  - Tests with deliberate timeouts or waits
  - Performance benchmarks

### Provider-Specific Markers

- **`@pytest.mark.openai_basic`** - Tests for OpenAI endpoints
- **`@pytest.mark.anthropic_basic`** - Tests for Anthropic endpoints  
- **`@pytest.mark.azure_basic`** - Tests for Azure endpoints
- **`@pytest.mark.gemini_basic`** - Tests for Gemini endpoints

### Sandbox Markers

- **`@pytest.mark.local_sandbox`** - Tests using local tool execution sandbox
- **`@pytest.mark.e2b_sandbox`** - Tests using E2B cloud sandbox

## Running Tests by Category

### Run only unit tests (fast, no dependencies)
```bash
poetry run pytest -m unit
```

### Run integration tests (requires database and services)
```bash
poetry run pytest -m integration
```

### Run tests that don't require external APIs
```bash
poetry run pytest -m "not external_api"
```

### Run database tests only
```bash
poetry run pytest -m database
```

### Run fast tests (exclude slow tests)
```bash
poetry run pytest -m "not slow"
```

### Combine markers for specific subsets
```bash
# Run unit tests and fast integration tests
poetry run pytest -m "unit or (integration and not slow)"

# Run all tests except those requiring external APIs
poetry run pytest -m "not external_api"

# Run only OpenAI-specific tests
poetry run pytest -m openai_basic
```

## Common Test Execution Patterns

### Local Development (no API keys)
```bash
# Run all tests that don't require external services
poetry run pytest -m "not external_api"
```

### CI/CD Pipeline
```bash
# Run unit tests first (fail fast)
poetry run pytest -m unit

# Then run integration tests without external APIs
poetry run pytest -m "integration and not external_api"
```

### Full Test Suite (with API keys configured)
```bash
# Run everything
poetry run pytest

# Or run with specific provider
poetry run pytest -m "openai_basic or unit"
```

### Quick Feedback Loop
```bash
# Run only fast unit tests during development
poetry run pytest -m "unit and not slow"
```

### Database-specific Testing
```bash
# Test database operations without external APIs
poetry run pytest -m "database and not external_api"
```

## Best Practices

1. **Multiple Markers**: Tests can have multiple markers. For example:
   ```python
   @pytest.mark.integration
   @pytest.mark.database
   @pytest.mark.slow
   def test_complex_database_operation():
       # Test that involves database and takes > 5 seconds
   ```

2. **Marker Inheritance**: When a test requires database, always include both markers:
   ```python
   @pytest.mark.integration  # Because it's not a unit test
   @pytest.mark.database     # Because it specifically uses database
   ```

3. **External API Tests**: Always mark tests that require API keys:
   ```python
   @pytest.mark.integration
   @pytest.mark.external_api
   @pytest.mark.openai_basic  # If using OpenAI specifically
   ```

4. **Performance Tests**: Mark slow tests to allow developers to skip them:
   ```python
   @pytest.mark.slow
   @pytest.mark.integration
   ```

## Environment Variables for Testing

Some tests require environment variables to be set:

- `OPENAI_API_KEY` - For OpenAI provider tests
- `ANTHROPIC_API_KEY` - For Anthropic provider tests
- `LETTA_PG_URI` - For PostgreSQL database tests
- `E2B_API_KEY` - For E2B sandbox tests

## Debugging Test Categories

To see which markers are applied to tests:
```bash
# List all markers in use
poetry run pytest --markers

# Show which tests have specific markers
poetry run pytest --collect-only -m unit

# Verbose output showing test markers
poetry run pytest -v --collect-only
```