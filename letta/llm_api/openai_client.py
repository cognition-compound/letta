import json
import os
from datetime import datetime
from typing import List, Optional

import openai
from openai import AsyncOpenAI, AsyncStream, OpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

# Import Response API types - required for Responses API migration
from openai.types.responses import Response

from letta.constants import LETTA_MODEL_ENDPOINT
from letta.errors import (
    ContextWindowExceededError,
    ErrorCode,
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMConnectionError,
    LLMNotFoundError,
    LLMPermissionDeniedError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMUnprocessableEntityError,
)
from letta.llm_api.helpers import convert_to_structured_output
from letta.llm_api.llm_client_base import LLMClientBase
from letta.log import get_logger
from letta.otel.tracing import log_event, trace_method
from letta.schemas.embedding_config import EmbeddingConfig
from letta.schemas.enums import ProviderCategory, ProviderType
from letta.schemas.letta_message_content import MessageContentType
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.openai.chat_completion_response import ChatCompletionResponse
from letta.settings import model_settings

logger = get_logger(__name__)


def is_openai_reasoning_model(model: str) -> bool:
    """Utility function to check if the model is a 'reasoner'"""

    # NOTE: needs to be updated with new model releases
    # GPT-5 is a reasoning model according to OpenAI docs
    is_reasoning = (
        model.startswith("o1") or model.startswith("o2") or model.startswith("o3") or model.startswith("o4") or model.startswith("gpt-5")
    )
    return is_reasoning


def accepts_developer_role(model: str) -> bool:
    """Checks if the model accepts the 'developer' role. Note that not all reasoning models accept this role.

    See: https://community.openai.com/t/developer-role-not-accepted-for-o1-o1-mini-o3-mini/1110750/7
    """
    if is_openai_reasoning_model(model) and "o1-mini" not in model or "o1-preview" in model:
        return True
    else:
        return False


def supports_temperature_param(model: str) -> bool:
    """Certain OpenAI models don't support configuring the temperature.

    Example error: 400 - {'error': {'message': "Unsupported parameter: 'temperature' is not supported with this model.", 'type': 'invalid_request_error', 'param': 'temperature', 'code': 'unsupported_parameter'}}
    """
    if is_openai_reasoning_model(model):
        return False
    else:
        return True


def supports_parallel_tool_calling(model: str) -> bool:
    """Certain OpenAI models don't support parallel tool calls."""

    if is_openai_reasoning_model(model):
        return False
    else:
        return True


# TODO move into LLMConfig as a field?
def supports_structured_output(llm_config: LLMConfig) -> bool:
    """Certain providers don't support structured output."""

    # FIXME pretty hacky - turn off for providers we know users will use,
    #       but also don't support structured output
    if "nebius.com" in llm_config.model_endpoint:
        return False
    else:
        return True


# TODO move into LLMConfig as a field?
def requires_auto_tool_choice(llm_config: LLMConfig) -> bool:
    """Certain providers require the tool choice to be set to 'auto'."""
    if "nebius.com" in llm_config.model_endpoint:
        return True
    if "together.ai" in llm_config.model_endpoint or "together.xyz" in llm_config.model_endpoint:
        return True
    if llm_config.handle and "vllm" in llm_config.handle:
        return True
    return False


