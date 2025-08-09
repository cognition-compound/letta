"""Test the modern schema generator using OpenAI's agents library."""

import pytest
from typing import Optional

from letta.functions.schema_generator_modern import generate_schema_modern
from letta.functions.function_sets.base import (
    conversation_search,
    archival_memory_search,
    memory_replace,
)


class TestModernSchemaGenerator:
    """Test that the modern implementation works correctly."""

    def test_modern_conversation_search_schema(self):
        """Test that modern generator produces correct schema for conversation_search."""
        schema = generate_schema_modern(conversation_search)
        
        # Check basic structure
        assert "name" in schema
        assert schema["name"] == "conversation_search"
        assert "description" in schema
        assert "parameters" in schema
        assert schema["strict"] is True
        
        # Check parameters
        params = schema["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params
        assert params["additionalProperties"] is False
        
        # Check specific parameters
        props = params["properties"]
        assert "query" in props
        assert "page" in props
        
        # ALL parameters must be in required for strict mode
        assert "query" in params["required"]
        assert "page" in params["required"]
        
        # Internal parameters should be filtered out
        assert "self" not in props
        assert "agent_state" not in props

    def test_modern_archival_memory_search_schema(self):
        """Test schema generation for archival_memory_search."""
        schema = generate_schema_modern(archival_memory_search)
        
        assert schema["name"] == "archival_memory_search"
        assert schema["strict"] is True
        
        props = schema["parameters"]["properties"]
        required = schema["parameters"]["required"]
        
        # Check all parameters are present
        assert "query" in props
        assert "page" in props
        assert "start" in props
        
        # ALL must be required for strict mode
        assert set(required) == {"query", "page", "start"}
        
        # No internal parameters
        assert "self" not in props

    def test_modern_memory_replace_schema(self):
        """Test schema generation for memory_replace."""
        schema = generate_schema_modern(memory_replace)
        
        assert schema["name"] == "memory_replace"
        assert schema["strict"] is True
        
        props = schema["parameters"]["properties"]
        required = schema["parameters"]["required"]
        
        # Check all parameters (excluding agent_state)
        assert "label" in props
        assert "old_str" in props
        assert "new_str" in props
        
        # ALL must be required for strict mode
        assert set(required) == {"label", "old_str", "new_str"}
        
        # No internal parameters
        assert "agent_state" not in props

    def test_custom_name_and_description(self):
        """Test that custom name and description overrides work."""
        def simple_func(param1: str, param2: int = 5) -> str:
            """Original description."""
            return f"{param1}: {param2}"
        
        schema = generate_schema_modern(
            simple_func,
            name="custom_name",
            description="Custom description"
        )
        
        assert schema["name"] == "custom_name"
        assert schema["description"] == "Custom description"
        assert schema["strict"] is True

    def test_optional_parameters_handling(self):
        """Test that Optional parameters are handled correctly."""
        def func_with_optional(
            required_param: str,
            optional_param: Optional[int] = None,
            optional_str: Optional[str] = None
        ) -> str:
            """
            Test function with optional parameters.
            
            Args:
                required_param: A required parameter.
                optional_param: An optional integer parameter.
                optional_str: An optional string parameter.
            """
            return "test"
        
        schema = generate_schema_modern(func_with_optional)
        
        props = schema["parameters"]["properties"]
        required = schema["parameters"]["required"]
        
        # All parameters should be present
        assert "required_param" in props
        assert "optional_param" in props
        assert "optional_str" in props
        
        # ALL parameters must be in required for strict mode
        assert set(required) == {"required_param", "optional_param", "optional_str"}
        
        # Check types are preserved
        assert props["required_param"]["type"] == "string"
        # Optional types might be represented as nullable
        # The exact representation depends on the agents library

    def test_no_docstring_function(self):
        """Test handling of functions without docstrings."""
        def no_docs_func(param: str):
            return param
        
        schema = generate_schema_modern(no_docs_func)
        
        assert schema["name"] == "no_docs_func"
        assert schema["description"] is not None  # Should have some default
        assert schema["strict"] is True
        
        # Parameter should still be extracted from signature
        assert "param" in schema["parameters"]["properties"]
        assert "param" in schema["parameters"]["required"]

    def test_complex_types(self):
        """Test handling of complex type annotations."""
        from typing import List, Dict
        
        def complex_func(
            items: List[str],
            mapping: Dict[str, int],
            optional_list: Optional[List[int]] = None
        ) -> Dict[str, List[int]]:
            """
            Function with complex types.
            
            Args:
                items: List of strings.
                mapping: Dictionary mapping strings to integers.
                optional_list: Optional list of integers.
            """
            return {}
        
        schema = generate_schema_modern(complex_func)
        
        props = schema["parameters"]["properties"]
        required = schema["parameters"]["required"]
        
        # All parameters should be present
        assert "items" in props
        assert "mapping" in props
        assert "optional_list" in props
        
        # ALL must be required for strict mode
        assert set(required) == {"items", "mapping", "optional_list"}
        
        # Check array type is preserved
        assert props["items"]["type"] == "array"
        assert props["mapping"]["type"] == "object"

    def test_backwards_compatibility(self):
        """Test that the compatibility wrapper works."""
        from letta.functions.schema_generator_modern import generate_schema
        
        # This should work exactly like generate_schema_modern
        schema = generate_schema(conversation_search)
        
        assert schema["name"] == "conversation_search"
        assert schema["strict"] is True
        assert "query" in schema["parameters"]["required"]
        assert "page" in schema["parameters"]["required"]


if __name__ == "__main__":
    # Run a quick test
    test = TestModernSchemaGenerator()
    
    print("Testing modern conversation_search schema...")
    test.test_modern_conversation_search_schema()
    print("✓ Passed")
    
    print("\nTesting optional parameters handling...")
    test.test_optional_parameters_handling()
    print("✓ Passed")
    
    print("\nTesting complex types...")
    test.test_complex_types()
    print("✓ Passed")
    
    print("\nAll tests passed!")