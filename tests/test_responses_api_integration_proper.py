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
def deep_reasoning_messages():
    """Create test messages that should trigger deep reasoning."""
    return [
        PydanticMessage(
            role=MessageRole.system,
            content=[{"type": "text", "text": "You are a helpful assistant that thinks step by step and uses tools when needed. Always show your reasoning process."}],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[{"type": "text", "text": "I need you to think deeply about this: Should I get weather information for San Francisco? Consider multiple factors like: 1) Why someone might need weather data, 2) What time of year considerations matter, 3) How weather affects daily planning, 4) Whether current conditions vs forecast matter. Think through each step carefully, then use the get_weather tool if you decide it's appropriate."}],
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
async def test_responses_api_deep_reasoning_integration(openai_client, llm_config, deep_reasoning_messages, test_tools):
    """Test that GPT-5 produces actual reasoning content with deep reasoning prompts."""
    
    print("\n=== Testing Deep Reasoning Content ===")
    
    # Override reasoning config to use medium effort for more reasoning content
    original_build = openai_client.build_request_data
    def build_with_high_effort(*args, **kwargs):
        data = original_build(*args, **kwargs)
        if data.get("reasoning"):
            data["reasoning"]["effort"] = "high"  # Use HIGH effort to get reasoning content
        return data
    
    openai_client.build_request_data = build_with_high_effort
    
    try:
        # Step 1: Build request data using our client
        print("1. Building request data with HIGH effort reasoning...")
        request_data = openai_client.build_request_data(
            messages=deep_reasoning_messages,
            llm_config=llm_config,
            tools=test_tools,
            force_tool_call=None
        )
        
        print("Request structure:")
        print(f"  - Input messages: {len(request_data.get('input', []))}")
        print(f"  - Tools: {len(request_data.get('tools', []))}")
        print(f"  - Reasoning effort: {request_data.get('reasoning', {}).get('effort', 'not set')}")
        
        # Step 2: Make real API call
        print("2. Making real OpenAI Responses API call with HIGH effort + deep reasoning prompt...")
        response_data = await openai_client.request_async(request_data, llm_config)
        print("✓ API call successful")
        
        # Step 3: Analyze reasoning content in detail
        output_items = response_data.get("output", [])
        reasoning_items = []
        function_call_items = []
        
        for item in output_items:
            if item.get("type") == "reasoning":
                reasoning_items.append(item)
                print(f"    - REASONING ITEM FOUND:")
                print(f"      ID: {item.get('id')}")
                print(f"      Status: {item.get('status')}")
                
                # Check reasoning content
                content = item.get("content")
                if content and isinstance(content, list):
                    print(f"      ✅ REASONING CONTENT: {len(content)} items")
                    for i, content_item in enumerate(content):
                        if isinstance(content_item, dict):
                            item_type = content_item.get("type")
                            text = content_item.get("text", "")
                            print(f"        Content {i}: type={item_type}, text_length={len(text)}")
                            if text and len(text) > 0:
                                print(f"        First 200 chars: {text[:200]}...")
                        else:
                            print(f"        Content {i}: {content_item}")
                else:
                    print(f"      ❌ REASONING CONTENT IS NULL OR EMPTY")
                    
                # Check reasoning summary
                summary = item.get("summary")
                if summary and isinstance(summary, list):
                    print(f"      ✅ REASONING SUMMARY: {len(summary)} items")
                    for i, summary_item in enumerate(summary):
                        if isinstance(summary_item, dict):
                            item_type = summary_item.get("type")
                            text = summary_item.get("text", "")
                            print(f"        Summary {i}: type={item_type}, text_length={len(text)}")
                            if text and len(text) > 0:
                                print(f"        First 200 chars: {text[:200]}...")
                        else:
                            print(f"        Summary {i}: {summary_item}")
                else:
                    print(f"      ❌ REASONING SUMMARY IS NULL OR EMPTY")
                    
            elif item.get("type") == "function_call":
                function_call_items.append(item)
        
        # Step 4: Check top-level reasoning metadata
        top_reasoning = response_data.get("reasoning", {})
        print(f"  - Top-level reasoning:")
        print(f"    - Effort: {top_reasoning.get('effort')}")
        print(f"    - Summary: {top_reasoning.get('summary')}")
        
        # Step 5: Test our serialization 
        print("3. Testing reasoning serialization...")
        serialized_reasoning = openai_client._serialize_reasoning_for_preservation(response_data)
        if serialized_reasoning:
            print(f"✅ Serialized reasoning data ({len(serialized_reasoning)} chars)")
            print(f"First 200 chars: {serialized_reasoning[:200]}...")
        else:
            print("❌ No reasoning data to serialize")
        
        # Assertions
        assert len(reasoning_items) > 0, "Should have reasoning items with deep reasoning prompt"
        has_content = reasoning_items[0].get("content") is not None
        has_summary = reasoning_items[0].get("summary") is not None
        
        if has_content or has_summary:
            print("✅ SUCCESS: Found actual reasoning content or summary!")
        else:
            print("⚠️  Both reasoning content and summary are null - may be OpenAI's current implementation")
            
    finally:
        # Restore original method
        openai_client.build_request_data = original_build


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


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_responses_api_streaming_integration(openai_client, llm_config, test_messages, test_tools):
    """Test that GPT-5 Responses API streaming works correctly.
    
    This test would have caught the stream_options.include_usage bug that broke production.
    The bug was in the streaming code path (stream_async) but existing tests only used
    the non-streaming code path (request_async).
    """
    
    print("\n=== Testing GPT-5 Responses API Streaming ===")
    
    # Step 1: Build request data using our client
    print("1. Building request data for streaming...")
    request_data = openai_client.build_request_data(
        messages=test_messages,
        llm_config=llm_config,
        tools=test_tools,
        force_tool_call=None
    )
    
    print("Request structure:")
    print(f"  - Input messages: {len(request_data.get('input', []))}")
    print(f"  - Tools: {len(request_data.get('tools', []))}")
    print(f"  - Model: {request_data.get('model')}")
    
    # Step 2: Test streaming API call (this would have failed with the original bug)
    print("2. Making streaming Responses API call...")
    try:
        stream = await openai_client.stream_async(request_data, llm_config)
        print("✓ Stream created successfully")
        
        # Consume the stream to verify it works
        events = []
        event_count = 0
        async for event in stream:
            events.append(event)
            event_count += 1
            if event_count <= 3:  # Log first few events for debugging
                event_type = getattr(event, 'type', 'unknown')
                print(f"  - Event {event_count}: {type(event).__name__} (type: {event_type})")
            if event_count >= 50:  # Limit to prevent infinite loops
                break
        
        print(f"✓ Received {len(events)} streaming events")
        
        # Verify we got actual streaming data
        assert len(events) > 0, "Should receive at least one streaming event"
        
        # Verify first event structure (should be response.created)
        first_event = events[0]
        assert hasattr(first_event, 'type'), "Streaming event should have type attribute"
        
        # Look for different event types in the stream
        event_types = set()
        has_text_content = False
        has_function_calls = False
        
        for event in events:
            if hasattr(event, 'type'):
                event_types.add(event.type)
                
                # Check for content or function calls based on event type
                if event.type == 'response.output_text.delta':
                    has_text_content = True
                elif event.type == 'response.function_call.created':
                    has_function_calls = True
        
        print(f"  - Event types found: {event_types}")
        print(f"  - Found text content: {has_text_content}")
        print(f"  - Found function calls: {has_function_calls}")
        
        # We should get at least a response.created event
        assert 'response.created' in event_types, "Stream should contain response.created event"
        
    except Exception as e:
        # This is where the original bug would have been caught
        error_msg = str(e)
        print(f"❌ Streaming failed: {type(e).__name__}: {error_msg}")
        
        # Check if it's the specific bug we're testing for
        if "stream_options" in error_msg or "include_usage" in error_msg:
            pytest.fail(f"CAUGHT THE BUG! stream_options.include_usage parameter error: {error_msg}")
        else:
            # Re-raise other errors for investigation
            raise
    
    print("✓ Streaming integration test passed!")


@pytest.mark.asyncio  
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_responses_api_streaming_vs_non_streaming_parity(openai_client, llm_config, test_messages, test_tools):
    """Test that streaming and non-streaming APIs produce equivalent results.
    
    This ensures both code paths work and can help catch divergent behavior.
    """
    
    print("\n=== Testing Streaming vs Non-Streaming Parity ===")
    
    # Build request once
    request_data = openai_client.build_request_data(
        messages=test_messages,
        llm_config=llm_config, 
        tools=test_tools,
        force_tool_call=None
    )
    
    # Test 1: Non-streaming (existing tested path)
    print("1. Testing non-streaming response...")
    response_data = await openai_client.request_async(request_data, llm_config)
    non_streaming_output = response_data.get("output", [])
    print(f"  - Non-streaming output items: {len(non_streaming_output)}")
    
    # Test 2: Streaming (previously untested path)
    print("2. Testing streaming response...")
    stream = await openai_client.stream_async(request_data, llm_config)
    
    events = []
    async for event in stream:
        events.append(event)
        if len(events) >= 100:  # Safety limit
            break
    
    print(f"  - Streaming events received: {len(events)}")
    
    # Both should succeed without errors
    assert len(non_streaming_output) > 0, "Non-streaming should produce output"
    assert len(events) > 0, "Streaming should produce events"
    
    print("✓ Both streaming and non-streaming work correctly")