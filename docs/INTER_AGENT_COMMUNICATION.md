# Letta Inter-Agent Communication Guide

This guide describes the enhanced inter-agent communication system in Letta, which provides clean message routing with proper sender context and both synchronous and asynchronous messaging capabilities.

## Overview

The enhanced messaging system addresses key issues in multi-agent communication:
- **Clean message format**: Sender information is provided in system messages, not embedded in content
- **Async messaging restored**: `send_message_to_agent_async` enables fire-and-forget messaging
- **Universal send function**: Single interface for all messaging needs
- **Clear routing**: Agents always know who sent messages and how to respond

## Message Format

When agents receive messages from other agents, the sender context is provided in a clean system message:

```
[Message from: Agent "SenderName" (ID: sender-agent-123)]
```

This is followed by the actual message content in a user message, with proper metadata fields populated.

## Available Functions

### 1. `send_message_to_agent_and_wait_for_reply`

Sends a message to another agent and waits for their response (synchronous).

```python
response = send_message_to_agent_and_wait_for_reply(
    message="What's your status?",
    other_agent_id="agent-456"
)
```

**Use when**: You need information from another agent before proceeding.

### 2. `send_message_to_agent_async`

Sends a message to another agent without waiting for a response (asynchronous).

```python
send_message_to_agent_async(
    message="FYI: Task completed",
    other_agent_id="agent-789"
)
```

**Use when**: You're notifying another agent but don't need a response.

### 3. `send_message_to_agents_matching_tags`

Broadcasts a message to all agents with specific tags.

```python
responses = send_message_to_agents_matching_tags(
    message="Critical alert!",
    match_all=["monitoring", "production"],
    match_some=["critical", "urgent"]
)
```

**Use when**: You need to reach multiple agents based on their capabilities or roles.

### 4. `send` (Universal Function)

A unified interface for all messaging needs with explicit routing.

```python
# Send to user
send("Hello!", to="user")

# Send to specific agent (async)
send("Status update", to="agent:agent-123", wait_for_reply=False)

# Send to specific agent (sync)
response = send("Need info", to="agent:agent-456", wait_for_reply=True)

# Broadcast by tag
send("Alert!", to="broadcast:critical")

# Send to group
send("Team update", to="group:my-team")
```

**Use when**: You want a consistent interface for all messaging patterns.

## Agent Instructions

When configuring agents for multi-agent communication, include these instructions in their prompts:

```
When you receive a message, the sender information is provided in a system message:
- [Message from: User] - Message is from the human user
- [Message from: Agent "Name" (ID: agent-123)] - Message is from another agent

To respond appropriately:
- To the user: send(message, to="user")
- To a specific agent: send(message, to="agent:<agent_id>", wait_for_reply=True/False)
- To broadcast: send(message, to="broadcast:<tag>")

Choose wait_for_reply=True when you need a response, False for notifications.
```

## Migration Guide

If you're upgrading from the old messaging system:

### Old Pattern (Deprecated)
```python
# Old: Confusing message with embedded instructions
augmented_message = (
    f"[Incoming message from agent with ID '{sender_id}' - "
    f"to reply use send_message_to_agent_and_wait_for_reply...] "
    f"{message}"
)
```

### New Pattern
```python
# New: Clean separation of context and content
messages = [
    MessageCreate(
        role=MessageRole.system,
        content=f'[Message from: Agent "{sender_name}" (ID: {sender_id})]'
    ),
    MessageCreate(
        role=MessageRole.user,
        content=message,
        name=sender_name,
        sender_id=sender_id
    )
]
```

## Best Practices

1. **Use async when possible**: For notifications and updates, use `send_message_to_agent_async` to avoid blocking.

2. **Explicit routing**: Use the `send` function with clear `to` parameters for readable code.

3. **Leverage message metadata**: The `sender_id` and `name` fields are properly populated for tracking.

4. **Group operations**: Use tag-based broadcasting for efficient multi-agent coordination.

5. **Error handling**: All functions validate that target agents exist and are in the same organization.

## Examples

### Example 1: Coordinator-Worker Pattern
```python
# Coordinator assigns tasks asynchronously
send("Please process dataset A", to="agent:worker-1", wait_for_reply=False)
send("Please process dataset B", to="agent:worker-2", wait_for_reply=False)

# Later, coordinator checks status synchronously
status1 = send("What's your progress?", to="agent:worker-1", wait_for_reply=True)
status2 = send("What's your progress?", to="agent:worker-2", wait_for_reply=True)
```

### Example 2: Alert Broadcasting
```python
# Monitor detects issue and broadcasts
send("Database connection lost!", to="broadcast:critical")

# All agents with 'critical' tag receive the alert with clean context:
# [Message from: Agent "Monitor" (ID: monitor-agent-123)]
# Database connection lost!
```

### Example 3: Chain of Thought
```python
# Agent A starts analysis
analysis = send("Analyze this data: {...}", to="agent:analyst", wait_for_reply=True)

# Agent A continues with results
summary = send(f"Summarize: {analysis}", to="agent:writer", wait_for_reply=True)

# Agent A reports to user
send(f"Analysis complete: {summary}", to="user")
```

## Technical Details

- **Performance**: Async messages return immediately, reducing latency in multi-agent systems
- **Reliability**: All messages are validated and errors are properly propagated
- **Compatibility**: The system maintains backward compatibility while providing cleaner semantics
- **Scalability**: Tag-based broadcasting and group messaging support large agent populations