"""
Test integration of tool call validation with OpenAI client.

This ensures that the validation system runs before every OpenAI API call
and properly logs debug information for tool call ID mismatches.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.enums import MessageRole
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.letta_message_content import TextContent


class TestOpenAIClientValidationIntegration:
    """Test that OpenAI client integrates validation before API calls."""
    
    @pytest.fixture
    def openai_client(self):
        """Create OpenAI client with mock actor."""
        client = OpenAIClient()
        client.actor = Mock()
        client.actor.id = "test-integration"
        return client
    
    @pytest.fixture
    def llm_config(self):
        """Create LLM config for testing."""
        return LLMConfig(
            model="gpt-4o-mini",
            model_endpoint_type="openai",
            model_endpoint="https://api.openai.com/v1",
            context_window=128000,
            max_tokens=100
        )
    
    def test_build_request_data_runs_validation(self, openai_client, llm_config, caplog):
        """Test that build_request_data runs tool call validation."""
        import logging
        caplog.set_level(logging.INFO)
        
        # Create messages with valid tool call/response pairing
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="You are a helpful assistant.")],
                agent_id="test-agent"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="test-agent"
            )
        ]
        
        # This should trigger validation
        request_data = openai_client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=None
        )
        
        # Verify validation ran by checking log output
        validation_logs = [record for record in caplog.records if "Tool call validation" in record.message]
        assert len(validation_logs) > 0
        
        # Should log that no issues were found
        summary_log = validation_logs[0]
        assert "0 calls, 0 responses, 0 issues" in summary_log.message
        
        # Request should still be built successfully
        assert "input" in request_data
        assert request_data["model"] == "gpt-4o-mini"
    
    def test_validation_detects_issues_in_build_request_data(self, openai_client, llm_config, caplog):
        """Test that validation detects and logs issues during build_request_data."""
        import logging
        caplog.set_level(logging.DEBUG)  # Capture all logs
        
        # Create messages with tool call ID mismatch (orphaned tool response)
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Hello")],
                agent_id="test-agent"
            ),
            # Orphaned tool response - this should be detected
            PydanticMessage(
                role=MessageRole.tool,
                content=[TextContent(text="Function result")],
                tool_call_id="call_orphaned_12345",
                agent_id="test-agent"
            )
        ]
        
        # This should trigger validation and detect the issue
        request_data = openai_client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=[{
                "name": "test_function", 
                "description": "A test function for validation",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }]
        )
        
        # Should have logged the validation issue (at ERROR level for orphaned responses)
        validation_logs = [record for record in caplog.records 
                          if "Tool call validation issue" in record.message]
        assert len(validation_logs) > 0
        
        # Should mention the orphaned tool response
        log_messages = " ".join([record.message for record in validation_logs])
        assert "call_orphaned_12345" in log_messages
        assert "orphaned_tool_response" in log_messages
        
        # Request should still be built (validation doesn't block)
        assert "input" in request_data
    
    def test_validation_context_includes_model_and_actor_info(self, openai_client, llm_config, caplog):
        """Test that validation context includes useful debugging information."""
        import logging
        caplog.set_level(logging.DEBUG)  # Need debug level for detailed mapping
        
        messages = [
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="Test message")],
                agent_id="test-agent"
            )
        ]
        
        tools = [
            {"name": "test_tool_1", "description": "First test tool", "parameters": {"type": "object", "properties": {}, "required": []}},
            {"name": "test_tool_2", "description": "Second test tool", "parameters": {"type": "object", "properties": {}, "required": []}},
        ]
        
        openai_client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=tools
        )
        
        # Find validation logs (INFO for summary, DEBUG for detailed mapping)
        validation_logs = [record for record in caplog.records if "Tool call validation" in record.message]
        assert len(validation_logs) > 0
        
        # Check that context information is captured somewhere in the logs
        all_log_text = " ".join([record.message for record in caplog.records])
        assert "gpt-4o-mini" in all_log_text or "test-integration" in all_log_text
        
        # The validation system should log useful context for debugging
    
    @patch('letta.llm_api.openai_client.validate_and_fix_conversation_before_api_call')
    def test_validation_auto_fix_is_used(self, mock_validate_fix, openai_client, llm_config):
        """Test that auto-fix functionality is used when available."""
        # Mock the validation to return fixed messages
        original_messages = [
            PydanticMessage(role=MessageRole.user, content=[TextContent(text="Hello")], agent_id="test")
        ]
        
        fixed_messages = [
            PydanticMessage(role=MessageRole.user, content=[TextContent(text="Hello (fixed)")], agent_id="test")
        ]
        
        mock_analysis = Mock()
        mock_analysis.is_valid.return_value = True
        mock_analysis.has_warnings.return_value = False
        
        mock_validate_fix.return_value = (fixed_messages, mock_analysis)
        
        request_data = openai_client.build_request_data(
            messages=original_messages,
            llm_config=llm_config
        )
        
        # Should have called validation
        mock_validate_fix.assert_called_once()
        
        # Should have used the fixed messages (indirectly verified by successful build)
        assert "input" in request_data
    
    def test_validation_preserves_original_behavior_when_no_issues(self, openai_client, llm_config):
        """Test that validation doesn't interfere with normal operation when no issues are found."""
        messages = [
            PydanticMessage(
                role=MessageRole.system,
                content=[TextContent(text="System prompt")],
                agent_id="test-agent"
            ),
            PydanticMessage(
                role=MessageRole.user,
                content=[TextContent(text="User message")],
                agent_id="test-agent"
            )
        ]
        
        # Should work exactly as before when no validation issues
        request_data = openai_client.build_request_data(
            messages=messages,
            llm_config=llm_config
        )
        
        # Verify normal request structure
        assert "input" in request_data
        assert "model" in request_data
        assert request_data["model"] == "gpt-4o-mini"
        assert len(request_data["input"]) == 2
        
        # Verify messages are properly converted
        assert request_data["input"][0]["type"] == "message"
        assert request_data["input"][0]["role"] == "system"
        assert request_data["input"][1]["role"] == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])