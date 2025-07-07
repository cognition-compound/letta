# Unified Send Function Implementation

## Overview

This document describes the implementation of the unified `send()` function in Letta, which consolidates all message sending functionality into a single, consistent interface. This work was completed on 2025-01-04, with a major architectural change completed on 2025-01-07 to remove synchronous messaging entirely.

## Background

Previously, Letta had multiple functions for sending messages to different targets:
- `send_message()` - Send to human user
- `send_message_to_agent()` - Send to another agent (synchronous)
- `send_message_to_agent_async()` - Send to another agent (asynchronous)
- `send_message_to_agent_and_wait_for_reply()` - Send and wait for response
- `send_message_to_all_agents_in_group()` - Broadcast to group
- `send_message_to_agents_matching_tags()` - Broadcast by tags

This fragmentation made the API inconsistent and harder to use.

## The Unified Send Function

### Location
`/letta/functions/function_sets/multi_agent.py` (lines 181-229)

### Signature
```python
def send(self: "Agent", message: str, to: str) -> str
```

### Parameters
- `message`: The content to send
- `to`: Target specification using a simple routing syntax:
  - `"user"` - sends to the human user
  - `"agent:<agent_id>"` - sends to a specific agent (always async)
  - `"group:<group_id>"` - sends to all agents in a group
  - `"broadcast:<tag>"` - sends to all agents with the specified tag

### Examples
```python
send("Hello!", to="user")                    # To human
send("Status update", to="agent:agent-123")  # Async to agent
send("Alert", to="broadcast:critical")       # Broadcast by tag
```

## Architecture Change: Async-Only Messaging (2025-01-07)

After the initial implementation, we identified a fundamental architectural issue with synchronous messaging:
- `wait_for_reply=True` caused blocking behavior that interrupted natural agent execution
- It created duplicate message delivery (once as tool return, once as system message)
- It went against the event-driven nature of the agent system

**Solution**: Removed the `wait_for_reply` parameter entirely. All agent-to-agent communication is now asynchronous (fire-and-forget), allowing for:
- Cleaner, more natural agent interaction patterns
- No execution blocking or interruption
- Consistent async messaging behavior
- Simplified API surface

## Implementation Details

### 1. Tool Registration

The function needed to be registered in multiple places:

#### a. Constants (`/letta/constants.py`)
Added to `MULTI_AGENT_TOOLS` list:
```python
"send",
"send_message_to_agent_async",  # Also added this missing function
```

#### b. Tool Executor (`/letta/services/tool_executor/multi_agent_tool_executor.py`)
Added to the `function_map` dictionary (lines 33-34):
```python
"send_message_to_agent_async": self.send_message_to_agent_async,
"send": self.send,
```

And implemented the executor methods following the existing pattern.

### 2. Message Flow Discovery

Through investigation, we discovered how messages flow through Letta:

#### Step 1: Function Execution
When an agent calls `send("Hello", to="user")`:
1. The `send` function in `multi_agent.py` is executed
2. It routes to the appropriate handler based on the `to` parameter
3. For `to="user"`, it internally calls `send_message(self, message)`

#### Step 2: Interface Display
The `send_message` function:
```python
def send_message(self: "Agent", message: str) -> Optional[str]:
    if self.interface:
        self.interface.assistant_message(message)
    return None
```
This only displays the message in the interface (ADE, CLI, etc.) but does NOT persist it to the database.

#### Step 3: Message Persistence Problem
Messages sent via `send(to="user")` were visible in the ADE but not when polling the API because they weren't persisted. The actual persistence happens at a higher level when processing LLM responses.

### 3. Streaming Interface Support

We updated both streaming interfaces to recognize the `send` tool:

#### OpenAI Streaming Interface (`/letta/interfaces/openai_streaming_interface.py`)
Lines 186-189 and 235-239:
```python
is_send_to_user = (
    self.function_name_buffer == self.assistant_message_tool_name or
    (self.function_name_buffer == "send" and 
     self.optimistic_json_parser.parse(self.current_function_arguments).get("to") == "user")
)
```

#### Anthropic Streaming Interface (`/letta/interfaces/anthropic_streaming_interface.py`)
Lines 292-295:
```python
is_send_to_user = (
    self.tool_call_name == DEFAULT_MESSAGE_TOOL or 
    (self.tool_call_name == "send" and current_parsed.get("to") == "user")
)
```

### 4. Message Persistence Fix

The key discovery was in `/letta/schemas/message.py` in the `to_letta_messages()` method. This method converts database messages to Letta's API format and has special handling for `send_message` tool calls.

We added support for the `send` function (lines 336-367):
```python
# Handle both send_message and send with to="user"
is_send_message = tool_call.function.name == assistant_message_tool_name
is_send_to_user = False

if tool_call.function.name == "send":
    try:
        func_args = parse_json(tool_call.function.arguments)
        if func_args.get("to") == "user":
            is_send_to_user = True
    except:
        pass

if use_assistant_message and (is_send_message or is_send_to_user):
    # Extract message content from the appropriate parameter
    message_key = assistant_message_tool_kwarg if is_send_message else "message"
    message_string = func_args[message_key]
    # Create AssistantMessage instead of ToolCallMessage
    messages.append(AssistantMessage(...))
```

## Message Processing Flow

1. **Agent calls tool** → `send("Hello", to="user")`
2. **Tool executes** → Routes to `send_message()` → Displays in interface
3. **LLM response created** → Contains tool_calls with the send function
4. **Response processed** → `create_letta_messages_from_llm_response()` in `utils.py`
5. **Messages saved** → Tool call and tool response messages persisted to DB
6. **API conversion** → `to_letta_messages()` converts send/send_message to AssistantMessage
7. **User sees message** → Polling returns the AssistantMessage, not the tool call

## Benefits

1. **Unified API** - Single function for all messaging needs
2. **Explicit routing** - Clear target specification with `to` parameter
3. **Async-only architecture** - All agent communication is non-blocking and event-driven
4. **Consistent behavior** - Same function whether sending to user, agent, or group
5. **Better discoverability** - One function to learn instead of six
6. **Simplified API** - No complex sync/async parameter decisions

## Technical Debt Identified

During implementation, we discovered that `/letta/schemas/message.py` is a 1174-line monster class that violates many software engineering principles. It handles message data, format conversions for multiple providers (OpenAI, Anthropic, Google, Cohere), and Letta format conversions all in one place. This should be refactored into smaller, focused classes.

## Bug Fix: Agent-to-Agent Message Display (2025-01-07)

### Issue
When the ADE (Agent Development Environment) set `assistant_message_tool_name="send"`, ALL `send()` calls were being converted to `AssistantMessage`, making agent-to-agent communication appear as regular text messages instead of showing the tool call details.

### Solution
Enhanced the message conversion logic in `to_letta_messages()` to:
- Always check the `to` parameter for `send()` function calls
- Only convert `send(to="user")` to `AssistantMessage`
- Keep all other targets (`agent:X`, `group:X`, `broadcast:X`) as `ToolCallMessage`
- Handle edge cases where JSON parsing might fail by defaulting to `ToolCallMessage`

The fix ensures that the ADE correctly displays agent-to-agent messages as tool calls, improving transparency and debugging capabilities.

## Testing

The implementation should be tested with:
1. Sending messages to users via `send(message, to="user")`
2. Verifying messages appear in the ADE
3. Confirming messages are returned when polling the API
4. Testing all routing targets (agent, group, broadcast)
5. Verifying async behavior for agent-to-agent communication