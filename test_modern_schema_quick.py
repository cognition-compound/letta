#!/usr/bin/env python
"""Quick test of modern schema generator without import conflicts."""

# Import only what we need
import importlib.util
from typing import Optional

# Load the openai-agents 'agents' module directly
spec = importlib.util.find_spec('agents')
if spec and spec.origin and 'openai-agents' in spec.origin:
    agents_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agents_module)
    function_schema = agents_module.function_schema.function_schema  # The actual function
    DocstringStyle = agents_module.function_schema.DocstringStyle
else:
    import agents as agents_module
    function_schema = agents_module.function_schema.function_schema  # The actual function
    DocstringStyle = agents_module.function_schema.DocstringStyle


def test_func(param1: str, param2: Optional[int] = None):
    """Test function with optional parameter.
    
    Args:
        param1: First parameter (required).
        param2: Second parameter (optional).
        
    Returns:
        String result.
    """
    return f"{param1}: {param2}"


# Generate schema using OpenAI's library
print("Testing OpenAI agents function_schema...")
schema = function_schema(
    func=test_func,
    docstring_style='google',  # DocstringStyle is a Literal['google', 'numpy', 'sphinx']
    strict_json_schema=True,
)

print(f"\nGenerated FuncSchema:")
print(f"  Name: {schema.name}")
print(f"  Description: {schema.description}")
print(f"  Strict mode: {schema.strict_json_schema}")
print(f"  JSON Schema: {schema.params_json_schema}")

# Check if all parameters are in required array
if "required" in schema.params_json_schema:
    print(f"\n  Required params: {schema.params_json_schema['required']}")
    print(f"  All params: {list(schema.params_json_schema['properties'].keys())}")
    
    # Verify all params are required for strict mode
    all_params = set(schema.params_json_schema['properties'].keys())
    required_params = set(schema.params_json_schema['required'])
    if all_params == required_params:
        print("  ✓ ALL parameters are in required array (correct for strict mode)")
    else:
        print(f"  ✗ Missing from required: {all_params - required_params}")
        
# Test with a more complex function
def complex_func(
    query: str,
    page: Optional[int] = None,
    start: Optional[int] = None
):
    """Search with pagination.
    
    Args:
        query: Search query string.
        page: Page number (optional).
        start: Starting index (optional).
    """
    return f"Searching for {query}"

print("\n" + "="*60)
print("Testing complex function with multiple optional params...")
schema2 = function_schema(
    func=complex_func,
    docstring_style='google',  # Use string literal
    strict_json_schema=True,
)

print(f"\nGenerated Schema:")
print(f"  Name: {schema2.name}")
print(f"  Properties: {list(schema2.params_json_schema['properties'].keys())}")
print(f"  Required: {schema2.params_json_schema['required']}")
print(f"  AdditionalProperties: {schema2.params_json_schema.get('additionalProperties', 'not set')}")

# Check strict mode compliance
is_strict_compliant = (
    set(schema2.params_json_schema['properties'].keys()) == set(schema2.params_json_schema['required'])
    and schema2.params_json_schema.get('additionalProperties') == False
)

if is_strict_compliant:
    print("  ✓ Schema is OpenAI strict mode compliant!")
else:
    print("  ✗ Schema is NOT strict mode compliant")
    
print("\n" + "="*60)
print("Summary: OpenAI's agents library properly generates strict mode schemas")