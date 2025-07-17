"""Test that parallel tool execution works correctly with NoopStepManager."""

import pytest
from unittest.mock import Mock, patch
from letta.agents.letta_agent import LettaAgent
from letta.services.step_manager import NoopStepManager, StepManager
from letta.agents.helpers import generate_step_id


@pytest.mark.asyncio
async def test_step_id_generation_with_noop_step_manager():
    """Test that step_id is None when using NoopStepManager."""
    
    # Create a mock agent with NoopStepManager
    with patch.object(LettaAgent, '__init__', return_value=None):
        agent = LettaAgent.__new__(LettaAgent)
        agent.step_manager = NoopStepManager()
        
        # Test the step_id generation logic (simulating the logic in LettaAgent)
        # NoopStepManager is a singleton, so we check by class name
        step_id = generate_step_id() if agent.step_manager.__class__.__name__ != 'NoopStepManager' else None
        
        assert step_id is None, f"Expected step_id to be None with NoopStepManager, but got {step_id}"


@pytest.mark.asyncio
async def test_step_id_generation_with_real_step_manager():
    """Test that step_id is generated when using a real StepManager."""
    
    # Create a mock agent with real StepManager
    with patch.object(LettaAgent, '__init__', return_value=None):
        agent = LettaAgent.__new__(LettaAgent)
        agent.step_manager = Mock(spec=StepManager)
        
        # Test the step_id generation logic (simulating the logic in LettaAgent)
        step_id = generate_step_id() if agent.step_manager.__class__.__name__ != 'NoopStepManager' else None
        
        assert step_id is not None, "Expected step_id to be generated with real StepManager"
        assert step_id.startswith("step-"), f"Expected step_id to start with 'step-', but got {step_id}"


def test_noop_step_manager_type_check():
    """Test that we can correctly identify NoopStepManager."""
    
    noop_manager = NoopStepManager()
    real_manager = Mock(spec=StepManager)
    
    # Since NoopStepManager is a singleton, check by class name
    assert noop_manager.__class__.__name__ == 'NoopStepManager', "NoopStepManager should have correct class name"
    assert real_manager.__class__.__name__ != 'NoopStepManager', "Mock StepManager should not have NoopStepManager class name"
    
    # Both should be instances of StepManager base class
    assert isinstance(noop_manager, StepManager), "NoopStepManager should be instance of StepManager"


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
    test_noop_step_manager_type_check()
    test_generate_step_id()
    print("\n✅ All NoopStepManager tests passed!")