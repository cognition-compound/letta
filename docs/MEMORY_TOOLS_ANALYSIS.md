# Letta Memory Tools Analysis

## Overview

This document provides a comprehensive analysis of all memory-related tools in the Letta framework, their differences, evolution, and recommendations for usage.

## Memory Tool Categories

### 1. Core Memory Tools (Basic Operations)
**Location**: `letta/functions/function_sets/base.py:133-167`

- **`core_memory_append(label, content)`** - Appends content to the end of a memory block
- **`core_memory_replace(label, old_content, new_content)`** - Exact string replacement in memory blocks

**Characteristics**:
- Original, most basic memory manipulation tools
- Simple append and replace operations
- No advanced error handling or validation
- Direct string manipulation

### 2. Enhanced Memory Tools v2 (Advanced Operations)
**Location**: `letta/functions/function_sets/base.py:195-373`

- **`memory_replace(label, old_str, new_str)`** - Enhanced replacement with validation
- **`memory_insert(label, new_str, insert_line)`** - Insert text at specific line numbers
- **`memory_rethink(label, new_memory)`** - Complete rewrite of a memory block
- **`memory_finish_edits()`** - Signal completion of memory editing session

**Key Improvements**:
- Line number validation prevents accidental inclusion of display prefixes
- Better error messages with snippets showing changes
- More sophisticated editing capabilities
- Validates against line number prefixes (e.g., "Line 1: ")

### 3. Archival Memory Tools (Long-term Storage)
**Location**: `letta/functions/function_sets/base.py:66-131`
**Status**: DEPRECATED but fully functional

- **`archival_memory_insert(content)`** - Add to long-term memory with embeddings
- **`archival_memory_search(query, page, start)`** - Semantic search using embeddings

**Important Notes**:
- Marked as `DEPRECATED_LETTA_TOOLS` in `letta/constants.py:86`
- Still fully functional and stable
- Internally uses the new passage system (AgentPassage)
- Provides semantic search capabilities via embeddings

### 4. Voice Agent Memory Tools
**Location**: `letta/functions/function_sets/voice.py`

- **`store_memories(chunks)`** - Persist dialogue before context window fills
- **`rethink_user_memory(new_memory)`** - Rewrite user memory for voice agents
- **`finish_rethinking_memory()`** - Complete memory rethinking process
- **`search_memory(convo_keyword_queries, start_minutes_ago, end_minutes_ago)`** - Time-based search

**Specialized for**: Voice agents managing real-time conversations with context window limitations

### 5. Conversation Search Tool
- **`conversation_search(query, page)`** - String-based search of conversation history (not semantic)

## Architecture Evolution: Archival Memory → Passages

### What Changed
1. **Terminology**: "Archival memory" → "Passages"
2. **Database Structure**: Single `passages` table split into:
   - `agent_passages` - Agent-created memories (former archival memory)
   - `source_passages` - File-derived content
3. **Implementation**: PassageManager now handles all operations

### What Stayed the Same
1. **Functionality**: All archival memory features work identically
2. **API**: The `archival_memory_*` functions remain unchanged
3. **Behavior**: Text chunking, embedding, and semantic search work the same way

### Under the Hood
When `archival_memory_insert` is called:
1. Text is chunked based on `embedding_chunk_size`
2. Each chunk is embedded using the agent's embedding config
3. Stored as `AgentPassage` with the agent's ID
4. Searchable via semantic similarity using pgvector

## Tool Set Recommendations by Use Case

### Standard Letta Agents
```python
recommended_tools = [
    "send_message",
    "memory_replace",           # Use over core_memory_replace
    "memory_insert",            # Use over core_memory_append
    "conversation_search",
    "archival_memory_insert",   # Still the best API for long-term storage
    "archival_memory_search"    # Still the best API for semantic search
]
```

### Agents Needing Full Memory Control
```python
extended_tools = [
    "send_message",
    "memory_replace",
    "memory_insert",
    "memory_rethink",          # For complete memory rewrites
    "memory_finish_edits",     # Signal completion of batch edits
    "conversation_search",
    "archival_memory_insert",
    "archival_memory_search"
]
```

### Voice/Streaming Agents
```python
voice_tools = [
    "send_message",
    "store_memories",
    "rethink_user_memory",
    "finish_rethinking_memory",
    "search_memory"            # Time-based instead of semantic
]
```

### Simple Agents (Minimal Requirements)
```python
minimal_tools = [
    "send_message",
    "core_memory_append",      # Simple but sufficient
    "core_memory_replace"      # Simple but sufficient
]
```

## Key Differences Between Memory Types

### Core Memory vs Archival Memory (Passages)
| Aspect | Core Memory | Archival Memory |
|--------|-------------|-----------------|
| Size | Small (5000 char limit) | Unlimited |
| Access | Always in context | Retrieved via search |
| Mutability | Frequently edited | Immutable once created |
| Search | N/A | Semantic (embedding-based) |
| Use Case | Active state, preferences | Historical facts, past conversations |

### v1 vs v2 Memory Tools
| Feature | v1 (core_memory_*) | v2 (memory_*) |
|---------|-------------------|---------------|
| Error Handling | Basic | Advanced with validation |
| Line Numbers | No validation | Prevents line number prefix errors |
| Feedback | Simple success/error | Detailed snippets of changes |
| Capabilities | Append, Replace | Replace, Insert at line, Rethink |

## Best Practices

1. **Prefer v2 tools** (`memory_*`) over v1 (`core_memory_*`) for better error handling
2. **Continue using archival memory tools** - they're deprecated in name only, not functionality
3. **Don't mix voice and standard tools** - they're designed for different use cases
4. **Ignore deprecation warnings** for archival tools - they're stable and well-maintained
5. **Use archival memory for**:
   - Facts that don't need constant access
   - Historical conversation data
   - Large amounts of reference information
6. **Use core memory for**:
   - Current conversation context
   - User preferences and state
   - Frequently accessed information

## Common Pitfalls to Avoid

1. **Don't include line numbers** when calling memory tools - they're for display only
2. **Don't worry about "passages"** - it's an implementation detail
3. **Don't use voice tools for standard agents** - they have different memory models
4. **Don't avoid archival tools** due to deprecation - they're the best interface for long-term memory

## Migration Notes

- No migration needed for existing agents using archival memory
- The deprecation is a naming convention change, not a functionality change
- New internal passage system is transparent to agents
- All existing archival memory data automatically works with the passage system

## Conclusion

The Letta memory system has evolved to be more sophisticated internally while maintaining backward compatibility. For most use cases, the combination of v2 memory tools (`memory_replace`, `memory_insert`) and archival memory tools (`archival_memory_insert`, `archival_memory_search`) provides the best balance of functionality and reliability.

The deprecation of archival memory tools is purely nomenclature - they remain the recommended interface for long-term memory storage and retrieval in Letta agents.