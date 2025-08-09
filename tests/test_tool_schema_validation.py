"""
Comprehensive test suite for tool schema validation with Responses API.

This test file validates that tool schemas are correctly formatted for OpenAI's
Responses API, particularly focusing on:
1. Required-but-nullable field contradictions
2. Missing required fields
3. Complex nullable patterns (anyOf)
4. Actual API behavior with problematic schemas
"""

import json
import os
import warnings
from typing import Any, Dict, List, Optional

import pytest
from dotenv import load_dotenv
from openai import OpenAI

from letta.llm_api.openai import (
    convert_chat_completion_to_responses_format,
    convert_responses_to_chat_completion_format,
)
from letta.llm_api.openai_client import OpenAIClient
from letta.log import get_logger
from letta.schemas.enums import MessageRole
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.openai.chat_completions import ChatCompletionRequest

# Load environment variables for API keys
load_dotenv()

logger = get_logger(__name__)


class TestToolSchemaValidation:
    """Test suite for tool schema validation issues."""

    def create_mcp_style_tool_with_nullable_required(self) -> Dict[str, Any]:
        """
        Create a tool with the MCP pattern: nullable fields marked as required.
        This pattern is found in ALL 32 MCP tools in tools.csv.
        """
        return {
            "name": "calendar_schedule",
            "description": "Create or update calendar events",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update", "cancel"],
                        "description": "Action to perform on calendar event"
                    },
                    "eventId": {
                        "type": ["string", "null"],  # Nullable
                        "description": "Event ID (required for update/cancel) or null"
                    },
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "attendees": {
                        "anyOf": [  # Complex nullable pattern
                            {"type": "array", "items": {"type": "string", "format": "email"}},
                            {"type": "null"}
                        ],
                        "description": "Attendee email addresses or null"
                    },
                    "location": {
                        "type": ["string", "null"],  # Simple nullable
                        "description": "Event location or null"
                    }
                },
                "required": ["action", "eventId", "title", "attendees", "location"],  # Problem: nullable fields in required!
                "additionalProperties": False
            }
        }

    def create_tool_missing_required_field(self) -> Dict[str, Any]:
        """
        Create a tool missing the 'required' field entirely.
        This pattern is found in 1 MCP tool: session_todo_get.
        """
        return {
            "name": "session_todo_get",
            "description": "Get current session todo list",
            "parameters": {
                "type": "object",
                "properties": {},  # Zero-arg tool
                "additionalProperties": False
                # Note: 'required' field is missing!
            }
        }

    def create_correctly_formatted_tool(self) -> Dict[str, Any]:
        """
        Create a correctly formatted tool following OpenAI conventions.
        Nullable fields are NOT in the required array.
        """
        return {
            "name": "send_message",
            "description": "Send a message to the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to send (required)"
                    },
                    "metadata": {
                        "type": ["object", "null"],
                        "description": "Optional metadata"
                    }
                },
                "required": ["message"],  # Only non-nullable fields are required
                "additionalProperties": False
            }
        }

    def create_complex_anyof_tool(self) -> Dict[str, Any]:
        """
        Create a tool with complex anyOf patterns as seen in MCP tools.
        """
        return {
            "name": "plane_sprint_management",
            "description": "Manage sprints in project management",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["create", "update", "delete"],
                        "description": "Operation to perform"
                    },
                    "sprintData": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "startDate": {"type": "string"},
                                    "endDate": {"type": "string"}
                                },
                                "required": ["name", "startDate", "endDate"]
                            },
                            {"type": "null"}
                        ],
                        "description": "Sprint data or null"
                    },
                    "selectionCriteria": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "assignee": {"type": ["string", "null"]},
                                    "priority": {"type": ["string", "null"]}
                                }
                            },
                            {"type": "null"}
                        ],
                        "description": "Selection criteria or null"
                    }
                },
                "required": ["operation", "sprintData", "selectionCriteria"],  # Problem: nullable fields required!
                "additionalProperties": False
            }
        }

    def validate_tool_schema(self, tool: Dict[str, Any]) -> List[str]:
        """
        Validate a tool schema for potential issues.
        Returns a list of issues found.
        """
        issues = []
        
        if "parameters" not in tool:
            issues.append("MISSING_PARAMETERS")
            return issues
        
        params = tool["parameters"]
        
        # Check for missing required field
        if "required" not in params:
            issues.append("MISSING_REQUIRED_FIELD")
        
        # Check for required-but-nullable contradictions
        if "properties" in params and "required" in params:
            for field_name in params["required"]:
                if field_name in params["properties"]:
                    prop = params["properties"][field_name]
                    
                    # Check if field is nullable
                    is_nullable = False
                    
                    # Check for simple nullable: type: ["string", "null"]
                    if isinstance(prop.get("type"), list) and "null" in prop["type"]:
                        is_nullable = True
                    
                    # Check for anyOf nullable pattern
                    elif "anyOf" in prop:
                        for option in prop["anyOf"]:
                            if option.get("type") == "null":
                                is_nullable = True
                                break
                    
                    if is_nullable:
                        issues.append(f"REQUIRED_BUT_NULLABLE:{field_name}")
        
        # Check for additionalProperties
        if "additionalProperties" not in params:
            issues.append("MISSING_ADDITIONAL_PROPERTIES")
        elif params["additionalProperties"] != False:
            issues.append(f"ADDITIONAL_PROPERTIES_NOT_FALSE:{params['additionalProperties']}")
        
        return issues

    def test_mcp_tool_schema_issues(self):
        """Test that MCP-style tools have the expected schema issues."""
        tool = self.create_mcp_style_tool_with_nullable_required()
        issues = self.validate_tool_schema(tool)
        
        # Verify the tool has the expected issues
        assert "REQUIRED_BUT_NULLABLE:eventId" in issues
        assert "REQUIRED_BUT_NULLABLE:attendees" in issues
        assert "REQUIRED_BUT_NULLABLE:location" in issues
        
        # Log the issues for visibility
        logger.warning(f"MCP tool schema issues found: {issues}")

    def test_missing_required_field(self):
        """Test handling of tools missing the required field."""
        tool = self.create_tool_missing_required_field()
        issues = self.validate_tool_schema(tool)
        
        assert "MISSING_REQUIRED_FIELD" in issues
        
        # Test that our code fixes this
        tool_copy = tool.copy()
        if "parameters" in tool_copy and "required" not in tool_copy["parameters"]:
            tool_copy["parameters"]["required"] = []
        
        # After fix, should not have this issue
        issues_after_fix = self.validate_tool_schema(tool_copy)
        assert "MISSING_REQUIRED_FIELD" not in issues_after_fix

    def test_correctly_formatted_tool(self):
        """Test that correctly formatted tools pass validation."""
        tool = self.create_correctly_formatted_tool()
        issues = self.validate_tool_schema(tool)
        
        # Should have no issues
        assert len(issues) == 0, f"Correctly formatted tool should have no issues, but found: {issues}"

    def test_complex_anyof_patterns(self):
        """Test tools with complex anyOf nullable patterns."""
        tool = self.create_complex_anyof_tool()
        issues = self.validate_tool_schema(tool)
        
        # Should detect nullable fields in required array
        assert "REQUIRED_BUT_NULLABLE:sprintData" in issues
        assert "REQUIRED_BUT_NULLABLE:selectionCriteria" in issues

    def fix_required_but_nullable(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fix the required-but-nullable contradiction in a tool schema.
        This is what should be added to the codebase.
        """
        tool_copy = json.loads(json.dumps(tool))  # Deep copy
        
        if "parameters" not in tool_copy:
            return tool_copy
        
        params = tool_copy["parameters"]
        
        # Add missing required field
        if "required" not in params:
            params["required"] = []
            logger.info(f"Added missing 'required' field to tool '{tool_copy.get('name')}'")
        
        # Fix required-but-nullable contradiction
        if "properties" in params and "required" in params:
            cleaned_required = []
            
            for field_name in params["required"]:
                if field_name not in params["properties"]:
                    # Field in required but not in properties - skip it
                    logger.warning(f"Field '{field_name}' in required but not in properties for tool '{tool_copy.get('name')}'")
                    continue
                
                prop = params["properties"][field_name]
                
                # Check if field is nullable
                is_nullable = False
                
                # Check for simple nullable: type: ["string", "null"]
                if isinstance(prop.get("type"), list) and "null" in prop["type"]:
                    is_nullable = True
                
                # Check for anyOf nullable pattern
                elif "anyOf" in prop:
                    for option in prop["anyOf"]:
                        if option.get("type") == "null":
                            is_nullable = True
                            break
                
                if not is_nullable:
                    cleaned_required.append(field_name)
                else:
                    logger.info(f"Removing nullable field '{field_name}' from required array in tool '{tool_copy.get('name')}'")
            
            params["required"] = cleaned_required
        
        # Ensure additionalProperties is false for strict mode
        if "additionalProperties" not in params:
            params["additionalProperties"] = False
        
        return tool_copy

    def test_fix_required_but_nullable(self):
        """Test that our fix correctly resolves schema issues."""
        # Test with MCP-style tool
        tool = self.create_mcp_style_tool_with_nullable_required()
        fixed_tool = self.fix_required_but_nullable(tool)
        
        # Validate fixed tool
        issues = self.validate_tool_schema(fixed_tool)
        
        # Should have no required-but-nullable issues
        required_but_nullable_issues = [i for i in issues if i.startswith("REQUIRED_BUT_NULLABLE")]
        assert len(required_but_nullable_issues) == 0, f"Fixed tool still has issues: {required_but_nullable_issues}"
        
        # Check that required fields are correct
        assert "action" in fixed_tool["parameters"]["required"]  # Non-nullable, should remain
        assert "title" in fixed_tool["parameters"]["required"]    # Non-nullable, should remain
        assert "eventId" not in fixed_tool["parameters"]["required"]  # Nullable, should be removed
        assert "attendees" not in fixed_tool["parameters"]["required"]  # Nullable, should be removed
        assert "location" not in fixed_tool["parameters"]["required"]  # Nullable, should be removed

    def test_responses_api_schema_validation(self):
        """
        Test that tool schemas are correctly validated and fixed for Responses API.
        """
        # Create a problematic tool (MCP-style)
        problematic_tool = self.create_mcp_style_tool_with_nullable_required()
        
        # Validate the problematic tool
        issues_before = self.validate_tool_schema(problematic_tool)
        assert "REQUIRED_BUT_NULLABLE:eventId" in issues_before
        assert "REQUIRED_BUT_NULLABLE:attendees" in issues_before
        assert "REQUIRED_BUT_NULLABLE:location" in issues_before
        
        # Fix the tool
        fixed_tool = self.fix_required_but_nullable(problematic_tool)
        
        # Validate the fixed tool
        issues_after = self.validate_tool_schema(fixed_tool)
        
        # Should have no required-but-nullable issues
        required_but_nullable_issues = [i for i in issues_after if i.startswith("REQUIRED_BUT_NULLABLE")]
        assert len(required_but_nullable_issues) == 0
        
        # Verify the fixed structure
        assert "parameters" in fixed_tool
        params = fixed_tool["parameters"]
        
        # Check required fields
        required_fields = params.get("required", [])
        
        # Non-nullable fields should be in required
        assert "action" in required_fields
        assert "title" in required_fields
        
        # Nullable fields should NOT be in required
        assert "eventId" not in required_fields
        assert "attendees" not in required_fields
        assert "location" not in required_fields
        
        # Check that additionalProperties is false for strict mode
        assert params.get("additionalProperties") == False
        
        logger.info("Successfully validated schema fixing for Responses API")

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    def test_responses_api_conversion_with_tools(self):
        """Test that tool schemas are correctly converted for Responses API."""
        # Create a chat completion request with tools
        chat_request = ChatCompletionRequest(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"}
            ],
            tools=[
                {
                    "type": "function",
                    "function": self.create_mcp_style_tool_with_nullable_required()
                }
            ],
            tool_choice="auto",
            max_completion_tokens=100
        )
        
        # Convert to Responses API format
        responses_request = convert_chat_completion_to_responses_format(chat_request)
        
        # Check that tools are properly formatted
        assert "tools" in responses_request
        assert len(responses_request["tools"]) == 1
        
        # Tool should be in the request (conversion should preserve it)
        tool = responses_request["tools"][0]
        assert tool["type"] == "function"
        assert "function" in tool
        
        # Log the converted format for inspection
        logger.info(f"Converted tool format: {json.dumps(tool, indent=2)}")

    def test_all_tool_patterns_from_csv(self):
        """
        Test validation of all problematic patterns found in tools.csv analysis.
        """
        # Pattern 1: Required-but-nullable (115 instances)
        tool1 = {
            "name": "test_tool",
            "description": "Test",
            "parameters": {
                "type": "object",
                "properties": {
                    "field1": {"type": ["string", "null"], "description": "Nullable field"},
                    "field2": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "AnyOf nullable"}
                },
                "required": ["field1", "field2"],  # Problem!
                "additionalProperties": False
            }
        }
        
        issues1 = self.validate_tool_schema(tool1)
        assert "REQUIRED_BUT_NULLABLE:field1" in issues1
        assert "REQUIRED_BUT_NULLABLE:field2" in issues1
        
        # Fix and revalidate
        fixed1 = self.fix_required_but_nullable(tool1)
        issues1_fixed = self.validate_tool_schema(fixed1)
        assert not any(i.startswith("REQUIRED_BUT_NULLABLE") for i in issues1_fixed)
        
        # Pattern 2: Missing required field (1 instance)
        tool2 = {
            "name": "test_tool2",
            "description": "Test",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
                # Missing 'required' field
            }
        }
        
        issues2 = self.validate_tool_schema(tool2)
        assert "MISSING_REQUIRED_FIELD" in issues2
        
        # Fix and revalidate
        fixed2 = self.fix_required_but_nullable(tool2)
        issues2_fixed = self.validate_tool_schema(fixed2)
        assert "MISSING_REQUIRED_FIELD" not in issues2_fixed

    def test_strict_mode_compatibility(self):
        """Test that fixed tools are compatible with Responses API strict mode."""
        tool = self.create_mcp_style_tool_with_nullable_required()
        fixed_tool = self.fix_required_but_nullable(tool)
        
        # Verify strict mode requirements
        params = fixed_tool["parameters"]
        
        # 1. Must have additionalProperties: false
        assert params.get("additionalProperties") == False
        
        # 2. Required array should only contain non-nullable fields
        for field in params.get("required", []):
            prop = params["properties"][field]
            
            # Check field is not nullable
            if isinstance(prop.get("type"), list):
                assert "null" not in prop["type"], f"Field {field} is nullable but in required array"
            
            if "anyOf" in prop:
                has_null = any(opt.get("type") == "null" for opt in prop["anyOf"])
                assert not has_null, f"Field {field} has null in anyOf but is in required array"
        
        logger.info("Fixed tool is compatible with strict mode")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])