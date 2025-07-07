# Deep Analysis: Letta's Unified Send() Function

## Overview

The `send()` function represents a significant architectural achievement in Letta's multi-agent system, consolidating all messaging patterns into a single, intuitive interface. This document provides a comprehensive analysis of how messages flow through the system and what final prompts agents receive.

## Architecture Overview

### Core Components

1. **Function Definition** (`letta/functions/function_sets/multi_agent.py:185-234`)
   - Provides the tool interface that agents use
   - Routes to appropriate backend functions based on `to` parameter

2. **Executor Implementation** (`letta/services/tool_executor/multi_agent_tool_executor.py:133-165`)
   - Handles actual message delivery
   - Manages agent instantiation and step() execution

3. **Streaming Interface Integration**
   - OpenAI and Anthropic interfaces detect `send(to="user")` calls
   - Convert tool calls to AssistantMessages for seamless user display

## Message Routing Analysis

### 1. User Messages (`to="user"`)

**Flow:**
```
Agent calls send("Hello", to="user")
  → Tool execution returns "Message sent to user"
  → Streaming interface detects send(to="user")
  → Extracts message parameter
  → Converts to AssistantMessage
  → Streams directly to user (bypasses tool display)
```

**Key Insight:** The executor doesn't actually deliver user messages. It returns immediately, and the streaming interfaces handle the actual delivery by intercepting the tool call.

### 2. Agent-to-Agent Synchronous (`to="agent:<id>", wait_for_reply=True`)

**Flow:**
```
Agent A calls send("Need info", to="agent:B", wait_for_reply=True)
  → Routes to send_message_to_agent_and_wait_for_reply()
  → Prefixes message: "[Message from agent 'A'] {message}"
  → Creates new LettaAgent instance for Agent B
  → Calls step() with prefixed message as system message
  → Agent B processes and responds
  → Response returned to Agent A
```

**Key Behavior:** The sending agent waits for a response. Agent B can choose how to respond based on its available tools and logic.

### 3. Agent-to-Agent Asynchronous (`to="agent:<id>", wait_for_reply=False`)

**Flow:**
```
Agent A calls send("FYI", to="agent:B", wait_for_reply=False)
  → Routes to send_message_to_agent_async()
  → Prefixes message: "[Message from agent 'A'] {message}"
  → Creates async task with new LettaAgent instance
  → Returns "Successfully sent message" immediately
  → Agent B processes in background
```

**Key Behavior:** The sending agent doesn't wait for a response. Agent B processes the message asynchronously and can decide whether and how to respond.

### 4. Broadcast Messages (`to="broadcast:<tag>"`)

**Flow:**
```
Agent calls send("Alert!", to="broadcast:critical")
  → Routes to send_message_to_agents_matching_tags_async()
  → Finds all agents with 'critical' tag
  → Prefixes message: "[Broadcast message from agent 'A'] {message}"
  → Creates parallel async tasks for all matching agents
  → Returns count of agents messaged
```

**Parallelization:** Uses `asyncio.gather()` to process all matching agents concurrently for maximum performance.

## Prompt Construction Deep Dive

When an agent receives a message via send(), here's exactly what happens:

### 1. System Prompt Compilation

The system prompt is dynamically compiled using:
- Base system template from `agent_state.system`
- Memory blocks injected via Jinja2 templating
- Metadata about message counts, timestamps, archival memory size
- Tool constraint rules if defined

Example compiled system prompt structure:
```
You are an AI agent with the following configuration:
<memory>
  <block label="persona" read_only="true" limit="2000">
    {agent's persona content}
  </block>
  <block label="human" read_only="true" limit="2000">
    {human information}
  </block>
</memory>

Current statistics:
- Messages in context: 15
- Archival memory entries: 247
- Current time: 2025-01-07 10:30:00
```

### 2. Message Integration

The incoming message is added as a system message with a simple prefix identifying the sender:

**Standard prefix format:**
```
[Message from agent 'sender-123'] {actual message}
```

**Broadcast prefix format:**
```
[Broadcast message from agent 'sender-123'] {actual message}
```

This simplified approach:
- Provides sender identification for potential replies
- Allows agents to use their own judgment on how to respond
- Reduces message verbosity
- Gives agents more autonomy in their interactions

### 3. Tool Availability

The agent has access to all registered tools, including:
- Memory management tools (archival_memory_insert, etc.)
- The `send` function itself for multi-agent communication
- Any custom tools defined for the agent

### 4. Provider-Specific Formatting

**OpenAI Format:**
- System message with compiled prompt
- User/assistant message history
- Tool calls as structured JSON
- Images as base64 data URLs

**Anthropic Format:**
- System prompt in top-level "system" field
- Inner thoughts wrapped in `<thinking>` tags
- Tool calls in Anthropic's specific format
- Images as structured content blocks

## Performance Optimizations

### 1. Lazy Agent Creation
Agents are only instantiated when messages are actually sent, not pre-loaded.

### 2. Async Processing
Non-blocking message delivery for async sends and broadcasts.

### 3. Parallel Execution
Broadcast messages use `asyncio.gather()` for concurrent processing.

### 4. Message Batching
Database persistence uses `create_many_messages_async()` for efficient storage.

## Security Considerations

### 1. Agent Isolation
Each agent runs in its own context with separate memory and state.

### 2. Message Prefixing
Simple sender identification allows agents to know the message source without prescribing response behavior.

### 3. Tool Access Control
Agents can only use tools explicitly registered for them.

## Implementation Gaps

### 1. Group Messaging
The `to="group:<id>"` functionality is not fully implemented in the executor (returns placeholder).

### 2. Error Handling
Limited error propagation for async messages - errors are logged but not returned to sender.

### 3. Message Acknowledgment
No built-in acknowledgment system for async messages.

## Best Practices

### 1. Use Synchronous for Queries
When you need a response, always use `wait_for_reply=True`.

### 2. Use Asynchronous for Notifications
For fire-and-forget messages, use `wait_for_reply=False`.

### 3. Broadcast for System-Wide Alerts
Use broadcast with meaningful tags for system-wide notifications.

### 4. Let Agents Decide Response Strategy
With simplified prefixes, agents can intelligently choose how to respond based on context and their available tools.

### 5. Include Context in Messages
Since prefixes are minimal, include any necessary context within the message itself if agents need it for proper response routing.

## Future Enhancements

### 1. Message Queuing
Implement proper message queuing for reliability.

### 2. Delivery Confirmation
Add optional delivery confirmation for async messages.

### 3. Group Implementation
Complete the group messaging functionality.

### 4. Message Filtering
Allow agents to filter incoming messages based on criteria.

## Conclusion

The unified `send()` function successfully abstracts complex multi-agent communication patterns into a simple, intuitive interface. The minimal message prefixing approach provides just enough context (sender identification) while allowing agents full autonomy in choosing how to respond. This design respects agent intelligence and reduces unnecessary verbosity in inter-agent communications.

The integration with streaming interfaces for user messages demonstrates thoughtful design that maintains backwards compatibility while providing a consistent API. The system's strength lies in its simplicity for users while handling complex routing, persistence, and prompt construction behind the scenes.

### Key Design Principles
- **Agent Autonomy**: Agents decide how to respond based on their tools and logic
- **Minimal Prefixing**: Only essential information (sender ID) is added
- **Unified Interface**: Single `send()` function for all messaging patterns
- **Backward Compatibility**: Seamless integration with existing systems