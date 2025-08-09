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
    """Log LLM errors with full request context for debugging.
    
    Args:
        error: The exception that occurred
        request_data: The LLM request data that caused the error
        agent_id: ID of the agent making the request
        additional_context: Additional debugging context
    """
    
    context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        
        # The actual request (truncated for readability)
        "model": request_data.get("model"),
        "prompt_preview": truncate_for_logging(request_data.get("messages", [])),
        "tools_used": [t.get("name", "unknown") for t in request_data.get("tools", [])],
        "tool_choice": request_data.get("tool_choice"),
        
        # Context
        "agent_id": agent_id,
        "stream_enabled": request_data.get("stream", False),
        
        # Raw request (for deep debugging, heavily truncated)
        "full_request_sample": _truncate_json(request_data, max_chars=2000)
    }
    
    # Add any additional context
    if additional_context:
        context.update(additional_context)
    
    logger.error(f"LLM request failed: {str(error)}", extra=context)


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