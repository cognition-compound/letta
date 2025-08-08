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
from letta.llm_api.helpers import add_inner_thoughts_to_functions, convert_to_structured_output, unpack_all_inner_thoughts_from_kwargs
from letta.llm_api.llm_client_base import LLMClientBase
from letta.local_llm.constants import INNER_THOUGHTS_KWARG, INNER_THOUGHTS_KWARG_DESCRIPTION, INNER_THOUGHTS_KWARG_DESCRIPTION_GO_FIRST
from letta.log import get_logger
from letta.otel.tracing import trace_method
from letta.schemas.embedding_config import EmbeddingConfig
from letta.schemas.enums import ProviderCategory, ProviderType
from letta.schemas.letta_message_content import MessageContentType
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.openai.chat_completion_request import ChatCompletionRequest
from letta.schemas.openai.chat_completion_request import FunctionCall as ToolFunctionChoiceFunctionCall
from letta.schemas.openai.chat_completion_request import FunctionSchema
from letta.schemas.openai.chat_completion_request import Tool as OpenAITool
from letta.schemas.openai.chat_completion_request import ToolFunctionChoice, cast_message_to_subtype
from letta.schemas.openai.chat_completion_response import ChatCompletionResponse
from letta.settings import model_settings

logger = get_logger(__name__)


