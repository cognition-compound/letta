"""
Integration test for OpenAI Responses API tool calling format.
Tests actual request/response with real OpenAI API.
"""

import json
import pytest
from unittest.mock import Mock

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage, MessageRole
from letta.settings import model_settings


@pytest.fixture
def openai_client():
    """Create OpenAI client with mock actor."""
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-actor-123"
    return client


@pytest.fixture  
def llm_config():
    """Create LLM config for gpt-5."""
    return LLMConfig(
        model="gpt-5",
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1", 
        context_window=128000,
        max_tokens=1000
    )


@pytest.fixture
def test_messages():
    """Create test message history."""
    return [
        PydanticMessage(
            role=MessageRole.system,
            content=[{"type": "text", "text": "You are a helpful assistant that uses tools when asked."}],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[{"type": "text", "text": "What's the weather in San Francisco?"}],
            agent_id="test-agent"
        )
    ]


@pytest.fixture
def test_tools():
    """Create test tools for weather lookup."""
    return [
        {
            "name": "get_weather",
            "description": "Get current weather for a specific location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string", 
                        "description": "The city and state, e.g. San Francisco, CA"
                    },
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature units to use"
                    }
                },
                "required": ["location"]
            }
        }
    ]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_responses_api_tool_format_integration(openai_client, llm_config, test_messages, test_tools):
    """Test that our Responses API tool format works with real OpenAI API."""
    
    print("\n=== Testing Responses API Tool Format ===")
    
    # Step 1: Build request data using our client
    print("1. Building request data with OpenAI client...")
    request_data = openai_client.build_request_data(
        messages=test_messages,
        llm_config=llm_config,
        tools=test_tools,
        force_tool_call=None
    )
    
    print("Request structure:")
    print(f"  - Input messages: {len(request_data.get('input', []))}")
    print(f"  - Tools: {len(request_data.get('tools', []))}")
    print(f"  - Tool choice: {request_data.get('tool_choice')}")
    
    # Verify our tool format is FLAT (not nested)
    assert "tools" in request_data, "Request should have tools"
    assert len(request_data["tools"]) == 1, "Should have exactly one tool"
    
    tool = request_data["tools"][0]
    assert tool["type"] == "function", "Tool should be function type"
    assert "name" in tool, "Tool should have direct 'name' field (flat format)"
    assert "description" in tool, "Tool should have direct 'description' field (flat format)"  
    assert "parameters" in tool, "Tool should have direct 'parameters' field (flat format)"
    assert "function" not in tool, "Tool should NOT have nested 'function' field"
    
    # Verify strict mode compliance
    assert tool.get("strict") is True, "Tool should have strict=True"
    assert tool["parameters"].get("additionalProperties") is False, "Should have additionalProperties=False"
    required = tool["parameters"].get("required", [])
    properties = tool["parameters"].get("properties", {})
    assert len(required) == len(properties), "All properties should be required in strict mode"
    
    print("✓ Tool format validation passed")
    
    # Step 2: Make real API call 
    print("2. Making real OpenAI Responses API call...")
    try:
        response_data = await openai_client.request_async(request_data, llm_config)
        print("✓ API call successful")
        
        # Log response structure for debugging
        print("FULL RESPONSE DUMP:")
        import json
        print(json.dumps(response_data, indent=2, default=str))
        
        # Check output item types
        output_types = []
        function_calls_count = 0
        reasoning_items = []
        for item in response_data.get("output", []):
            item_type = item.get("type", "unknown")
            output_types.append(item_type)
            if item_type == "function_call":
                function_calls_count += 1
                print(f"    - Function call: {item.get('name')} with args: {item.get('arguments')}")
            elif item_type == "reasoning":
                reasoning_items.append(item)
                print(f"    - REASONING ITEM FULL DUMP:")
                import json
                print(json.dumps(item, indent=6, default=str))
                
                # Check if we have actual reasoning content now
                content = item.get("content")
                if content:
                    print(f"    ✅ REASONING CONTENT FOUND: {len(str(content))} chars")
                    print(f"    First 200 chars: {str(content)[:200]}...")
                else:
                    print(f"    ❌ REASONING CONTENT IS NULL")
        
        print(f"  - Reasoning items: {len(reasoning_items)}")
        
        # Check top-level reasoning configuration
        top_reasoning = response_data.get("reasoning", {})
        if top_reasoning:
            print(f"  - Top-level reasoning config:")
            print(f"    - Effort: {top_reasoning.get('effort', 'not set')}")
            print(f"    - Generate summary: {top_reasoning.get('generate_summary', 'not set')}")
            print(f"    - Summary: {top_reasoning.get('summary', 'not set')}")
        
        print(f"  - Output types: {output_types}")
        print(f"  - Function calls: {function_calls_count}")
        
        # Verify response structure
        assert "output" in response_data, "Response should have 'output' field"
        assert len(response_data["output"]) > 0, "Response should have output items"
        
        # With tool_choice="required", we should get function calls
        assert function_calls_count > 0, "Should get function calls with tool_choice='required'"
        
    except Exception as e:
        print(f"❌ API call failed: {type(e).__name__}: {str(e)}")
        # Try to get error details
        if hasattr(e, 'response'):
            try:
                error_body = e.response.json() if hasattr(e.response, 'json') else str(e.response.content)
                print(f"Error details: {error_body}")
            except:
                pass
        raise
    
    # Step 3: Test response conversion
    print("3. Testing response conversion...")
    chat_completion_response = openai_client.convert_response_to_chat_completion(
        response_data=response_data,
        input_messages=test_messages,
        llm_config=llm_config
    )
    
    print("Conversion results:")
    print(f"  - Choices: {len(chat_completion_response.choices)}")
    
    assert len(chat_completion_response.choices) > 0, "Should have at least one choice"
    choice = chat_completion_response.choices[0]
    message = choice.message
    
    print(f"  - Message role: {message.role}")
    print(f"  - Message content: {message.content}")
    print(f"  - Tool calls: {len(message.tool_calls) if message.tool_calls else 0}")
    
    # Verify conversion
    assert message.role == "assistant", "Message should be from assistant"
    assert message.tool_calls is not None, "Should have tool calls after conversion"
    assert len(message.tool_calls) > 0, "Should have at least one tool call"
    
    # Verify tool call structure
    tool_call = message.tool_calls[0]
    assert tool_call.type == "function", "Tool call should be function type"
    assert tool_call.function.name == "get_weather", "Tool call should be for get_weather"
    assert tool_call.function.arguments, "Tool call should have arguments"
    
    # Try to parse arguments as JSON
    try:
        args = json.loads(tool_call.function.arguments)
        assert "location" in args, "Arguments should contain location parameter"
        print(f"  - Parsed arguments: {args}")
    except json.JSONDecodeError as e:
        pytest.fail(f"Tool call arguments should be valid JSON: {e}")
    
    print("✓ Response conversion successful")
    print("✓ Integration test passed!")


@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")  
def test_tool_format_structure(openai_client, llm_config, test_messages, test_tools):
    """Test that our tool format is correct without making API calls."""
    
    request_data = openai_client.build_request_data(
        messages=test_messages,
        llm_config=llm_config,
        tools=test_tools,
        force_tool_call=None
    )
    
    # Detailed tool format verification
    tool = request_data["tools"][0]
    expected_structure = {
        "type": "function",
        "name": "get_weather", 
        "description": "Get current weather for a specific location",
        "parameters": dict,
        "strict": True
    }
    
    for key, expected_value in expected_structure.items():
        assert key in tool, f"Tool should have '{key}' field"
        if not callable(expected_value):
            assert tool[key] == expected_value, f"Tool '{key}' should be {expected_value}"
        else:
            assert isinstance(tool[key], expected_value), f"Tool '{key}' should be type {expected_value}"
    
    # Verify parameters structure
    params = tool["parameters"]
    assert params["type"] == "object", "Parameters should be object type"
    assert params["additionalProperties"] is False, "Should have additionalProperties=False"
    assert "properties" in params, "Parameters should have properties"
    assert "required" in params, "Parameters should have required fields"
    
    print("✓ Tool format structure test passed")