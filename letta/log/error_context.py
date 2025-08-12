import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def log_llm_error_with_context(
    error: Exception, 
    request_data: Dict[str, Any], 
    agent_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
):
    """Log LLM errors with structured context for debugging.
    
    Args:
        error: The exception that occurred
        request_data: The LLM request data that caused the error
        agent_id: ID of the agent making the request
        additional_context: Additional debugging context
    """
    
    # Build structured context for logging
    context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "model": request_data.get("model"),
        "agent_id": agent_id,
        "stream_enabled": request_data.get("stream", False),
    }
    
    # Add input/message information
    if "input" in request_data:  # Responses API format
        input_messages = request_data.get("input", [])
        context["input_count"] = len(input_messages)
        if input_messages:
            context["first_input_type"] = input_messages[0].get("type")
            context["last_input_type"] = input_messages[-1].get("type")
    elif "messages" in request_data:  # Chat Completions API format
        messages = request_data.get("messages", [])
        context["messages_count"] = len(messages)
        context["message_preview"] = truncate_for_logging(messages)
    
    # Add tool information
    tools = request_data.get("tools", [])
    if tools:
        context["tools_count"] = len(tools)
        context["tool_names"] = [t.get("name", "unknown") for t in tools[:5]]  # First 5 tools
        if len(tools) > 5:
            context["tool_names"].append(f"... and {len(tools) - 5} more")
        context["tool_choice"] = request_data.get("tool_choice")
    
    # Add any additional context
    if additional_context:
        context.update(additional_context)
    
    # Use structured logging with 'extra' parameter
    logger.error("LLM request failed", extra=context)


def truncate_for_logging(messages: List[Dict], max_chars: int = 800) -> str:
    """Make prompts readable in logs without losing debugging value.
    
    Args:
        messages: List of message dictionaries from LLM request
        max_chars: Maximum characters to include in output
        
    Returns:
        Truncated string representation of messages for logging
    """
    
    if not messages:
        return "No messages"
        
    parts = []
    
    # Always include system message (first message, truncated)
    if messages and messages[0].get("role") == "system":
        system_content = messages[0].get("content", "")[:200]
        parts.append(f"System: {system_content}{'...' if len(system_content) == 200 else ''}")
    
    # Always include last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_content = msg.get("content", "")[:300] 
            parts.append(f"User: {user_content}{'...' if len(user_content) == 300 else ''}")
            break
    
    # Show message count for context
    parts.insert(-1, f"[{len(messages)} total messages]")
    
    return " | ".join(parts)


def _truncate_json(data: Any, max_chars: int = 2000) -> str:
    """Truncate JSON data for logging with proper error handling."""
    try:
        json_str = json.dumps(data, default=str)
        if len(json_str) > max_chars:
            return json_str[:max_chars] + "..."
        return json_str
    except Exception:
        return f"<unable to serialize data: {type(data).__name__}>"