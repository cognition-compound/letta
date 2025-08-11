"""
Tool Call ID Validation System

Validates conversation structure before sending to OpenAI to detect tool call ID mismatches
that cause "No tool call found for function call output with call_id XXX" errors.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from enum import Enum

from letta.log import get_logger
from letta.schemas.message import Message as PydanticMessage
from letta.schemas.enums import MessageRole

logger = get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ToolCallInfo:
    """Information about a tool call."""
    call_id: str
    function_name: str
    arguments: str
    message_index: int
    message_role: MessageRole
    agent_id: Optional[str] = None


@dataclass
class ToolResponseInfo:
    """Information about a tool response."""
    call_id: str
    content: str
    message_index: int
    message_role: MessageRole
    agent_id: Optional[str] = None


@dataclass
class ValidationIssue:
    """A validation issue found in the conversation."""
    severity: ValidationSeverity
    issue_type: str
    description: str
    call_id: Optional[str] = None
    message_indices: List[int] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationAnalysis:
    """Analysis of conversation structure and tool call mappings."""
    total_messages: int
    tool_calls: List[ToolCallInfo]
    tool_responses: List[ToolResponseInfo]
    issues: List[ValidationIssue]
    call_id_mapping: Dict[str, Dict[str, Any]]  # call_id -> {call: ToolCallInfo, response: ToolResponseInfo}
    
    def is_valid(self) -> bool:
        """Check if conversation has critical or error validation issues."""
        return not any(issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR] for issue in self.issues)
    
    def has_warnings(self) -> bool:
        """Check if conversation has warnings or errors."""
        return any(issue.severity in [ValidationSeverity.WARNING, ValidationSeverity.ERROR] for issue in self.issues)


class ToolCallValidator:
    """Validates tool call ID consistency in conversations before OpenAI API calls."""
    
    def __init__(self, strict_mode: bool = True):
        """
        Initialize validator.
        
        Args:
            strict_mode: If True, treat mismatches as critical errors. If False, only warn.
        """
        self.strict_mode = strict_mode
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")
    
    def validate_conversation(self, messages: List[PydanticMessage], context: Optional[Dict[str, Any]] = None) -> ConversationAnalysis:
        """
        Validate tool call ID consistency in a conversation.
        
        Args:
            messages: List of conversation messages
            context: Optional context for debugging (agent_id, source, etc.)
            
        Returns:
            ConversationAnalysis with validation results
        """
        analysis = ConversationAnalysis(
            total_messages=len(messages),
            tool_calls=[],
            tool_responses=[],
            issues=[],
            call_id_mapping={}
        )
        
        # Extract tool calls and responses
        self._extract_tool_calls_and_responses(messages, analysis)
        
        # Build call ID mapping
        self._build_call_id_mapping(analysis)
        
        # Validate consistency
        self._validate_tool_call_consistency(analysis, context or {})
        
        # Log results
        self._log_validation_results(analysis, context)
        
        return analysis
    
    def _extract_tool_calls_and_responses(self, messages: List[PydanticMessage], analysis: ConversationAnalysis) -> None:
        """Extract tool calls and responses from messages."""
        for i, message in enumerate(messages):
            # Extract tool calls from assistant messages
            if message.role == MessageRole.assistant and hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    if hasattr(tool_call, 'id') and hasattr(tool_call, 'function'):
                        call_info = ToolCallInfo(
                            call_id=tool_call.id,
                            function_name=tool_call.function.name,
                            arguments=tool_call.function.arguments,
                            message_index=i,
                            message_role=message.role,
                            agent_id=getattr(message, 'agent_id', None)
                        )
                        analysis.tool_calls.append(call_info)
            
            # Extract tool responses from tool messages
            elif message.role == MessageRole.tool and hasattr(message, 'tool_call_id'):
                # Extract text content properly
                content_text = ""
                if message.content:
                    if isinstance(message.content, str):
                        content_text = message.content
                    elif isinstance(message.content, list):
                        # Extract text from content items
                        content_parts = []
                        for item in message.content:
                            if hasattr(item, 'text'):
                                content_parts.append(item.text)
                            else:
                                content_parts.append(str(item))
                        content_text = " ".join(content_parts)
                    else:
                        content_text = str(message.content)
                
                response_info = ToolResponseInfo(
                    call_id=message.tool_call_id,
                    content=content_text,
                    message_index=i,
                    message_role=message.role,
                    agent_id=getattr(message, 'agent_id', None)
                )
                analysis.tool_responses.append(response_info)
    
    def _build_call_id_mapping(self, analysis: ConversationAnalysis) -> None:
        """Build mapping of tool call IDs to their calls and responses."""
        # Initialize mapping with tool calls
        for call in analysis.tool_calls:
            if call.call_id not in analysis.call_id_mapping:
                analysis.call_id_mapping[call.call_id] = {"call": None, "response": None}
            analysis.call_id_mapping[call.call_id]["call"] = call
        
        # Add tool responses
        for response in analysis.tool_responses:
            if response.call_id not in analysis.call_id_mapping:
                analysis.call_id_mapping[response.call_id] = {"call": None, "response": None}
            analysis.call_id_mapping[response.call_id]["response"] = response
    
    def _validate_tool_call_consistency(self, analysis: ConversationAnalysis, context: Dict[str, Any]) -> None:
        """Validate that tool calls and responses are properly matched."""
        
        # Check for orphaned tool calls (calls without responses)
        orphaned_calls = []
        for call_id, mapping in analysis.call_id_mapping.items():
            if mapping["call"] and not mapping["response"]:
                orphaned_calls.append(mapping["call"])
        
        if orphaned_calls:
            severity = ValidationSeverity.CRITICAL if self.strict_mode else ValidationSeverity.ERROR
            for call in orphaned_calls:
                issue = ValidationIssue(
                    severity=severity,
                    issue_type="orphaned_tool_call",
                    description=f"Tool call '{call.call_id}' for function '{call.function_name}' has no corresponding tool response",
                    call_id=call.call_id,
                    message_indices=[call.message_index],
                    context={
                        "function_name": call.function_name,
                        "arguments": call.arguments,
                        "agent_id": call.agent_id,
                        **context
                    }
                )
                analysis.issues.append(issue)
        
        # Check for orphaned tool responses (responses without calls)
        orphaned_responses = []
        for call_id, mapping in analysis.call_id_mapping.items():
            if mapping["response"] and not mapping["call"]:
                orphaned_responses.append(mapping["response"])
        
        if orphaned_responses:
            severity = ValidationSeverity.CRITICAL if self.strict_mode else ValidationSeverity.ERROR
            for response in orphaned_responses:
                issue = ValidationIssue(
                    severity=severity,
                    issue_type="orphaned_tool_response",
                    description=f"Tool response with call_id '{response.call_id}' has no corresponding tool call",
                    call_id=response.call_id,
                    message_indices=[response.message_index],
                    context={
                        "content_preview": response.content[:100] + "..." if len(response.content) > 100 else response.content,
                        "agent_id": response.agent_id,
                        **context
                    }
                )
                analysis.issues.append(issue)
        
        # Check for duplicate tool call IDs
        call_ids_seen = {}
        for call in analysis.tool_calls:
            if call.call_id in call_ids_seen:
                issue = ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    issue_type="duplicate_tool_call_id",
                    description=f"Duplicate tool call ID '{call.call_id}' found",
                    call_id=call.call_id,
                    message_indices=[call_ids_seen[call.call_id], call.message_index],
                    context={
                        "function_names": [call_ids_seen[call.call_id], call.function_name],
                        **context
                    }
                )
                analysis.issues.append(issue)
            else:
                call_ids_seen[call.call_id] = call.message_index
        
        # Check for proper ordering (tool calls should come before their responses)
        for call_id, mapping in analysis.call_id_mapping.items():
            call_info = mapping.get("call")
            response_info = mapping.get("response")
            
            if call_info and response_info:
                if response_info.message_index <= call_info.message_index:
                    issue = ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        issue_type="tool_response_before_call",
                        description=f"Tool response for call_id '{call_id}' appears before the tool call",
                        call_id=call_id,
                        message_indices=[call_info.message_index, response_info.message_index],
                        context={
                            "function_name": call_info.function_name,
                            **context
                        }
                    )
                    analysis.issues.append(issue)
    
    def _log_validation_results(self, analysis: ConversationAnalysis, context: Optional[Dict[str, Any]]) -> None:
        """Log detailed validation results."""
        
        # Always log summary
        context_str = f" (context: {context})" if context else ""
        self.logger.info(f"Tool call validation{context_str}: {len(analysis.tool_calls)} calls, {len(analysis.tool_responses)} responses, {len(analysis.issues)} issues")
        
        # Log detailed mapping for debugging
        if analysis.tool_calls or analysis.tool_responses:
            mapping_data = {
                "tool_call_mapping": {
                    call_id: {
                        "has_call": mapping["call"] is not None,
                        "has_response": mapping["response"] is not None,
                        "call_function": mapping["call"].function_name if mapping["call"] else None,
                        "call_message_idx": mapping["call"].message_index if mapping["call"] else None,
                        "response_message_idx": mapping["response"].message_index if mapping["response"] else None,
                    }
                    for call_id, mapping in analysis.call_id_mapping.items()
                },
                "context": context
            }
            self.logger.debug(f"Tool call mapping details: {json.dumps(mapping_data, indent=2)}")
        
        # Log issues by severity
        for issue in analysis.issues:
            log_method = getattr(self.logger, issue.severity.value)
            issue_data = {
                "issue_type": issue.issue_type,
                "call_id": issue.call_id,
                "message_indices": issue.message_indices,
                "context": issue.context
            }
            log_method(f"Tool call validation issue: {issue.description} | Data: {json.dumps(issue_data)}")
    
    def validate_and_fix_conversation(self, messages: List[PydanticMessage], context: Optional[Dict[str, Any]] = None) -> tuple[List[PydanticMessage], ConversationAnalysis]:
        """
        Validate conversation and attempt to fix common issues.
        
        Args:
            messages: List of conversation messages
            context: Optional context for debugging
            
        Returns:
            Tuple of (potentially_fixed_messages, analysis)
        """
        analysis = self.validate_conversation(messages, context)
        
        if not analysis.issues:
            return messages, analysis
        
        # Create a copy for potential fixes
        fixed_messages = messages.copy()
        fixes_applied = []
        
        # Attempt to fix orphaned tool responses by removing them
        for issue in analysis.issues:
            if issue.issue_type == "orphaned_tool_response" and issue.message_indices:
                msg_idx = issue.message_indices[0]
                if 0 <= msg_idx < len(fixed_messages):
                    removed_msg = fixed_messages.pop(msg_idx)
                    fixes_applied.append(f"Removed orphaned tool response at index {msg_idx} with call_id {issue.call_id}")
                    self.logger.warning(f"Auto-fixed: Removed orphaned tool response with call_id {issue.call_id}")
        
        # Log fixes applied
        if fixes_applied:
            self.logger.info(f"Applied {len(fixes_applied)} auto-fixes: {fixes_applied}")
            
            # Re-validate after fixes
            fixed_analysis = self.validate_conversation(fixed_messages, {**(context or {}), "auto_fixed": True})
            return fixed_messages, fixed_analysis
        
        return messages, analysis


# Global validator instance
_default_validator = ToolCallValidator(strict_mode=False)  # Default to warnings, not critical errors


def validate_conversation_before_api_call(messages: List[PydanticMessage], context: Optional[Dict[str, Any]] = None) -> ConversationAnalysis:
    """
    Convenience function to validate conversation before OpenAI API calls.
    
    Args:
        messages: Conversation messages
        context: Optional context (model, agent_id, etc.)
        
    Returns:
        ConversationAnalysis with validation results
    """
    return _default_validator.validate_conversation(messages, context)


def validate_and_fix_conversation_before_api_call(messages: List[PydanticMessage], context: Optional[Dict[str, Any]] = None) -> tuple[List[PydanticMessage], ConversationAnalysis]:
    """
    Convenience function to validate and potentially fix conversation before OpenAI API calls.
    
    Args:
        messages: Conversation messages
        context: Optional context (model, agent_id, etc.)
        
    Returns:
        Tuple of (potentially_fixed_messages, analysis)
    """
    return _default_validator.validate_and_fix_conversation(messages, context)