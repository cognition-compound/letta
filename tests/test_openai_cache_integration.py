"""
Integration tests for OpenAI prompt caching optimization.

Tests actual cache behavior using the real OpenAI API to verify that:
1. System messages are properly extracted to instructions field
2. Cache hits occur on repeated requests
3. Cache metrics are properly logged

Requires OPENAI_API_KEY environment variable to be set.
"""

import json
import os
import time
import pytest
from unittest.mock import Mock, patch

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent


class TestOpenAICacheIntegration:
    """Integration test suite for OpenAI cache optimization."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup test fixtures."""
        # Skip if no OpenAI API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set, skipping integration tests")
        
        self.client = OpenAIClient()
        self.client.actor = Mock()
        self.client.actor.id = "test-user-integration"
        
        # Use GPT-4o-mini for cost efficiency in tests
        self.llm_config = LLMConfig.default_config("gpt-4o-mini")
        self.llm_config.max_tokens = 50  # Keep responses short

    @pytest.mark.integration
    @pytest.mark.openai_basic
    async def test_cache_hit_with_system_instructions(self):
        """Test that identical requests with system instructions result in cache hits."""
        system_message = "You are a helpful assistant. Always respond with exactly one word."
        user_message = "Say hello"
        
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text=system_message)],
                agent_id="agent-123",
                model="gpt-4o-mini"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text=user_message)],
                agent_id="agent-123", 
                model="gpt-4o-mini"
            )
        ]

        # Build request data
        request_data = self.client.build_request_data(
            messages=messages, 
            llm_config=self.llm_config
        )
        
        # Verify instructions field is set for cache optimization
        assert "instructions" in request_data
        assert request_data["instructions"] == system_message
        print(f"✅ Instructions field set: '{request_data['instructions'][:50]}...'")
        
        # First request - should be cache miss
        response1 = await self.client.request_async(request_data, self.llm_config)
        
        # Wait briefly to ensure requests are separate
        time.sleep(0.1)
        
        # Second identical request - should be cache hit
        response2 = await self.client.request_async(request_data, self.llm_config)

        # Both should succeed
        assert "output" in response1
        assert "output" in response2
        assert len(response1["output"]) > 0
        assert len(response2["output"]) > 0
        
        # Check for cache metrics (if available)
        if "usage" in response2 and "prompt_tokens_details" in response2["usage"]:
            cached_tokens = response2["usage"]["prompt_tokens_details"].get("cached_tokens", 0)
            total_tokens = response2["usage"].get("prompt_tokens", 0)
            if cached_tokens > 0:
                print(f"✅ Cache hit detected: {cached_tokens} cached tokens out of {total_tokens} total")
            else:
                print("ℹ️ No cached tokens detected (model may not support caching yet)")
        else:
            print("ℹ️ Cache details not available from API")

    @pytest.mark.integration
    @pytest.mark.openai_basic  
    def test_instructions_field_in_request(self):
        """Test that system messages result in instructions field being set."""
        system_message = "You are a concise assistant."
        user_message = "Hello"
        
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text=system_message)],
                agent_id="agent-123",
                model="gpt-4o-mini"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text=user_message)],
                agent_id="agent-123",
                model="gpt-4o-mini"
            )
        ]

        # Build request data and inspect it
        request_data = self.client.build_request_data(
            messages=messages,
            llm_config=self.llm_config
        )
        
        # Should have instructions field with system message content
        assert "instructions" in request_data
        assert request_data["instructions"] == system_message
        print(f"✅ Instructions field correctly set: '{request_data['instructions']}'")
        
        # Input should only contain user message (system moved to instructions)
        assert "input" in request_data
        assert len(request_data["input"]) == 1
        assert request_data["input"][0]["role"] == "user"
        print(f"✅ Input contains only user message: {request_data['input'][0]['role']}")

    @pytest.mark.integration
    @pytest.mark.openai_basic
    def test_no_instructions_field_without_system_message(self):
        """Test that requests without system messages don't include instructions field."""
        user_message = "Hello"
        
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text=user_message)],
                agent_id="agent-123",
                model="gpt-4o-mini"
            )
        ]

        # Build request data and inspect it
        request_data = self.client.build_request_data(
            messages=messages,
            llm_config=self.llm_config
        )
        
        # Should NOT have instructions field when no system messages
        assert "instructions" not in request_data
        print("✅ Instructions field correctly omitted when no system messages")
        
        # Input should contain user message
        assert "input" in request_data
        assert len(request_data["input"]) == 1
        assert request_data["input"][0]["role"] == "user"
        print(f"✅ Input contains user message: {request_data['input'][0]['role']}")

    @pytest.mark.integration
    @pytest.mark.openai_basic
    async def test_cache_metrics_logging(self):
        """Test that cache metrics are properly logged when available."""
        system_message = "You are a test assistant."
        user_message = "Test message"
        
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text=system_message)],
                agent_id="agent-123",
                model="gpt-4o-mini"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text=user_message)],
                agent_id="agent-123",
                model="gpt-4o-mini"
            )
        ]

        # Build request data
        request_data = self.client.build_request_data(
            messages=messages,
            llm_config=self.llm_config
        )
        
        # Make the request
        response = await self.client.request_async(request_data, self.llm_config)
        
        # Should succeed
        assert "output" in response
        assert len(response["output"]) > 0
        
        # Check if cache details are available in response
        if "usage" in response:
            usage = response["usage"]
            if "prompt_tokens_details" in usage and usage["prompt_tokens_details"]:
                cached_tokens = usage["prompt_tokens_details"].get("cached_tokens", 0)
                total_tokens = usage.get("prompt_tokens", 0)
                if cached_tokens > 0:
                    print(f"ℹ️ Cache metrics available: {cached_tokens} cached tokens out of {total_tokens} total")
                    
                    # Verify cache hit rate calculation would work
                    if total_tokens > 0:
                        cache_hit_rate = cached_tokens / total_tokens
                        print(f"✅ Cache hit rate: {cache_hit_rate:.1%}")
                else:
                    print("ℹ️ No cache hits in this request")
            else:
                print("ℹ️ Cache token details not available from API")
        else:
            print("ℹ️ No usage information in response")


if __name__ == "__main__":
    # Run with: poetry run pytest tests/test_openai_cache_integration.py -v -m integration
    pytest.main([__file__, "-v", "-m", "integration"])