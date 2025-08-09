"""
Critical regression tests for convert_to_structured_output function.

These tests specifically target the bugs that broke agent-to-agent communication:
1. Indentation bug causing KeyError when properties lack 'type' fields
2. Schema corruption from automatic 'string' type addition
"""

import pytest
from letta.llm_api.helpers import convert_to_structured_output


class TestConvertToStructuredOutputCriticalBugs:
    """Tests for critical bugs in convert_to_structured_output that broke multi-agent communication."""

    def test_indentation_bug_with_mixed_property_types(self):
        """
        Test the indentation bug that caused KeyError when processing properties.
        
        Bug: if/elif/else blocks for param_type processing were outside the for loop,
        causing KeyError when param_type was undefined after processing properties without 'type' fields.
        """
        # Schema with mix of properties: some with 'type', some without
        schema_with_missing_types = {
            "name": "send",
            "description": "Send message to agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to send"
                    },
                    "to": {
                        "type": "string", 
                        "description": "Target agent"
                    },
                    "priority": {
                        "description": "Message priority"
                        # Missing 'type' field - this triggers the bug
                    },
                    "attachments": {
                        "description": "File attachments"
                        # Missing 'type' field - this triggers the bug
                    }
                },
                "required": ["message", "to"]
            }
        }
        
        # This should NOT raise a KeyError - the indentation bug would cause:
        # KeyError: 'type' when param_type is undefined after processing 'attachments'
        result = convert_to_structured_output(schema_with_missing_types)
        
        # Should successfully create structured output
        assert "parameters" in result
        assert "properties" in result["parameters"]
        
        # Properties with 'type' fields should be included
        assert "message" in result["parameters"]["properties"]
        assert "to" in result["parameters"]["properties"]
        
        # Properties without 'type' fields should be gracefully skipped
        # (not crash with KeyError)
        properties = result["parameters"]["properties"]
        
        # Verify the function completed successfully without KeyError
        assert result["name"] == "send"
        assert result["strict"] == True

    def test_send_tool_schema_preservation(self):
        """
        Test that the send tool schema is not corrupted by schema validation.
        
        Bug: Schema validation was automatically adding 'string' types to properties,
        corrupting valid schemas and causing LLM to call tools incorrectly.
        """
        # Real send tool schema (simplified)
        original_send_schema = {
            "name": "send",
            "description": "Universal message sending function",
            "parameters": {
                "type": "object", 
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message content"
                    },
                    "to": {
                        "type": "string",
                        "description": "Target specification"  
                    }
                },
                "required": ["message", "to"]
            }
        }
        
        # Should convert without corruption
        result = convert_to_structured_output(original_send_schema)
        
        # Verify schema structure preserved
        assert result["name"] == "send"
        assert "parameters" in result
        assert "properties" in result["parameters"]
        
        # Verify required properties present with correct types
        props = result["parameters"]["properties"]
        assert "message" in props
        assert "to" in props
        assert props["message"]["type"] == "string"
        assert props["to"]["type"] == "string"
        
        # Verify required fields preserved
        assert "message" in result["parameters"]["required"]
        assert "to" in result["parameters"]["required"]

    def test_properties_without_type_field_are_gracefully_skipped(self):
        """
        Test that properties without 'type' fields are skipped, not corrupted with default types.
        
        This prevents the schema corruption that was breaking tool calls.
        """
        schema_with_optional_properties = {
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "required_param": {
                        "type": "string",
                        "description": "Required parameter"
                    },
                    "optional_metadata": {
                        "description": "Optional metadata without type"
                        # Intentionally missing 'type' field
                    }
                },
                "required": ["required_param"]
            }
        }
        
        result = convert_to_structured_output(schema_with_optional_properties)
        
        # Required param should be included
        assert "required_param" in result["parameters"]["properties"]
        assert result["parameters"]["properties"]["required_param"]["type"] == "string"
        
        # Optional param without type should be gracefully skipped (not corrupted)
        # The old bug would add "type": "string" automatically
        properties = result["parameters"]["properties"]
        
        # If optional_metadata appears, it should NOT have an auto-added 'string' type
        if "optional_metadata" in properties:
            # This would indicate the corruption bug is back
            pytest.fail("Properties without 'type' fields should be skipped, not included with default types")
        
        # Only the properly typed property should remain
        assert len(properties) == 1
        assert "required_param" in properties

    def test_empty_properties_dict(self):
        """Test edge case with empty properties that could trigger indentation bug."""
        empty_schema = {
            "name": "empty_tool",
            "description": "Tool with no parameters",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        # Should not crash
        result = convert_to_structured_output(empty_schema)
        
        assert result["name"] == "empty_tool"
        assert result["parameters"]["properties"] == {}
        assert result["parameters"]["required"] == []