class OpenAIClient(LLMClientBase):
    def _prepare_client_kwargs(self, llm_config: LLMConfig) -> dict:
        api_key = None
        if llm_config.provider_category == ProviderCategory.byok:
            from letta.services.provider_manager import ProviderManager

            api_key = ProviderManager().get_override_key(llm_config.provider_name, actor=self.actor)
        if llm_config.model_endpoint_type == ProviderType.together:
            api_key = model_settings.together_api_key or os.environ.get("TOGETHER_API_KEY")

        if not api_key:
            api_key = model_settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        # supposedly the openai python client requires a dummy API key
        api_key = api_key or "DUMMY_API_KEY"
        kwargs = {"api_key": api_key, "base_url": llm_config.model_endpoint}

        return kwargs

    def _prepare_client_kwargs_embedding(self, embedding_config: EmbeddingConfig) -> dict:
        api_key = None
        if embedding_config.embedding_endpoint_type == ProviderType.together:
            api_key = model_settings.together_api_key or os.environ.get("TOGETHER_API_KEY")

        if not api_key:
            api_key = model_settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        # supposedly the openai python client requires a dummy API key
        api_key = api_key or "DUMMY_API_KEY"
        kwargs = {"api_key": api_key, "base_url": embedding_config.embedding_endpoint}
        return kwargs

    async def _prepare_client_kwargs_async(self, llm_config: LLMConfig) -> dict:
        api_key = None
        if llm_config.provider_category == ProviderCategory.byok:
            from letta.services.provider_manager import ProviderManager

            api_key = await ProviderManager().get_override_key_async(llm_config.provider_name, actor=self.actor)
        if llm_config.model_endpoint_type == ProviderType.together:
            api_key = model_settings.together_api_key or os.environ.get("TOGETHER_API_KEY")

        if not api_key:
            api_key = model_settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        # supposedly the openai python client requires a dummy API key
        api_key = api_key or "DUMMY_API_KEY"
        kwargs = {"api_key": api_key, "base_url": llm_config.model_endpoint}

        return kwargs

    def _convert_messages_to_response_input(self, messages: List[PydanticMessage]) -> List[dict]:
        """Convert internal message format to Responses API input format.

        Based on OpenAI Responses API documentation, the input format is:
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Hello"}
            ]
        }

        Args:
            messages: List of PydanticMessage objects

        Returns:
            List of dicts in Responses API input format
        """
        logger.debug(f"[DEBUG] Converting {len(messages)} messages to Responses API format")
        response_input = []

        for i, message in enumerate(messages):
            logger.debug(f"[DEBUG] Converting message {i}: role={message.role}, content_type={type(message.content)}")

            if message.role == "user":
                content = []
                if isinstance(message.content, str):
                    # Simple string content
                    content.append({"type": "input_text", "text": message.content})
                elif isinstance(message.content, list):
                    # Multi-modal content (text + images)
                    for item in message.content:
                        if item.type == MessageContentType.text:
                            content.append({"type": "input_text", "text": item.text})
                        elif item.type == MessageContentType.image:
                            content.append(
                                {"type": "input_image", "image_url": {"url": f"data:{item.source.media_type};base64,{item.source.data}"}}
                            )
                        else:
                            # Handle other content types as text fallback
                            content.append({"type": "input_text", "text": str(item)})
                else:
                    # Fallback for non-string, non-list content
                    content.append({"type": "input_text", "text": str(message.content)})

                response_input.append({"role": "user", "content": content})

            elif message.role == "assistant":
                # Handle assistant messages with potential tool calls
                response_input.append(self._convert_assistant_message(message))

            elif message.role == "system":
                # System messages in Responses API
                content = []
                if isinstance(message.content, str):
                    content.append({"type": "input_text", "text": message.content})
                elif isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, "text"):
                            content.append({"type": "input_text", "text": item.text})
                        else:
                            content.append({"type": "input_text", "text": str(item)})
                else:
                    content.append({"type": "input_text", "text": str(message.content)})

                response_input.append({"role": "system", "content": content})

            elif message.role == "developer":
                # Developer role messages (if supported by model)
                content = []
                if isinstance(message.content, str):
                    content.append({"type": "input_text", "text": message.content})
                else:
                    content.append({"type": "input_text", "text": str(message.content)})

                response_input.append({"role": "developer", "content": content})

            elif message.role == "tool":
                # Tool result messages -> convert to function_call_output format per Responses API
                tool_result = {
                    "type": "function_call_output",
                    "output": message.content[0].text if isinstance(message.content, list) else str(message.content),
                }
                # Add call_id if present (required for function_call_output)
                if hasattr(message, "tool_call_id") and message.tool_call_id:
                    tool_result["call_id"] = message.tool_call_id

                response_input.append(tool_result)

        logger.debug(f"[DEBUG] Converted to {len(response_input)} response input items")
        return response_input

    def _convert_assistant_message(self, message: PydanticMessage) -> dict:
        """Convert assistant message to Responses API format."""

        # Check if this assistant message has tool calls
        if hasattr(message, "tool_calls") and message.tool_calls:
            # For assistant messages with tool calls, we should include the raw response output
            # This matches the official example: input_list += response.output
            # However, since we're converting FROM message history, we need to reconstruct
            # the function call format
            function_call_items = []

            for tool_call in message.tool_calls:
                function_call_item = {
                    "type": "function_call",
                    "call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                }
                function_call_items.append(function_call_item)

            # For now, return the first function call item
            # TODO: Handle multiple tool calls properly
            if function_call_items:
                return function_call_items[0]

        # Regular assistant message without tool calls
        content = []

        # Handle content - assistant messages also need content as array
        if isinstance(message.content, str):
            if message.content:  # Only add non-empty content
                content.append({"type": "input_text", "text": message.content})
        elif isinstance(message.content, list):
            for item in message.content:
                if hasattr(item, "text") and item.text:
                    content.append({"type": "input_text", "text": item.text})
                elif hasattr(item, "type") and item.type == MessageContentType.text and hasattr(item, "text"):
                    content.append({"type": "input_text", "text": item.text})
        elif message.content:  # Handle other non-empty content types
            content.append({"type": "input_text", "text": str(message.content)})

        assistant_message = {"role": "assistant", "content": content}

        return assistant_message

    def _convert_responses_to_chat_completion(self, response_data: dict) -> dict:
        """Convert Responses API response format to Chat Completions format."""

        # Extract output items
        output_items = response_data.get("output", [])
        choices = []

        # Separate different types of output items
        message_items = []
        function_call_items = []
        reasoning_items = []

        for item in output_items:
            if item.get("type") == "message":
                message_items.append(item)
            elif item.get("type") == "function_call":
                function_call_items.append(item)
            elif item.get("type") == "reasoning":
                reasoning_items.append(item)

        # Convert function_call items to Chat Completions tool_calls format
        tool_calls = []
        for func_call in function_call_items:
            tool_call = {
                "id": func_call.get("call_id", f"call_{len(tool_calls)}"),
                "type": "function",
                "function": {"name": func_call.get("name", ""), "arguments": func_call.get("arguments", "{}")},
            }
            tool_calls.append(tool_call)

        # Process message items (standard responses)
        for i, item in enumerate(message_items):
            content = self._convert_response_content(item.get("content", []))

            choice = {
                "index": i,
                "message": {
                    "role": item.get("role", "assistant"),
                    "content": content,
                    "tool_calls": tool_calls if tool_calls else None,  # Add converted tool calls
                    "reasoning_content": self._serialize_reasoning_for_preservation(response_data),
                },
                "finish_reason": (
                    "stop" if response_data.get("status") == "completed" else response_data.get("status", "stop")
                ),  # Map status to finish_reason
            }
            choices.append(choice)

        # Handle function calls without message (tool-only response)
        if not message_items and tool_calls:
            choice = {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,  # No text content, only tool calls
                    "tool_calls": tool_calls,
                    "reasoning_content": self._serialize_reasoning_for_preservation(response_data),
                },
                "finish_reason": "stop" if response_data.get("status") == "completed" else response_data.get("status", "stop"),
            }
            choices.append(choice)

        # Handle GPT-5 reasoning-only responses (when no message items exist)
        elif not message_items and not tool_calls and reasoning_items:
            # Create a synthetic message from reasoning for backward compatibility
            reasoning_content = self._serialize_reasoning_for_preservation(response_data)

            choice = {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "I need to think about this step by step.",  # Default content for reasoning-only
                    "tool_calls": None,
                    "reasoning_content": reasoning_content,
                },
                "finish_reason": "stop" if response_data.get("status") == "completed" else response_data.get("status", "stop"),
            }
            choices.append(choice)

        return {
            "id": response_data.get("id"),
            "choices": choices,
            "created": int(datetime.now().timestamp()),
            "model": response_data.get("model"),
            "usage": response_data.get("usage", {}),
            "system_fingerprint": response_data.get("system_fingerprint"),
        }

    def _convert_response_content(self, content_items: List[dict]) -> str:
        """Convert Responses API content format to string content.

        Args:
            content_items: List of content items from Responses API

        Returns:
            Combined text content as string
        """
        if not content_items:
            return ""

        text_parts = []
        for item in content_items:
            if item.get("type") == "output_text":  # Correct Responses API type
                text_parts.append(item.get("text", ""))
            elif item.get("type") == "text":  # Fallback for other formats
                text_parts.append(item.get("text", ""))
            elif item.get("type") == "input_text":  # Input format (shouldn't appear in output)
                text_parts.append(item.get("text", ""))
            # Note: We could handle other content types like images here if needed

        return "".join(text_parts)

    def _serialize_reasoning_for_preservation(self, response_data: dict) -> Optional[str]:
        """Serialize the entire reasoning field from OpenAI for exact preservation.

        This ensures we can reconstruct the EXACT reasoning object when converting
        back to OpenAI format, maintaining perfect round-trip fidelity.

        Args:
            response_data: Raw response data from Responses API

        Returns:
            JSON-serialized reasoning object if present, None otherwise.
        """
        # First check for reasoning at the top level (most common)
        top_level_reasoning = response_data.get("reasoning")
        if top_level_reasoning is not None:  # Handle empty dict {} as valid
            try:
                return json.dumps(top_level_reasoning, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to JSON serialize top-level reasoning: {e}")

        # Also check for reasoning items in output (future OpenAI format possibility)
        output_items = response_data.get("output", [])
        reasoning_items = []

        for item in output_items:
            if item.get("type") == "reasoning":
                reasoning_items.append(item)

        if reasoning_items:
            try:
                # Store all reasoning items
                reasoning_data = {"output_reasoning_items": reasoning_items}
                return json.dumps(reasoning_data, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to JSON serialize reasoning items: {e}")

        return None

    def _process_reasoning_content(self, chat_completion_response: ChatCompletionResponse, response_data: dict):
        """Process reasoning content for reasoning models.

        This method:
        1. Serializes the entire reasoning object for exact preservation
        2. Sets omitted flag when reasoning is present but not readable
        """
        if not chat_completion_response.choices:
            return

        message = chat_completion_response.choices[0].message

        # Always serialize the complete reasoning object for preservation
        serialized_reasoning = self._serialize_reasoning_for_preservation(response_data)
        if serialized_reasoning:
            # Store serialized reasoning in reasoning_content field
            message.reasoning_content = serialized_reasoning
            # Set omitted flag since reasoning content is serialized/not directly readable
            message.omitted_reasoning_content = True
            logger.debug(f"[REASONING] Preserved reasoning object ({len(serialized_reasoning)} chars) - set omitted flag")
        else:
            # No reasoning data at all - still set omitted flag for reasoning models
            message.omitted_reasoning_content = True
            logger.debug(f"[REASONING] No reasoning data found - set omitted flag")

    @trace_method
    def build_request_data(
        self,
        messages: List[PydanticMessage],
        llm_config: LLMConfig,
        tools: Optional[List[dict]] = None,  # Keep as dict for now as per base class
        force_tool_call: Optional[str] = None,
    ) -> dict:
        """
        Constructs a request object in the Responses API format for the OpenAI API.
        """
        # Convert messages to Responses API input format
        response_input = self._convert_messages_to_response_input(messages)

        if llm_config.model:
            model = llm_config.model
        else:
            logger.warning(f"Model type not set in llm_config: {llm_config.model_dump_json(indent=4)}")
            model = None

        # Build Responses API request (uses OpenAI's expected format)
        data = {
            "model": model,
            "input": response_input,  # Changed from 'messages' to 'input'
            # NOTE: the reasoners that don't support temperature require 1.0, not None
            "temperature": llm_config.temperature if supports_temperature_param(model) else 1.0,
        }

        # Add max_output_tokens parameter if specified (Responses API parameter name)
        if llm_config.max_tokens:
            data["max_output_tokens"] = llm_config.max_tokens

        # Handle tools (Responses API format differs from Chat Completions API)
        if tools:
            # Responses API uses FLAT tool format (no nesting!)
            converted_tools = []
            for tool in tools:
                tool_name = tool.get("name", "UNKNOWN_TOOL")

                # Validate tool structure and log issues
                if "parameters" not in tool:
                    logger.error(f"Tool '{tool_name}' is missing 'parameters' field. Full tool: {json.dumps(tool, default=str)}")
                    continue

                if not isinstance(tool["parameters"], dict):
                    logger.error(
                        f"Tool '{tool_name}' has invalid 'parameters' type: {type(tool['parameters'])}. Expected dict. Full tool: {json.dumps(tool, default=str)}"
                    )
                    continue

                # Check for missing 'required' field and log warning with context
                if "required" not in tool["parameters"]:
                    # Check if this is an MCP tool
                    tool_description = tool.get("description", "")
                    is_mcp_tool = "MCP tool" in tool_description or tool_name.startswith("mcp_")

                    logger.warning(
                        f"Tool '{tool_name}' is missing 'required' field in parameters. "
                        f"{'This appears to be an MCP tool. ' if is_mcp_tool else ''}"
                        f"Adding empty array. Tool parameters: {json.dumps(tool['parameters'], default=str)}"
                    )
                    tool["parameters"]["required"] = []

                # Create tool in flat format (not nested like Chat Completions API)
                converted_tool = {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"].copy(),  # Copy to avoid modifying original
                }

                # Ensure Responses API strict mode compatibility
                if converted_tool["parameters"].get("type") == "object":
                    # Force strict mode compatibility for Responses API
                    converted_tool["parameters"]["additionalProperties"] = False

                    # Ensure all properties are required (strict mode requirement)
                    properties = converted_tool["parameters"].get("properties", {})
                    if properties:
                        # Check if required field exists, if not create it
                        if "required" not in converted_tool["parameters"]:
                            logger.info(f"Tool '{tool_name}' creating 'required' field with all properties as required for strict mode")
                        converted_tool["parameters"]["required"] = list(properties.keys())

                if supports_structured_output(llm_config):
                    try:
                        structured_output_version = convert_to_structured_output(tool)
                        # Update the tool with structured output
                        converted_tool.update(structured_output_version)
                    except ValueError as e:
                        logger.warning(f"Failed to convert tool function to structured output, tool={tool}, error={e}")

                # Final validation: ensure strict mode compatibility
                converted_tool["strict"] = True
                converted_tools.append(converted_tool)

            data["tools"] = converted_tools

            # Handle tool choice
            if force_tool_call:
                data["tool_choice"] = {"type": "function", "function": {"name": force_tool_call}}
            elif requires_auto_tool_choice(llm_config):
                data["tool_choice"] = "auto"
            else:
                data["tool_choice"] = "required"

            # Handle parallel tool calls
            if supports_parallel_tool_calling(model):
                enable_parallel = os.getenv("LETTA_ENABLE_PARALLEL_TOOL_CALLS", "true").lower() == "true"
                data["parallel_tool_calls"] = enable_parallel

        # Add frequency penalty if specified - NOTE: not officially documented for Responses API
        # Commenting out for now to ensure compatibility
        # if llm_config.frequency_penalty is not None:
        #     data["frequency_penalty"] = llm_config.frequency_penalty

        # Use prompt_cache_key instead of deprecated user field for Responses API
        if self.actor:
            data["prompt_cache_key"] = self.actor.id
        else:
            data["prompt_cache_key"] = ""

        # Configure reasoning parameters for reasoning models
        if is_openai_reasoning_model(model):
            data["reasoning"] = {"effort": "low"}  # Use low effort for faster responses
            # Note: reasoning.content is not available via API - only reasoning.encrypted_content
            # OpenAI intentionally does not expose actual reasoning thoughts

        # Handle special endpoint configurations
        if llm_config.model_endpoint == LETTA_MODEL_ENDPOINT:
            if not self.actor:
                # override user id for inference.letta.com
                import uuid

                data["user"] = str(uuid.UUID(int=0))
            data["model"] = "memgpt-openai"

        return data

    @trace_method
    def to_openai_format(self, response) -> dict:
        """Convert our internal response format to clean OpenAI SDK format.

        Uses blacklist approach: include everything except clearly internal fields.
        This is more robust than whitelisting since we don't need to guess required fields.
        """
        # Start with the raw response
        response_dict = response.model_dump()

        # Clean the output items by removing only internal fields
        if "output" in response_dict and response.output:
            # Fields that are clearly internal/metadata and shouldn't be passed as input
            INTERNAL_FIELDS = {"status", "encrypted_content"}  # Response processing status  # Internal security field

            clean_output = []

            for item in response.output:
                item_dict = item.model_dump() if hasattr(item, "model_dump") else item

                # Include all fields except blacklisted internal ones
                clean_item = {k: v for k, v in item_dict.items() if k not in INTERNAL_FIELDS}

                clean_output.append(clean_item)

            response_dict["output"] = clean_output

        return response_dict

    def request(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying synchronous request to OpenAI Responses API.
        Returns response in clean OpenAI SDK format (ready for input reuse).
        """
        client = OpenAI(**self._prepare_client_kwargs(llm_config))
        response = client.responses.create(**request_data)

        # Convert to clean OpenAI format (matches official SDK behavior)
        return self.to_openai_format(response)

    @trace_method
    async def request_async(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying asynchronous request to OpenAI Responses API.
        Returns response in clean OpenAI SDK format (ready for input reuse).
        """
        try:
            # Log structured request details
            logger.info(f"[API_REQUEST] Responses API call starting")
            logger.debug(f"[API_REQUEST] Model: {llm_config.model}, Endpoint: {llm_config.model_endpoint}")
            logger.debug(f"[API_REQUEST] Input messages: {len(request_data.get('input', []))}, Tools: {len(request_data.get('tools', []))}")
            logger.debug(
                f"[API_REQUEST] Tool choice: {request_data.get('tool_choice')}, Parallel tools: {request_data.get('parallel_tool_calls')}"
            )

            # Log first few tools for debugging
            if request_data.get("tools"):
                tools = request_data["tools"]
                logger.debug(
                    f"[API_REQUEST] First tool: name='{tools[0].get('name')}', type='{tools[0].get('type')}', params_count={len(tools[0].get('parameters', {}).get('properties', {}))}"
                )

            # Log request structure (truncated)
            request_summary = {
                "model": request_data.get("model"),
                "input_count": len(request_data.get("input", [])),
                "tools_count": len(request_data.get("tools", [])),
                "tool_choice": request_data.get("tool_choice"),
                "temperature": request_data.get("temperature"),
                "max_output_tokens": request_data.get("max_output_tokens"),
            }
            logger.debug(f"[API_REQUEST] Request summary: {json.dumps(request_summary, indent=2)}")

            kwargs = await self._prepare_client_kwargs_async(llm_config)
            client = AsyncOpenAI(**kwargs)
            response = await client.responses.create(**request_data)

            # Log structured response details
            clean_response = self.to_openai_format(response)
            response_summary = {
                "id": clean_response.get("id"),
                "model": clean_response.get("model"),
                "status": clean_response.get("status"),
                "output_count": len(clean_response.get("output", [])),
                "usage": clean_response.get("usage", {}),
            }

            # Check for tool calls in response
            output_items = clean_response.get("output", [])
            tool_calls_count = 0
            for item in output_items:
                if item.get("type") == "message" and item.get("tool_calls"):
                    tool_calls_count += len(item["tool_calls"])
                elif item.get("type") == "function_call":
                    tool_calls_count += 1

            response_summary["tool_calls_returned"] = tool_calls_count

            logger.info(f"[API_RESPONSE] Responses API call successful")
            logger.debug(f"[API_RESPONSE] Response summary: {json.dumps(response_summary, indent=2)}")

            # Log first tool call if present for debugging
            if tool_calls_count > 0:
                for item in output_items:
                    if item.get("type") == "message" and item.get("tool_calls"):
                        first_tool = item["tool_calls"][0]
                        logger.debug(
                            f"[API_RESPONSE] First tool call: name='{first_tool.get('function', {}).get('name')}', id='{first_tool.get('id')}'"
                        )
                        break
                    elif item.get("type") == "function_call":
                        logger.debug(f"[API_RESPONSE] First function call: name='{item.get('name')}', args='{item.get('arguments')}'")
                        break
            else:
                logger.warning(f"[API_RESPONSE] No tool calls returned despite tools provided!")

            return clean_response

        except Exception as e:
            # Log structured error event for non-streaming requests
            log_event(
                "llm_request_error",
                {
                    "model": request_data.get("model", "unknown"),
                    "tool_count": len(request_data.get("tools", [])),
                    "api_type": "responses",
                    "stream_mode": False,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "provider": "openai",
                    "endpoint": llm_config.model_endpoint or "default",
                },
            )

            logger.error(f"[API_ERROR] Responses API call failed: {type(e).__name__}: {str(e)}")
            logger.error(f"[API_ERROR] Request model: {request_data.get('model')}, tools: {len(request_data.get('tools', []))}")
            logger.debug(f"[API_ERROR] Full request data: {json.dumps(request_data, indent=2, default=str)}")
            raise

    @trace_method
    def convert_response_to_chat_completion(
        self,
        response_data: dict,
        input_messages: List[PydanticMessage],  # Included for consistency, maybe used later
        llm_config: LLMConfig,
    ) -> ChatCompletionResponse:
        """
        Converts raw Responses API response dict into the ChatCompletionResponse Pydantic model.
        Handles potential extraction of inner thoughts if they were added via kwargs.
        """
        # Convert Responses API response to ChatCompletionResponse format
        converted_response = self._convert_responses_to_chat_completion(response_data)

        chat_completion_response = ChatCompletionResponse(**converted_response)
        chat_completion_response = self._fix_truncated_json_response(chat_completion_response)

        # Handle reasoning content for reasoning models
        if is_openai_reasoning_model(llm_config.model):
            self._process_reasoning_content(chat_completion_response, response_data)

        return chat_completion_response

    @trace_method
    async def stream_async(self, request_data: dict, llm_config: LLMConfig) -> AsyncStream[ChatCompletionChunk]:
        """
        Performs underlying asynchronous streaming request to OpenAI Responses API and returns the async stream iterator.
        """
        model = request_data.get("model", "unknown")
        tool_count = len(request_data.get("tools", []))

        # Log structured request start event
        log_event(
            "llm_stream_request_start",
            {
                "model": model,
                "tool_count": tool_count,
                "api_type": "responses",
                "stream_mode": True,
                "provider": "openai",
                "endpoint": llm_config.model_endpoint or "default",
                "temperature": request_data.get("temperature"),
                "max_output_tokens": request_data.get("max_output_tokens"),
            },
        )

        try:
            kwargs = await self._prepare_client_kwargs_async(llm_config)
            client = AsyncOpenAI(**kwargs)

            response_stream = await client.responses.create(**request_data, stream=True)

            # Log successful stream initiation
            log_event("llm_stream_request_success", {"model": model, "tool_count": tool_count, "api_type": "responses"})

            # Convert Responses API stream to Chat Completions format for compatibility
            return self._convert_responses_stream_to_chat_completions(response_stream)

        except Exception as e:
            # Log structured error event
            log_event(
                "llm_stream_request_error",
                {
                    "model": model,
                    "tool_count": tool_count,
                    "api_type": "responses",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "base_url": kwargs.get("base_url", "default"),
                    "provider": "openai",
                },
            )

            raise

    async def _convert_responses_stream_to_chat_completions(self, response_stream: AsyncStream) -> AsyncStream[ChatCompletionChunk]:
        """
        Convert Responses API stream to Chat Completions format for compatibility with streaming interfaces.
        """
        async for chunk in response_stream:
            try:
                # Convert the chunk to dictionary format if needed
                if hasattr(chunk, "model_dump"):
                    chunk_dict = chunk.model_dump()
                else:
                    chunk_dict = chunk

                # Convert using the existing conversion function (import here to avoid circular import)
                from letta.llm_api.openai import convert_response_stream_chunk_to_chat_completion_format

                converted_chunk = convert_response_stream_chunk_to_chat_completion_format(chunk_dict)

                # Yield as ChatCompletionChunk
                yield ChatCompletionChunk(**converted_chunk)

            except Exception as e:
                logger.error(f"Error converting Responses API stream chunk: {e}")
                # Re-raise to be handled by the error handling in stream_async
                raise

    @trace_method
    async def request_embeddings(self, inputs: List[str], embedding_config: EmbeddingConfig) -> List[List[float]]:
        """Request embeddings given texts and embedding config"""
        kwargs = self._prepare_client_kwargs_embedding(embedding_config)
        client = AsyncOpenAI(**kwargs)
        response = await client.embeddings.create(model=embedding_config.embedding_model, input=inputs)

        # TODO: add total usage
        return [r.embedding for r in response.data]

    @trace_method
    def handle_llm_error(self, e: Exception) -> Exception:
        """
        Maps OpenAI-specific errors to common LLMError types.
        """
        if isinstance(e, openai.APITimeoutError):
            timeout_duration = getattr(e, "timeout", "unknown")
            logger.warning(f"[OpenAI] Request timeout after {timeout_duration} seconds: {e}")
            return LLMTimeoutError(
                message=f"Request to OpenAI timed out: {str(e)}",
                code=ErrorCode.TIMEOUT,
                details={
                    "timeout_duration": timeout_duration,
                    "cause": str(e.__cause__) if e.__cause__ else None,
                },
            )

        if isinstance(e, openai.APIConnectionError):
            logger.warning(f"[OpenAI] API connection error: {e}")
            return LLMConnectionError(
                message=f"Failed to connect to OpenAI: {str(e)}",
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                details={"cause": str(e.__cause__) if e.__cause__ else None},
            )

        if isinstance(e, openai.RateLimitError):
            logger.warning(f"[OpenAI] Rate limited (429). Consider backoff. Error: {e}")
            return LLMRateLimitError(
                message=f"Rate limited by OpenAI: {str(e)}",
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                details=e.body,  # Include body which often has rate limit details
            )

        if isinstance(e, openai.BadRequestError):
            logger.warning(f"[OpenAI] Bad request (400): {str(e)}")
            # BadRequestError can signify different issues (e.g., invalid args, context length)
            # Check message content if finer-grained errors are needed
            # Example: if "context_length_exceeded" in str(e): return LLMContextLengthExceededError(...)
            # TODO: This is a super soft check. Not sure if we can do better, needs more investigation.
            if "This model's maximum context length is" in str(e):
                return ContextWindowExceededError(
                    message=f"Bad request to OpenAI (context window exceeded): {str(e)}",
                )
            else:
                return LLMBadRequestError(
                    message=f"Bad request to OpenAI: {str(e)}",
                    code=ErrorCode.INVALID_ARGUMENT,  # Or more specific if detectable
                    details=e.body,
                )

        if isinstance(e, openai.AuthenticationError):
            logger.error(f"[OpenAI] Authentication error (401): {str(e)}")  # More severe log level
            return LLMAuthenticationError(
                message=f"Authentication failed with OpenAI: {str(e)}", code=ErrorCode.UNAUTHENTICATED, details=e.body
            )

        if isinstance(e, openai.PermissionDeniedError):
            logger.error(f"[OpenAI] Permission denied (403): {str(e)}")  # More severe log level
            return LLMPermissionDeniedError(
                message=f"Permission denied by OpenAI: {str(e)}", code=ErrorCode.PERMISSION_DENIED, details=e.body
            )

        if isinstance(e, openai.NotFoundError):
            logger.warning(f"[OpenAI] Resource not found (404): {str(e)}")
            # Could be invalid model name, etc.
            return LLMNotFoundError(message=f"Resource not found in OpenAI: {str(e)}", code=ErrorCode.NOT_FOUND, details=e.body)

        if isinstance(e, openai.UnprocessableEntityError):
            logger.warning(f"[OpenAI] Unprocessable entity (422): {str(e)}")
            return LLMUnprocessableEntityError(
                message=f"Invalid request content for OpenAI: {str(e)}",
                code=ErrorCode.INVALID_ARGUMENT,  # Usually validation errors
                details=e.body,
            )

        # General API error catch-all
        if isinstance(e, openai.APIStatusError):
            logger.warning(f"[OpenAI] API status error ({e.status_code}): {str(e)}")
            # Map based on status code potentially
            if e.status_code >= 500:
                error_cls = LLMServerError
                error_code = ErrorCode.INTERNAL_SERVER_ERROR
            else:
                # Treat other 4xx as bad requests if not caught above
                error_cls = LLMBadRequestError
                error_code = ErrorCode.INVALID_ARGUMENT

            return error_cls(
                message=f"OpenAI API error: {str(e)}",
                code=error_code,
                details={
                    "status_code": e.status_code,
                    "response": str(e.response),
                    "body": e.body,
                },
            )

        # Fallback for unexpected errors
        return super().handle_llm_error(e)


def fill_image_content_in_messages(openai_message_list: List[dict], pydantic_message_list: List[PydanticMessage]) -> List[dict]:
    """
    Converts image content to openai format.
    """

    if len(openai_message_list) != len(pydantic_message_list):
        return openai_message_list

    new_message_list = []
    for idx in range(len(openai_message_list)):
        openai_message, pydantic_message = openai_message_list[idx], pydantic_message_list[idx]
        if pydantic_message.role != "user":
            new_message_list.append(openai_message)
            continue

        if not isinstance(pydantic_message.content, list) or (
            len(pydantic_message.content) == 1 and pydantic_message.content[0].type == MessageContentType.text
        ):
            new_message_list.append(openai_message)
            continue

        message_content = []
        for content in pydantic_message.content:
            if content.type == MessageContentType.text:
                message_content.append(
                    {
                        "type": "text",
                        "text": content.text,
                    }
                )
            elif content.type == MessageContentType.image:
                message_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{content.source.media_type};base64,{content.source.data}",
                            "detail": content.source.detail or "auto",
                        },
                    }
                )
            else:
                raise ValueError(f"Unsupported content type {content.type}")

        new_message_list.append({"role": "user", "content": message_content})

    return new_message_list
