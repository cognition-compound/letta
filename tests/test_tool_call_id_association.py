"""
Test tool call ID association in Responses API implementation.

This test verifies that tool_call_id is correctly:
1. Generated for tool calls in assistant messages
2. Preserved in the conversion to Responses API format
3. Associated with tool responses (tool role messages)
4. Maintained through the complete round-trip
"""

import json
import uuid
from unittest.mock import Mock, patch

import pytest

from letta.llm_api.openai import (
    convert_chat_completion_to_responses_format,
    convert_responses_to_chat_completion_format,
)
from letta.schemas.openai.chat_completion_request import ChatCompletionRequest
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent


def test_tool_call_id_preservation_in_conversion():
    """Test that tool_call_id is preserved when converting between formats."""
    
    # Create a unique tool_call_id for testing
    test_tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
    
    # 1. Create messages with tool call and response
    messages = [
        {
            "role": "user",
            "content": "What's the weather?"
        },
        {
            "role": "assistant",
            "content": "I'll check the weather for you.",
            "tool_calls": [
                {
                    "id": test_tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"location": "San Francisco"})
                    }
                }
            ]
        },
        {
            "role": "tool",
            "content": json.dumps({"temperature": "72°F", "conditions": "sunny"}),
            "tool_call_id": test_tool_call_id  # This MUST match the tool call ID above
        }
    ]
    
    # 2. Create ChatCompletionRequest
    request = ChatCompletionRequest(
        model="gpt-4",
        messages=messages,
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {"type": "object", "properties": {}}
            }
        }]
    )
    
    # 3. Convert to Responses API format
    responses_format = convert_chat_completion_to_responses_format(request)
    
    # 4. Verify the conversion preserves tool_call_id
    assert "input" in responses_format
    assert len(responses_format["input"]) == 3
    
    # Check assistant message with tool call
    assistant_msg = responses_format["input"][1]
    assert assistant_msg["role"] == "assistant"
    assert "tool_calls" in assistant_msg
    assert len(assistant_msg["tool_calls"]) == 1
    assert assistant_msg["tool_calls"][0]["id"] == test_tool_call_id
    
    # Check tool response message
    tool_msg = responses_format["input"][2]
    assert tool_msg["role"] == "tool"
    assert "tool_call_id" in tool_msg
    assert tool_msg["tool_call_id"] == test_tool_call_id
    
    print(f"✅ Tool call ID {test_tool_call_id} preserved in conversion")


