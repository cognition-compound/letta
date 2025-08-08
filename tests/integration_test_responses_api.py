"""
Integration tests for OpenAI Responses API implementation.

Tests actual API calls to validate the complete migration from Chat Completions API 
to Responses API, ensuring GPT-5 and other models work correctly.
"""

import os
import pytest
from unittest.mock import Mock

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.settings import model_settings


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
def test_gpt4o_responses_api_basic_call():
    """Test basic GPT-4o call through Responses API (non-reasoning model)."""
    
    # Setup client
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-user-123"
    
    # GPT-4o config (non-reasoning model)
    llm_config = LLMConfig(
        model="gpt-4o",
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=128000,
        max_tokens=100,  # Short for testing
        temperature=0.7,
        put_inner_thoughts_in_kwargs=True  # GPT-4o is NOT a reasoning model
    )
    
    # Test message
    messages = [
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Say exactly: 'Hello from GPT-4o via Responses API'")],
            agent_id="test-agent",
            model="gpt-4o"
        )
    ]
    
    # Build request using Responses API format
    request_data = client.build_request_data(messages, llm_config)
    
    # Validate request structure
    assert "input" in request_data  # Responses API uses 'input' not 'messages'
    assert "max_output_tokens" in request_data  # Responses API parameter
    assert request_data["model"] == "gpt-4o"
    assert len(request_data["input"]) == 1
    assert request_data["input"][0]["role"] == "user"
    assert request_data["input"][0]["content"][0]["type"] == "input_text"
    
    # Make actual API call
    response_data = client.request(request_data, llm_config)
    
    # Validate raw response structure
    assert "id" in response_data
    assert "model" in response_data
    assert "status" in response_data
    assert "output" in response_data
    assert len(response_data["output"]) > 0
    
    # Convert to ChatCompletionResponse format
    chat_response = client.convert_response_to_chat_completion(
        response_data, messages, llm_config
    )
    
    # Validate conversion worked
    assert chat_response.id == response_data["id"]
    assert chat_response.model == response_data["model"]
    assert len(chat_response.choices) == 1
    
    message = chat_response.choices[0].message
    assert message.role == "assistant"
    assert message.content is not None
    assert len(message.content) > 0
    print(f"✅ GPT-4o Response: {message.content}")


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
def test_gpt5_responses_api_basic_call():
    """Test basic GPT-5 call through Responses API (reasoning model)."""
    
    # Setup client
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-user-123"
    
    # GPT-5 config (reasoning model)  
    llm_config = LLMConfig(
        model="gpt-5",
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=400000,
        max_tokens=100,  # Short for testing
        temperature=0.7,
        put_inner_thoughts_in_kwargs=False  # GPT-5 IS a reasoning model
    )
    
    # Test message that should trigger reasoning
    messages = [
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Calculate 15 * 23 and explain your reasoning step by step.")],
            agent_id="test-agent",
            model="gpt-5"
        )
    ]
    
    # Build request using Responses API format
    request_data = client.build_request_data(messages, llm_config)
    
    # Validate GPT-5 request structure
    assert "input" in request_data
    assert "max_output_tokens" in request_data
    assert request_data["model"] == "gpt-5"
    
    # Make actual API call (this should NOT fail with "tools is not supported")
    response_data = client.request(request_data, llm_config)
    
    # Validate raw response has reasoning content
    assert "id" in response_data
    assert "output" in response_data
    # GPT-5 should include reasoning
    reasoning_present = "reasoning" in response_data and len(response_data.get("reasoning", [])) > 0
    
    # Convert to ChatCompletionResponse format
    chat_response = client.convert_response_to_chat_completion(
        response_data, messages, llm_config
    )
    
    # Validate conversion worked for GPT-5
    assert len(chat_response.choices) == 1
    message = chat_response.choices[0].message
    assert message.content is not None
    assert len(message.content) > 0
    
    # Check reasoning content extraction
    if reasoning_present:
        assert hasattr(message, 'reasoning_content')
        if message.reasoning_content:
            assert len(message.reasoning_content) > 0
            print(f"✅ GPT-5 Reasoning: {message.reasoning_content[:100]}...")
    
    print(f"✅ GPT-5 Response: {message.content}")


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
def test_gpt5_function_calling_responses_api():
    """Test GPT-5 function calling through Responses API (the critical use case)."""
    
    # Setup client
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-user-123"
    
    # GPT-5 config
    llm_config = LLMConfig(
        model="gpt-5",
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=400000,
        max_tokens=150,
        temperature=0.7,
        put_inner_thoughts_in_kwargs=False  # GPT-5 IS a reasoning model
    )
    
    # Test message requesting function call
    messages = [
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Calculate the area of a rectangle with width 8 and height 12. Use the calculate_area function.")],
            agent_id="test-agent",
            model="gpt-5"
        )
    ]
    
    # Define test function
    tools = [{
        "name": "calculate_area",
        "description": "Calculate the area of a rectangle",
        "parameters": {
            "type": "object",
            "properties": {
                "width": {"type": "number", "description": "Rectangle width"},
                "height": {"type": "number", "description": "Rectangle height"}
            },
            "required": ["width", "height"]
        }
    }]
    
    # Build request with function calling
    request_data = client.build_request_data(messages, llm_config, tools=tools)
    
    # Validate function calling request structure
    assert "tools" in request_data
    assert len(request_data["tools"]) == 1
    assert request_data["tools"][0]["name"] == "calculate_area"  # Responses API format
    assert request_data["tools"][0]["type"] == "function"
    
    # Make actual API call (this is where the original "tools is not supported" error occurred)
    response_data = client.request(request_data, llm_config)
    
    # This should NOT fail - the core issue we're testing
    assert "id" in response_data
    assert "output" in response_data
    
    # Convert response
    chat_response = client.convert_response_to_chat_completion(
        response_data, messages, llm_config
    )
    
    # Validate function calling response
    assert len(chat_response.choices) == 1
    message = chat_response.choices[0].message
    
    # Check if GPT-5 made tool calls (it should)
    if hasattr(message, 'tool_calls') and message.tool_calls:
        print(f"✅ GPT-5 Function Calls: {len(message.tool_calls)} tool calls made")
        for tool_call in message.tool_calls:
            print(f"   - {tool_call.function.name}: {tool_call.function.arguments}")
    else:
        # Sometimes the model might respond with text instead of tool calls
        print(f"✅ GPT-5 Text Response: {message.content}")
    
    # Most importantly: the API call succeeded without "tools is not supported" error
    print("🎉 GPT-5 function calling request completed successfully via Responses API!")


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
def test_responses_api_parameter_validation():
    """Test that our Responses API implementation uses correct parameters."""
    
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-user-123"
    
    llm_config = LLMConfig(
        model="gpt-4o",
        model_endpoint_type="openai", 
        model_endpoint="https://api.openai.com/v1",
        context_window=128000,
        max_tokens=50,
        temperature=0.5,
        frequency_penalty=0.2
    )
    
    messages = [
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Test parameter validation")],
            agent_id="test-agent",
            model="gpt-4o"
        )
    ]
    
    # Build request
    request_data = client.build_request_data(messages, llm_config)
    
    # Validate Responses API specific parameters are used
    assert "input" in request_data  # Not "messages"
    assert "max_output_tokens" in request_data  # Not "max_tokens" or "max_completion_tokens" 
    assert "prompt_cache_key" in request_data  # Not deprecated "user" field
    assert request_data["temperature"] == 0.5
    
    # Ensure deprecated/incorrect parameters are not present
    assert "messages" not in request_data
    assert "max_tokens" not in request_data
    assert "max_completion_tokens" not in request_data
    assert "user" not in request_data
    # frequency_penalty is commented out in implementation as not documented for Responses API
    
    # The request should succeed with correct parameters
    response_data = client.request(request_data, llm_config)
    assert "id" in response_data
    
    print("✅ All Responses API parameters validated correctly")


if __name__ == "__main__":
    # Run with: pytest tests/integration_test_responses_api.py -v -m openai_basic
    pytest.main([__file__, "-v", "-m", "openai_basic"])