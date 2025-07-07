import json
import time
from abc import abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from anthropic.types.beta.messages import BetaMessageBatch
from openai import AsyncStream, Stream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from letta.errors import LLMError
from letta.log import get_logger, LazyLogContext, create_lazy_context, lazy_log_enabled
from letta.otel.tracing import log_event, trace_method
from letta.schemas.embedding_config import EmbeddingConfig
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message
from letta.schemas.openai.chat_completion_response import ChatCompletionResponse
from letta.schemas.provider_trace import ProviderTraceCreate
from letta.services.telemetry_manager import TelemetryManager

if TYPE_CHECKING:
    from letta.orm import User


class LLMClientBase:
    """
    Abstract base class for LLM clients, formatting the request objects,
    handling the downstream request and parsing into chat completions response format
    """

    def __init__(
        self,
        put_inner_thoughts_first: Optional[bool] = True,
        use_tool_naming: bool = True,
        actor: Optional["User"] = None,
    ):
        self.actor = actor
        self.put_inner_thoughts_first = put_inner_thoughts_first
        self.use_tool_naming = use_tool_naming
        self.logger = get_logger(__name__)

    @trace_method
    def send_llm_request(
        self,
        messages: List[Message],
        llm_config: LLMConfig,
        tools: Optional[List[dict]] = None,  # TODO: change to Tool object
        force_tool_call: Optional[str] = None,
        telemetry_manager: Optional["TelemetryManager"] = None,
        step_id: Optional[str] = None,
    ) -> Union[ChatCompletionResponse, Stream[ChatCompletionChunk]]:
        """
        Issues a request to the downstream model endpoint and parses response.
        If stream=True, returns a Stream[ChatCompletionChunk] that can be iterated over.
        Otherwise returns a ChatCompletionResponse.
        """
        start_time = time.time()
        provider_name = getattr(llm_config, "provider", "unknown")
        model_name = getattr(llm_config, "model", "unknown")

        # Use lazy evaluation for expensive metrics calculation
        def _calculate_metrics():
            num_messages = len(messages)
            num_tools = len(tools) if tools else 0
            total_chars = sum(len(str(msg.text)) for msg in messages if hasattr(msg, "text") and msg.text)
            return {"num_messages": num_messages, "num_tools": num_tools, "total_input_chars": total_chars}

        request_data = self.build_request_data(messages, llm_config, tools, force_tool_call)

        try:
            log_event(name="llm_request_sent", attributes=request_data)

            # Use lazy logging context for expensive request metrics
            if lazy_log_enabled(self.logger, logging.INFO):
                lazy_ctx = create_lazy_context(self.logger, logging.INFO)
                lazy_ctx.add_value("event_type", "llm_request_start")
                lazy_ctx.add_value("provider", provider_name)
                lazy_ctx.add_value("model", model_name)
                lazy_ctx.add_value("user_id", str(self.actor.id) if self.actor else None)
                lazy_ctx.add_value(
                    "organization_id", str(self.actor.organization_id) if self.actor and self.actor.organization_id else None
                )
                lazy_ctx.add_value("step_id", step_id)
                lazy_ctx.add_lazy_value("metrics", _calculate_metrics)
                lazy_ctx.add_value("has_force_tool_call", force_tool_call is not None)
                lazy_ctx.add_value("is_streaming", getattr(llm_config, "stream", False))
                lazy_ctx.add_lazy_string("timestamp", "{}", datetime.now(timezone.utc).isoformat())

                # Flatten metrics into main context
                metrics = lazy_ctx._context_data["metrics"].evaluate() if "metrics" in lazy_ctx._context_data else {}
                for key, value in metrics.items():
                    lazy_ctx.add_value(key, value)

                lazy_ctx.info("LLM API request initiated")

            response_data = self.request(request_data, llm_config)
            response_time_ms = round((time.time() - start_time) * 1000, 2)

            # Extract usage metrics from response
            usage_metrics = self._extract_usage_metrics(response_data)

            if step_id and telemetry_manager:
                telemetry_manager.create_provider_trace(
                    actor=self.actor,
                    provider_trace_create=ProviderTraceCreate(
                        request_json=request_data,
                        response_json=response_data,
                        step_id=step_id,
                        organization_id=self.actor.organization_id,
                    ),
                )

            log_event(name="llm_response_received", attributes=response_data)

            # Use lazy logging context for expensive response metrics
            if lazy_log_enabled(self.logger, logging.INFO):
                lazy_ctx = create_lazy_context(self.logger, logging.INFO)
                lazy_ctx.add_value("event_type", "llm_request_success")
                lazy_ctx.add_value("provider", provider_name)
                lazy_ctx.add_value("model", model_name)
                lazy_ctx.add_value("user_id", str(self.actor.id) if self.actor else None)
                lazy_ctx.add_value(
                    "organization_id", str(self.actor.organization_id) if self.actor and self.actor.organization_id else None
                )
                lazy_ctx.add_value("step_id", step_id)
                lazy_ctx.add_value("response_time_ms", response_time_ms)

                # Add usage metrics with lazy evaluation
                for key, value in usage_metrics.items():
                    lazy_ctx.add_value(key, value)

                lazy_ctx.add_lazy_string("timestamp", "{}", datetime.now(timezone.utc).isoformat())
                lazy_ctx.info("LLM API request completed successfully")

        except Exception as e:
            error_time_ms = round((time.time() - start_time) * 1000, 2)

            # Use lazy logging context for error metrics
            if lazy_log_enabled(self.logger, logging.ERROR):
                lazy_ctx = create_lazy_context(self.logger, logging.ERROR)
                lazy_ctx.add_value("event_type", "llm_request_error")
                lazy_ctx.add_value("provider", provider_name)
                lazy_ctx.add_value("model", model_name)
                lazy_ctx.add_value("user_id", str(self.actor.id) if self.actor else None)
                lazy_ctx.add_value(
                    "organization_id", str(self.actor.organization_id) if self.actor and self.actor.organization_id else None
                )
                lazy_ctx.add_value("step_id", step_id)
                lazy_ctx.add_value("error_time_ms", error_time_ms)
                lazy_ctx.add_value("error_type", type(e).__name__)
                lazy_ctx.add_value("error_message", str(e))
                lazy_ctx.add_lazy_value("request_metrics", _calculate_metrics)
                lazy_ctx.add_lazy_string("timestamp", "{}", datetime.now(timezone.utc).isoformat())

                # Flatten request metrics into main context
                metrics = lazy_ctx._context_data["request_metrics"].evaluate() if "request_metrics" in lazy_ctx._context_data else {}
                for key, value in metrics.items():
                    lazy_ctx.add_value(key, value)

                lazy_ctx.error(f"LLM API request failed: {str(e)}", exc_info=True)

            raise self.handle_llm_error(e)

        return self.convert_response_to_chat_completion(response_data, messages, llm_config)

    def _extract_usage_metrics(self, response_data: dict) -> dict:
        """Extract usage metrics from LLM response for logging."""
        metrics = {}

        # Try to extract token usage (OpenAI format is most common)
        if isinstance(response_data, dict):
            usage = response_data.get("usage", {})
            if usage:
                metrics["prompt_tokens"] = usage.get("prompt_tokens")
                metrics["completion_tokens"] = usage.get("completion_tokens")
                metrics["total_tokens"] = usage.get("total_tokens")

                # Estimate cost based on token usage (rough approximation)
                if metrics.get("total_tokens"):
                    # Very rough cost estimation (actual costs vary by provider/model)
                    estimated_cost = metrics["total_tokens"] * 0.00002  # ~$0.02 per 1K tokens
                    metrics["estimated_cost"] = round(estimated_cost, 6)

            # Extract finish reason
            if "choices" in response_data and response_data["choices"]:
                first_choice = response_data["choices"][0]
                metrics["finish_reason"] = first_choice.get("finish_reason")

                # Check for tool calls
                message = first_choice.get("message", {})
                metrics["has_tool_calls"] = bool(message.get("tool_calls"))

        return metrics

    @trace_method
    async def send_llm_request_async(
        self,
        request_data: dict,
        messages: List[Message],
        llm_config: LLMConfig,
        telemetry_manager: "TelemetryManager | None" = None,
        step_id: str | None = None,
    ) -> Union[ChatCompletionResponse, AsyncStream[ChatCompletionChunk]]:
        """
        Issues a request to the downstream model endpoint.
        If stream=True, returns an AsyncStream[ChatCompletionChunk] that can be async iterated over.
        Otherwise returns a ChatCompletionResponse.
        """

        try:
            log_event(name="llm_request_sent", attributes=request_data)
            response_data = await self.request_async(request_data, llm_config)
            await telemetry_manager.create_provider_trace_async(
                actor=self.actor,
                provider_trace_create=ProviderTraceCreate(
                    request_json=request_data,
                    response_json=response_data,
                    step_id=step_id,
                    organization_id=self.actor.organization_id,
                ),
            )

            log_event(name="llm_response_received", attributes=response_data)
        except Exception as e:
            raise self.handle_llm_error(e)

        return self.convert_response_to_chat_completion(response_data, messages, llm_config)

    async def send_llm_batch_request_async(
        self,
        agent_messages_mapping: Dict[str, List[Message]],
        agent_tools_mapping: Dict[str, List[dict]],
        agent_llm_config_mapping: Dict[str, LLMConfig],
    ) -> Union[BetaMessageBatch]:
        raise NotImplementedError

    @abstractmethod
    def build_request_data(
        self,
        messages: List[Message],
        llm_config: LLMConfig,
        tools: List[dict],
        force_tool_call: Optional[str] = None,
    ) -> dict:
        """
        Constructs a request object in the expected data format for this client.
        """
        raise NotImplementedError

    @abstractmethod
    def request(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying request to llm and returns raw response.
        """
        raise NotImplementedError

    @abstractmethod
    async def request_async(self, request_data: dict, llm_config: LLMConfig) -> dict:
        """
        Performs underlying request to llm and returns raw response.
        """
        raise NotImplementedError

    @abstractmethod
    async def request_embeddings(self, texts: List[str], embedding_config: EmbeddingConfig) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts (List[str]): List of texts to generate embeddings for.
            embedding_config (EmbeddingConfig): Configuration for the embedding model.

        Returns:
            embeddings (List[List[float]]): List of embeddings for the input texts.
        """
        raise NotImplementedError

    @abstractmethod
    def convert_response_to_chat_completion(
        self,
        response_data: dict,
        input_messages: List[Message],
        llm_config: LLMConfig,
    ) -> ChatCompletionResponse:
        """
        Converts custom response format from llm client into an OpenAI
        ChatCompletionsResponse object.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream_async(self, request_data: dict, llm_config: LLMConfig) -> AsyncStream[ChatCompletionChunk]:
        """
        Performs underlying streaming request to llm and returns raw response.
        """
        raise NotImplementedError(f"Streaming is not supported for {llm_config.model_endpoint_type}")

    @abstractmethod
    def handle_llm_error(self, e: Exception) -> Exception:
        """
        Maps provider-specific errors to common LLMError types.
        Each LLM provider should implement this to translate their specific errors.

        Args:
            e: The original provider-specific exception

        Returns:
            An LLMError subclass that represents the error in a provider-agnostic way
        """
        return LLMError(f"Unhandled LLM error: {str(e)}")

    def _fix_truncated_json_response(self, response: ChatCompletionResponse) -> ChatCompletionResponse:
        """
        Fixes truncated JSON responses by ensuring the content is properly formatted.
        This is a workaround for some providers that may return incomplete JSON.
        """
        if response.choices and response.choices[0].message and response.choices[0].message.tool_calls:
            tool_call_args_str = response.choices[0].message.tool_calls[0].function.arguments
            try:
                json.loads(tool_call_args_str)
            except json.JSONDecodeError:
                try:
                    json_str_end = ""
                    quote_count = tool_call_args_str.count('"')
                    if quote_count % 2 != 0:
                        json_str_end = json_str_end + '"'

                    open_braces = tool_call_args_str.count("{")
                    close_braces = tool_call_args_str.count("}")
                    missing_braces = open_braces - close_braces
                    json_str_end += "}" * missing_braces
                    fixed_tool_call_args_str = tool_call_args_str[: -len(json_str_end)] + json_str_end
                    json.loads(fixed_tool_call_args_str)
                    response.choices[0].message.tool_calls[0].function.arguments = fixed_tool_call_args_str
                except json.JSONDecodeError:
                    pass
        return response
