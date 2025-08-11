"""Test that request_heartbeat parameter is added to all tool schemas."""

import pytest
from letta.functions.functions import derive_openai_json_schema, load_function_set
from letta.functions.schema_generator import generate_schema
from letta.constants import REQUEST_HEARTBEAT_PARAM, REQUEST_HEARTBEAT_DESCRIPTION


def test_generate_schema_adds_heartbeat():
    """Test that generate_schema adds the request_heartbeat parameter."""
    
    def test_function(message: str) -> str:
        """Test function for schema generation.
        
        Args:
            message: The message to echo
            
        Returns:
            The echoed message
        """
        return message
    
    schema = generate_schema(test_function)
    
    # Check that heartbeat is in properties
    assert REQUEST_HEARTBEAT_PARAM in schema["parameters"]["properties"], \
        f"Expected {REQUEST_HEARTBEAT_PARAM} in properties"
    
    # Check that heartbeat is in required array
    assert REQUEST_HEARTBEAT_PARAM in schema["parameters"]["required"], \
        f"Expected {REQUEST_HEARTBEAT_PARAM} in required array"
    
    # Check the heartbeat field details
    heartbeat_field = schema["parameters"]["properties"][REQUEST_HEARTBEAT_PARAM]
    assert heartbeat_field["type"] == "boolean", \
        f"Expected heartbeat type to be boolean, got {heartbeat_field['type']}"
    assert heartbeat_field["description"] == REQUEST_HEARTBEAT_DESCRIPTION, \
        f"Unexpected heartbeat description"


def test_derive_openai_json_schema_adds_heartbeat():
    """Test that derive_openai_json_schema includes heartbeat via generate_schema."""
    
    test_source = '''
def another_test_function(value: int) -> int:
    """Doubles the input value.
    
    Args:
        value: The value to double
        
    Returns:
        The doubled value
    """
    return value * 2
'''
    
    schema = derive_openai_json_schema(test_source)
    
    # Check that heartbeat is present
    assert REQUEST_HEARTBEAT_PARAM in schema["parameters"]["properties"], \
        f"Expected {REQUEST_HEARTBEAT_PARAM} in properties from derive_openai_json_schema"
    assert REQUEST_HEARTBEAT_PARAM in schema["parameters"]["required"], \
        f"Expected {REQUEST_HEARTBEAT_PARAM} in required from derive_openai_json_schema"


def test_load_function_set_includes_heartbeat():
    """Test that load_function_set generates schemas with heartbeat."""
    
    # Load a built-in function set
    import importlib
    module_name = "letta.functions.function_sets.base"
    module = importlib.import_module(module_name)
    functions_schemas = load_function_set(module)
    
    # Check that at least one function was loaded
    assert len(functions_schemas) > 0, "No functions loaded from base module"
    
    # Check that all functions have heartbeat
    for func_name, func_data in functions_schemas.items():
        # The structure is {"module": ..., "python_function": ..., "json_schema": ...}
        func_schema = func_data["json_schema"]
        assert REQUEST_HEARTBEAT_PARAM in func_schema["parameters"]["properties"], \
            f"Function {func_name} missing {REQUEST_HEARTBEAT_PARAM} in properties"
        assert REQUEST_HEARTBEAT_PARAM in func_schema["parameters"]["required"], \
            f"Function {func_name} missing {REQUEST_HEARTBEAT_PARAM} in required"


def test_no_duplicate_heartbeat_in_required():
    """Test that heartbeat is only added once to the required array."""
    
    def simple_function() -> str:
        """Function with no parameters.
        
        Returns:
            A simple string
        """
        return "hello"
    
    schema = generate_schema(simple_function)
    
    # Count occurrences of heartbeat in required array
    heartbeat_count = schema["parameters"]["required"].count(REQUEST_HEARTBEAT_PARAM)
    assert heartbeat_count == 1, \
        f"Expected {REQUEST_HEARTBEAT_PARAM} to appear exactly once in required, found {heartbeat_count} times"


if __name__ == "__main__":
    test_generate_schema_adds_heartbeat()
    print("✅ test_generate_schema_adds_heartbeat passed")
    
    test_derive_openai_json_schema_adds_heartbeat()
    print("✅ test_derive_openai_json_schema_adds_heartbeat passed")
    
    test_load_function_set_includes_heartbeat()
    print("✅ test_load_function_set_includes_heartbeat passed")
    
    test_no_duplicate_heartbeat_in_required()
    print("✅ test_no_duplicate_heartbeat_in_required passed")
    
    print("\n🎉 All heartbeat tests passed!")