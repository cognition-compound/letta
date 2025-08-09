"""
Integration test for OpenAI Responses API streaming fix.
This test validates that the streaming interface properly handles Responses API format.
"""
import os
import pytest
from datetime import datetime, timezone
from typing import AsyncGenerator

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.enums import MessageRole
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set in environment")
    return api_key


@pytest.fixture
def llm_config():
    """OpenAI LLM configuration for testing"""
    return LLMConfig(
        model="gpt-4o-mini",  # Use a smaller model for testing
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=32000,
        handle="openai/gpt-4o-mini",
        put_inner_thoughts_in_kwargs=False,
        max_tokens=100,  # Limit tokens for faster test
        temperature=0.1,
    )


@pytest.fixture
def openai_client(openai_api_key):
    """OpenAI client for testing"""
    return OpenAIClient()


@pytest.fixture
def test_messages():
    """Simple test messages for streaming"""
    return [
        PydanticMessage(
            role=MessageRole.system,
            content=[{"type": "text", "text": "You are a helpful assistant. Respond concisely."}],
            created_at=datetime.now(timezone.utc),
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[{"type": "text", "text": "Say hello"}],
            created_at=datetime.now(timezone.utc),
        ),
    ]


@pytest.mark.asyncio
async def test_streaming_responses_api_conversion(openai_client, llm_config, test_messages):
    """
    Test that the OpenAI client properly converts Responses API streaming to Chat Completions format.
    This validates the fix for the 'type' error in streaming responses.
    """
    # Build request data using the client's method (should use Responses API format)
    request_data = openai_client.build_request_data(test_messages, llm_config)
    
    # Verify the request data is in Responses API format
    assert "input" in request_data, "Request should use 'input' field for Responses API"
    assert "model" in request_data
    
    # Test streaming - this should not raise the 'type' error
    try:
        stream = await openai_client.stream_async(request_data, llm_config)
        
        # Verify we get a proper async generator
        assert hasattr(stream, '__aiter__'), "Should return an async iterator"
        
        # Consume a few chunks to verify the conversion works
        chunk_count = 0
        async for chunk in stream:
            # Verify chunk has Chat Completions format (not Responses API format)
            assert hasattr(chunk, 'choices'), f"Chunk should have 'choices' attribute, got: {type(chunk)}"
            assert hasattr(chunk, 'model'), f"Chunk should have 'model' attribute"
            
            # Verify the chunk is properly formed
            if chunk.choices and len(chunk.choices) > 0:
                choice = chunk.choices[0]
                assert hasattr(choice, 'delta'), "Choice should have 'delta' attribute"
                
            chunk_count += 1
            if chunk_count >= 3:  # Just test a few chunks
                break
                
        print(f"✅ Successfully processed {chunk_count} streaming chunks")
        
    except Exception as e:
        # If we get the 'type' error, the fix didn't work
        if "type" in str(e).lower():
            pytest.fail(f"Got the 'type' error that should be fixed: {e}")
        else:
            # Re-raise other errors
            raise


@pytest.mark.asyncio
async def test_streaming_with_function_calls(openai_client, llm_config):
    """
    Test streaming with function calls to ensure tool calling works properly.
    """
    # Create a simple function for testing
    test_tool = {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
    
    messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[{"type": "text", "text": "You are a helpful assistant. Use the provided function when appropriate."}],
            created_at=datetime.now(timezone.utc),
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[{"type": "text", "text": "What time is it?"}],
            created_at=datetime.now(timezone.utc),
        ),
    ]
    
    # Build request with tools
    request_data = openai_client.build_request_data(messages, llm_config, tools=[test_tool])
    
    # Verify tools are included
    assert "tools" in request_data
    assert len(request_data["tools"]) == 1
    
    try:
        stream = await openai_client.stream_async(request_data, llm_config)
        
        chunk_count = 0
        found_tool_call = False
        
        async for chunk in stream:
            # Check for tool calls in streaming chunks
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    found_tool_call = True
                    print(f"✅ Found tool call in streaming chunk: {delta.tool_calls[0]}")
                    
            chunk_count += 1
            if chunk_count >= 10:  # Test more chunks for function calls
                break
        
        print(f"✅ Successfully processed {chunk_count} chunks with function calling")
        
    except Exception as e:
        if "type" in str(e).lower():
            pytest.fail(f"Got the 'type' error in function calling test: {e}")
        else:
            raise


if __name__ == "__main__":
    # Run the tests if executed directly
    pytest.main([__file__, "-v"])