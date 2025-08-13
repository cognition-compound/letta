"""
Unit tests for OpenAI Responses API conversion logic.

Tests the conversion between Chat Completions API format and Responses API format
for proper GPT-5 support and future-proofing.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import MessageContentType, TextContent


class TestResponsesAPIConversion:
    """Test suite for Responses API conversion methods."""

    def setup_method(self):
        """Setup test fixtures."""
        self.client = OpenAIClient()
        self.client.actor = Mock()
        self.client.actor.id = "test-user-123"
        
        # Use the default config for GPT-5
        self.llm_config = LLMConfig.default_config("gpt-5")

    def test_convert_messages_to_response_input_simple(self):
        """Test converting simple text messages to Responses API format with system extraction."""
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="You are a helpful assistant.")],
                agent_id="agent-123",
                model="gpt-5"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello, how are you?")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]
        
        system_instructions, response_input = self.client._convert_messages_to_response_input(messages)
        
        # System message should be extracted to instructions field
        assert system_instructions == "You are a helpful assistant."
        
        # Only user message should be in response input
        assert len(response_input) == 1
        
        # User message
        assert response_input[0]["type"] == "message"
        assert response_input[0]["role"] == "user"
        # Content is an array with input_text item (API accepts both formats)
        assert isinstance(response_input[0]["content"], list)
        assert response_input[0]["content"][0]["type"] == "input_text"
        assert response_input[0]["content"][0]["text"] == "Hello, how are you?"

    def test_convert_messages_to_response_input_multimodal(self):
        """Test converting multimodal messages with text and images."""
        text_content = TextContent(text="What do you see in this image?")
        
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[text_content],  # Multimodal content
                agent_id="agent-123",
                model="gpt-5"
            )
        ]
        
        system_instructions, response_input = self.client._convert_messages_to_response_input(messages)
        
        # No system message, so instructions should be None
        assert system_instructions is None
        
        # Only user message should be in response input
        assert len(response_input) == 1
        assert response_input[0]["role"] == "user"
        assert response_input[0]["type"] == "message"
        # Content is an array with input_text item
        assert isinstance(response_input[0]["content"], list)
        assert response_input[0]["content"][0]["type"] == "input_text"
        assert response_input[0]["content"][0]["text"] == "What do you see in this image?"

    def test_convert_assistant_message_with_tool_calls(self):
        """Test converting assistant message with tool calls."""
        # Create a mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function = Mock()
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = '{"location": "San Francisco"}'
        
        message = PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text="I'll check the weather for you.")],
            agent_id="agent-123",
            model="gpt-5"
        )
        message.tool_calls = [mock_tool_call]
        
        result = self.client._convert_assistant_message(message)
        
        # Assistant messages with tool calls return function call format, not message format
        assert result["type"] == "function_call"
        assert result["call_id"] == "call_123"
        assert result["name"] == "get_weather"
        assert result["arguments"] == '{"location": "San Francisco"}'

    def test_convert_assistant_message_without_tool_calls(self):
        """Test converting assistant message without tool calls."""
        message = PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text="Hello! I'm doing great.")],
            agent_id="agent-123",
            model="gpt-5"
        )
        
        result = self.client._convert_assistant_message(message)
        
        # Assistant messages without tool calls return regular message format
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert result["content"] == "Hello! I'm doing great."

    def test_convert_responses_to_chat_completion(self):
        """Test converting Responses API response to Chat Completions format."""
        responses_data = {
            "id": "resp-123",
            "model": "gpt-5",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Hello! I'm doing great, thank you for asking."}
                    ]
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 12,
                "total_tokens": 32
            },
            "reasoning": {
                "effort": "minimal",
                "summary": "The user is greeting me and asking how I am. I should respond politely."
            }
        }
        
        result = self.client._convert_responses_to_chat_completion(responses_data)
        
        assert result["id"] == "resp-123"
        assert result["model"] == "gpt-5"
        assert len(result["choices"]) == 1
        
        choice = result["choices"][0]
        assert choice["index"] == 0
        assert choice["message"]["role"] == "assistant"
        assert choice["message"]["content"] == "Hello! I'm doing great, thank you for asking."
        assert choice["finish_reason"] == "stop"  # Response status "completed" maps to finish_reason "stop"
        assert "reasoning_content" in choice["message"]

    def test_convert_response_content(self):
        """Test converting Responses API content format to string."""
        content_items = [
            {"type": "output_text", "text": "Hello "},
            {"type": "output_text", "text": "world!"}
        ]
        
        result = self.client._convert_response_content(content_items)
        assert result == "Hello world!"

    def test_convert_response_content_empty(self):
        """Test converting empty content."""
        result = self.client._convert_response_content([])
        assert result == ""

    def test_serialize_reasoning_for_preservation(self):
        """Test serializing reasoning content for exact preservation."""
        response_data = {
            "reasoning": {
                "effort": "medium",
                "summary": "First, I need to understand the user's question. Then, I should provide a helpful response."
            }
        }
        
        result = self.client._serialize_reasoning_for_preservation(response_data)
        assert result is not None
        # Should be JSON-serialized
        deserialized = json.loads(result)
        assert deserialized["effort"] == "medium"
        assert "First, I need to understand" in deserialized["summary"]

    def test_serialize_reasoning_for_preservation_empty(self):
        """Test serializing reasoning content when none exists."""
        response_data = {"reasoning": {}}
        
        result = self.client._serialize_reasoning_for_preservation(response_data)
        assert result == "{}"  # Empty object serializes to "{}"

    def test_build_request_data_responses_format(self):
        """Test that build_request_data produces Responses API format."""
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="What is the weather like?")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]
        
        tools = [{
            "name": "get_weather",
            "description": "Get weather information",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Location to get weather for"}
                },
                "required": ["location"]
            }
        }]
        
        result = self.client.build_request_data(messages, self.llm_config, tools)
        
        # Should have Responses API format
        assert "input" in result  # Not "messages"
        assert "model" in result
        assert "max_output_tokens" in result
        assert "tools" in result
        assert "tool_choice" in result
        
        # Check input format
        assert len(result["input"]) == 1
        assert result["input"][0]["role"] == "user"
        assert isinstance(result["input"][0]["content"], list)
        assert result["input"][0]["content"][0]["type"] == "input_text"
        assert result["input"][0]["content"][0]["text"] == "What is the weather like?"

    def test_build_request_data_gpt5_parameters(self):
        """Test that GPT-5 specific parameters are excluded in Responses API format."""
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]
        
        result = self.client.build_request_data(messages, self.llm_config)
        
        # GPT-5 specific parameters should not appear in the raw dict
        # as they'll be handled by the Responses API format
        assert "verbosity" not in result
        assert "reasoning_effort" not in result
    
    def test_gpt5_reasoning_settings(self):
        """Test that GPT-5 models get the correct reasoning settings."""
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]
        
        # Create a config with GPT-5 model
        gpt5_config = self.llm_config.model_copy()
        gpt5_config.model = "gpt-5"
        
        result = self.client.build_request_data(messages, gpt5_config)
        
        # Should include reasoning parameters for GPT-5
        assert "reasoning" in result
        assert result["reasoning"]["effort"] == "minimal"
        assert result["reasoning"]["summary"] == "auto"

    def test_full_conversion_pipeline(self):
        """Test the complete conversion pipeline from request to response."""
        # Test message
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello, GPT-5!")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]
        
        # Build request
        request_data = self.client.build_request_data(messages, self.llm_config)
        
        # Mock response data (what we'd get from Responses API)
        mock_response_data = {
            "id": "resp-456",
            "model": "gpt-5",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Hello! Nice to meet you!"}
                    ]
                }
            ],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 8,
                "total_tokens": 23
            },
            "reasoning": {
                "summary": "User is greeting me, I should respond warmly."
            }
        }
        
        # Convert response
        chat_completion = self.client.convert_response_to_chat_completion(
            mock_response_data, messages, self.llm_config
        )
        
        # Verify the result
        assert chat_completion.id == "resp-456"
        assert chat_completion.model == "gpt-5"
        assert len(chat_completion.choices) == 1
        assert chat_completion.choices[0].message.content == "Hello! Nice to meet you!"
        assert chat_completion.choices[0].message.omitted_reasoning_content is False  # Reasoning content is preserved, not omitted
        assert chat_completion.choices[0].message.reasoning_content is not None
        assert chat_completion.usage.total_tokens == 23


class TestCacheOptimization:
    """Test suite for cache optimization features."""

    def setup_method(self):
        """Setup test fixtures."""
        self.client = OpenAIClient()
        self.client.actor = Mock()
        self.client.actor.id = "test-user-123"
        self.llm_config = LLMConfig.default_config("gpt-5")

    def test_system_message_extraction_single(self):
        """Test that single system message is extracted to instructions field."""
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="You are a helpful assistant.")],
                agent_id="agent-123",
                model="gpt-5"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]

        system_instructions, response_input = self.client._convert_messages_to_response_input(messages)
        
        # System message should be extracted
        assert system_instructions == "You are a helpful assistant."
        
        # Only user message should remain in input
        assert len(response_input) == 1
        assert response_input[0]["role"] == "user"

    def test_system_message_extraction_multiple(self):
        """Test that multiple system messages are combined into instructions field."""
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="You are a helpful assistant.")],
                agent_id="agent-123",
                model="gpt-5"
            ),
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="Please be concise.")],
                agent_id="agent-123",
                model="gpt-5"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]

        system_instructions, response_input = self.client._convert_messages_to_response_input(messages)
        
        # System messages should be combined
        assert system_instructions == "You are a helpful assistant.\n\nPlease be concise."
        
        # Only user message should remain in input
        assert len(response_input) == 1
        assert response_input[0]["role"] == "user"

    def test_no_system_messages(self):
        """Test that instructions field is None when no system messages."""
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]

        system_instructions, response_input = self.client._convert_messages_to_response_input(messages)
        
        # No system instructions
        assert system_instructions is None
        
        # User message should be in input
        assert len(response_input) == 1
        assert response_input[0]["role"] == "user"

    def test_build_request_data_with_instructions_field(self):
        """Test that build_request_data includes instructions field for system messages."""
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="You are a helpful assistant.")],
                agent_id="agent-123",
                model="gpt-5"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]

        result = self.client.build_request_data(messages, self.llm_config)
        
        # Instructions field should be present with system message content
        assert "instructions" in result
        assert result["instructions"] == "You are a helpful assistant."
        
        # Input should only contain user message
        assert len(result["input"]) == 1
        assert result["input"][0]["role"] == "user"

    def test_build_request_data_without_instructions_field(self):
        """Test that build_request_data omits instructions field when no system messages."""
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]

        result = self.client.build_request_data(messages, self.llm_config)
        
        # Instructions field should not be present
        assert "instructions" not in result
        
        # Input should contain user message
        assert len(result["input"]) == 1
        assert result["input"][0]["role"] == "user"

    def test_system_message_with_list_content(self):
        """Test system message extraction with list-based content."""
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[
                    TextContent(text="You are helpful. "),
                    TextContent(text="Be concise.")
                ],
                agent_id="agent-123",
                model="gpt-5"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="agent-123",
                model="gpt-5"
            )
        ]

        system_instructions, response_input = self.client._convert_messages_to_response_input(messages)
        
        # List content should be concatenated
        assert system_instructions == "You are helpful. Be concise."
        
        # Only user message should remain
        assert len(response_input) == 1
        assert response_input[0]["role"] == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])