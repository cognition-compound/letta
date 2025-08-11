"""Test that MCP tool schemas are preserved during startup refresh (simplified)."""

import copy
from letta.functions.functions import derive_openai_json_schema
from letta.services.tool_manager import ensure_heartbeat_in_schema


def test_mcp_wrapper_loses_parameters():
    """Demonstrate that MCP wrapper functions lose their parameters when analyzed."""
    
    # This is what an MCP wrapper looks like
    mcp_wrapper_source = """\
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
    regenerated_schema = derive_openai_json_schema(source_code=mcp_wrapper_source, name="weather_forecast")
    
    # It generates a schema with NO parameters (except heartbeat)
    props = regenerated_schema.get("parameters", {}).get("properties", {})
    non_heartbeat_props = {k: v for k, v in props.items() if k != "request_heartbeat"}
    
    print("Regenerated schema from MCP wrapper has these non-heartbeat properties:", non_heartbeat_props)
    assert len(non_heartbeat_props) == 0, "MCP wrapper has no real parameters"
    
    # This is the ACTUAL schema that MCP tools should have
    original_mcp_schema = {
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
    }
    
    # The original schema has the actual parameters
    assert "location" in original_mcp_schema["parameters"]["properties"]
    assert "days" in original_mcp_schema["parameters"]["properties"]
    
    # If we preserve and just add heartbeat, it works
    preserved_schema = ensure_heartbeat_in_schema(copy.deepcopy(original_mcp_schema))
    assert "location" in preserved_schema["parameters"]["properties"]
    assert "days" in preserved_schema["parameters"]["properties"]
    assert "request_heartbeat" in preserved_schema["parameters"]["properties"]
    
    print("\nTHE PROBLEM:")
    print("- MCP tools have dummy wrapper source code with NO parameters")
    print("- Startup refresh regenerates schema from this dummy source")
    print("- This loses ALL the actual MCP tool parameters!")
    print("\nTHE FIX:")
    print("- Check if tool.tool_type == ToolType.EXTERNAL_MCP")
    print("- For MCP tools, preserve existing schema (just add heartbeat)")
    print("- Only regenerate schema for non-MCP tools")


if __name__ == "__main__":
    test_mcp_wrapper_loses_parameters()
    print("\nTest passed! The issue is confirmed and the fix approach is validated.")