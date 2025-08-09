# MCP Tool Schema Update Fix

## Issue Summary

When patching MCP tools with updated JSON schemas using `zod-to-json-schema`, Letta throws validation errors when agents try to use the tools:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for FunctionTool
```

## Root Cause

The issue occurs because `zod-to-json-schema` with the OpenAI target generates schemas that are already wrapped in the OpenAI function format:

```json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    "description": "...",
    "parameters": { ... }
  }
}
```

When Letta tries to create OpenAI tools in `context_window_calculator.py:102`:

```python
OpenAITool(type="function", function=f.json_schema)
```

It's double-wrapping the schema, causing validation to fail.

## Solution

### Option 1: Fix in the API Service (Recommended)

When patching tools, extract the inner function schema if it's already wrapped:

```typescript
const updatePayload: Letta.ToolUpdate = {
  returnCharLimit: 100000,
  jsonSchema: (() => {
    const schema = zodToJsonSchema(zodSchema, {
      target: 'openAi',
      strictUnions: true
    });
    
    // Check if schema is already wrapped
    if (schema.type === 'function' && schema.function) {
      // Extract the inner function definition
      return schema.function;
    }
    
    return schema;
  })()
};
```

### Option 2: Fix in Letta

Update `context_window_calculator.py` to handle both wrapped and unwrapped schemas:

```python
# Line 101-102 in context_window_calculator.py
if agent_state.tools:
    available_functions_definitions = []
    for tool in agent_state.tools:
        schema = tool.json_schema
        
        # Handle wrapped schemas
        if isinstance(schema, dict) and schema.get("type") == "function" and "function" in schema:
            # Schema is already wrapped, extract the inner function
            function_def = schema["function"]
        else:
            # Schema is unwrapped, use it directly
            function_def = schema
            
        available_functions_definitions.append(
            OpenAITool(type="function", function=function_def)
        )
```

### Option 3: Change zod-to-json-schema Configuration

Instead of using the `openAi` target, use the default target and manually format:

```typescript
const schema = zodToJsonSchema(zodSchema, {
  // Don't use 'openAi' target
  strictUnions: true
});

const updatePayload: Letta.ToolUpdate = {
  returnCharLimit: 100000,
  jsonSchema: {
    name: schema.title || toolName,
    description: schema.description || '',
    parameters: schema,
    strict: true
  }
};
```

## Validation Test

To verify the fix works, ensure the patched tool's `json_schema` has this structure:

```json
{
  "name": "tool_name",
  "description": "Tool description",
  "parameters": {
    "type": "object",
    "properties": { ... },
    "required": [...]
  },
  "strict": true  // optional
}
```

NOT this structure:

```json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    ...
  }
}
```

## Immediate Workaround

Until a permanent fix is deployed, you can:

1. **Manually patch the tools** without the wrapper structure
2. **Restart Letta agents** after fixing the tool schemas
3. **Use Option 1** in your API service code immediately

## Testing

Run the provided debug script to validate schemas:

```bash
poetry run python debug_tool_schema_issue.py
```

This will test various schema formats and show which ones pass validation.