# Troubleshooting Lessons Learned

## File Processing & Visibility Issues

1. **Status tracking is critical** - Job completion ≠ file processing completion
2. **Two processing paths exist** - Cloud vs legacy with different behaviors  
3. **Filtering is essential** - Database queries need proper status/deletion filtering
4. **UX vs data consistency tradeoff** - Showing files immediately vs waiting for completion affects user experience
5. **Filtering can be too restrictive** - Good data integrity measures can create confusing user experiences
6. **Processing status visibility** - Users need to see file processing progress, not just final results

## Tool Development

7. **File tools are Python-based** - Not shell commands, different paradigm
8. **Tool advertising vs implementation** - Don't advertise tools that raise NotImplementedError
9. **Tool completeness matters** - Missing basic tools like list_files reduce agent effectiveness

## Performance & Architecture

10. **Performance TODOs accumulate** - Known inefficiencies need prioritized fixes
11. **Content storage vs passage creation** - Two separate concerns that both paths must handle
12. **Database relationship patterns** - FileMetadata ↔ FileContent requires explicit eager loading
13. **LlamaIndex consistency** - Same readers should be used for content storage and passage generation

## Error Handling & Background Tasks

14. **Background tasks require careful status management** - Async processing needs explicit completion signals
15. **Object comparison in error handling** - Pydantic object removal from lists can fail, use ID-based tracking instead

## Common Debugging Patterns

### File Not Visible After Upload
1. Check if file has `FileProcessingStatus.COMPLETED`
2. Verify file is not soft-deleted (`is_deleted=False`)
3. Check if processing path (cloud vs legacy) is working correctly
4. Look for exceptions in background task processing

### open_file Returns "No Content"
1. Verify `FileContent` table has entry for file
2. Check if processing path stores content via `upsert_file_content()`
3. Ensure `include_content=True` when fetching file metadata
4. Confirm DirectoryConnector calls `load_file_content()` method

### Tool Not Working
1. Check if tool is properly registered in function_map
2. Verify tool schema matches implementation
3. Ensure proper error handling with try/catch blocks
4. Check if agent has files attached through sources

### Performance Issues
1. Look for full database lookups that could be cached
2. Check for content-agnostic processing that could be optimized
3. Monitor for large result sets that need pagination
4. Review TODO comments for known inefficiencies

## Best Practices

### Error Handling
- Always use ID-based tracking instead of object references in lists
- Wrap tool implementations in comprehensive try/catch blocks
- Return user-friendly error messages, not raw exceptions
- Log detailed errors for debugging while showing simple messages to users

### Tool Implementation
- Follow existing patterns in LettaFileToolExecutor
- Maintain consistency with FileAgent/Manager architecture
- Use proper actor permission checks
- Return structured data with consistent formatting

### Database Operations
- Use eager loading for relationships that will be accessed
- Filter out soft-deleted records consistently
- Consider pagination for potentially large result sets
- Separate concerns between metadata and content storage

### Background Processing
- Update status fields explicitly at each stage
- Handle exceptions gracefully without breaking the pipeline
- Use atomic operations where possible
- Provide progress visibility to users