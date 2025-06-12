# File Tools Reference

## Current File Tools Status

### Working Tools ✅

#### 1. `open_file` - Opens file content into agent's core memory
- **Location**: `letta/services/tool_executor/files_tool_executor.py:82-118`
- **Parameters**: `file_name: str`, `view_range: Optional[Tuple[int, int]]`
- **Functionality**: 
  - Loads file content via FileAgentManager and SourceManager
  - Supports optional view_range parameter for partial content viewing
  - Uses LineChunker for line-numbered display with metadata
  - Updates FileAgent record with visible_content and is_open=True
- **Architecture**: Direct database integration with proper error handling

#### 2. `close_file` - Removes file from agent's active memory
- **Location**: `letta/services/tool_executor/files_tool_executor.py:120-125`
- **Parameters**: `file_name: str`
- **Functionality**: Simply sets is_open=False in FileAgent record
- **Architecture**: Minimal but effective implementation

#### 3. `search_files` - Semantic search across attached files
- **Location**: `letta/services/tool_executor/files_tool_executor.py:172-182`
- **Parameters**: `query: str`
- **Functionality**:
  - Uses vector embeddings for semantic search via PassageManager
  - Returns formatted results with filename prefixes
  - Searches across all agent-attached sources
- **Architecture**: Leverages existing passage/embedding infrastructure

#### 4. `grep` - Pattern/regex search tool ✅ FIXED
- **Location**: `letta/services/tool_executor/files_tool_executor.py:127-170`
- **Parameters**: `pattern: str`, `case_sensitive: bool = False`
- **Functionality**: Regex pattern matching with case sensitivity support
- **Features**: Line number reporting, error handling for invalid regex
- **Return format**: `["filename:line_number:matching_line", ...]`

#### 5. `list_files` - List all accessible files with status ✅ NEW
- **Location**: `letta/services/tool_executor/files_tool_executor.py:185-219`
- **Parameters**: None
- **Functionality**: Shows all files with processing status and open/closed state
- **Output format**: `filename (processing_status) [open/closed]`

## Architecture Patterns

### Tool Registration System
- **Tool Type**: `ToolType.LETTA_FILES_CORE` in enum
- **Module**: `LETTA_FILES_TOOL_MODULE_NAME = "letta.functions.function_sets.files"`
- **Executor**: `LettaFileToolExecutor` handles all file tool execution
- **Auto-attachment**: File tools automatically added/removed when sources attached/detached to agents

### File-Agent Association Architecture
- **ORM Model**: `FileAgent` in `letta/orm/files_agents.py`
- **Key Fields**:
  - `is_open`: Whether agent currently has file open in memory
  - `visible_content`: Portion of file content agent is viewing
  - `last_accessed_at`: Timestamp tracking
- **Manager**: `FileAgentManager` handles CRUD operations

### Content Processing
- **LineChunker**: Processes file content with line numbers and metadata
- **View Ranges**: Support for partial file viewing (start, end line numbers)
- **Content Limits**: Automatic truncation with warnings for large files
- **Format**: `Line {number}: {content}` with metadata headers

## Performance Issues & TODOs

### Inefficient File Loading
- **Location**: `files_tool_executor.py:89-107`
- **Issue**: Full database lookup for each file access
- **TODO**: Cache file_id in block metadata to avoid repeated lookups

### Non-Content-Aware Splitting
- **Location**: `files_tool_executor.py:104-106`
- **Issue**: LineChunker treats all content equally
- **TODO**: Implement content-aware chunking for different file types

### Search Result Pagination
- **Location**: `files_tool_executor.py:127`
- **Issue**: Large search results could overwhelm agent context
- **TODO**: Add pagination support to search_files

## Future Tool Ideas

### Advanced Navigation Tools
```python
async def goto_line(self, agent_state: AgentState, file_name: str, line_number: int, context_lines: int = 5) -> str:
    """Jump to specific line with surrounding context."""

async def list_functions(self, agent_state: AgentState, file_name: str) -> List[str]:
    """List all functions/classes in a code file."""

async def find_definition(self, agent_state: AgentState, symbol: str) -> List[str]:
    """Find definition of function/class/variable across files."""
```

### Enhanced Content Tools
```python
async def view_file_outline(self, agent_state: AgentState, file_name: str) -> str:
    """Show file structure/table of contents."""

async def diff_files(self, agent_state: AgentState, file1: str, file2: str) -> str:
    """Compare two files and show differences."""
```

## Tool Dependencies
- Files must be attached to agents through sources
- File tools use Letta's structured file management, not direct filesystem access
- All tools properly validate parameters via Pydantic
- Error handling captures exceptions and returns friendly messages
- Agent state is required for all file operations
- Proper integration with Letta's security model (actor permissions)