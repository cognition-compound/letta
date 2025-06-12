# File Processing Architecture

## Overview
Letta uses a dual-path file processing system to handle document ingestion and make content available to agents.

## Processing Paths

### 1. FileProcessor (Cloud Path) 
- **Trigger**: When Mistral + OpenAI API keys are available
- **Location**: `letta/services/file_processor/file_processor.py`
- **Features**: OCR processing, proper content storage
- **Status**: ✅ Works correctly

### 2. DirectoryConnector (Legacy Path)
- **Trigger**: Default/fallback when cloud path unavailable
- **Location**: `letta/data_sources/connectors.py`
- **Features**: Basic file processing, now with content storage
- **Status**: ✅ Fixed in recent updates

## File Processing Pipeline

1. **Upload** → Background task `load_file_to_source_async` created
2. **Processing** → DirectoryConnector or FileProcessor handles file/passage creation
3. **Status Update** → Files marked as COMPLETED (now working)
4. **Availability** → Files appear in UI and available for agent attachment

## Key Components

- **SourceManager**: File-to-source associations and status management
- **DirectoryConnector**: Default file processing (legacy path)
- **FileProcessor**: Cloud-based processing (newer path)
- **PassageManager**: Creates searchable passages from file content

## File Processing Status States

- `PENDING` - Just uploaded, not processed
- `PARSING` - Being parsed by file processor
- `EMBEDDING` - Generating vector embeddings
- `COMPLETED` - Ready for use ✅
- `ERROR` - Processing failed

## Database Tables

- `FileMetadata` - File information and processing status
- `FileContent` - Actual file content storage
- `Passage` - Searchable chunks with embeddings
- `Source` - Container for files and passages

## Known Issues

### Text File OCR Processing
- **Location**: `letta/services/file_processor/parser/mistral_parser.py:36-50`
- **Issue**: Text files processed through same OCR pipeline as PDFs
- **Impact**: Unnecessary complexity, potential encoding issues
- **Priority**: Low - works but inefficient

### Agent Attachment Race Conditions
- **Location**: `letta/server/rest_api/routers/v1/agents.py:319-330`
- **Issue**: No validation that attached files are fully processed
- **Status**: Partially mitigated by filtering fixes
- **Future**: Add explicit file status validation before attachment

### Streaming Error Handling
- **Location**: `letta/server/rest_api/streaming_response.py:84-103`
- **Issue**: Generic error handling for file-related failures
- **Impact**: Poor error visibility during streaming with file attachments
- **Priority**: Medium - affects debugging experience

## Future Improvements

### File Content Storage Unification
- Legacy path now stores content in database (fixed)
- Cloud path properly stores via `source_manager.upsert_file_content()`
- Consider making path selection more explicit/configurable

### Tool Sandbox Architecture
- Tools execute in isolated Python subprocesses
- 180-second timeout for tool execution
- No shell command execution by design
- MCP integration available for external tools