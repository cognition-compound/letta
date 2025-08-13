# Letta Development Progress Summary

## 🚀 Current Status

**Fork Version:** Custom fork based on Letta 0.8.15  
**Branch:** `dev` (157 commits ahead of main)  
**Last Upstream Merge:** 0.8.15 (2025-01-17)

## 🎯 Active Focus Areas

### Production Systems
- **Unified Send Function** - Single `send()` API for all agent messaging (user, agent-to-agent, group, broadcast)
- **Multimodal Messages** - Full image support across all providers (OpenAI/Anthropic/Google AI)
- **File Processing** - Complete file handling pipeline with agent tools
- **Parallel Tool Execution** - 2-5x performance gains with concurrent tool calls

### Known Issues
- **Database Connection Pooling** - Excessive PostgreSQL connections (workaround: set `LETTA_PG_POOL_SIZE=10`)
- **Upstream Incompatibility** - Cannot merge 0.9.1+ due to breaking changes to core architecture

## 📝 Recent Critical Fixes (Last 7 Days)

### ✅ FIXED: Send() Checkpoint Logic Causing Complete Context Loss (2025-08-13)
**Fixed critical bug where send() checkpoint logic was evicting entire conversation history**

**Problem:** Agents were losing ALL context except the last 3-4 messages. Main agents appeared to have amnesia after just a few exchanges. The send() checkpoint logic had a backwards condition that caused massive over-eviction.

**Root Cause:** In `summarizer.py`, when all send() calls were "too recent" (within retain window), instead of falling back to standard trimming, the code incorrectly used the FIRST send as the trim point, evicting everything.

**Solution:**
- Fixed checkpoint logic to fall back to standard approach when all sends are within retain window
- Added explicit summarization parameters (message_buffer_limit=60, message_buffer_min=15) to REST API
- Created comprehensive tests to prevent regression

**Files Modified:**
- `letta/services/summarizer/summarizer.py:283-285` - Fixed checkpoint fallback logic
- `letta/server/rest_api/routers/v1/agents.py` - Added explicit summarization parameters
- `tests/test_send_checkpoint_bug.py` - New test file validating the fix

**Result:** Agents now maintain proper conversation context. No unexpected eviction occurs when send() calls are recent.

### ✅ FIXED: Agent Message Role Confusion - System vs User Message Processing (2025-08-13)
**Resolved critical issue where main agent treated research agent system messages as user messages**

**Problem:** Main agent continuously responded with "Noted. I will continue..." to research agent updates because system messages were prefixed with conversational language that made them appear as user communications.

**Root Cause:** Message prefixes like `[Message from agent 'X']` and `[Broadcast message from agent 'X']` made system messages appear conversational rather than directive, causing LLMs to interpret them as user communications requiring acknowledgment.

**Solution:**
- Changed message prefixes to use directive system language:
  - `[Message from agent 'X']` → `SYSTEM UPDATE from X:`  
  - `[Broadcast message from agent 'X']` → `SYSTEM BROADCAST from X:`
- System messages now appear as clear directives rather than conversational notifications

**Files Modified:**
- `letta/services/tool_executor/multi_agent_tool_executor.py:216` - Updated system message prefix
- `letta/services/tool_executor/multi_agent_tool_executor.py:64` - Updated broadcast message prefix

**Result:** Main agents now correctly process system messages from research agents without generating acknowledgment responses.

### ✅ FIXED: Research Agent Context Death (2025-08-13)
**Resolved critical production issue where research agents crash permanently when hitting context limits**

**Problem:** Research agents working on long todo lists would hit context window limits and lose ALL context, becoming completely non-functional. Agents would be left with only the system message and no memory of their task.

**Root Cause:** `multi_agent_tool_executor.py` creates `LettaAgent` instances without summarization parameters, causing context death when limits are hit.

**Solution:**
- Added missing summarization parameters to agent creation in `multi_agent_tool_executor.py`
- Created uniform tool formatter for readable tool call summaries  
- Implemented `send()` calls as natural checkpoint boundaries for summarization
- Fixed system message detection to prevent keeping extra messages in tests

**Files Modified:**
- `letta/services/tool_executor/multi_agent_tool_executor.py:134-138` - Added summarization params
- `letta/services/summarizer/summarizer.py:450-505` - Enhanced `tool_formatter` with call/response correlation
- `letta/services/summarizer/summarizer.py:266-291` - Implemented checkpoint boundaries
- `letta/services/summarizer/summarizer.py:522` - Updated `simple_summary` to use formatter
- `tests/test_research_agent_context_death.py` - Test reproducing and validating fix

**Result:** Research agents now survive context window limits and maintain task context through summarization.

**Enhanced Tool Correlation (2025-08-13):**
- Enhanced `tool_formatter()` to explicitly link tool calls with responses using `call → response` format
- Research summaries now show clear cause-effect relationships: `tavily_search({query}) → Search results...`  
- Eliminates ambiguity in parallel tool execution scenarios
- Properly handles orphaned calls/responses for robust error recovery

### OpenAI Reasoning Architecture (2025-08-12)
- Fixed reasoning display showing JSON metadata instead of actual reasoning content
- Implemented complete reasoning structure serialization for OpenAI Responses API
- Models now receive their full reasoning context back for proper continuity

### Agent Communication Resilience (2025-08-11)
- Fixed agent-to-agent messaging to accept multiple ID formats
- Added error recovery to prevent system crashes from malformed tool calls
- Fixed heartbeat handling in parallel tool execution

### Tool Schema Updates (2025-08-10)
- Fixed OpenAI strict mode compatibility (all parameters in required array)
- Fixed Optional types to generate proper anyOf schemas
- Added request_heartbeat parameter to all tool schemas

## 🏗️ Architecture Highlights

### Custom Fork Features
- **Unified send() function** - Single API for all agent messaging
- **Async-only communication** - Fire-and-forget agent messaging
- **Modern logging** - OpenTelemetry integration with structured events
- **Parallel tool execution** - Concurrent tool calls for performance
- **Multimodal support** - Native image handling in messages

### Key Environment Variables
```bash
# Database
LETTA_PG_URI="postgresql://user:pass@host:port/db"
LETTA_PG_POOL_SIZE="10"  # Reduce connection pool size

# Parallel Tools
LETTA_ENABLE_PARALLEL_TOOL_CALLS="true"  # Enable/disable parallel execution

# LLM Providers
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
```

## 📚 Documentation

**Core Docs:**
- @CLAUDE.md - AI assistant instructions and project overview
- @docs/UNIFIED_SEND_IMPLEMENTATION.md - Agent messaging architecture
- @docs/MULTIMODAL_*.md - Image support documentation
- @docs/FILE_PROCESSING_ARCHITECTURE.md - File handling system
- @docs/archive/progress_2025_01.md - Historical progress archive

**For historical context and detailed implementation notes, see @docs/archive/**