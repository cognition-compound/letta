"""Test that tool schemas are generated correctly for OpenAI strict mode."""

import pytest
from typing import Optional

from letta.functions.schema_generator import generate_schema
from letta.functions.function_sets.base import (
    conversation_search,
    archival_memory_search,
    memory_replace,
)


class TestStrictModeSchemaGeneration:
    """Test that all parameters are in the required array for strict mode compliance."""

    def test_conversation_search_schema_all_params_required(self):
        """Test that conversation_search has ALL parameters in required array."""
        schema = generate_schema(conversation_search)
        
        # All parameters should be in the required array for strict mode
        assert "query" in schema["parameters"]["required"], "query parameter must be in required array"
        assert "page" in schema["parameters"]["required"], "page parameter must be in required array for strict mode"
        
        # The page parameter should be nullable with anyOf
        page_prop = schema["parameters"]["properties"]["page"]
        assert "anyOf" in page_prop, "page should have anyOf for nullable type"
        assert {"type": "integer"} in page_prop["anyOf"], "page anyOf should include integer"
        assert {"type": "null"} in page_prop["anyOf"], "page anyOf should include null"
        # Note: The function accepts Optional[int] which means it can be null
        # This is handled by the type annotation, not by omitting from required

    def test_archival_memory_search_schema_all_params_required(self):
        """Test that archival_memory_search has ALL parameters in required array."""
        schema = generate_schema(archival_memory_search)
        
        # All parameters should be in the required array for strict mode
        assert "query" in schema["parameters"]["required"], "query parameter must be in required array"
        assert "page" in schema["parameters"]["required"], "page parameter must be in required array for strict mode"
        assert "start" in schema["parameters"]["required"], "start parameter must be in required array for strict mode"
        
        # Both optional parameters should be nullable with anyOf
        page_prop = schema["parameters"]["properties"]["page"]
        start_prop = schema["parameters"]["properties"]["start"]
        assert "anyOf" in page_prop, "page should have anyOf for nullable type"
        assert {"type": "integer"} in page_prop["anyOf"], "page anyOf should include integer"
        assert {"type": "null"} in page_prop["anyOf"], "page anyOf should include null"
        assert "anyOf" in start_prop, "start should have anyOf for nullable type"
        assert {"type": "integer"} in start_prop["anyOf"], "start anyOf should include integer"
        assert {"type": "null"} in start_prop["anyOf"], "start anyOf should include null"

    def test_memory_replace_schema_all_params_required(self):
        """Test that memory_replace has ALL parameters in required array."""
        # Note: memory_replace is a standalone function, not a method
        from letta.functions.function_sets.base import memory_replace
        
        schema = generate_schema(memory_replace)
        
        # All parameters should be in the required array for strict mode
        # (excluding 'agent_state' which is filtered out)
        assert "label" in schema["parameters"]["required"], "label parameter must be in required array"
        assert "old_str" in schema["parameters"]["required"], "old_str parameter must be in required array"
        assert "new_str" in schema["parameters"]["required"], "new_str parameter must be in required array for strict mode"
        
        # new_str should be nullable with anyOf
        new_str_prop = schema["parameters"]["properties"]["new_str"]
        assert "anyOf" in new_str_prop, "new_str should have anyOf for nullable type"
        assert {"type": "string"} in new_str_prop["anyOf"], "new_str anyOf should include string"
        assert {"type": "null"} in new_str_prop["anyOf"], "new_str anyOf should include null"

    def test_optional_params_with_defaults_still_required(self):
        """Test that Optional parameters with default values are still in required array."""
        
        def test_function(required_param: str, optional_param: Optional[int] = None) -> str:
            """
            Test function with optional parameter.
            
            Args:
                required_param (str): A required parameter.
                optional_param (Optional[int]): An optional parameter with default None.
                
            Returns:
                str: Test result.
            """
            return f"required: {required_param}, optional: {optional_param}"
        
        schema = generate_schema(test_function)
        
        # BOTH parameters should be in required array for strict mode
        assert "required_param" in schema["parameters"]["required"]
        assert "optional_param" in schema["parameters"]["required"], "Optional params with defaults must still be in required array for strict mode"
        
        # The optional parameter should have anyOf schema to allow null
        optional_prop = schema["parameters"]["properties"]["optional_param"]
        assert "anyOf" in optional_prop, "Optional[int] should generate anyOf schema"
        assert len(optional_prop["anyOf"]) == 2, "anyOf should have exactly 2 options"
        assert {"type": "integer"} in optional_prop["anyOf"], "anyOf should include integer type"
        assert {"type": "null"} in optional_prop["anyOf"], "anyOf should include null type"

    def test_strict_mode_required_array_completeness(self):
        """Test that the required array contains ALL parameters for strict mode."""
        
        def complex_function(
            param1: str,
            param2: int,
            param3: Optional[str] = None,
            param4: Optional[int] = None,
            param5: str = "default"
        ) -> str:
            """
            Complex function with mixed parameter types.
            
            Args:
                param1 (str): First parameter.
                param2 (int): Second parameter.
                param3 (Optional[str]): Third parameter (optional).
                param4 (Optional[int]): Fourth parameter (optional).
                param5 (str): Fifth parameter with default.
                
            Returns:
                str: Test result.
            """
            return "test"
        
        schema = generate_schema(complex_function)
        
        # ALL parameters must be in required array for strict mode
        expected_required = ["param1", "param2", "param3", "param4", "param5"]
        assert set(schema["parameters"]["required"]) == set(expected_required), \
            f"Required array must contain ALL parameters for strict mode. Expected {expected_required}, got {schema['parameters']['required']}"


if __name__ == "__main__":
    # Run the tests to see failures
    test = TestStrictModeSchemaGeneration()
    
    print("Testing conversation_search schema...")
    try:
        test.test_conversation_search_schema_all_params_required()
        print("✓ conversation_search test passed")
    except AssertionError as e:
        print(f"✗ conversation_search test failed: {e}")
    
    print("\nTesting archival_memory_search schema...")
    try:
        test.test_archival_memory_search_schema_all_params_required()
        print("✓ archival_memory_search test passed")
    except AssertionError as e:
        print(f"✗ archival_memory_search test failed: {e}")
    
    print("\nTesting memory_replace schema...")
    try:
        test.test_memory_replace_schema_all_params_required()
        print("✓ memory_replace test passed")
    except AssertionError as e:
        print(f"✗ memory_replace test failed: {e}")
    
    print("\nTesting optional params with defaults...")
    try:
        test.test_optional_params_with_defaults_still_required()
        print("✓ optional params test passed")
    except AssertionError as e:
        print(f"✗ optional params test failed: {e}")
    
    print("\nTesting strict mode completeness...")
    try:
        test.test_strict_mode_required_array_completeness()
        print("✓ strict mode completeness test passed")
    except AssertionError as e:
        print(f"✗ strict mode completeness test failed: {e}")