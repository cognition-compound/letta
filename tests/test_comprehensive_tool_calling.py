"""
Comprehensive end-to-end tool calling tests for OpenAI Responses API.

This validates that the complete tool calling flow works:
1. User request → 2. Model function call → 3. Function execution → 4. Result incorporation

Focus: Proving the model actually USES function results in meaningful responses.
"""

import os
import pytest
import json
from unittest.mock import Mock

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent


class ToolCallingTestSuite:
    """Comprehensive tool calling test suite."""
    
    def __init__(self):
        # Ensure API key is set via environment variable
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY environment variable not set")
        
        # Setup client
        self.client = OpenAIClient()
        self.client.actor = Mock()
        self.client.actor.id = "test-user-123"
    
    def get_llm_config(self, model="gpt-4o", max_tokens=300):
        """Get LLM config for testing."""
        return LLMConfig(
            model=model,
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1", 
            context_window=128000 if "gpt-4o" in model else 400000,
            max_tokens=max_tokens,
            temperature=0.1  # Low temperature for consistency
        )
    
    def execute_complete_flow(self, model, user_message, tools, expected_function, validation_func):
        """Execute complete tool calling flow and validate results."""
        
        print(f"\n=== TESTING {model.upper()} COMPLETE FLOW ===")
        
        # 1. Initial request
        llm_config = self.get_llm_config(model)
        initial_messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text=user_message)],
                agent_id="test-agent",
                model=model
            )
        ]
        
        print(f"1. Making initial request: '{user_message}'")
        request_data = self.client.build_request_data(initial_messages, llm_config, tools=tools)
        response_data = self.client.request(request_data, llm_config)
        
        # 2. Find and execute function calls
        function_calls = [item for item in response_data["output"] if item.get("type") == "function_call"]
        assert len(function_calls) > 0, f"Expected function calls, got: {response_data['output']}"
        
        function_call = function_calls[0]  
        assert function_call["name"] == expected_function, f"Expected {expected_function}, got {function_call['name']}"
        
        print(f"2. Found function call: {function_call['name']} with args: {function_call['arguments']}")
        
        # Execute function (mock implementation)
        arguments = json.loads(function_call["arguments"])
        function_result = self.mock_function_execution(function_call["name"], arguments)
        
        print(f"3. Function result: {function_result}")
        
        # 3. Build follow-up following the official OpenAI example pattern
        # input_list += response.output + function_call_output
        
        # Start with original user message
        input_list = [{
            "role": "user",
            "content": [{"type": "input_text", "text": user_message}]
        }]
        
        # Use official OpenAI pattern: input_list += response.output
        print("DEBUG: Output items (clean OpenAI format):")
        for i, item in enumerate(response_data["output"]):
            print(f"  [{i}] {item.get('type')}: {list(item.keys())}")
        
        # Direct extend (official pattern) - should work now with clean format
        input_list.extend(response_data["output"])
        
        # Add function call output 
        input_list.append({
            "type": "function_call_output",
            "call_id": function_call["call_id"],
            "output": json.dumps(function_result)
        })
        
        print(f"DEBUG: Input list for follow-up ({len(input_list)} items):")
        for i, item in enumerate(input_list):
            item_type = item.get('type', item.get('role', 'unknown'))
            print(f"  [{i}] {item_type}: {list(item.keys())}")
        
        # Build follow-up request manually (bypass message conversion)
        follow_up_request = {
            "model": model,
            "input": input_list,
            "tools": tools,
            "max_output_tokens": llm_config.max_tokens,
            "instructions": f"You MUST use the exact result from the {expected_function} function call in your response. Include the specific data returned by the function."
        }
        
        # Only add temperature for models that support it (GPT-5 doesn't)
        if "gpt-5" not in model.lower():
            follow_up_request["temperature"] = llm_config.temperature
        
        print("4. Making follow-up request with function result")
        final_response = self.client.request(follow_up_request, llm_config)
        
        # Debug the raw response
        print(f"DEBUG: Final response keys: {list(final_response.keys())}")
        print(f"DEBUG: Final response output: {final_response.get('output', [])}")
        print(f"DEBUG: Final response status: {final_response.get('status', 'unknown')}")
        
        # 4. Validate final response - create dummy messages for conversion
        dummy_messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text=user_message)],
                agent_id="test-agent",
                model=model
            )
        ]
        chat_response = self.client.convert_response_to_chat_completion(
            final_response, dummy_messages, llm_config
        )
        
        message = chat_response.choices[0].message
        print(f"5. Final response: {message.content}")
        
        # 5. Validate response contains function result
        validation_result = validation_func(message.content, function_result)
        
        print(f"6. Validation: {'✅ PASSED' if validation_result else '❌ FAILED'}")
        
        return {
            "model": model,
            "success": validation_result,
            "function_result": function_result, 
            "final_response": message.content,
            "reasoning_content": getattr(message, 'reasoning_content', None)
        }
    
    def clean_output_items_for_input(self, output_items):
        """Clean response output items to only include fields valid for input."""
        cleaned_items = []
        
        for item in output_items:
            item_type = item.get("type")
            
            if item_type == "reasoning":
                # Keep only essential fields for reasoning input
                cleaned_item = {
                    "type": "reasoning",
                    "content": item.get("content", "")
                }
                cleaned_items.append(cleaned_item)
            
            elif item_type == "function_call":
                # Keep only essential fields for function_call input
                cleaned_item = {
                    "type": "function_call", 
                    "call_id": item.get("call_id"),
                    "name": item.get("name"),
                    "arguments": item.get("arguments")
                }
                cleaned_items.append(cleaned_item)
            
            elif item_type == "message":
                # Keep message items as-is but clean any extra fields
                cleaned_item = {
                    "type": "message",
                    "role": item.get("role", "assistant"),
                    "content": item.get("content", [])
                }
                cleaned_items.append(cleaned_item)
            
            else:
                # For other types, include as-is but log for debugging
                print(f"DEBUG: Unknown output item type: {item_type}")
                cleaned_items.append(item)
        
        return cleaned_items
    
    def mock_function_execution(self, function_name, arguments):
        """Mock function execution with predictable results."""
        
        if function_name == "get_current_time":
            return {"current_time": "2025-08-08 15:30:45", "timezone": "UTC"}
            
        elif function_name == "calculate_simple":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result = a + b
            return {"calculation": f"{a} + {b} = {result}", "result": result}
            
        elif function_name == "get_weather":
            location = arguments.get("location", "Unknown")
            return {
                "location": location,
                "temperature": 72,
                "condition": "sunny", 
                "forecast": f"The weather in {location} is 72°F and sunny"
            }
        
        return {"error": "Unknown function"}


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
def test_simple_calculation_gpt4o():
    """Test simple calculation function calling with GPT-4o."""
    
    suite = ToolCallingTestSuite()
    
    tools = [{
        "type": "function",
        "name": "calculate_simple",
        "description": "Add two numbers together",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    }]
    
    def validate_calculation(response_content, function_result):
        """Validate response contains the calculation result."""
        expected_result = str(function_result["result"]) 
        calculation_text = function_result["calculation"]
        
        # Response should contain either the result number or the full calculation
        return (expected_result in response_content or 
                calculation_text in response_content or
                str(function_result["result"]) in response_content)
    
    result = suite.execute_complete_flow(
        model="gpt-4o",
        user_message="What is 15 + 27? Use the calculator function.",
        tools=tools,
        expected_function="calculate_simple",
        validation_func=validate_calculation
    )
    
    assert result["success"], f"GPT-4o calculation test failed: {result}"


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
def test_simple_calculation_gpt5():
    """Test simple calculation function calling with GPT-5."""
    
    suite = ToolCallingTestSuite()
    
    tools = [{
        "type": "function", 
        "name": "calculate_simple",
        "description": "Add two numbers together",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    }]
    
    def validate_calculation(response_content, function_result):
        """Validate response contains the calculation result."""
        expected_result = str(function_result["result"])
        calculation_text = function_result["calculation"]
        
        return (expected_result in response_content or 
                calculation_text in response_content)
    
    result = suite.execute_complete_flow(
        model="gpt-5",
        user_message="What is 15 + 27? Use the calculator function.",
        tools=tools,
        expected_function="calculate_simple", 
        validation_func=validate_calculation
    )
    
    assert result["success"], f"GPT-5 calculation test failed: {result}"


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
def test_time_function_gpt4o():
    """Test time function calling with GPT-4o."""
    
    suite = ToolCallingTestSuite()
    
    tools = [{
        "type": "function",
        "name": "get_current_time",
        "description": "Get the current date and time",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }]
    
    def validate_time(response_content, function_result):
        """Validate response contains the time information."""
        time_str = function_result["current_time"] 
        timezone = function_result["timezone"]
        
        # Should contain either the exact time or timezone info
        return (time_str in response_content or 
                timezone in response_content or
                "15:30" in response_content or  # Part of the time
                "2025-08-08" in response_content)  # Part of the date
    
    result = suite.execute_complete_flow(
        model="gpt-4o",
        user_message="What time is it? Please use the time function.",
        tools=tools,
        expected_function="get_current_time",
        validation_func=validate_time
    )
    
    assert result["success"], f"GPT-4o time test failed: {result}"


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic 
def test_weather_function_gpt5():
    """Test weather function calling with GPT-5."""
    
    suite = ToolCallingTestSuite()
    
    tools = [{
        "type": "function",
        "name": "get_weather", 
        "description": "Get weather information for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"]
        }
    }]
    
    def validate_weather(response_content, function_result):
        """Validate response contains weather information."""
        location = function_result["location"]
        temperature = str(function_result["temperature"])
        condition = function_result["condition"]
        
        return (location in response_content or 
                temperature in response_content or
                condition in response_content or
                "72" in response_content or  # Temperature value
                "sunny" in response_content)
    
    result = suite.execute_complete_flow(
        model="gpt-5",
        user_message="What's the weather like in Paris? Use the weather function.",
        tools=tools,
        expected_function="get_weather",
        validation_func=validate_weather
    )
    
    assert result["success"], f"GPT-5 weather test failed: {result}"


if __name__ == "__main__":
    # Run individual tests for debugging
    test_simple_calculation_gpt4o()
    print("✅ GPT-4o calculation test passed")
    
    test_simple_calculation_gpt5()  
    print("✅ GPT-5 calculation test passed")
    
    test_time_function_gpt4o()
    print("✅ GPT-4o time test passed")
    
    test_weather_function_gpt5()
    print("✅ GPT-5 weather test passed")
    
    print("\n🎉 All comprehensive tool calling tests passed!")