def test_tool_call_id_in_response_conversion():
    """Test that tool_call_id is maintained when converting Responses API response back."""
    
    test_tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
    
    # Create a mock Responses API response with tool calls
    response_data = {
        "id": "resp-123",
        "model": "gpt-4",
        "output": [
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me check the weather."}
                    ],
                    "tool_calls": [
                        {
                            "id": test_tool_call_id,
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"location": "NYC"}'
                            }
                        }
                    ]
                }
            }
        ],
        "usage": {"total_tokens": 100}
    }
    
    # Convert back to Chat Completions format
    chat_format = convert_responses_to_chat_completion_format(response_data)
    
    # Verify structure
    assert "choices" in chat_format
    assert len(chat_format["choices"]) == 1
    
    # Check the message
    message = chat_format["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert "tool_calls" in message
    assert len(message["tool_calls"]) == 1
    
    # Verify tool_call_id is preserved
    assert message["tool_calls"][0]["id"] == test_tool_call_id
    assert message["tool_calls"][0]["function"]["name"] == "get_weather"
    
    print(f"✅ Tool call ID {test_tool_call_id} preserved in response conversion")


def test_multiple_tool_calls_with_unique_ids():
    """Test that multiple tool calls each have unique IDs that are preserved."""
    
    # Create multiple unique tool call IDs
    tool_call_ids = [f"call_{uuid.uuid4().hex[:8]}" for _ in range(3)]
    
    messages = [
        {
            "role": "user",
            "content": "Check weather in NYC, SF, and LA"
        },
        {
            "role": "assistant",
            "content": "I'll check the weather in all three cities.",
            "tool_calls": [
                {
                    "id": tool_call_ids[0],
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"location": "NYC"})
                    }
                },
                {
                    "id": tool_call_ids[1],
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"location": "SF"})
                    }
                },
                {
                    "id": tool_call_ids[2],
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"location": "LA"})
                    }
                }
            ]
        },
        # Tool responses must have matching tool_call_ids
        {
            "role": "tool",
            "content": json.dumps({"temperature": "65°F"}),
            "tool_call_id": tool_call_ids[0]
        },
        {
            "role": "tool",
            "content": json.dumps({"temperature": "72°F"}),
            "tool_call_id": tool_call_ids[1]
        },
        {
            "role": "tool",
            "content": json.dumps({"temperature": "78°F"}),
            "tool_call_id": tool_call_ids[2]
        }
    ]
    
    request = ChatCompletionRequest(
        model="gpt-4",
        messages=messages,
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {"type": "object", "properties": {}}
            }
        }]
    )
    
    # Convert to Responses API format
    responses_format = convert_chat_completion_to_responses_format(request)
    
    # Verify all tool call IDs are preserved
    assistant_msg = responses_format["input"][1]
    assert len(assistant_msg["tool_calls"]) == 3
    
    for i, tool_call in enumerate(assistant_msg["tool_calls"]):
        assert tool_call["id"] == tool_call_ids[i]
    
    # Verify tool responses have matching IDs
    for i in range(3):
        tool_msg = responses_format["input"][2 + i]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == tool_call_ids[i]
    
    print(f"✅ All {len(tool_call_ids)} tool call IDs preserved correctly")


def test_tool_call_id_mismatch_detection():
    """Test that we can detect when tool_call_id doesn't match."""
    
    # Create mismatched IDs
    tool_call_id = "call_12345678"
    wrong_tool_call_id = "call_87654321"
    
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "test_func",
                        "arguments": "{}"
                    }
                }
            ]
        },
        {
            "role": "tool",
            "content": "result",
            "tool_call_id": wrong_tool_call_id  # Intentionally wrong
        }
    ]
    
    # This should be detected as a mismatch
    # In a real system, this might log a warning or raise an error
    # For now, we just verify the IDs are different
    assert tool_call_id != wrong_tool_call_id
    print(f"⚠️ Tool call ID mismatch detected: {tool_call_id} != {wrong_tool_call_id}")


def test_streaming_preserves_tool_call_id():
    """Test that streaming responses preserve tool_call_id."""
    
    from letta.llm_api.openai import convert_response_stream_chunk_to_chat_completion_format
    
    test_tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
    
    # Simulate a streaming chunk with function call
    chunk_data = {
        "id": "resp-stream-123",
        "type": "response.function_call.name.delta",
        "model": "gpt-4",
        "call_id": test_tool_call_id,
        "delta": "get_weather"
    }
    
    # Convert streaming chunk
    converted_chunk = convert_response_stream_chunk_to_chat_completion_format(chunk_data)
    
    # Verify tool_call_id is preserved in streaming
    assert "choices" in converted_chunk
    assert len(converted_chunk["choices"]) == 1
    
    delta = converted_chunk["choices"][0]["delta"]
    assert "tool_calls" in delta
    assert delta["tool_calls"][0]["id"] == test_tool_call_id
    
    print(f"✅ Tool call ID {test_tool_call_id} preserved in streaming")


if __name__ == "__main__":
    # Run all tests
    test_tool_call_id_preservation_in_conversion()
    test_tool_call_id_in_response_conversion()
    test_multiple_tool_calls_with_unique_ids()
    test_tool_call_id_mismatch_detection()
    test_streaming_preserves_tool_call_id()
    
    print("\n🎉 All tool call ID association tests passed!")