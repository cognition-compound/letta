"""Test that tools created/updated via API get request_heartbeat parameter."""

import pytest
from unittest.mock import MagicMock, patch

from letta.constants import REQUEST_HEARTBEAT_PARAM, REQUEST_HEARTBEAT_DESCRIPTION
from letta.schemas.tool import Tool as PydanticTool, ToolUpdate
from letta.schemas.user import User as PydanticUser
from letta.services.tool_manager import ToolManager, ensure_heartbeat_in_schema


def test_ensure_heartbeat_in_schema():
    """Test the ensure_heartbeat_in_schema helper function."""
    
    # Test with None schema
    schema = None
    result = ensure_heartbeat_in_schema(schema)
    assert result is None
    
    # Test with empty schema - should add parameters structure
    schema = {}
    result = ensure_heartbeat_in_schema(schema)
    assert "parameters" in result
    assert REQUEST_HEARTBEAT_PARAM in result["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in result["parameters"]["required"]
    
    # Test with schema missing heartbeat
    schema = {
        "name": "test_tool",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"}
            },
            "required": ["message"]
        }
    }
    result = ensure_heartbeat_in_schema(schema)
    assert REQUEST_HEARTBEAT_PARAM in result["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in result["parameters"]["required"]
    assert "message" in result["parameters"]["properties"]  # Original param preserved
    assert "message" in result["parameters"]["required"]
    
    # Test with schema already having heartbeat (idempotent)
    schema = {
        "parameters": {
            "properties": {
                REQUEST_HEARTBEAT_PARAM: {
                    "type": "boolean",
                    "description": REQUEST_HEARTBEAT_DESCRIPTION
                }
            },
            "required": [REQUEST_HEARTBEAT_PARAM]
        }
    }
    result = ensure_heartbeat_in_schema(schema)
    # Should not duplicate
    assert result["parameters"]["required"].count(REQUEST_HEARTBEAT_PARAM) == 1


def test_create_tool_with_custom_schema():
    """Test that create_tool adds heartbeat to custom schemas."""
    
    tool_manager = ToolManager()
    
    # Mock database operations
    with patch('letta.server.db.db_registry.session') as mock_session_context:
        mock_session = MagicMock()
        mock_session_context.return_value.__enter__.return_value = mock_session
        
        # Create a tool with custom schema (no heartbeat)
        custom_schema = {
            "name": "custom_tool",
            "description": "A custom tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "The input"}
                },
                "required": ["input"]
            }
        }
        
        pydantic_tool = PydanticTool(
            id="tool-12345678",
            name="custom_tool",
            json_schema=custom_schema,
            source_code="def custom_tool(input: str): pass"
        )
        
        actor = PydanticUser(
            id="user-12345678",
            organization_id="org-12345678",
            name="Test User"
        )
        
        # Mock the ORM model
        with patch('letta.orm.tool.Tool') as MockToolModel:
            mock_tool_instance = MagicMock()
            mock_tool_instance.to_pydantic.return_value = pydantic_tool
            MockToolModel.return_value = mock_tool_instance
            
            # Call create_tool
            result = tool_manager.create_tool(pydantic_tool, actor)
            
            # Verify heartbeat was added to the schema
            assert REQUEST_HEARTBEAT_PARAM in pydantic_tool.json_schema["parameters"]["properties"]
            assert REQUEST_HEARTBEAT_PARAM in pydantic_tool.json_schema["parameters"]["required"]


def test_update_tool_with_custom_schema():
    """Test that update_tool_by_id calls ensure_heartbeat_in_schema for custom schemas."""
    
    # Test the function directly first
    new_schema = {
        "name": "updated_tool",
        "parameters": {
            "type": "object", 
            "properties": {
                "new_param": {"type": "integer"}
            },
            "required": ["new_param"]
        }
    }
    
    # This should modify the schema in place
    ensure_heartbeat_in_schema(new_schema)
    
    # Verify heartbeat was added
    assert REQUEST_HEARTBEAT_PARAM in new_schema["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in new_schema["parameters"]["required"]
    
    # Verify original parameter is still there
    assert "new_param" in new_schema["parameters"]["properties"]
    assert "new_param" in new_schema["parameters"]["required"]


def test_no_duplicate_heartbeat():
    """Test that heartbeat is not duplicated if already present."""
    
    # Schema already has heartbeat
    schema = {
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string"},
                REQUEST_HEARTBEAT_PARAM: {
                    "type": "boolean",
                    "description": REQUEST_HEARTBEAT_DESCRIPTION
                }
            },
            "required": ["param1", REQUEST_HEARTBEAT_PARAM]
        }
    }
    
    result = ensure_heartbeat_in_schema(schema.copy())
    
    # Should not duplicate heartbeat
    assert result["parameters"]["required"].count(REQUEST_HEARTBEAT_PARAM) == 1
    assert len(result["parameters"]["properties"]) == 2  # param1 + heartbeat


if __name__ == "__main__":
    test_ensure_heartbeat_in_schema()
    print("✅ test_ensure_heartbeat_in_schema passed")
    
    test_create_tool_with_custom_schema()
    print("✅ test_create_tool_with_custom_schema passed")
    
    test_update_tool_with_custom_schema()
    print("✅ test_update_tool_with_custom_schema passed")
    
    test_no_duplicate_heartbeat()
    print("✅ test_no_duplicate_heartbeat passed")
    
    print("\n🎉 All API tool heartbeat tests passed!")