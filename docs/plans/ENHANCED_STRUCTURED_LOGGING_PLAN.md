# Simple Error Debugging Logging Plan

**Status:** Draft  
**Created:** 2025-01-09  
**Priority:** High  
**Timeline:** 1-2 days max

## Problem

When shit breaks (like the recent "Unhandled LLM error: 'type'" streaming error), we have no fucking clue what LLM request caused it. The error logs are useless - they don't tell us:

- What was the actual request sent to the LLM?
- Which tools were involved?
- What agent was making the request?
- What was the conversation context?

## Solution: Add Request Context to Error Logs

**One simple change:** When any LLM-related error occurs, log the full request context that caused it.

### What We'll Log in Errors

```python
def log_llm_error_with_context(error: Exception, request_data: dict, agent_id: str = None):
    """Log an LLM error with the full request context that caused it."""
    
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
        "request_id": getattr(request, "state", {}).get("request_id", "unknown"),
        
        # Raw request (for deep debugging, heavily truncated)
        "full_request_sample": json.dumps(request_data, default=str)[:2000] + "..." if len(json.dumps(request_data, default=str)) > 2000 else json.dumps(request_data, default=str)
    }
    
    logger.error(f"LLM request failed: {str(error)}", extra=context)
```

### Smart Prompt Truncation

```python
def truncate_for_logging(messages: list, max_chars: int = 800) -> str:
    """Make prompts readable in logs without losing debugging value."""
    
    if not messages:
        return "No messages"
        
    parts = []
    char_count = 0
    
    # Always include system message (first message, truncated)
    if messages and messages[0].get("role") == "system":
        system_content = messages[0].get("content", "")[:200]
        parts.append(f"System: {system_content}{'...' if len(system_content) == 200 else ''}")
        char_count += len(parts[-1])
    
    # Always include last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_content = msg.get("content", "")[:300] 
            parts.append(f"User: {user_content}{'...' if len(user_content) == 300 else ''}")
            char_count += len(parts[-1])
            break
    
    # Show message count for context
    parts.insert(-1, f"[{len(messages)} total messages]")
    
    return " | ".join(parts)
```

## Implementation

### Step 1: Add Error Logging Utility (30 minutes)

Create `letta/logging/error_context.py`:

```python
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
    """Log LLM errors with full request context for debugging."""
    # Implementation above
    
def truncate_for_logging(messages: List[Dict], max_chars: int = 800) -> str:
    """Smart prompt truncation for logs.""" 
    # Implementation above
```

### Step 2: Add to Streaming Error Handler (15 minutes)

In `letta/server/rest_api/streaming_response.py:169` (the "Unhandled Streaming Error" location):

```python
except Exception as exc:
    # NEW: Add request context to error logs
    if hasattr(self, '_llm_request_data') and hasattr(self, '_agent_id'):
        from letta.logging.error_context import log_llm_error_with_context
        log_llm_error_with_context(
            error=exc,
            request_data=self._llm_request_data,
            agent_id=self._agent_id,
            additional_context={"error_location": "streaming_response"}
        )
    
    logger.exception("Unhandled Streaming Error")  # Keep existing log
    # ... rest of existing error handling
```

### Step 3: Pass Request Data to Streaming Response (15 minutes)

In the agent streaming methods, pass the LLM request data:

```python
# In letta/agents/base_agent.py or wherever streaming is initiated
response = StreamingResponseWithStatusCode(...)
# Add request context for error logging
response._llm_request_data = llm_request_data  # The actual request sent to LLM
response._agent_id = self.agent_id
```

### Step 4: Add to Other Critical Error Points (30 minutes)

- `letta/llm_api/openai_client.py` - API call failures
- `letta/llm_api/helpers.py:85` - The convert_to_structured_output error we just fixed
- Any other places that catch LLM exceptions

## That's It

**Total implementation time:** ~90 minutes

**Result:** When anything LLM-related breaks, we immediately see:
- The truncated prompt that caused it
- Which tools were involved  
- What agent made the request
- The error context we need to debug

**No complex schemas, no performance metrics, no multi-phase rollout.** Just useful error logs.

## Example Output

Instead of this useless log:
```
ERROR: Unhandled Streaming Error
KeyError: 'type'
```

We get this useful log:
```
ERROR: LLM request failed: KeyError: 'type'
{
  "error_type": "KeyError",
  "error_message": "'type'",
  "model": "gpt-4o",
  "prompt_preview": "System: You are Letta, an AI assistant... | [23 total messages] | User: Help me send a message to the other agent",
  "tools_used": ["send_message", "core_memory_append", "archival_memory_search"],
  "tool_choice": "auto", 
  "agent_id": "agent-abc123",
  "stream_enabled": true,
  "request_id": "req-def456",
  "error_location": "streaming_response"
}
```

Now we can debug the damn thing.

---

**Next step:** Implement this simple logging enhancement in 90 minutes and never again wonder "what request caused this error?"