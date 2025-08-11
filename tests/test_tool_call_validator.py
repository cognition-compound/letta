"""
Tests for the tool call validation system.

This validates that our detection system correctly identifies tool call ID mismatches
before they reach OpenAI API calls.
"""

import pytest
from unittest.mock import Mock

from letta.llm_api.tool_call_validator import (
    ToolCallValidator, 
    ValidationSeverity, 
    validate_conversation_before_api_call,
    validate_and_fix_conversation_before_api_call
)
from letta.schemas.enums import MessageRole
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.letta_message_content import TextContent


class TestToolCallValidator:
    """Test the tool call validation system."""
    
    def test_valid_conversation_passes_validation(self):
        """Test that a valid conversation with proper tool call/response pairing passes."""
        messages = [
            self._create_message(MessageRole.system, "You are a helpful assistant."),
            self._create_message(MessageRole.user, "Hello"),
            self._create_assistant_message_with_tool_call("call_123", "test_function", '{"arg": "value"}'),
            self._create_tool_response_message("call_123", "Function executed successfully")
        ]
        
        validator = ToolCallValidator()
        analysis = validator.validate_conversation(messages)
        
        assert analysis.is_valid()
        assert len(analysis.issues) == 0
        assert len(analysis.tool_calls) == 1
        assert len(analysis.tool_responses) == 1
        assert "call_123" in analysis.call_id_mapping
        assert analysis.call_id_mapping["call_123"]["call"] is not None
        assert analysis.call_id_mapping["call_123"]["response"] is not None
    
    def test_orphaned_tool_call_detected(self):
        """Test detection of tool call without corresponding response."""
        messages = [
            self._create_message(MessageRole.user, "Hello"),
            self._create_assistant_message_with_tool_call("call_orphaned", "test_function", '{"arg": "value"}'),
            # Missing tool response
        ]
        
        validator = ToolCallValidator()
        analysis = validator.validate_conversation(messages)
        
        assert not analysis.is_valid()  # Should be invalid in strict mode
        assert len(analysis.issues) == 1
        
        issue = analysis.issues[0]
        assert issue.issue_type == "orphaned_tool_call"
        assert issue.call_id == "call_orphaned"
        assert issue.severity == ValidationSeverity.CRITICAL
        assert "no corresponding tool response" in issue.description.lower()
    
    def test_orphaned_tool_response_detected(self):
        """Test detection of tool response without corresponding call."""
        messages = [
            self._create_message(MessageRole.user, "Hello"),
            # Missing assistant message with tool call
            self._create_tool_response_message("call_missing", "Function result")
        ]
        
        validator = ToolCallValidator()
        analysis = validator.validate_conversation(messages)
        
        assert not analysis.is_valid()
        assert len(analysis.issues) == 1
        
        issue = analysis.issues[0]
        assert issue.issue_type == "orphaned_tool_response"
        assert issue.call_id == "call_missing"
        assert issue.severity == ValidationSeverity.CRITICAL
        assert "no corresponding tool call" in issue.description.lower()
    
    def test_duplicate_tool_call_ids_detected(self):
        """Test detection of duplicate tool call IDs."""
        messages = [
            self._create_message(MessageRole.user, "Hello"),
            self._create_assistant_message_with_tool_call("call_duplicate", "function1", '{"arg1": "value1"}'),
            self._create_tool_response_message("call_duplicate", "Result 1"),
            self._create_assistant_message_with_tool_call("call_duplicate", "function2", '{"arg2": "value2"}'),  # Duplicate ID
            self._create_tool_response_message("call_duplicate", "Result 2")
        ]
        
        validator = ToolCallValidator()
        analysis = validator.validate_conversation(messages)
        
        assert analysis.has_warnings()
        duplicate_issues = [issue for issue in analysis.issues if issue.issue_type == "duplicate_tool_call_id"]
        assert len(duplicate_issues) == 1
        
        issue = duplicate_issues[0]
        assert issue.call_id == "call_duplicate"
        assert issue.severity == ValidationSeverity.ERROR
    
    def test_tool_response_before_call_detected(self):
        """Test detection of tool response appearing before its call."""
        messages = [
            self._create_message(MessageRole.user, "Hello"),
            self._create_tool_response_message("call_backwards", "Function result"),  # Response first
            self._create_assistant_message_with_tool_call("call_backwards", "test_function", '{"arg": "value"}'),  # Call second
        ]
        
        validator = ToolCallValidator()
        analysis = validator.validate_conversation(messages)
        
        assert analysis.has_warnings()
        ordering_issues = [issue for issue in analysis.issues if issue.issue_type == "tool_response_before_call"]
        assert len(ordering_issues) == 1
        
        issue = ordering_issues[0]
        assert issue.call_id == "call_backwards"
        assert issue.severity == ValidationSeverity.ERROR
        assert "appears before the tool call" in issue.description
    
    def test_auto_fix_removes_orphaned_responses(self):
        """Test that auto-fix removes orphaned tool responses."""
        messages = [
            self._create_message(MessageRole.user, "Hello"),
            self._create_assistant_message_with_tool_call("call_good", "test_function", '{"arg": "value"}'),
            self._create_tool_response_message("call_good", "Good result"),
            self._create_tool_response_message("call_orphaned", "Orphaned result"),  # This should be removed
        ]
        
        validator = ToolCallValidator()
        fixed_messages, analysis = validator.validate_and_fix_conversation(messages)
        
        # Should have removed the orphaned response
        assert len(fixed_messages) == 3  # One less than original
        assert all(msg.tool_call_id != "call_orphaned" for msg in fixed_messages if hasattr(msg, 'tool_call_id'))
        
        # Re-validation should show no critical issues
        assert analysis.is_valid()
    
    def test_complex_scenario_like_original_bug(self):
        """Test a complex scenario that mimics the original tool call ID bug conditions."""
        messages = [
            self._create_message(MessageRole.system, "You are a research assistant."),
            self._create_message(MessageRole.user, "Research Wolpertinger"),
            self._create_assistant_message_with_tool_call("call_research_1", "archival_memory_insert", '{"content": "Initial research"}'),
            self._create_tool_response_message("call_research_1", "Research stored"),
            self._create_message(MessageRole.assistant, "Research completed."),
            
            # This simulates the agent-to-agent message that caused issues
            self._create_message(MessageRole.system, "[Message from agent 'research-agent'] Additional findings..."),
            
            self._create_assistant_message_with_tool_call("call_research_2", "archival_memory_insert", '{"content": "Additional findings"}'),
            # What if this tool response has wrong ID? (simulating the bug)
            self._create_tool_response_message("call_WRONG_ID", "Additional research stored"),  # Wrong ID!
        ]
        
        validator = ToolCallValidator()
        analysis = validator.validate_conversation(messages)
        
        # Should detect the mismatch
        assert not analysis.is_valid()
        assert len(analysis.issues) >= 1
        
        # Should detect orphaned tool call (call_research_2) and orphaned tool response (call_WRONG_ID)
        orphaned_calls = [issue for issue in analysis.issues if issue.issue_type == "orphaned_tool_call"]
        orphaned_responses = [issue for issue in analysis.issues if issue.issue_type == "orphaned_tool_response"]
        
        assert len(orphaned_calls) == 1
        assert orphaned_calls[0].call_id == "call_research_2"
        
        assert len(orphaned_responses) == 1 
        assert orphaned_responses[0].call_id == "call_WRONG_ID"
    
    def test_convenience_functions_work(self):
        """Test that convenience functions work correctly."""
        messages = [
            self._create_message(MessageRole.user, "Hello"),
            self._create_assistant_message_with_tool_call("call_123", "test_function", '{"arg": "value"}'),
            # Missing tool response - should be detected
        ]
        
        context = {"test": True, "model": "gpt-4o-mini"}
        
        # Test validation function
        analysis = validate_conversation_before_api_call(messages, context)
        assert not analysis.is_valid()
        assert len(analysis.issues) == 1
        
        # Test validation and fix function
        fixed_messages, fixed_analysis = validate_and_fix_conversation_before_api_call(messages, context)
        # In this case, no auto-fix available for orphaned tool calls, so should be same
        assert len(fixed_messages) == len(messages)
    
    # Helper methods
    
    def _create_message(self, role: MessageRole, content: str, agent_id: str = "test-agent") -> PydanticMessage:
        """Create a simple message."""
        return PydanticMessage(
            role=role,
            content=[TextContent(text=content)],
            agent_id=agent_id
        )
    
    def _create_assistant_message_with_tool_call(
        self, 
        call_id: str, 
        function_name: str, 
        arguments: str, 
        agent_id: str = "test-agent"
    ) -> PydanticMessage:
        """Create an assistant message with a tool call."""
        message = PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text="I'll use a tool.")],
            agent_id=agent_id
        )
        
        # Add tool call data
        message.tool_calls = [Mock()]
        message.tool_calls[0].id = call_id
        message.tool_calls[0].type = "function"
        message.tool_calls[0].function = Mock()
        message.tool_calls[0].function.name = function_name
        message.tool_calls[0].function.arguments = arguments
        
        return message
    
    def _create_tool_response_message(
        self, 
        tool_call_id: str, 
        content: str, 
        agent_id: str = "test-agent"
    ) -> PydanticMessage:
        """Create a tool response message."""
        message = PydanticMessage(
            role=MessageRole.tool,
            content=[TextContent(text=content)],
            agent_id=agent_id
        )
        message.tool_call_id = tool_call_id
        return message


class TestValidationIntegration:
    """Test integration of validation with OpenAI client."""
    
    def test_validation_logs_structured_debug_data(self, caplog):
        """Test that validation logs structured debug data for analysis."""
        import logging
        caplog.set_level(logging.DEBUG)
        
        # Create a conversation with issues
        messages = [
            PydanticMessage(role=MessageRole.user, content=[TextContent(text="Hello")], agent_id="test"),
            # Orphaned tool response - this should be detected and logged
            PydanticMessage(
                role=MessageRole.tool, 
                content=[TextContent(text="Result")], 
                agent_id="test",
                tool_call_id="call_missing"
            )
        ]
        
        analysis = validate_conversation_before_api_call(
            messages, 
            {"test_context": "integration", "model": "gpt-4o-mini"}
        )
        
        # Should have detected the issue
        assert not analysis.is_valid()
        
        # Check that structured data was logged
        log_records = [record for record in caplog.records if "Tool call validation issue" in record.message]
        assert len(log_records) > 0
        
        # Should contain JSON data for debugging
        log_message = log_records[0].message
        assert "call_missing" in log_message
        assert "orphaned_tool_response" in log_message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])