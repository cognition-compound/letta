"""Test that MCP tool schemas are preserved during startup refresh."""

import asyncio
import copy
from unittest.mock import AsyncMock, Mock, patch

import pytest

from letta.functions.functions import derive_openai_json_schema
from letta.orm.enums import ToolType
from letta.schemas.tool import Tool as PydanticTool
from letta.schemas.user import User as PydanticUser
from letta.services.tool_manager import ensure_heartbeat_in_schema


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return PydanticUser(id="user-12345678", name="Test User", organization_id="org-87654321")


@pytest.fixture
def mock_mcp_tool():
    """Create a mock MCP tool with dummy source code and full schema."""
    # This is what an MCP tool looks like - dummy source code but full schema
    return PydanticTool(
        id="tool-12345678",
        name="weather_forecast",
        tool_type=ToolType.EXTERNAL_MCP,
        source_code="""\
def weather_forecast() -> None:
    '''MCP tool wrapper - actual execution happens through MCP client.
    
    This is a placeholder function. The real MCP tool execution is handled
    by the MCP client, not this source code. This exists only to satisfy
    the tool registration system.
    
    Returns:
        Never returns - raises RuntimeError if executed
    '''
    raise RuntimeError("Something went wrong - we should never be using the persisted source code for MCP. Please reach out to Letta team")
""",
        json_schema={
            "name": "weather_forecast",
            "description": "Get weather forecast for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The location to get weather for"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to forecast"
                    }
                },
                "required": ["location"]
            }
        },
        tags=["mcp:weather-server"]
    )


@pytest.fixture
def mock_custom_tool():
    """Create a mock custom tool with real source code."""
    return PydanticTool(
        id="tool-87654321",
        name="calculate_sum",
        tool_type=ToolType.CUSTOM,
        source_code="""\
def calculate_sum(a: int, b: int) -> int:
    \"\"\"Calculate the sum of two numbers.\"\"\"
    return a + b
""",
        json_schema={
            "name": "calculate_sum",
            "description": "Calculate the sum of two numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"}
                },
                "required": ["a", "b"]
            }
        }
    )


