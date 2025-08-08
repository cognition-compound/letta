"""
Test that Responses API tool schemas are properly formatted for strict mode compatibility.

This test ensures that the fix for OpenAI Responses API strict mode requirements
is working correctly and prevents regression of the agent silence issue.
"""

import pytest

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage, MessageRole


def create_test_tool():
    """Create a simple test tool definition."""
    return {
        "name": "send_message",
        "description": "Send a message to the user",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to send to the user"
                }
            },
            "required": ["message"]
        }
    }


def create_complex_test_tool():
    """Create a more complex tool to test strict mode handling."""
    return {
        "name": "update_memory",
        "description": "Update core memory",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Memory section to update",
                    "enum": ["persona", "human"]
                },
                "content": {
                    "type": "string", 
                    "description": "Content to update"
                },
                "append": {
                    "type": "boolean",
                    "description": "Whether to append or replace"
                }
            },
            "required": ["section", "content"]
        }
    }


def create_test_messages():
    """Create test message history."""
    return [
        PydanticMessage(
            role=MessageRole.system,
            content=[{"type": "text", "text": "You are a helpful assistant."}],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[{"type": "text", "text": "Hello!"}],
            agent_id="test-agent"
        )
    ]


class TestResponsesAPIStrictMode:
    """Test Responses API strict mode compatibility."""

    def test_simple_tool_strict_mode_compliance(self):
        """Test that simple tools are made strict mode compliant."""
        client = OpenAIClient()
        llm_config = LLMConfig(
            model="gpt-4o",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=128000
        )
        
        messages = create_test_messages()
        tools = [create_test_tool()]
        
        request_data = client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            force_tool_call=None
        )
        
        # Verify request structure
        assert "tools" in request_data
        assert len(request_data["tools"]) == 1
        
        tool = request_data["tools"][0]
        
        # Test strict mode requirements
        assert tool["strict"] is True, "Tool must have strict=True"
        assert tool["parameters"]["additionalProperties"] is False, "Must have additionalProperties=False for strict mode"
        
        # Test all properties are required
        properties = set(tool["parameters"]["properties"].keys())
        required = set(tool["parameters"]["required"])
        assert properties == required, f"All properties must be required in strict mode. Properties: {properties}, Required: {required}"
        
        # Test basic structure
        assert tool["type"] == "function"
        assert tool["name"] == "send_message"
        assert "description" in tool
        assert tool["parameters"]["type"] == "object"

    def test_complex_tool_strict_mode_compliance(self):
        """Test that complex tools with optional parameters are made strict mode compliant."""
        client = OpenAIClient()
        llm_config = LLMConfig(
            model="gpt-4o",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=128000
        )
        
        messages = create_test_messages()
        tools = [create_complex_test_tool()]
        
        request_data = client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            force_tool_call=None
        )
        
        tool = request_data["tools"][0]
        
        # Test strict mode requirements
        assert tool["strict"] is True
        assert tool["parameters"]["additionalProperties"] is False
        
        # Test that ALL properties are made required (strict mode requirement)
        properties = set(tool["parameters"]["properties"].keys())
        required = set(tool["parameters"]["required"])
        assert properties == required, "Strict mode requires all properties to be required"
        
        # Should include the originally optional 'append' parameter
        assert "append" in required, "Optional parameters should be made required for strict mode"
        assert len(required) == 3, f"Expected 3 required parameters, got {len(required)}: {required}"

    def test_multiple_tools_strict_mode_compliance(self):
        """Test that multiple tools are all made strict mode compliant."""
        client = OpenAIClient()
        llm_config = LLMConfig(
            model="gpt-4o",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=128000
        )
        
        messages = create_test_messages()
        tools = [create_test_tool(), create_complex_test_tool()]
        
        request_data = client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            force_tool_call=None
        )
        
        assert len(request_data["tools"]) == 2
        
        for i, tool in enumerate(request_data["tools"]):
            # Each tool must be strict mode compliant
            assert tool["strict"] is True, f"Tool {i} must have strict=True"
            assert tool["parameters"]["additionalProperties"] is False, f"Tool {i} must have additionalProperties=False"
            
            properties = set(tool["parameters"]["properties"].keys())
            required = set(tool["parameters"]["required"])
            assert properties == required, f"Tool {i}: all properties must be required. Properties: {properties}, Required: {required}"

    def test_tool_choice_preserved(self):
        """Test that tool_choice parameter is preserved with strict mode."""
        client = OpenAIClient()
        llm_config = LLMConfig(
            model="gpt-4o",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=128000
        )
        
        messages = create_test_messages()
        tools = [create_test_tool()]
        
        # Test default tool_choice
        request_data = client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            force_tool_call=None
        )
        
        assert request_data["tool_choice"] == "required", "Default tool_choice should be 'required'"
        
        # Test specific function forcing
        request_data = client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            force_tool_call="send_message"
        )
        
        expected_choice = {"type": "function", "function": {"name": "send_message"}}
        assert request_data["tool_choice"] == expected_choice, "Forced tool choice should work with strict mode"

    def test_no_tools_no_strict_mode_applied(self):
        """Test that when no tools are provided, no strict mode processing occurs."""
        client = OpenAIClient()
        llm_config = LLMConfig(
            model="gpt-4o",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=128000
        )
        
        messages = create_test_messages()
        
        request_data = client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=None,
            force_tool_call=None
        )
        
        # Should not have tools or tool_choice
        assert "tools" not in request_data
        assert "tool_choice" not in request_data
        assert "parallel_tool_calls" not in request_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])