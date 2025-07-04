# Context Compression in Letta: How It Works

## Overview

Letta uses a sophisticated context compression system to manage conversation history when the context window becomes too large. This system is responsible for creating summaries and can result in agents having "0 conversation messages" with only summaries.

## Key Components

### 1. Summarizer System (`letta/services/summarizer/summarizer.py`)

The `Summarizer` class handles message compression using different modes:
- **STATIC_MESSAGE_BUFFER**: The current implementation that maintains a fixed buffer of recent messages
- Buffer limits are configurable (default: 60 messages max, 15 messages min)

### 2. Static Buffer Summarization Process

When the message buffer exceeds the limit:
1. **Eviction**: Messages beyond the buffer limit are marked for eviction
2. **Retention**: Only the most recent `message_buffer_min` messages are kept
3. **Summary Generation**: Evicted messages are passed to a summarization agent
4. **Context Update**: The agent's in-context messages are updated to include only the system message + retained messages

### 3. EphemeralSummaryAgent (`letta/agents/ephemeral_summary_agent.py`)

- A lightweight OpenAI wrapper that generates summaries
- Stores summaries in a memory block labeled `conversation_summary`
- Recursively builds on previous summaries when new summarization occurs

### 4. Message Buffer Management in LettaAgent

Key configuration in `LettaAgent.__init__`:
```python
message_buffer_limit=60,  # Maximum messages before summarization
message_buffer_min=15,    # Minimum messages to retain after summarization
enable_summarization=True # Enable/disable summarization
```

### 5. Context Window Rebuilding

The `_rebuild_context_window` method in LettaAgent:
- Triggers when total tokens exceed the LLM's context window
- Can be forced to clear all messages except the system message
- Updates the agent's `message_ids` to reflect the new context

## Why Agents Have "0 Conversation Messages"

This occurs when:
1. **Force Summarization**: When `force=True` and `clear=True` are passed to the summarizer
2. **Token Limit Exceeded**: When total tokens exceed the configured context window
3. **Message Buffer Autoclear**: Agents with `message_buffer_autoclear=True` don't retain messages

## The "Do It" Problem (FIXED)

**UPDATE (2025-01-03)**: This issue has been addressed. When `clear=True` is used, the system now retains at least 2 recent messages in addition to the system message, ensuring agents maintain context for follow-up commands.

Previously, when an agent only had summaries and no recent conversation history, it would lose the immediate context needed to understand vague references like "do it". This happened because:

1. The summarization process condensed detailed conversation into high-level notes
2. Specific action requests got abstracted away
3. The agent had no recent messages to reference for context

**The Fix**: Modified `summarizer.py` to set `retain_count = 2` when `clear=True`, ensuring the agent always keeps:
- The system message (always preserved)
- The last 2 messages (user's last request + agent's last response)

This minimal change dramatically improves the agent's ability to understand follow-up commands.

## Summary Storage

The conversation summary is stored in:
- A memory block with label `conversation_summary` (configurable)
- The block is created/updated by the EphemeralSummaryAgent
- Summaries are recursive - new summaries build on previous ones

## Configuration Options

Agents can be configured with:
- `message_buffer_limit`: When to trigger summarization
- `message_buffer_min`: How many messages to keep
- `enable_summarization`: Toggle summarization on/off
- `message_buffer_autoclear`: Clear all messages after each interaction (workflow agents)

## Impact on Agent Behavior

1. **Memory Preservation**: Core memory and archival memory remain intact
2. **Context Loss**: Specific conversation details are lost
3. **Summary Quality**: Depends on the summarization model (currently GPT-4)
4. **Follow-up Understanding**: Vague references become impossible to resolve

## Files Involved

- `/letta/services/summarizer/summarizer.py` - Main summarization logic
- `/letta/agents/letta_agent.py` - Integration with agent lifecycle
- `/letta/agents/ephemeral_summary_agent.py` - Summary generation
- `/letta/services/context_window_calculator/context_window_calculator.py` - Token counting
- `/letta/schemas/agent.py` - Agent configuration including `message_buffer_autoclear`