"""
Workflow state tracking utilities for multi-agent and multi-step processes.
Helps correlate business events across complex agent workflows.
"""
import contextvars
from typing import Dict, Any, Optional
from letta.log import get_logger

logger = get_logger(__name__)

# Context variables for correlation tracking
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('request_id', default=None)
workflow_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('workflow_id', default=None)


class WorkflowTracker:
    """Utility class for tracking multi-step workflow states."""
    
    @staticmethod
    def get_correlation_context() -> Dict[str, Any]:
        """Get current correlation IDs for logging."""
        return {
            "correlation_id": request_id_var.get(),
            "workflow_id": workflow_id_var.get()
        }
    
    @staticmethod
    def log_workflow_checkpoint(
        checkpoint_name: str,
        agent_id: str,
        step_number: int,
        max_steps: int,
        additional_context: Optional[Dict[str, Any]] = None
    ):
        """Log a workflow checkpoint for multi-step processes."""
        context = WorkflowTracker.get_correlation_context()
        if additional_context:
            context.update(additional_context)
            
        logger.info("Workflow checkpoint reached", extra={
            "event": "workflow_checkpoint",
            "checkpoint_name": checkpoint_name,
            "agent_id": agent_id,
            "step_number": step_number,
            "max_steps": max_steps,
            "progress_percentage": round((step_number / max_steps) * 100, 1) if max_steps > 0 else 0,
            **context
        })
    
    @staticmethod
    def log_workflow_transition(
        from_state: str,
        to_state: str,
        agent_id: str,
        trigger: str,
        additional_context: Optional[Dict[str, Any]] = None
    ):
        """Log transitions between workflow states."""
        context = WorkflowTracker.get_correlation_context()
        if additional_context:
            context.update(additional_context)
            
        logger.info("Workflow state transition", extra={
            "event": "workflow_transition",
            "from_state": from_state,
            "to_state": to_state,
            "agent_id": agent_id,
            "transition_trigger": trigger,
            **context
        })
    
    @staticmethod
    def log_multi_agent_coordination(
        coordinator_agent_id: str,
        participant_agent_ids: list[str],
        coordination_type: str,
        message_summary: str,
        additional_context: Optional[Dict[str, Any]] = None
    ):
        """Log multi-agent coordination events."""
        context = WorkflowTracker.get_correlation_context()
        if additional_context:
            context.update(additional_context)
            
        logger.info("Multi-agent coordination", extra={
            "event": "multi_agent_coordination",
            "coordinator_agent_id": coordinator_agent_id,
            "participant_agent_ids": participant_agent_ids,
            "participant_count": len(participant_agent_ids),
            "coordination_type": coordination_type,
            "message_summary": message_summary,
            **context
        })
    
    @staticmethod
    def set_correlation_context(request_id: str, workflow_id: str):
        """Set correlation context for current execution context."""
        request_id_var.set(request_id)
        workflow_id_var.set(workflow_id)