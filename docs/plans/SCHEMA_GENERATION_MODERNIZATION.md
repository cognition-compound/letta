# Schema Generation Modernization Plan

## Current State: Amateur Hour 🎓

The current `schema_generator.py` is a 700+ line mess of:
- Manual type introspection with `inspect`
- Hand-rolled type-to-JSON-schema conversion
- Edge cases and special handling everywhere
- Poor separation of concerns
- Duplicated logic
- Comments like "TODO why are we inferring here?"

This is what happens when students write production code without understanding proper engineering patterns.

## Professional Alternatives

### 1. **OpenAI's Official Approach (openai-agents-python)**
OpenAI themselves solved this problem properly in their agents library:

```python
from agents import function_schema, FuncSchema

# Clean, professional API
schema = function_schema(
    func=my_function,
    strict_json_schema=True,  # Strict mode built-in
)
```

Features:
- Automatic Pydantic model generation from function signatures
- Built-in strict mode support
- Proper docstring parsing (Google/NumPy/Sphinx styles)
- Clean separation of concerns with `FuncSchema` dataclass
- Handles all parameter types correctly

### 2. **msgspec - The Performance Champion**
- **10x faster** than Pydantic v2
- Zero-dependency
- Validates during decoding for optimal performance
- Perfect for high-throughput systems

```python
import msgspec

class ToolParams(msgspec.Struct):
    query: str
    page: int | None = None  # Proper nullable handling
```

### 3. **Pydantic v2 - The Industry Standard**
Already used partially in Letta, but not properly:

```python
from pydantic import BaseModel, Field

class ConversationSearchParams(BaseModel):
    query: str = Field(..., description="String to search for")
    page: int | None = Field(None, description="Page number")
    
    model_config = {
        "json_schema_extra": {
            "strict": True,
            "additionalProperties": False
        }
    }

# Generate OpenAI-compatible schema
schema = ConversationSearchParams.model_json_schema()
```

### 4. **zon - Zod for Python**
For developers who love Zod's API:

```python
from zon import schema

tool_schema = schema.object({
    "query": schema.string().describe("Search query"),
    "page": schema.number().nullable().default(None)
}).strict()
```

## Recommended Approach

### Option 1: Use OpenAI's agents library (Cleanest)
```python
from openai_agents import function_schema

# Replace entire schema_generator.py with:
def generate_tool_schema(func):
    return function_schema(
        func,
        strict_json_schema=True
    ).to_openai_format()
```

### Option 2: Proper Pydantic Integration (Most Compatible)
```python
from pydantic import BaseModel, create_model
from typing import get_type_hints

def generate_schema(func):
    """Generate OpenAI function schema from function."""
    hints = get_type_hints(func)
    
    # Create Pydantic model dynamically
    fields = {}
    for param_name, param_type in hints.items():
        if param_name == 'return':
            continue
        # ALL parameters required for strict mode
        fields[param_name] = (param_type, Field(...))
    
    Model = create_model(
        f"{func.__name__}_params",
        **fields
    )
    
    schema = Model.model_json_schema()
    
    # Ensure strict mode compliance
    schema["additionalProperties"] = False
    schema["required"] = list(schema["properties"].keys())
    
    return {
        "name": func.__name__,
        "description": func.__doc__,
        "parameters": schema,
        "strict": True
    }
```

## Benefits of Modernization

1. **Maintainability**: 700 lines → ~50 lines
2. **Correctness**: No more manual type mapping bugs
3. **Performance**: msgspec is 10x faster if needed
4. **Standards**: Using industry-standard libraries
5. **Testing**: Libraries are battle-tested
6. **Documentation**: Proper documentation exists

## Migration Path

### Phase 1: Quick Win
1. Fix current `generate_schema()` to add ALL params to required array ✅
2. Add comprehensive tests ✅

### Phase 2: Refactor Core Functions
1. Convert all tool functions to use Pydantic models for parameters
2. Use `BaseModel.model_json_schema()` for schema generation
3. Remove manual type conversion code

### Phase 3: Full Modernization
1. Evaluate OpenAI agents library vs Pydantic vs msgspec
2. Replace entire `schema_generator.py`
3. Update all tool definitions
4. Add runtime validation

## Why This Matters

The current implementation is fragile, buggy, and embarrassing. Professional engineers use:
- **Type-safe validation** (Pydantic/msgspec)
- **Industry standards** (JSON Schema)
- **Tested libraries** (not hand-rolled code)
- **Clear APIs** (not 700-line messes)

This is the difference between student code and production code.

## Decision Required

Choose one:
1. **OpenAI agents library** - Cleanest, official solution
2. **Pydantic v2** - Already in use, industry standard
3. **msgspec** - If performance is critical
4. **Keep the mess** - And keep fixing bugs forever

## Recommendation

Use **Pydantic v2 properly** since it's already a dependency:
- Immediate compatibility
- Well-documented
- FastAPI integration
- Gradual migration possible

Stop writing amateur code. Use professional tools.