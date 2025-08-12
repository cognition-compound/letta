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
from letta.llm_api.tool_call_validator import validate_and_fix_conversation_before_api_call
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


def truncate_message_content_for_logging(messages: list, max_chars: int = 200) -> list:
    """Create a truncated version of messages for logging that preserves structure but limits content size."""
    truncated = []
    for msg in messages[:3]:  # Only show first 3 messages
        truncated_msg = {
            "type": msg.get("type"),
            "role": msg.get("role"),
        }
        
        # Handle content field
        content = msg.get("content")
        if isinstance(content, str):
            truncated_msg["content_preview"] = content[:max_chars] + ("..." if len(content) > max_chars else "")
        elif isinstance(content, list):
            truncated_msg["content_items"] = len(content)
            truncated_msg["content_types"] = [item.get("type") for item in content[:2]]  # First 2 types
        
        # Include tool calls if present
        if msg.get("tool_calls"):
            truncated_msg["tool_calls"] = [tc.get("function", {}).get("name") for tc in msg.get("tool_calls", [])[:2]]
            
        truncated.append(truncated_msg)
    
    if len(messages) > 3:
        truncated.append({"...": f"and {len(messages) - 3} more messages"})
    
    return truncated


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

    def _convert_messages_to_response_input(self, messages: List) -> List[dict]:
        """Convert internal message format to Responses API input format.

        Based on OpenAI Responses API documentation (2025), the input format uses simple content:
        {
            "role": "user",
            "content": "Hello"
        }
        or for multimodal:
        {
            "role": "user", 
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "image_url", "image_url": {...}}
            ]
        }

        Args:
            messages: List of PydanticMessage objects OR raw API response dicts (for multi-turn)

        Returns:
            List of dicts in Responses API input format
        """
        logger.debug(f"[DEBUG] Converting {len(messages)} messages to Responses API format")
        response_input = []

        for i, message in enumerate(messages):
            # Handle raw dicts from API responses (for multi-turn conversations)
            if isinstance(message, dict):
                # These are already in the correct format (e.g., function_call, reasoning, function_call_output)
                # Per OpenAI pattern: input_list += response.output
                logger.debug(f"[DEBUG] Message {i} is raw dict with type: {message.get('type')}")
                response_input.append(message)
                continue
            
            # Handle PydanticMessage objects
            logger.debug(f"[DEBUG] Converting message {i}: role={message.role}, content_type={type(message.content)}")

            if message.role == "user":
                if isinstance(message.content, str):
                    # Simple string content
                    response_input.append({"type": "message", "role": "user", "content": message.content})
                elif isinstance(message.content, list):
                    # Multi-modal content (text + images)
                    content = []
                    for item in message.content:
                        if item.type == MessageContentType.text:
                            content.append({"type": "input_text", "text": item.text})
                        elif item.type == MessageContentType.image:
                            content.append({
                                "type": "input_image", 
                                "image_url": {"url": f"data:{item.source.media_type};base64,{item.source.data}"}
                            })
                        else:
                            # Handle other content types as text fallback
                            content.append({"type": "input_text", "text": str(item)})
                    response_input.append({"type": "message", "role": "user", "content": content})
                else:
                    # Fallback for non-string, non-list content
                    response_input.append({"type": "message", "role": "user", "content": str(message.content)})

            elif message.role == "assistant":
                # Handle assistant messages with potential tool calls
                response_input.append(self._convert_assistant_message(message))

            elif message.role == "system":
                # System messages in Responses API
                if isinstance(message.content, str):
                    response_input.append({"type": "message", "role": "system", "content": message.content})
                elif isinstance(message.content, list):
                    # Handle list content by extracting text
                    content_text = ""
                    for item in message.content:
                        if hasattr(item, "text"):
                            content_text += item.text
                        else:
                            content_text += str(item)
                    response_input.append({"type": "message", "role": "system", "content": content_text})
                else:
                    response_input.append({"type": "message", "role": "system", "content": str(message.content)})

            elif message.role == "developer":
                # Developer role messages (if supported by model)
                if isinstance(message.content, str):
                    response_input.append({"type": "message", "role": "developer", "content": message.content})
                else:
                    response_input.append({"type": "message", "role": "developer", "content": str(message.content)})

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

        # Handle content - assistant messages use simple content format
        if isinstance(message.content, str):
            if message.content:  # Only add non-empty content
                assistant_message = {"type": "message", "role": "assistant", "content": message.content}
            else:
                assistant_message = {"type": "message", "role": "assistant", "content": ""}
        elif isinstance(message.content, list):
            # Extract text from list content
            content_text = ""
            for item in message.content:
                if hasattr(item, "text") and item.text:
                    content_text += item.text
                elif hasattr(item, "type") and item.type == MessageContentType.text and hasattr(item, "text"):
                    content_text += item.text
            assistant_message = {"type": "message", "role": "assistant", "content": content_text}
        elif message.content:  # Handle other non-empty content types
            assistant_message = {"type": "message", "role": "assistant", "content": str(message.content)}
        else:
            assistant_message = {"type": "message", "role": "assistant", "content": ""}

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

    def _extract_reasoning_content_and_summary(self, response_data: dict) -> tuple[Optional[str], Optional[str]]:
        """Extract actual reasoning content and summary from OpenAI Responses API.
        
        This method looks for the actual reasoning content and summary, not just metadata.
        It prioritizes actual content over summary but returns both if available.
        
        Args:
            response_data: Raw response data from Responses API
            
        Returns:
            Tuple of (reasoning_content, reasoning_summary)
            - reasoning_content: The full reasoning text if available 
            - reasoning_summary: The reasoning summary if available
        """
        reasoning_content = None
        reasoning_summary = None
        
        # First, check for reasoning items in output (contains the actual reasoning content)
        output_items = response_data.get("output", [])
        for item in output_items:
            if item.get("type") == "reasoning":
                # Extract content field - this contains the actual reasoning
                content = item.get("content")
                if content:
                    if isinstance(content, list):
                        # Content is array of content items, extract text
                        content_texts = []
                        for content_item in content:
                            if isinstance(content_item, dict) and content_item.get("type") == "reasoning_text":
                                text = content_item.get("text", "")
                                if text:
                                    content_texts.append(text)
                        if content_texts:
                            reasoning_content = "".join(content_texts)
                    elif isinstance(content, str):
                        # Content is direct string
                        reasoning_content = content
                
                # Extract summary field - this contains the reasoning summary
                summary = item.get("summary")
                if summary:
                    if isinstance(summary, list):
                        # Summary is array of content items, extract text
                        summary_texts = []
                        for summary_item in summary:
                            if isinstance(summary_item, dict) and summary_item.get("type") == "summary_text":
                                text = summary_item.get("text", "")
                                if text:
                                    summary_texts.append(text)
                        if summary_texts:
                            reasoning_summary = "".join(summary_texts)
                    elif isinstance(summary, str):
                        # Summary is direct string
                        reasoning_summary = summary
                        
                # If we found reasoning items, use the first one (OpenAI typically returns one)
                break
        
        # Fallback: check for summary in top-level reasoning metadata
        if not reasoning_summary and not reasoning_content:
            top_reasoning = response_data.get("reasoning", {})
            if isinstance(top_reasoning, dict):
                metadata_summary = top_reasoning.get("summary")
                if metadata_summary and isinstance(metadata_summary, str):
                    reasoning_summary = metadata_summary
        
        return reasoning_content, reasoning_summary

    def _process_reasoning_content(self, chat_completion_response: ChatCompletionResponse, response_data: dict):
        """Process reasoning content for reasoning models.

        This method:
        1. Extracts actual reasoning content and summary from response
        2. Stores the content in reasoning_content field for ReasoningMessage creation
        3. Preserves the complete reasoning object for round-trip fidelity
        """
        if not chat_completion_response.choices:
            return

        message = chat_completion_response.choices[0].message

        # Extract actual reasoning content and summary
        reasoning_content, reasoning_summary = self._extract_reasoning_content_and_summary(response_data)
        
        # Store actual reasoning text in reasoning_content for ReasoningMessage display
        if reasoning_content:
            # Use the actual reasoning content (preferred)
            message.reasoning_content = reasoning_content
            logger.debug(f"[REASONING] Using actual reasoning content ({len(reasoning_content)} chars)")
        elif reasoning_summary:
            # Fall back to reasoning summary if no full content
            message.reasoning_content = reasoning_summary
            logger.debug(f"[REASONING] Using reasoning summary ({len(reasoning_summary)} chars)")
        
        # Always preserve the original reasoning object in reasoning_content_signature for round-trip OpenAI conversion
        serialized_reasoning = self._serialize_reasoning_for_preservation(response_data)
        if serialized_reasoning:
            message.reasoning_content_signature = serialized_reasoning
            logger.debug(f"[REASONING] Preserved original reasoning object ({len(serialized_reasoning)} chars) for round-trip conversion")
        
        # Set omitted flag appropriately
        if reasoning_content:
            # We have actual readable content - don't set omitted flag
            message.omitted_reasoning_content = False
            logger.debug("[REASONING] Actual content available - omitted flag set to False")
        else:
            # Either summary or no content - set omitted flag
            message.omitted_reasoning_content = True
            logger.debug("[REASONING] Only summary/no content available - omitted flag set to True")

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
        # VALIDATION: Check tool call ID consistency before building request
        validation_context = {
            "model": llm_config.model,
            "tools_count": len(tools) if tools else 0,
            "messages_count": len(messages),
            "actor_id": getattr(self.actor, 'id', None) if self.actor else None,
        }
        
        validated_messages, analysis = validate_and_fix_conversation_before_api_call(messages, validation_context)
        
        # Log critical validation failures but don't block the request
        # This is for debugging the root cause of tool call ID issues
        if not analysis.is_valid():
            logger.error(f"CRITICAL tool call validation issues detected before OpenAI API call: {len(analysis.issues)} issues found")
            for issue in analysis.issues:
                if issue.severity.value in ['critical', 'error']:
                    logger.error(f"Tool call validation error: {issue.description} | Context: {issue.context}")
        elif analysis.has_warnings():
            logger.warning(f"Tool call validation warnings detected: {len(analysis.issues)} issues found")
        
        # Use the validated (and potentially fixed) messages
        messages = validated_messages
        
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
                # Handle both nested (Chat Completions) and flat formats
                if tool.get("type") == "function" and "function" in tool:
                    # Nested format (Chat Completions API) - extract the function
                    tool_def = tool["function"]
                else:
                    # Already flat format or old format
                    tool_def = tool
                
                tool_name = tool_def.get("name", "UNKNOWN_TOOL")

                # Validate tool structure and log issues
                if "parameters" not in tool_def:
                    logger.error(f"Tool '{tool_name}' is missing 'parameters' field. Full tool: {json.dumps(tool, default=str)}")
                    continue

                if not isinstance(tool_def["parameters"], dict):
                    logger.error(
                        f"Tool '{tool_name}' has invalid 'parameters' type: {type(tool_def['parameters'])}. Expected dict. Full tool: {json.dumps(tool, default=str)}"
                    )
                    continue

                # Check for missing 'required' field and log warning with context
                if "required" not in tool_def["parameters"]:
                    # Check if this is an MCP tool
                    tool_description = tool_def.get("description", "")
                    is_mcp_tool = "MCP tool" in tool_description or tool_name.startswith("mcp_")

                    logger.warning(
                        f"Tool '{tool_name}' is missing 'required' field in parameters. "
                        f"{'This appears to be an MCP tool. ' if is_mcp_tool else ''}"
                        f"Adding empty array. Tool parameters: {json.dumps(tool_def['parameters'], default=str)}"
                    )
                    tool_def["parameters"]["required"] = []

                # Create tool in flat format (not nested like Chat Completions API)
                converted_tool = {
                    "type": "function",
                    "name": tool_def["name"],
                    "description": tool_def["description"],
                    "parameters": tool_def["parameters"].copy(),  # Copy to avoid modifying original
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
                        structured_output_version = convert_to_structured_output(tool_def)
                        # Update the tool with structured output
                        converted_tool.update(structured_output_version)
                    except ValueError as e:
                        logger.warning(f"Failed to convert tool function to structured output, tool={tool_def}, error={e}")

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
            data["reasoning"] = {"effort": "minimal", "summary": "auto"}  # Use minimal effort with auto summary
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
        try:
            client = OpenAI(**self._prepare_client_kwargs(llm_config))
            response = client.responses.create(**request_data)

            # Convert to clean OpenAI format (matches official SDK behavior)
            return self.to_openai_format(response)
        except Exception as e:
            # Add error context for Responses API debugging
            from letta.log.error_context import log_llm_error_with_context
            log_llm_error_with_context(
                error=e,
                request_data=request_data,
                additional_context={
                    "error_location": "openai_client_request_sync",
                    "model": llm_config.model,
                    "endpoint": llm_config.model_endpoint,
                    "api_type": "responses_api"
                }
            )
            raise

    @trace_method
    async def request_async(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying asynchronous request to OpenAI Responses API.
        Returns response in clean OpenAI SDK format (ready for input reuse).
        """
        try:
            # Log structured request details using 'extra' for structured logging
            request_context = {
                "model": llm_config.model,
                "endpoint": llm_config.model_endpoint,
                "input_count": len(request_data.get('input', [])),
                "tools_count": len(request_data.get('tools', [])),
                "tool_choice": request_data.get('tool_choice'),
                "parallel_tools": request_data.get('parallel_tool_calls'),
                "temperature": request_data.get('temperature'),
                "max_output_tokens": request_data.get('max_output_tokens'),
            }
            
            # Add tool names (first 5 only for brevity)
            if request_data.get("tools"):
                request_context["tool_names"] = [t.get('name') for t in request_data["tools"][:5]]
                if len(request_data["tools"]) > 5:
                    request_context["tool_names"].append(f"... and {len(request_data['tools']) - 5} more")
            
            logger.info("[API_REQUEST] Responses API call starting", extra=request_context)

            kwargs = await self._prepare_client_kwargs_async(llm_config)
            client = AsyncOpenAI(**kwargs)
            response = await client.responses.create(**request_data)

            # Convert and analyze response
            clean_response = self.to_openai_format(response)
            
            # Count tool calls in response
            output_items = clean_response.get("output", [])
            tool_calls_info = []
            for item in output_items:
                if item.get("type") == "message" and item.get("tool_calls"):
                    for tc in item["tool_calls"]:
                        tool_calls_info.append({
                            "name": tc.get('function', {}).get('name'),
                            "id": tc.get('id')
                        })
                elif item.get("type") == "function_call":
                    tool_calls_info.append({
                        "name": item.get('name'),
                        "id": item.get('call_id')
                    })
            
            # Log structured response using 'extra' for better observability
            response_context = {
                "response_id": clean_response.get("id"),
                "model": clean_response.get("model"),
                "status": clean_response.get("status"),
                "output_count": len(output_items),
                "tool_calls_count": len(tool_calls_info),
                "usage": clean_response.get("usage", {}),
            }
            
            # Add tool call names if present (first 3 for brevity)
            if tool_calls_info:
                response_context["tool_calls"] = [tc["name"] for tc in tool_calls_info[:3]]
                if len(tool_calls_info) > 3:
                    response_context["tool_calls"].append(f"... and {len(tool_calls_info) - 3} more")
            
            # Log with appropriate level based on outcome
            if not tool_calls_info and request_data.get("tools"):
                logger.warning("[API_RESPONSE] No tool calls returned despite tools provided", extra=response_context)
            else:
                logger.info("[API_RESPONSE] Responses API call successful", extra=response_context)

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

            # Add comprehensive error context for debugging
            from letta.log.error_context import log_llm_error_with_context
            log_llm_error_with_context(
                error=e,
                request_data=request_data,
                additional_context={
                    "error_location": "openai_client_request_async",
                    "model": llm_config.model,
                    "endpoint": llm_config.model_endpoint,
                    "api_type": "responses_api",
                    "stream_mode": False
                }
            )

            # Log structured error with truncated request data
            error_context = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "model": request_data.get('model'),
                "tools_count": len(request_data.get('tools', [])),
                "input_count": len(request_data.get('input', [])),
                "tool_names": [t.get('name') for t in request_data.get('tools', [])[:5]],  # First 5 tool names
            }
            
            # Add truncated request sample for debugging
            if request_data.get('input'):
                # Show first and last message types only
                input_messages = request_data['input']
                error_context['first_input_type'] = input_messages[0].get('type') if input_messages else None
                error_context['last_input_type'] = input_messages[-1].get('type') if input_messages else None
                
            logger.error(f"[API_ERROR] Responses API call failed", extra=error_context)
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
