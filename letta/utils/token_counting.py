"""
Centralized token counting utilities for all LLM providers.

This module consolidates all token counting logic and provides proper fallback
strategies for models not yet supported by tiktoken.
"""

from typing import Dict, List, Optional

import tiktoken

from letta.log import get_logger

logger = get_logger(__name__)


def get_encoding_for_model(model: str) -> tiktoken.Encoding:
    """
    Get the appropriate tiktoken encoding for a model.

    Uses tiktoken's built-in model mapping for all known models,
    with specific workarounds only for models not yet in tiktoken.

    Args:
        model: The model name (e.g., "gpt-5-chat-latest", "gpt-4o")

    Returns:
        tiktoken.Encoding: The appropriate encoding for the model
    """
    try:
        # Try tiktoken's built-in model mapping first
        # This handles all officially supported models automatically
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # Model not in tiktoken's registry - only need workarounds for specific cases
        model_lower = model.lower()

        # GPT-5 family - probably uses o200k_base (same as GPT-4o/o1 series)
        if model_lower.startswith(("gpt-5", "gpt5")):
            return tiktoken.get_encoding("o200k_base")

        # For any other unknown model, let user know we're guessing
        logger.warning(f"Unknown model '{model}' not in tiktoken registry, falling back to o200k_base")
        return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str, model: str) -> int:
    """
    Count tokens in a text string using the appropriate encoding for the model.

    Args:
        text: The text to count tokens for
        model: The model name to determine encoding

    Returns:
        int: Number of tokens in the text
    """
    if not text:
        return 0

    encoding = get_encoding_for_model(model)
    return len(encoding.encode(text))


def num_tokens_from_messages(messages: List[Dict], model: str) -> int:
    """
    Count tokens used by a list of messages, including OpenAI chat format overhead.

    Adapted from OpenAI cookbook:
    https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb

    Args:
        messages: List of message dicts in OpenAI format
        model: The model name to determine encoding and overhead

    Returns:
        int: Total number of tokens including message formatting overhead
    """
    if not messages:
        return 0

    encoding = get_encoding_for_model(model)

    # Message formatting token costs vary by model family
    if "gpt-3.5-turbo" in model or "gpt-35-turbo" in model:
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif any(family in model for family in ["gpt-4", "gpt-5", "o1", "o2", "o3", "o4"]):
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        # Unknown model, use GPT-4 as reasonable default
        logger.warning(f"Unknown model '{model}' for message token counting, using GPT-4 format")
        tokens_per_message = 3
        tokens_per_name = 1

    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            if isinstance(value, str):
                num_tokens += len(encoding.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name

    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


def num_tokens_from_functions(functions: List[Dict], model: str) -> int:
    """
    Count tokens used by function definitions in OpenAI function calling.

    Args:
        functions: List of function definition dicts
        model: The model name to determine encoding

    Returns:
        int: Total number of tokens for all function definitions
    """
    if not functions:
        return 0

    encoding = get_encoding_for_model(model)

    num_tokens = 0
    for function in functions:
        # Convert function to string representation for token counting
        # This matches OpenAI's internal function token calculation
        function_tokens = len(encoding.encode(str(function)))
        num_tokens += function_tokens

    return num_tokens


# Backward compatibility - export the main functions
__all__ = [
    "count_tokens",
    "num_tokens_from_messages",
    "num_tokens_from_functions",
    "get_encoding_for_model",
]
