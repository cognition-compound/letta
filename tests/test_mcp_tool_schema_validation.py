"""Tests for MCP tool schema validation and fixing."""

import pytest

from letta.llm_api.helpers import convert_to_structured_output
from letta.orm.enums import ToolType
from letta.schemas.tool import Tool


class TestMCPToolSchemaValidation:
    """Test MCP tool schema validation and automatic fixing."""

    def test_mcp_tool_missing_type_fields(self):
        """Test that MCP tools with missing 'type' fields in properties are automatically fixed."""
        # Create a malformed MCP tool schema
        malformed_schema = {
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "prop_without_type": {
                        "description": "Missing type field"
                    },
                    "prop_with_type": {
                        "type": "string",
                        "description": "Has type field"
                    },
                    "enum_without_type": {
                        "description": "Enum without type",
                        "enum": ["opt1", "opt2"]
                    }
                },
                "required": ["prop_without_type"]
            }
        }
        
        # Create MCP tool
        tool = Tool(
            id="tool-12345678",
            name="test_tool",
            tool_type=ToolType.EXTERNAL_MCP,
            json_schema=malformed_schema,
            tags=["mcp:test"]
        )
        
        # Verify all properties now have 'type' field
        properties = tool.json_schema["parameters"]["properties"]
        assert "type" in properties["prop_without_type"]
        assert properties["prop_without_type"]["type"] == "string"
        assert "type" in properties["prop_with_type"]
        assert properties["prop_with_type"]["type"] == "string"
        assert "type" in properties["enum_without_type"]
        assert properties["enum_without_type"]["type"] == "string"
    
    def test_wrapped_mcp_tool_schema(self):
        """Test that wrapped MCP tool schemas (from zod-to-json-schema) are unwrapped."""
        # Create wrapped schema
        wrapped_schema = {
            "type": "function",
            "function": {
                "name": "wrapped_tool",
                "description": "Wrapped tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param": {
                            "type": "string",
                            "description": "Parameter"
                        }
                    },
                    "required": ["param"]
                }
            }
        }
        
        # Create MCP tool
        tool = Tool(
            id="tool-abcdef12",
            name="wrapped_tool",
            tool_type=ToolType.EXTERNAL_MCP,
            json_schema=wrapped_schema,
            tags=["mcp:test"]
        )
        
        # Verify schema is unwrapped
        assert "type" not in tool.json_schema or tool.json_schema.get("type") != "function"
        assert "function" not in tool.json_schema
        assert "name" in tool.json_schema
        assert "parameters" in tool.json_schema
        assert tool.json_schema["name"] == "wrapped_tool"
    
    def test_mcp_tool_with_combined_issues(self):
        """Test MCP tool with both wrapped schema AND missing type fields."""
        # Create wrapped schema with missing types
        complex_schema = {
            "type": "function",
            "function": {
                "name": "complex_tool",
                "description": "Complex tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "missing_type": {
                            "description": "No type"
                        },
                        "has_type": {
                            "type": "number",
                            "description": "Has type"
                        }
                    },
                    "required": []
                }
            }
        }
        
        # Create MCP tool
        tool = Tool(
            id="tool-fedcba98",
            name="complex_tool",
            tool_type=ToolType.EXTERNAL_MCP,
            json_schema=complex_schema,
            tags=["mcp:test"]
        )
        
        # Verify both fixes applied
        assert "type" not in tool.json_schema or tool.json_schema.get("type") != "function"
        assert "function" not in tool.json_schema
        
        properties = tool.json_schema["parameters"]["properties"]
        assert "type" in properties["missing_type"]
        assert properties["missing_type"]["type"] == "string"
        assert "type" in properties["has_type"]
        assert properties["has_type"]["type"] == "number"
    
    def test_convert_to_structured_output_with_fixed_mcp_tool(self):
        """Test that convert_to_structured_output works with auto-fixed MCP tools."""
        # Create malformed schema
        malformed_schema = {
            "name": "send_message",
            "description": "Send message",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "description": "Recipient"
                        # Missing 'type' field
                    },
                    "message": {
                        "type": "string",
                        "description": "Message"
                    }
                },
                "required": ["recipient", "message"]
            }
        }
        
        # Create and fix tool
        tool = Tool(
            id="tool-11223344",
            name="send_message",
            tool_type=ToolType.EXTERNAL_MCP,
            json_schema=malformed_schema,
            tags=["mcp:test"]
        )
        
        # Test convert_to_structured_output doesn't crash
        result = convert_to_structured_output(tool.json_schema)
        
        # Verify result structure
        assert "parameters" in result
        assert "properties" in result["parameters"]
        
        # Verify all properties have types in output
        for prop_name, prop_schema in result["parameters"]["properties"].items():
            if prop_name != "request_heartbeat":  # Skip heartbeat
                assert "type" in prop_schema
    
    def test_langchain_tool_schema_validation(self):
        """Test that LangChain tools also get schema validation."""
        # Create malformed LangChain tool schema
        malformed_schema = {
            "name": "langchain_tool",
            "description": "LangChain tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "missing_type": {
                        "description": "No type"
                    }
                },
                "required": []
            }
        }
        
        # Create LangChain tool
        tool = Tool(
            id="tool-aabbccdd",
            name="langchain_tool",
            tool_type=ToolType.EXTERNAL_LANGCHAIN,
            json_schema=malformed_schema,
            tags=["langchain"]
        )
        
        # Verify property has type added
        properties = tool.json_schema["parameters"]["properties"]
        assert "type" in properties["missing_type"]
        assert properties["missing_type"]["type"] == "string"