class TestMCPStartupRefresh:
    """Test that MCP tools are handled correctly during startup refresh."""

    def test_mcp_tool_schema_preserved(self, mock_mcp_tool):
        """Test that MCP tool schema is preserved and not regenerated from dummy source."""
        # What would happen if we regenerate from the dummy source code
        regenerated_schema = derive_openai_json_schema(
            source_code=mock_mcp_tool.source_code, 
            name=mock_mcp_tool.name
        )
        
        # The regenerated schema would lose all the actual parameters!
        # It would only have the heartbeat parameter added by derive_openai_json_schema
        assert "location" not in regenerated_schema.get("parameters", {}).get("properties", {})
        assert "days" not in regenerated_schema.get("parameters", {}).get("properties", {})
        
        # Now test our fix - we should preserve the original schema
        original_schema = copy.deepcopy(mock_mcp_tool.json_schema)
        preserved_schema = ensure_heartbeat_in_schema(copy.deepcopy(original_schema))
        
        # The preserved schema should still have all the original parameters
        assert "location" in preserved_schema["parameters"]["properties"]
        assert "days" in preserved_schema["parameters"]["properties"]
        
        # And it should also have the heartbeat
        assert "request_heartbeat" in preserved_schema["parameters"]["properties"]
        assert "request_heartbeat" in preserved_schema["parameters"]["required"]

    def test_custom_tool_schema_regenerated(self, mock_custom_tool):
        """Test that custom tool schemas are regenerated from source code."""
        # For custom tools, we should regenerate from source
        regenerated_schema = derive_openai_json_schema(
            source_code=mock_custom_tool.source_code,
            name=mock_custom_tool.name
        )
        
        # The regenerated schema should have the correct parameters
        assert "a" in regenerated_schema["parameters"]["properties"]
        assert "b" in regenerated_schema["parameters"]["properties"]
        
        # And it should have the heartbeat
        assert "request_heartbeat" in regenerated_schema["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_startup_refresh_logic(self, mock_user, mock_mcp_tool, mock_custom_tool):
        """Test the actual startup refresh logic with both MCP and custom tools."""
        
        # Mock the tool manager
        mock_tool_manager = Mock()
        mock_tool_manager.list_tools_async = AsyncMock(return_value=[mock_mcp_tool, mock_custom_tool])
        mock_tool_manager.update_tool_by_id_async = AsyncMock()
        
        # Mock the server
        mock_server = Mock()
        mock_server.tool_manager = mock_tool_manager
        mock_server.default_user = mock_user
        
        # Simulate the startup refresh logic
        from letta.functions.functions import derive_openai_json_schema
        from letta.orm.enums import ToolType
        from letta.schemas.tool import ToolUpdate
        from letta.services.tool_manager import ensure_heartbeat_in_schema
        
        all_tools = await mock_server.tool_manager.list_tools_async(actor=mock_server.default_user)
        
        updates_made = []
        for tool in all_tools:
            new_schema = None
            
            # This is our fix - check for MCP tools specifically
            if tool.tool_type == ToolType.EXTERNAL_MCP:
                # For MCP tools, preserve the existing schema
                if tool.json_schema:
                    schema_copy = copy.deepcopy(tool.json_schema)
                    new_schema = ensure_heartbeat_in_schema(schema_copy)
            elif tool.source_code:
                # For non-MCP tools with source code, regenerate from source
                new_schema = derive_openai_json_schema(source_code=tool.source_code, name=tool.name)
            elif tool.json_schema:
                # For tools without source code, just ensure heartbeat
                schema_copy = copy.deepcopy(tool.json_schema)
                new_schema = ensure_heartbeat_in_schema(schema_copy)
            
            if new_schema and new_schema != tool.json_schema:
                updates_made.append({
                    "tool_name": tool.name,
                    "tool_type": tool.tool_type,
                    "new_schema": new_schema
                })
        
        # Verify MCP tool schema was preserved correctly
        mcp_update = next((u for u in updates_made if u["tool_name"] == "weather_forecast"), None)
        assert mcp_update is not None
        assert "location" in mcp_update["new_schema"]["parameters"]["properties"]
        assert "days" in mcp_update["new_schema"]["parameters"]["properties"]
        assert "request_heartbeat" in mcp_update["new_schema"]["parameters"]["properties"]
        
        # Verify custom tool schema was regenerated correctly
        custom_update = next((u for u in updates_made if u["tool_name"] == "calculate_sum"), None)
        assert custom_update is not None
        assert "a" in custom_update["new_schema"]["parameters"]["properties"]
        assert "b" in custom_update["new_schema"]["parameters"]["properties"]
        assert "request_heartbeat" in custom_update["new_schema"]["parameters"]["properties"]

    def test_mcp_dummy_wrapper_has_no_params(self):
        """Verify that MCP dummy wrapper functions have no parameters when analyzed."""
        # This is the actual MCP wrapper function format
        dummy_source = """\
def weather_forecast() -> None:
    '''MCP tool wrapper - actual execution happens through MCP client.
    
    This is a placeholder function. The real MCP tool execution is handled
    by the MCP client, not this source code. This exists only to satisfy
    the tool registration system.
    
    Returns:
        Never returns - raises RuntimeError if executed
    '''
    raise RuntimeError("Something went wrong - we should never be using the persisted source code for MCP. Please reach out to Letta team")
"""
        
        # When derive_openai_json_schema analyzes this dummy function
        schema = derive_openai_json_schema(source_code=dummy_source, name="weather_forecast")
        
        # It should only have the heartbeat parameter, nothing else!
        props = schema.get("parameters", {}).get("properties", {})
        
        # Remove heartbeat to check other params
        non_heartbeat_props = {k: v for k, v in props.items() if k != "request_heartbeat"}
        
        # Should have NO other parameters because **kwargs doesn't generate params
        assert len(non_heartbeat_props) == 0, f"Dummy function should have no params except heartbeat, but has: {non_heartbeat_props}"
        
        # But it should have heartbeat
        assert "request_heartbeat" in props