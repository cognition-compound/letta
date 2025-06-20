# Task Completion Checklist

## After Completing Any Task

### 1. Code Quality Checks (REQUIRED)
```bash
# Format code
poetry run black letta/ tests/ --line-length 140
poetry run isort letta/ tests/

# Type checking
poetry run pyright

# Pre-commit hooks (run all checks)
poetry run pre-commit run --all-files
```

### 2. Testing (if applicable)
```bash
# Run relevant tests
poetry run pytest

# For specific components
poetry run pytest tests/test_[component].py

# Check test markers in pytest.ini for targeted testing
```

### 3. Database Migrations (if database changes)
```bash
# Create migration if ORM models changed
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

### 4. Documentation Updates (if needed)
- Update relevant documentation in `docs/`
- Update CLAUDE.md if adding new development patterns
- Update current_progress.md with significant changes

## Before Committing
1. Ensure all tests pass
2. Ensure no linting errors
3. Verify type checking passes
4. Review changes for security issues
5. Never commit secrets or API keys