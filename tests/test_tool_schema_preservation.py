"""
Integration tests for tool schema preservation during validation.

These tests ensure that valid tool schemas are not corrupted by the validation pipeline,
specifically targeting the schema corruption bug that broke multi-agent communication.
"""

import pytest
from letta.orm.enums import ToolType
from letta.schemas.tool import Tool


class TestToolSchemaPreservation:
    """Integration tests for tool schema preservation during validation."""

    def test_send_tool_schema_not_corrupted_by_validation(self):
        """
        Test that the send tool schema is preserved during validation.
        
        Bug: Tool validation was automatically adding 'string' types to properties,
        corrupting the send tool and causing "missing 2 required positional arguments" errors.
        """
        # Real send tool schema from multi_agent.py
        original_send_schema = {
            "name": "send",
            "description": "Universal message sending function with explicit routing",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The content of the message to send"
                    },
                    "to": {
                        "type": "string", 
                        "description": "Target specification: 'user', 'agent:<id>', 'group:<id>', 'broadcast:<tag>'"
                    }
                },
                "required": ["message", "to"]
            }
        }
        
        # Create tool - this should NOT corrupt the schema
        tool = Tool(
            id="tool-abcd1234",
            name="send",
            tool_type=ToolType.LETTA_MULTI_AGENT_CORE,
            json_schema=original_send_schema,
            tags=["multi-agent"]
        )
        
        # Verify schema was not corrupted
        assert tool.json_schema["name"] == "send"
        assert tool.json_schema["parameters"]["type"] == "object"
        
        properties = tool.json_schema["parameters"]["properties"]
        
        # Required properties should be present with correct types
        assert "message" in properties
        assert "to" in properties
        assert properties["message"]["type"] == "string"
        assert properties["to"]["type"] == "string"
        
        # Required array should be preserved
        assert "message" in tool.json_schema["parameters"]["required"]
        assert "to" in tool.json_schema["parameters"]["required"]
        
        # Should have exactly 2 properties (no auto-added properties)
        assert len(properties) == 2

    def test_mcp_tool_with_missing_type_fields_not_auto_fixed(self):
        """
        Test that MCP tools with missing 'type' fields are not automatically 'fixed'.
        
        Bug: Schema validation was adding default 'string' types to properties missing 'type' fields,
        which corrupted valid schemas that intentionally omit types.
        """
        # MCP tool schema with some properties missing 'type' fields (this is valid!)
        mcp_tool_schema = {
            "name": "mcp_tool",
            "description": "Example MCP tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "typed_param": {
                        "type": "string",
                        "description": "Parameter with explicit type"
                    },
                    "untyped_param": {
                        "description": "Parameter without explicit type - this is valid in JSON schema!"
                        # Intentionally no 'type' field
                    }
                },
                "required": ["typed_param"]
            }
        }
        
        original_properties = mcp_tool_schema["parameters"]["properties"].copy()
        
        # Create tool - this should NOT auto-fix the schema
        tool = Tool(
            id="tool-ef123456",
            name="mcp_tool", 
            tool_type=ToolType.EXTERNAL_MCP,
            json_schema=mcp_tool_schema,
            tags=["mcp:test"]
        )
        
        # Schema should be preserved as-is
        properties = tool.json_schema["parameters"]["properties"]
        
        # Typed parameter should remain unchanged
        assert "typed_param" in properties
        assert properties["typed_param"]["type"] == "string"
        
        # Untyped parameter should remain unchanged (NOT auto-fixed with "type": "string")
        assert "untyped_param" in properties
        assert properties["untyped_param"]["description"] == "Parameter without explicit type - this is valid in JSON schema!"
        
        # CRITICAL: Should NOT have auto-added "type": "string" 
        if "type" in properties["untyped_param"]:
            pytest.fail(f"Schema corruption detected: auto-added type '{properties['untyped_param']['type']}' to untyped parameter")

    def test_tool_schema_validation_does_not_modify_original(self):
        """
        Test that tool validation does not modify the original schema dict.
        
        This ensures immutability and prevents side effects.
        """
        original_schema = {
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object", 
                "properties": {
                    "param1": {"type": "string"},
                    "param2": {"description": "No type field"}
                },
                "required": ["param1"]
            }
        }
        
        # Keep a deep copy to compare
        import copy
        schema_before = copy.deepcopy(original_schema)
        
        # Create tool
        tool = Tool(
            id="tool-78901234",
            name="test_tool",
            tool_type=ToolType.EXTERNAL_MCP,  # Use MCP type which doesn't require source_code
            json_schema=original_schema,
            tags=["test"]
        )
        
        # Original schema should be unchanged
        assert original_schema == schema_before, "Tool validation modified the original schema dict"

    def test_builtin_send_tool_loads_correctly(self):
        """
        Test that the actual builtin send tool can be loaded without schema corruption.
        
        This is the most critical test - the exact tool that was broken.
        """
        # Use the exact send tool schema that was being corrupted
        send_schema = {
            "name": "send",
            "description": "Universal message sending function with explicit routing",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The content of the message to send"},
                    "to": {"type": "string", "description": "Target specification"}
                },
                "required": ["message", "to"]
            }
        }
        
        # Create tool from builtin send
        tool = Tool(
            id="tool-56789abc",
            name="send",
            tool_type=ToolType.LETTA_MULTI_AGENT_CORE,
            json_schema=send_schema,
            tags=["multi-agent", "builtin"]
        )
        
        # Should have exactly the required parameters
        properties = tool.json_schema["parameters"]["properties"]
        assert len(properties) == 2  # Exactly message and to
        assert "message" in properties
        assert "to" in properties
        
        # Should have proper types
        assert properties["message"]["type"] == "string"
        assert properties["to"]["type"] == "string"
        
        # Should be callable without "missing arguments" error
        from letta.llm_api.helpers import convert_to_structured_output
        structured_output = convert_to_structured_output(tool.json_schema)
        assert "parameters" in structured_output
        assert len(structured_output["parameters"]["properties"]) == 2