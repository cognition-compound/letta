# Letta Test Suite API Keys Documentation

This guide provides comprehensive information about the API keys required to run the Letta test suite, including how to obtain them, which tests require them, and strategies for running tests without certain keys.

## Table of Contents
- [Overview](#overview)
- [Required vs Optional API Keys](#required-vs-optional-api-keys)
- [Obtaining API Keys](#obtaining-api-keys)
- [Test Categories and Requirements](#test-categories-and-requirements)
- [Running Tests Without All Keys](#running-tests-without-all-keys)
- [Environment Setup](#environment-setup)
- [Troubleshooting](#troubleshooting)

## Overview

The Letta test suite includes integration tests for many different LLM providers, tools, and services. While the core functionality can be tested with just an OpenAI API key, comprehensive testing requires multiple API keys.

## Required vs Optional API Keys

### Essential (Core Tests)
- **OpenAI API Key** - Required for most basic tests and default Letta operation
  - Used by: Core agent tests, default LLM tests, embedding tests
  - Test markers: Default tests (no special markers)

### Provider-Specific (Optional)
These are only required if you want to test specific LLM provider integrations:

- **Anthropic API Key** - For Claude model tests
  - Test marker: `@pytest.mark.anthropic_basic`
- **Google AI (Gemini) API Key** - For Gemini model tests
  - Test marker: `@pytest.mark.gemini_basic`
- **Azure API Keys** - For Azure OpenAI tests
  - Test marker: `@pytest.mark.azure_basic`

### Tool & Integration Keys (Optional)
Required only for specific tool/integration tests:

- **E2B API Key** - For cloud sandbox execution tests
  - Test marker: `@pytest.mark.e2b_sandbox`
- **Composio API Key** - For Composio tool integration tests
- **Pinecone API Key** - For vector database tests
  - Also requires: `LETTA_ENABLE_PINECONE=true`
- **Tavily API Key** - For web search tool tests
- **Firecrawl API Key** - For web scraping tool tests

## Obtaining API Keys

### LLM Providers

#### OpenAI
1. Visit [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign up or log in
3. Navigate to API keys section
4. Create a new secret key
5. Format: `sk-...`

#### Anthropic (Claude)
1. Visit [Anthropic Console](https://console.anthropic.com/account/keys)
2. Create an account (may require waitlist approval)
3. Generate an API key
4. Format: `sk-ant-...`

#### Google AI (Gemini)
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with Google account
3. Create an API key
4. No special format

#### Azure OpenAI
1. Create an [Azure account](https://azure.microsoft.com)
2. Set up [Azure OpenAI Service](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
3. Deploy a model
4. Get your endpoint URL and API key
5. Note your deployed model names

#### Other Providers
- **Groq**: [Console](https://console.groq.com/keys) - Fast inference
- **Together AI**: [API Keys](https://api.together.xyz/settings/api-keys)
- **xAI**: [API](https://x.ai/api) - Grok models
- **DeepSeek**: [Platform](https://platform.deepseek.com/api_keys)
- **Mistral**: [Console](https://console.mistral.ai/api-keys)

### Tool & Integration Services

#### E2B (Code Sandbox)
1. Visit [E2B Dashboard](https://e2b.dev/dashboard)
2. Sign up for free tier
3. Generate API key
4. Optional: Create custom sandbox templates

#### Composio
1. Visit [Composio App](https://app.composio.dev/)
2. Create account
3. Generate API key from dashboard

#### Pinecone
1. Visit [Pinecone](https://app.pinecone.io/)
2. Sign up for free tier
3. Create API key
4. Note: Free tier is sufficient for tests

#### Tavily (Search)
1. Visit [Tavily](https://tavily.com/)
2. Sign up for API access
3. Free tier available

#### Firecrawl (Web Scraping)
1. Visit [Firecrawl](https://www.firecrawl.dev/)
2. Request API access
3. May have waitlist

## Test Categories and Requirements

### 1. Core Tests (OpenAI Only)
```bash
# Run all tests except sandboxes and specific providers
pytest tests/ -m "not e2b_sandbox and not local_sandbox and not anthropic_basic and not gemini_basic and not azure_basic"
```

### 2. Provider-Specific Tests
```bash
# Anthropic tests (requires ANTHROPIC_API_KEY)
pytest tests/ -m "anthropic_basic"

# Google AI tests (requires GEMINI_API_KEY)
pytest tests/ -m "gemini_basic"

# Azure tests (requires AZURE_* keys)
pytest tests/ -m "azure_basic"
```

### 3. Sandbox Tests
```bash
# Local sandbox (no API key required)
pytest tests/ -m "local_sandbox"

# E2B cloud sandbox (requires E2B_API_KEY)
pytest tests/ -m "e2b_sandbox"
```

### 4. Integration Tests
```bash
# Composio integration
pytest tests/integration_test_composio.py

# Pinecone tests (requires PINECONE_API_KEY and LETTA_ENABLE_PINECONE=true)
pytest tests/test_sources.py -k "pinecone"

# File tools (no additional keys required)
pytest tests/integration_test_builtin_tools.py
```

### 5. Database Tests
```bash
# Start PostgreSQL first
docker-compose -f scripts/docker-compose.yml up -d postgres

# Run database tests
pytest tests/ -m "database"
```

## Running Tests Without All Keys

### Strategy 1: Skip Tests Missing Keys
Tests will automatically skip if required API keys are not set:
```python
if not os.getenv("COMPOSIO_API_KEY"):
    pytest.skip("COMPOSIO_API_KEY not set")
```

### Strategy 2: Use Test Markers
Run only tests that don't require specific keys:
```bash
# Skip all provider-specific tests
pytest tests/ -m "not anthropic_basic and not gemini_basic and not azure_basic"

# Skip integration tests
pytest tests/ -k "not composio and not pinecone"
```

### Strategy 3: Mock External Services
For development, you can mock API calls:
```bash
# Run with mocked responses
pytest tests/ --mock-external-apis
```

### Strategy 4: Use Local Models
Test with local models instead of API providers:
```bash
# Set up Ollama
OLLAMA_BASE_URL=http://localhost:11434

# Or use vLLM
VLLM_API_BASE=http://localhost:8000
```

## Environment Setup

### Quick Start
1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Add your API keys:
   ```bash
   # Edit .env and add at minimum:
   OPENAI_API_KEY=sk-...
   ```

3. Set up database:
   ```bash
   docker-compose -f scripts/docker-compose.yml up -d postgres
   ```

4. Run basic tests:
   ```bash
   pytest tests/ -m "not slow"
   ```

### Docker Setup
When using Docker, some endpoints need special configuration:
```bash
# For local services from Docker
OLLAMA_BASE_URL=http://host.docker.internal:11434
VLLM_API_BASE=http://host.docker.internal:8000
```

### CI/CD Setup
For GitHub Actions or other CI:
1. Add secrets for each API key
2. Use environment variables in workflow:
   ```yaml
   env:
     OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
     ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
   ```

## Troubleshooting

### Common Issues

#### "Missing API key" errors
- Check spelling of environment variable names
- Ensure `.env` file is in the project root
- Verify keys are not commented out in `.env`
- Try `export OPENAI_API_KEY=sk-...` directly in terminal

#### Tests skipping unexpectedly
- Check if required services are running (PostgreSQL, Redis)
- Verify API keys are valid and not expired
- Check rate limits on API services

#### Provider-specific failures
- Azure: Ensure model deployments match test expectations
- Vertex AI: Check Google Cloud project permissions
- Bedrock: Verify AWS credentials and region

### Debugging Tips

1. **Check loaded environment**:
   ```python
   import os
   print(os.getenv("OPENAI_API_KEY"))
   ```

2. **Run single test with verbose output**:
   ```bash
   pytest -vvs tests/test_specific.py::test_name
   ```

3. **Check test markers**:
   ```bash
   pytest --markers
   ```

4. **List available tests by marker**:
   ```bash
   pytest --collect-only -m "anthropic_basic"
   ```

## Best Practices

1. **Start Small**: Begin with just OpenAI API key
2. **Add Incrementally**: Add provider keys as needed
3. **Use Free Tiers**: Most services offer free tiers sufficient for testing
4. **Rotate Keys**: Regularly rotate API keys for security
5. **Monitor Usage**: Track API usage to avoid unexpected charges
6. **Local First**: Use local models when possible to reduce API costs

## Contributing

When adding new tests that require API keys:
1. Add the key to `.env.example` with clear documentation
2. Update this documentation
3. Use appropriate test markers
4. Add skip conditions for missing keys
5. Document which tier/plan is required (if not free)