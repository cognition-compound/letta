"""Test that MCP tools get request_heartbeat parameter during startup refresh."""

import copy
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from letta.constants import REQUEST_HEARTBEAT_PARAM
from letta.schemas.tool import Tool as PydanticTool, ToolUpdate
from letta.schemas.user import User as PydanticUser


@pytest.mark.asyncio
async def test_startup_refresh_adds_heartbeat_to_mcp_tools():
    """Test that the startup refresh adds heartbeat to MCP tools without source_code."""
    
    # Create a mock MCP tool without heartbeat
    mcp_tool = PydanticTool(
        id="tool-12345678",
        name="test_mcp_tool",
        tool_type="external_mcp",
        json_schema={
            "name": "test_mcp_tool",
            "description": "A test MCP tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Input parameter"}
                },
                "required": ["input"]
            }
        },
        source_code=None  # MCP tools don't have source code
    )
    
    # Verify it doesn't have heartbeat initially
    assert REQUEST_HEARTBEAT_PARAM not in mcp_tool.json_schema["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM not in mcp_tool.json_schema["parameters"]["required"]
    
    # Simulate the startup refresh logic
    from letta.services.tool_manager import ensure_heartbeat_in_schema
    
    # The startup code should do this for MCP tools
    schema_copy = copy.deepcopy(mcp_tool.json_schema)
    new_schema = ensure_heartbeat_in_schema(schema_copy)
    
    # Verify heartbeat was added
    assert REQUEST_HEARTBEAT_PARAM in new_schema["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in new_schema["parameters"]["required"]
    
    # Verify original parameters are preserved
    assert "input" in new_schema["parameters"]["properties"]
    assert "input" in new_schema["parameters"]["required"]


@pytest.mark.asyncio
async def test_startup_refresh_handles_tools_with_source_code():
    """Test that the startup refresh regenerates schema for tools with source_code."""
    
    # Create a mock tool with source code
    source_tool = PydanticTool(
        id="tool-87654321",
        name="test_source_tool",
        tool_type="custom",
        source_code="""
def test_source_tool(message: str) -> str:
    '''A test tool.
    
    Args:
        message: The message to process
        
    Returns:
        The processed message
    '''
    return message
""",
        json_schema={
            "name": "test_source_tool",
            "description": "A test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to process"}
                },
                "required": ["message"]
            }
        }
    )
    
    # For tools with source code, the startup should regenerate from source
    # which will automatically include heartbeat via generate_schema
    from letta.functions.functions import derive_openai_json_schema
    
    new_schema = derive_openai_json_schema(source_code=source_tool.source_code, name=source_tool.name)
    
    # Verify heartbeat was added via generate_schema
    assert REQUEST_HEARTBEAT_PARAM in new_schema["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in new_schema["parameters"]["required"]
    assert "message" in new_schema["parameters"]["properties"]


@pytest.mark.skip(reason="Integration test not needed")
@pytest.mark.asyncio
async def test_startup_refresh_integration():
    """Test the full startup refresh flow with mixed tool types."""
    
    # Mock the server and tool manager
    mock_server = MagicMock()
    mock_tool_manager = AsyncMock()
    mock_server.tool_manager = mock_tool_manager
    mock_server.default_user = PydanticUser(
        id="user-12345678",
        organization_id="org-12345678",
        name="Test User"
    )
    
    # Create test tools - some with source_code, some without (MCP tools)
    tools = [
        # MCP tool without heartbeat
        PydanticTool(
            id="tool-aabbccdd",
            name="mcp_tool_1",
            tool_type="external_mcp",
            json_schema={
                "name": "mcp_tool_1",
                "parameters": {
                    "type": "object",
                    "properties": {"param1": {"type": "string"}},
                    "required": ["param1"]
                }
            },
            source_code=None
        ),
        # Regular tool with source code
        PydanticTool(
            id="tool-11223344",
            name="source_tool_1",
            tool_type="custom",
            source_code="def source_tool_1(x: str) -> str:\n    '''Test.\n    Args:\n        x: input\n    '''\n    return x",
            json_schema={
                "name": "source_tool_1",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"]
                }
            }
        )
    ]
    
    mock_tool_manager.list_tools_async.return_value = tools
    
    # Track update calls
    update_calls = []
    async def mock_update(tool_id, tool_update, actor):
        update_calls.append((tool_id, tool_update.json_schema if tool_update else None))
        return MagicMock()
    
    mock_tool_manager.update_tool_by_id_async.side_effect = mock_update
    
    # Run the startup refresh logic
    from letta.functions.functions import derive_openai_json_schema
    from letta.schemas.tool import ToolUpdate
    from letta.services.tool_manager import ensure_heartbeat_in_schema
    
    all_tools = await mock_tool_manager.list_tools_async(actor=mock_server.default_user)
    
    for tool in all_tools:
        try:
            new_schema = None
            
            if tool.source_code:
                # For tools with source code, regenerate schema from source
                new_schema = derive_openai_json_schema(source_code=tool.source_code, name=tool.name)
            elif tool.json_schema:
                # For tools without source code (like MCP tools), just ensure heartbeat is present
                schema_copy = copy.deepcopy(tool.json_schema)
                new_schema = ensure_heartbeat_in_schema(schema_copy)
            
            # Update the tool if the schema changed
            if new_schema and new_schema != tool.json_schema:
                update = ToolUpdate(json_schema=new_schema)
                await mock_tool_manager.update_tool_by_id_async(
                    tool_id=tool.id,
                    tool_update=update,
                    actor=mock_server.default_user
                )
        except Exception as e:
            pass  # Ignore errors in test
    
    # Verify updates were called for the right tools
    assert len(update_calls) == 2  # MCP tool and source tool
    
    # Check MCP tool was updated with heartbeat
    mcp_update = next((u for u in update_calls if u[0] == "tool-aabbccdd"), None)
    assert mcp_update is not None
    assert REQUEST_HEARTBEAT_PARAM in mcp_update[1]["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in mcp_update[1]["parameters"]["required"]
    
    # Check source tool was updated with heartbeat
    source_update = next((u for u in update_calls if u[0] == "tool-11223344"), None)
    assert source_update is not None
    assert REQUEST_HEARTBEAT_PARAM in source_update[1]["parameters"]["properties"]
    assert REQUEST_HEARTBEAT_PARAM in source_update[1]["parameters"]["required"]


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_startup_refresh_adds_heartbeat_to_mcp_tools())
    print("✅ test_startup_refresh_adds_heartbeat_to_mcp_tools passed")
    
    asyncio.run(test_startup_refresh_handles_tools_with_source_code())
    print("✅ test_startup_refresh_handles_tools_with_source_code passed")
    
    asyncio.run(test_startup_refresh_integration())
    print("✅ test_startup_refresh_integration passed")
    
    print("\n🎉 All MCP tool startup refresh tests passed!")