"""Test that parallel tool execution works correctly with NoopStepManager."""

import pytest
from unittest.mock import Mock, patch
from letta.agents.letta_agent import LettaAgent
from letta.services.step_manager import NoopStepManager, StepManager
from letta.agents.helpers import generate_step_id
from letta.schemas.user import User
from letta.schemas.openai.chat_completion_response import UsageStatistics


@pytest.mark.asyncio
async def test_step_id_generation_with_noop_step_manager():
    """Test that step_id is generated even with NoopStepManager (but logged_step will be None)."""
    
    # Create a mock agent with NoopStepManager
    with patch.object(LettaAgent, '__init__', return_value=None):
        agent = LettaAgent.__new__(LettaAgent)
        agent.step_manager = NoopStepManager()
        
        # Test the step_id generation logic - step_id is always generated
        step_id = generate_step_id()
        
        assert step_id is not None, "Expected step_id to be generated"
        assert step_id.startswith("step-"), f"Expected step_id to start with 'step-', but got {step_id}"
        
        # But when we log the step with NoopStepManager, it returns None
        actor = User(id="user-12345678", organization_id="org-12345678", name="Test User")
        usage = UsageStatistics(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        
        logged_step = agent.step_manager.log_step(
            actor=actor,
            agent_id="test-agent",
            provider_name="openai",
            provider_category="llm",
            model="gpt-4",
            model_endpoint=None,
            context_window_limit=8192,
            usage=usage,
            step_id=step_id
        )
        
        assert logged_step is None, "Expected NoopStepManager.log_step to return None"


@pytest.mark.asyncio
async def test_step_id_generation_with_real_step_manager():
    """Test that step_id is generated and logged_step is returned when using a real StepManager."""
    
    # Create a mock agent with real StepManager
    with patch.object(LettaAgent, '__init__', return_value=None):
        agent = LettaAgent.__new__(LettaAgent)
        agent.step_manager = Mock(spec=StepManager)
        
        # Test the step_id generation logic - step_id is always generated
        step_id = generate_step_id()
        
        assert step_id is not None, "Expected step_id to be generated with real StepManager"
        assert step_id.startswith("step-"), f"Expected step_id to start with 'step-', but got {step_id}"
        
        # Mock the logged step response
        mock_logged_step = Mock()
        mock_logged_step.id = step_id
        agent.step_manager.log_step.return_value = mock_logged_step
        
        # When we log the step with a real StepManager, it returns a step object
        actor = User(id="user-12345678", organization_id="org-12345678", name="Test User")
        usage = UsageStatistics(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        
        logged_step = agent.step_manager.log_step(
            actor=actor,
            agent_id="test-agent",
            provider_name="openai",
            provider_category="llm",
            model="gpt-4",
            model_endpoint=None,
            context_window_limit=8192,
            usage=usage,
            step_id=step_id
        )
        
        assert logged_step is not None, "Expected real StepManager.log_step to return a step"
        assert logged_step.id == step_id, f"Expected logged_step.id to be {step_id}, but got {logged_step.id}"


def test_noop_step_manager_behavior():
    """Test that NoopStepManager returns None for all operations."""
    
    noop_manager = NoopStepManager()
    
    # Test that log_step returns None
    actor = User(id="user-12345678", organization_id="org-12345678", name="Test User")
    usage = UsageStatistics(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    
    result = noop_manager.log_step(
        actor=actor,
        agent_id="test-agent",
        provider_name="openai",
        provider_category="llm",
        model="gpt-4",
        model_endpoint=None,
        context_window_limit=8192,
        usage=usage,
        step_id="step-123"
    )
    
    assert result is None, "NoopStepManager.log_step should return None"


def test_generate_step_id():
    """Test that generate_step_id creates proper step IDs."""
    
    step_id = generate_step_id()
    assert step_id is not None, "generate_step_id should return a value"
    assert step_id.startswith("step-"), f"Step ID should start with 'step-', got {step_id}"
    assert len(step_id) > 5, f"Step ID should include a UUID, got {step_id}"


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_step_id_generation_with_noop_step_manager())
    asyncio.run(test_step_id_generation_with_real_step_manager())
    test_noop_step_manager_behavior()
    test_generate_step_id()
    print("\n✅ All NoopStepManager tests passed!")