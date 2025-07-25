"""
Test for sleeptime agent block attachment race condition fix.

This test verifies that the race condition in attach_block_async() has been fixed
by simulating concurrent block attachment attempts to sleeptime agents.
"""

import asyncio
import pytest
from sqlalchemy.exc import IntegrityError
from letta.orm.errors import UniqueConstraintViolationError
from letta.services.agent_manager import AgentManager
from letta.schemas.agent import CreateAgent
from letta.schemas.block import CreateBlock
from letta.orm.enums import AgentType, ManagerType
from letta.schemas.user import User as PydanticUser


class TestSleeptimeBlockRaceCondition:
    """Test race condition fixes for sleeptime agent block attachment."""

    @pytest.fixture
    def agent_manager(self):
        """Get AgentManager instance."""
        return AgentManager()
    
    @pytest.fixture 
    def test_user(self):
        """Create test user."""
        return PydanticUser(id="test-user", name="Test User")

    @pytest.fixture
    async def sleeptime_agent_pair(self, agent_manager, test_user):
        """Create a main agent with sleeptime enabled."""
        # Create main agent with sleeptime enabled
        main_agent_request = CreateAgent(
            name="test-main-agent",
            agent_type=AgentType.main_agent,
            enable_sleeptime=True,
            memory_blocks=[
                {"label": "human", "value": "Test human info", "limit": 1000},
                {"label": "persona", "value": "Test persona info", "limit": 1000}
            ]
        )
        
        main_agent = await agent_manager.create_agent_async(main_agent_request, test_user)
        
        # The sleeptime agent should be automatically created
        # Find it by checking the multi_agent_group
        group = main_agent.multi_agent_group
        sleeptime_agent_id = None
        
        if group and group.manager_type == ManagerType.sleeptime:
            for agent_id in group.agent_ids or []:
                if agent_id != main_agent.id:
                    try:
                        sleeptime_agent = await agent_manager.get_agent_async(agent_id, test_user)
                        if sleeptime_agent.agent_type == AgentType.sleeptime_agent:
                            sleeptime_agent_id = agent_id
                            break
                    except:
                        continue
        
        return main_agent.id, sleeptime_agent_id

    @pytest.fixture
    async def test_block(self, agent_manager, test_user):
        """Create a test block for attachment."""
        block_request = CreateBlock(
            label="test_registry",
            value="Test registry block for race condition testing",
            limit=1000
        )
        
        block = await agent_manager.create_block_async(block_request, test_user)
        return block.id

    @pytest.mark.asyncio
    async def test_concurrent_block_attachment_no_race_condition(self, agent_manager, test_user, sleeptime_agent_pair, test_block):
        """Test that concurrent block attachments don't cause race conditions."""
        main_agent_id, sleeptime_agent_id = sleeptime_agent_pair
        block_id = test_block
        
        # Create multiple concurrent attachment tasks
        num_concurrent_tasks = 5
        tasks = []
        
        async def attach_block_task():
            """Task that attempts to attach the same block."""
            try:
                result = await agent_manager.attach_block_async(main_agent_id, block_id, test_user)
                return {"success": True, "result": result}
            except (IntegrityError, UniqueConstraintViolationError) as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": f"Unexpected error: {str(e)}"}
        
        # Launch concurrent tasks
        for _ in range(num_concurrent_tasks):
            tasks.append(attach_block_task())
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successful_attachments = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
        failed_attachments = sum(1 for r in results if isinstance(r, dict) and not r.get("success", False))
        exceptions = sum(1 for r in results if not isinstance(r, dict))
        
        # All tasks should complete successfully (either by attaching or gracefully handling duplicates)
        assert exceptions == 0, f"Unexpected exceptions occurred: {[r for r in results if not isinstance(r, dict)]}"
        assert successful_attachments > 0, "At least one attachment should succeed"
        
        # Verify the block is actually attached to both agents
        main_agent = await agent_manager.get_agent_async(main_agent_id, test_user)
        block_labels = [block.label for block in main_agent.memory.blocks]
        assert "test_registry" in block_labels, "Block should be attached to main agent"
        
        if sleeptime_agent_id:
            sleeptime_agent = await agent_manager.get_agent_async(sleeptime_agent_id, test_user)
            sleeptime_block_labels = [block.label for block in sleeptime_agent.memory.blocks]
            assert "test_registry" in sleeptime_block_labels, "Block should be attached to sleeptime agent"

    @pytest.mark.asyncio
    async def test_atomic_transaction_rollback(self, agent_manager, test_user, sleeptime_agent_pair, test_block):
        """Test that failed transactions are properly rolled back."""
        main_agent_id, sleeptime_agent_id = sleeptime_agent_pair
        block_id = test_block
        
        # First, successfully attach the block
        result = await agent_manager.attach_block_async(main_agent_id, block_id, test_user)
        assert result is not None
        
        # Try to attach the same block again - should handle gracefully
        result2 = await agent_manager.attach_block_async(main_agent_id, block_id, test_user)
        assert result2 is not None
        
        # Verify state is consistent
        main_agent = await agent_manager.get_agent_async(main_agent_id, test_user)
        block_count = sum(1 for block in main_agent.memory.blocks if block.label == "test_registry")
        assert block_count == 1, "Block should only be attached once despite multiple attempts"

    @pytest.mark.asyncio
    async def test_sleeptime_group_propagation(self, agent_manager, test_user, sleeptime_agent_pair, test_block):
        """Test that blocks are properly propagated to sleeptime agents."""
        main_agent_id, sleeptime_agent_id = sleeptime_agent_pair
        block_id = test_block
        
        if not sleeptime_agent_id:
            pytest.skip("No sleeptime agent found in the group")
        
        # Attach block to main agent
        await agent_manager.attach_block_async(main_agent_id, block_id, test_user)
        
        # Verify block is attached to both agents
        main_agent = await agent_manager.get_agent_async(main_agent_id, test_user)
        sleeptime_agent = await agent_manager.get_agent_async(sleeptime_agent_id, test_user)
        
        main_labels = [block.label for block in main_agent.memory.blocks]
        sleeptime_labels = [block.label for block in sleeptime_agent.memory.blocks]
        
        assert "test_registry" in main_labels, "Block should be attached to main agent"
        assert "test_registry" in sleeptime_labels, "Block should be propagated to sleeptime agent"
        
        # Verify they have the same block instance (same ID)
        main_block = next(block for block in main_agent.memory.blocks if block.label == "test_registry")
        sleeptime_block = next(block for block in sleeptime_agent.memory.blocks if block.label == "test_registry")
        
        assert main_block.id == sleeptime_block.id, "Both agents should reference the same block"

    @pytest.mark.asyncio
    async def test_error_handling_for_missing_agents(self, agent_manager, test_user, test_block):
        """Test error handling when sleeptime agents are missing."""
        # Create a main agent without sleeptime (no group)
        main_agent_request = CreateAgent(
            name="test-standalone-agent",
            agent_type=AgentType.main_agent,
            enable_sleeptime=False,
            memory_blocks=[
                {"label": "human", "value": "Test human info", "limit": 1000},
                {"label": "persona", "value": "Test persona info", "limit": 1000}
            ]
        )
        
        main_agent = await agent_manager.create_agent_async(main_agent_request, test_user)
        
        # Attach block - should work fine for standalone agent
        result = await agent_manager.attach_block_async(main_agent.id, test_block, test_user)
        assert result is not None
        
        # Verify block is attached
        updated_agent = await agent_manager.get_agent_async(main_agent.id, test_user)
        block_labels = [block.label for block in updated_agent.memory.blocks]
        assert "test_registry" in block_labels, "Block should be attached to standalone agent"