def is_openai_reasoning_model(model: str) -> bool:
    """Utility function to check if the model is a 'reasoner'"""

    # NOTE: needs to be updated with new model releases
    # GPT-5 is a reasoning model according to OpenAI docs
    is_reasoning = model.startswith("o1") or model.startswith("o2") or model.startswith("o3") or model.startswith("o4") or model.startswith("gpt-5")
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
        
        Args:
            messages: List of PydanticMessage objects
            
        Returns:
            List of dicts in Responses API input format
        """
        response_input = []
        
        for message in messages:
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
                            content.append({
                                "type": "input_image",
                                "image_url": f"data:{item.source.media_type};base64,{item.source.data}"
                            })
                        else:
                            # Handle other content types as text fallback
                            content.append({"type": "input_text", "text": str(item)})
                
                response_input.append({
                    "role": "user", 
                    "content": content
                })
            
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
                        if hasattr(item, 'text'):
                            content.append({"type": "input_text", "text": item.text})
                        else:
                            content.append({"type": "input_text", "text": str(item)})
                else:
                    content.append({"type": "input_text", "text": str(message.content)})
                
                response_input.append({
                    "role": "system",
                    "content": content
                })
                
            elif message.role == "developer":
                # Developer role messages (if supported by model)
                content = []
                if isinstance(message.content, str):
                    content.append({"type": "input_text", "text": message.content})
                else:
                    content.append({"type": "input_text", "text": str(message.content)})
                
                response_input.append({
                    "role": "developer", 
                    "content": content
                })
            
            elif message.role == "tool":
                # Tool result messages
                content = []
                if isinstance(message.content, str):
                    content.append({"type": "input_text", "text": message.content})
                else:
                    content.append({"type": "input_text", "text": str(message.content)})
                
                tool_message = {
                    "role": "tool",
                    "content": content
                }
                # Add tool_call_id if present
                if hasattr(message, 'tool_call_id') and message.tool_call_id:
                    tool_message["tool_call_id"] = message.tool_call_id
                
                response_input.append(tool_message)
        
        return response_input
    
    def _convert_assistant_message(self, message: PydanticMessage) -> dict:
        """Convert assistant message to Responses API format."""
        content = []
        
        # Handle content
        if isinstance(message.content, str):
            if message.content:  # Only add non-empty content
                content.append({"type": "input_text", "text": message.content})
        elif isinstance(message.content, list):
            for item in message.content:
                if hasattr(item, 'text') and item.text:
                    content.append({"type": "input_text", "text": item.text})
                elif hasattr(item, 'type') and item.type == MessageContentType.text and hasattr(item, 'text'):
                    content.append({"type": "input_text", "text": item.text})
        
        assistant_message = {
            "role": "assistant",
            "content": content
        }
        
        # Handle tool calls if present
        if hasattr(message, 'tool_calls') and message.tool_calls:
            # Tool calls format should be compatible between APIs
            assistant_message["tool_calls"] = [tc.model_dump() for tc in message.tool_calls]
        
        return assistant_message

    def _convert_responses_to_chat_completion(self, response_data: dict) -> dict:
        """Convert Responses API response format to Chat Completions format."""
        
        # Extract output items 
        output_items = response_data.get("output", [])
        choices = []
        
        for i, item in enumerate(output_items):
            if item.get("type") == "message":
                message_data = item.get("message", {})
                
                # Convert content format
                content = self._convert_response_content(message_data.get("content", []))
                
                choice = {
                    "index": i,
                    "message": {
                        "role": message_data.get("role", "assistant"),
                        "content": content,
                        "tool_calls": message_data.get("tool_calls"),  # Should be compatible
                        "reasoning_content": self._extract_reasoning_content(response_data)
                    },
                    "finish_reason": response_data.get("status", "stop")  # Map status to finish_reason
                }
                choices.append(choice)
        
        return {
            "id": response_data.get("id"),
            "choices": choices,
            "created": int(datetime.now().timestamp()),
            "model": response_data.get("model"),
            "usage": response_data.get("usage", {}),
            "system_fingerprint": response_data.get("system_fingerprint")
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
            if item.get("type") == "text":
                text_parts.append(item.get("text", ""))
            elif item.get("type") == "input_text":
                text_parts.append(item.get("text", ""))
            # Note: We could handle other content types like images here if needed
            # For now, focus on text content which is most common
            
        return "".join(text_parts)

    def _extract_reasoning_content(self, response_data: dict) -> Optional[str]:
        """Extract reasoning content from Responses API response.
        
        Args:
            response_data: Raw response data from Responses API
            
        Returns:
            Reasoning content if available, None otherwise
        """
        reasoning_items = response_data.get("reasoning", [])
        if not reasoning_items:
            return None
            
        reasoning_parts = []
        for item in reasoning_items:
            if isinstance(item, dict) and "text" in item:
                reasoning_parts.append(item["text"])
            elif isinstance(item, str):
                reasoning_parts.append(item)
                
        return "\n".join(reasoning_parts) if reasoning_parts else None

    def _process_reasoning_content(self, chat_completion_response: ChatCompletionResponse, response_data: dict):
        """Process reasoning content for reasoning models like GPT-5."""
        reasoning_content = self._extract_reasoning_content(response_data)
        if reasoning_content and chat_completion_response.choices:
            # Add reasoning content to the first choice's message
            if not hasattr(chat_completion_response.choices[0].message, 'reasoning_content'):
                chat_completion_response.choices[0].message.reasoning_content = reasoning_content
            else:
                chat_completion_response.choices[0].message.reasoning_content = reasoning_content

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
        if tools and llm_config.put_inner_thoughts_in_kwargs:
            # Special case for LM Studio backend since it needs extra guidance to force out the thoughts first
            # TODO(fix)
            inner_thoughts_desc = (
                INNER_THOUGHTS_KWARG_DESCRIPTION_GO_FIRST if ":1234" in llm_config.model_endpoint else INNER_THOUGHTS_KWARG_DESCRIPTION
            )
            tools = add_inner_thoughts_to_functions(
                functions=tools,
                inner_thoughts_key=INNER_THOUGHTS_KWARG,
                inner_thoughts_description=inner_thoughts_desc,
                put_inner_thoughts_first=True,
            )

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
            "max_completion_tokens": llm_config.max_tokens,
            # NOTE: the reasoners that don't support temperature require 1.0, not None
            "temperature": llm_config.temperature if supports_temperature_param(model) else 1.0,
        }
        
        # Handle tools (format should be compatible between APIs)
        if tools:
            # Convert tools to proper format with structured output if supported
            converted_tools = []
            for tool in tools:
                converted_tool = {"type": "function", "function": tool}
                if supports_structured_output(llm_config):
                    try:
                        structured_output_version = convert_to_structured_output(tool)
                        converted_tool["function"] = structured_output_version
                    except ValueError as e:
                        logger.warning(f"Failed to convert tool function to structured output, tool={tool}, error={e}")
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

        # Add frequency penalty if specified
        if llm_config.frequency_penalty is not None:
            data["frequency_penalty"] = llm_config.frequency_penalty

        # Always set user id for openai requests
        if self.actor:
            data["user"] = self.actor.id
        else:
            data["user"] = ""

        # Handle special endpoint configurations
        if llm_config.model_endpoint == LETTA_MODEL_ENDPOINT:
            if not self.actor:
                # override user id for inference.letta.com
                import uuid
                data["user"] = str(uuid.UUID(int=0))
            data["model"] = "memgpt-openai"

        return data

    @trace_method
    def request(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying synchronous request to OpenAI Responses API and returns raw response dict.
        """
        client = OpenAI(**self._prepare_client_kwargs(llm_config))
        response = client.responses.create(**request_data)
        return response.model_dump()

    @trace_method
    async def request_async(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying asynchronous request to OpenAI Responses API and returns raw response dict.
        """
        kwargs = await self._prepare_client_kwargs_async(llm_config)
        client = AsyncOpenAI(**kwargs)

        response = await client.responses.create(**request_data)
        return response.model_dump()

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
        
        # Unpack inner thoughts if they were embedded in function arguments
        if llm_config.put_inner_thoughts_in_kwargs:
            chat_completion_response = unpack_all_inner_thoughts_from_kwargs(
                response=chat_completion_response, inner_thoughts_key=INNER_THOUGHTS_KWARG
            )

        # Handle reasoning content for reasoning models
        if is_openai_reasoning_model(llm_config.model):
            self._process_reasoning_content(chat_completion_response, response_data)
            # Also set the omitted reasoning flag for backward compatibility
            if chat_completion_response.choices:
                chat_completion_response.choices[0].message.omitted_reasoning_content = True

        return chat_completion_response

    @trace_method
    async def stream_async(self, request_data: dict, llm_config: LLMConfig) -> AsyncStream[ChatCompletionChunk]:
        """
        Performs underlying asynchronous streaming request to OpenAI Responses API and returns the async stream iterator.
        """
        kwargs = await self._prepare_client_kwargs_async(llm_config)
        client = AsyncOpenAI(**kwargs)
        response_stream = await client.responses.create(
            **request_data, stream=True, stream_options={"include_usage": True}
        )
        return response_stream

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
