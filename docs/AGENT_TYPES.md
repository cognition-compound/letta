# Letta Agent Type Parameters Documentation

This document explains the different `agent_type` parameter values available when creating agents in Letta.

## Overview

The `agent_type` parameter determines which system prompt and behavior configuration an agent will use. This is different from the agent implementation classes - it's a configuration parameter that affects how agents behave.

## Agent Type Parameter Values

The `agent_type` parameter is defined in `schemas/agent.py` as an enum with the following values:

```python
class AgentType(str, Enum):
    memgpt_agent = "memgpt_agent"
    memgpt_v2_agent = "memgpt_v2_agent"
    split_thread_agent = "split_thread_agent"
    sleeptime_agent = "sleeptime_agent"
    voice_convo_agent = "voice_convo_agent"
    voice_sleeptime_agent = "voice_sleeptime_agent"
```

## Agent Type Descriptions

### 1. `memgpt_agent`
- **System Prompt**: `memgpt_v2_chat.txt`
- **Purpose**: Original MemGPT conversational agent
- **Implementation Class**: `LettaAgent`
- **Features**: Full memory system, tool execution, stateful conversations
- **Note**: Uses the same v2 prompt as `memgpt_v2_agent`

### 2. `memgpt_v2_agent`
- **System Prompt**: `memgpt_v2_chat.txt`
- **Purpose**: Updated MemGPT agent with improved prompts
- **Implementation Class**: `LettaAgent`
- **Features**: Same as memgpt_agent but explicitly v2
- **Difference**: Currently identical to memgpt_agent in behavior

### 3. `split_thread_agent`
- **Status**: Not implemented
- **Purpose**: Placeholder for future threading capabilities

### 4. `sleeptime_agent`
- **System Prompt**: `sleeptime_v2.txt`
- **Purpose**: Background memory processing and consolidation
- **Implementation Class**: `LettaAgent` (with sleeptime configuration)
- **Features**: Designed for offline memory computation
- **Use Case**: Processing memories when main agent is inactive

### 5. `voice_convo_agent`
- **System Prompt**: `voice_chat.txt`
- **Purpose**: Real-time voice conversation handling
- **Implementation Class**: `VoiceAgent`
- **Features**: Low-latency streaming, voice-optimized responses
- **Use Case**: Voice assistants and real-time voice interactions

### 6. `voice_sleeptime_agent`
- **System Prompt**: `voice_sleeptime.txt`
- **Purpose**: Memory management for voice conversations
- **Implementation Class**: `VoiceSleeptimeAgent`
- **Features**: Background memory processing for voice agents
- **Use Case**: Works alongside voice_convo_agent for memory updates

## How Agent Types Map to Implementation Classes

The agent_type parameter determines which implementation class and system prompt will be used:

| agent_type | Implementation Class | System Prompt |
|------------|---------------------|---------------|
| `memgpt_agent` | LettaAgent | memgpt_v2_chat.txt |
| `memgpt_v2_agent` | LettaAgent | memgpt_v2_chat.txt |
| `sleeptime_agent` | LettaAgent | sleeptime_v2.txt |
| `voice_convo_agent` | VoiceAgent | voice_chat.txt |
| `voice_sleeptime_agent` | VoiceSleeptimeAgent | voice_sleeptime.txt |

## Usage Example

When creating an agent, specify the agent_type:

```python
from letta.schemas.agent import AgentType

# Create a standard conversational agent
agent = client.create_agent(
    agent_type=AgentType.memgpt_agent,
    name="MyAgent"
)

# Create a voice agent
voice_agent = client.create_agent(
    agent_type=AgentType.voice_convo_agent,
    name="VoiceAssistant"
)
```

## Key Differences

- **memgpt_agent vs memgpt_v2_agent**: Currently identical, both use v2 prompts
- **sleeptime_agent**: Uses different prompts optimized for memory processing
- **voice agents**: Require pairing (voice_convo_agent + voice_sleeptime_agent) for full functionality