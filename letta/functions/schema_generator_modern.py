"""Modern schema generator using OpenAI's official agents library.

This replaces the 700-line amateur implementation with a professional solution.
"""

from typing import Optional, Callable, Any
import inspect
import logging

# We need to import from the openai-agents package, but there's a naming conflict
# with our local letta.agents module. We'll use importlib to get the right module.
import importlib.util

# We need to avoid importing our local letta.agents module
# So we temporarily manipulate sys.path to get the right agents module
import sys
_original_path = sys.path.copy()
try:
    # Remove the current directory from path to avoid importing local agents
    sys.path = [p for p in sys.path if not p.endswith('/letta')]
    
    # Now import the openai-agents package
    import agents as agents_module
    function_schema = agents_module.function_schema.function_schema
    FuncSchema = agents_module.function_schema.FuncSchema
finally:
    # Restore original path
    sys.path = _original_path

logger = logging.getLogger(__name__)


def generate_schema_modern(
    function: Callable[..., Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
    tool_id: Optional[str] = None
) -> dict:
    """Generate OpenAI function schema using the official agents library.
    
    This is a drop-in replacement for the old generate_schema() function
    that uses OpenAI's professional implementation instead of our
    700-line amateur code.
    
    Args:
        function: The function to generate schema for
        name: Optional name override (defaults to function.__name__)
        description: Optional description override (defaults to docstring)
        tool_id: Optional tool ID for logging
        
    Returns:
        OpenAI-compatible function schema dictionary with strict mode enabled
    """
    try:
        # Generate the function schema using OpenAI's library
        schema: FuncSchema = function_schema(
            func=function,
            docstring_style='google',  # Letta uses Google style (literal string)
            name_override=name,
            description_override=description,
            use_docstring_info=True,
            strict_json_schema=True,  # Always use strict mode
        )
        
        # Convert to OpenAI function format
        openai_schema = {
            "name": schema.name,
            "description": schema.description or "No description available",
            "parameters": schema.params_json_schema,
            "strict": True,  # Ensure strict mode is set
        }
        
        # Ensure all parameters are in the required array for strict mode
        # This is critical for OpenAI's strict mode compliance
        if "properties" in openai_schema["parameters"]:
            all_params = list(openai_schema["parameters"]["properties"].keys())
            openai_schema["parameters"]["required"] = all_params
            openai_schema["parameters"]["additionalProperties"] = False
        
        # Filter out 'self' and 'agent_state' parameters if present
        # These are internal parameters that shouldn't be exposed to the LLM
        if "properties" in openai_schema["parameters"]:
            properties = openai_schema["parameters"]["properties"]
            required = openai_schema["parameters"].get("required", [])
            
            # Remove internal parameters
            for internal_param in ["self", "agent_state"]:
                if internal_param in properties:
                    del properties[internal_param]
                if internal_param in required:
                    required.remove(internal_param)
            
            openai_schema["parameters"]["required"] = required
        
        logger.debug(
            f"Generated schema for function '{function.__name__}' "
            f"{'(tool_id=' + tool_id + ') ' if tool_id else ''}"
            f"using OpenAI agents library"
        )
        
        return openai_schema
        
    except Exception as e:
        logger.error(
            f"Failed to generate schema for function '{function.__name__}' "
            f"{'(tool_id=' + tool_id + ') ' if tool_id else ''}: {e}"
        )
        # Fall back to basic schema if OpenAI library fails
        return {
            "name": name or function.__name__,
            "description": description or function.__doc__ or "No description available",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        }


def generate_schema(
    function: Callable[..., Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
    tool_id: Optional[str] = None
) -> dict:
    """Compatibility wrapper for the old generate_schema function.
    
    This maintains backwards compatibility while using the modern implementation.
    """
    return generate_schema_modern(
        function=function,
        name=name,
        description=description,
        tool_id=tool_id
    )


# Additional helper functions for specific schema types

def generate_tool_schema_for_mcp(
    mcp_tool,
    append_heartbeat: bool = True,
    strict: bool = True,
) -> dict:
    """Generate schema for MCP tools.
    
    MCP tools already have their schema defined, so we just need to
    ensure it's in the right format with strict mode enabled.
    """
    parameters_schema = mcp_tool.inputSchema.copy()
    
    # Ensure all required fields for strict mode
    parameters_schema.setdefault("required", [])
    parameters_schema["additionalProperties"] = False
    
    # Make all properties required for strict mode
    if "properties" in parameters_schema:
        parameters_schema["required"] = list(parameters_schema["properties"].keys())
    
    # Add heartbeat parameter if requested
    if append_heartbeat:
        from letta.constants import REQUEST_HEARTBEAT_PARAM, REQUEST_HEARTBEAT_DESCRIPTION
        parameters_schema["properties"][REQUEST_HEARTBEAT_PARAM] = {
            "type": "boolean",
            "description": REQUEST_HEARTBEAT_DESCRIPTION,
        }
        parameters_schema["required"].append(REQUEST_HEARTBEAT_PARAM)
    
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description,
        "parameters": parameters_schema,
        "strict": strict,
    }


def generate_tool_schema_for_composio(
    parameters_model,
    name: str,
    description: str,
    append_heartbeat: bool = True,
    strict: bool = True,
) -> dict:
    """Generate schema for Composio tools.
    
    Composio tools have their own parameter model format that we need
    to convert to OpenAI's format.
    """
    properties_json = {}
    required_fields = []
    
    # Extract properties from the ActionParametersModel
    for field_name, field_props in parameters_model.properties.items():
        property_schema = {
            "type": field_props["type"],
            "description": field_props.get("description", ""),
        }
        
        if "default" in field_props:
            property_schema["default"] = field_props["default"]
        if "enum" in field_props:
            property_schema["enum"] = field_props["enum"]
        if field_props["type"] == "array" and "items" in field_props:
            property_schema["items"] = field_props["items"]
        
        properties_json[field_name] = property_schema
        # For strict mode, all parameters must be required
        required_fields.append(field_name)
    
    # Add heartbeat parameter if requested
    if append_heartbeat:
        from letta.constants import REQUEST_HEARTBEAT_PARAM, REQUEST_HEARTBEAT_DESCRIPTION
        properties_json[REQUEST_HEARTBEAT_PARAM] = {
            "type": "boolean",
            "description": REQUEST_HEARTBEAT_DESCRIPTION,
        }
        required_fields.append(REQUEST_HEARTBEAT_PARAM)
    
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties_json,
            "required": required_fields,
            "additionalProperties": False,
        },
        "strict": strict,
    }