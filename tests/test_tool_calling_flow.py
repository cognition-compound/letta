"""
Test complete tool calling flow for Responses API.

This test validates the entire conversation flow:
1. User asks for tool usage
2. Model responds with function calls 
3. Tool results are provided back
4. Model gives final response

Based on official OpenAI Responses API example.
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


@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
def test_complete_tool_calling_flow():
    """Test complete tool calling flow matching OpenAI Responses API example."""
    
    # API key must be set via environment variable OPENAI_API_KEY
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY environment variable not set")
    
    # Setup client
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-user-123"
    
    # GPT-5 config for tool calling
    llm_config = LLMConfig(
        model="gpt-5",
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=400000,
        max_tokens=200,
        temperature=0.0  # Deterministic for testing
    )
    
    # Define test tool (same as official example)
    tools = [{
        "type": "function",
        "name": "get_horoscope", 
        "description": "Get today's horoscope for an astrological sign.",
        "parameters": {
            "type": "object",
            "properties": {
                "sign": {
                    "type": "string",
                    "description": "An astrological sign like Taurus or Aquarius"
                }
            },
            "required": ["sign"]
        }
    }]
    
    # 1. Initial user message (same as official example)
    initial_messages = [
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="What is my horoscope? I am an Aquarius.")],
            agent_id="test-agent",
            model="gpt-5"
        )
    ]
    
    print("=== STEP 1: Initial request with tools ===")
    
    # Build request with tools
    request_data = client.build_request_data(initial_messages, llm_config, tools=tools)
    
    # Validate request structure
    assert "tools" in request_data
    assert len(request_data["tools"]) == 1
    assert request_data["tools"][0]["name"] == "get_horoscope"
    
    # Make initial request
    response_data = client.request(request_data, llm_config)
    
    print(f"Initial response keys: {list(response_data.keys())}")
    print(f"Output items: {len(response_data.get('output', []))}")
    
    # Validate response structure
    assert "id" in response_data
    assert "output" in response_data
    
    # Look for function calls in output
    function_calls = []
    for item in response_data["output"]:
        if item.get("type") == "function_call":
            function_calls.append(item)
            print(f"Found function call: {item.get('name')} with call_id: {item.get('call_id')}")
    
    # Should have at least one function call
    assert len(function_calls) > 0, f"Expected function calls, got output: {response_data['output']}"
    
    # 2. Execute function and prepare result
    print("=== STEP 2: Execute function ===")
    
    function_call = function_calls[0]
    arguments = json.loads(function_call["arguments"])
    print(f"Function arguments: {arguments}")
    
    # Mock function execution (same as official example)
    def get_horoscope(sign):
        return f"{sign}: Next Tuesday you will befriend a baby otter."
    
    result = {"horoscope": get_horoscope(arguments["sign"])}
    print(f"Function result: {result}")
    
    # 3. Build follow-up conversation with function result
    print("=== STEP 3: Follow-up request with function result ===")
    
    # This is the KEY part - how to properly format the conversation history
    # Based on official example: input_list += response.output + function result
    
    # Create messages representing the full conversation:
    # 1. Original user message
    # 2. Assistant message with function call (from response.output) 
    # 3. Function result
    
    follow_up_messages = [
        # Original user message
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="What is my horoscope? I am an Aquarius.")],
            agent_id="test-agent",
            model="gpt-5"
        ),
        # Assistant message with tool call (this needs proper conversion)
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text="I'll get your horoscope using the horoscope tool.")],
            agent_id="test-agent", 
            model="gpt-5",
            tool_calls=[{
                "id": function_call["call_id"],
                "type": "function",
                "function": {
                    "name": function_call["name"],
                    "arguments": function_call["arguments"]
                }
            }]
        ),
        # Tool result 
        PydanticMessage(
            role=MessageRole.tool,
            content=[TextContent(text=json.dumps(result))],
            agent_id="test-agent",
            model="gpt-5",
            tool_call_id=function_call["call_id"]
        )
    ]
    
    # Build follow-up request with instructions like in the official example
    follow_up_request = client.build_request_data(follow_up_messages, llm_config, tools=tools)
    
    # Add instructions like in the official example
    follow_up_request["instructions"] = "Respond only with a horoscope generated by a tool."
    
    print(f"Follow-up input length: {len(follow_up_request['input'])}")
    for i, item in enumerate(follow_up_request["input"]):
        print(f"Input[{i}]: {item.get('type', item.get('role'))} - {list(item.keys())}")
    
    # Make follow-up request
    final_response = client.request(follow_up_request, llm_config)
    
    print("=== STEP 4: Validate final response ===")
    
    # Convert to chat completion format
    chat_response = client.convert_response_to_chat_completion(
        final_response, follow_up_messages, llm_config
    )
    
    # Validate final response
    assert len(chat_response.choices) == 1
    message = chat_response.choices[0].message
    assert message.content is not None
    
    print(f"✅ Final response: {message.content}")
    
    # The response should contain the horoscope information
    assert "Aquarius" in message.content or "otter" in message.content
    
    print("🎉 Complete tool calling flow test passed!")


if __name__ == "__main__":
    test_complete_tool_calling_flow()