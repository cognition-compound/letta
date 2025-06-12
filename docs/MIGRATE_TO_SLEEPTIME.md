# Migrating Existing Agents to Sleeptime: Implementation Plan

This document outlines the detailed plan for updating the `update_agent` method to support migrating existing agents to sleeptime mode by creating all necessary infrastructure.

## Current Limitation

Currently, the `update_agent` method only sets `enable_sleeptime=True` on an existing agent and updates the system prompt. It does NOT create the required sleeptime infrastructure:

- ❌ No background sleeptime agent creation
- ❌ No multi-agent group creation
- ❌ No memory block sharing setup

The sleeptime infrastructure is only created during initial agent creation with `enable_sleeptime=True`.

## Required Infrastructure for Sleeptime

When an agent is created with `enable_sleeptime=True`, the following infrastructure is automatically set up:

1. **Multi-Agent Group** (`ManagerType.sleeptime`)
   - Coordinates between main agent and sleeptime agent
   - Configurable `sleeptime_agent_frequency`
   - Manages turn-taking and memory processing

2. **Background Sleeptime Agent**
   - Separate agent with `agent_type=sleeptime_agent`
   - Uses `sleeptime_v2.txt` system prompt
   - Specialized tools for memory processing
   - Shares memory blocks with main agent

3. **Shared Memory Blocks**
   - Core memory blocks linked to both agents
   - Memory updates propagated between agents
   - Consistent state across agent group

## Implementation Plan

### Phase 1: Detection and Validation

**Location**: `letta/services/agent_manager.py:update_agent()` and `update_agent_async()`

**Code Addition** (after line 623):
```python
# Detect sleeptime migration
is_migrating_to_sleeptime = (
    agent_update.enable_sleeptime is True and 
    not agent.enable_sleeptime and 
    agent.multi_agent_group is None
)

if is_migrating_to_sleeptime:
    # Validate migration is possible
    if agent.agent_type not in [AgentType.memgpt_agent, AgentType.memgpt_v2_agent]:
        raise ValueError(f"Cannot migrate agent_type {agent.agent_type} to sleeptime")
    
    # Create sleeptime infrastructure
    await self._create_sleeptime_infrastructure(session, agent, actor)
```

### Phase 2: Sleeptime Infrastructure Creation

**New Method**: `_create_sleeptime_infrastructure()`

```python
async def _create_sleeptime_infrastructure(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    actor: PydanticUser
) -> None:
    """Create sleeptime infrastructure for an existing agent"""
    
    # Step 1: Create the background sleeptime agent
    sleeptime_agent = await self._create_sleeptime_agent(session, main_agent, actor)
    
    # Step 2: Create the multi-agent group
    group = await self._create_sleeptime_group(session, main_agent, sleeptime_agent, actor)
    
    # Step 3: Link memory blocks
    await self._share_memory_blocks(session, main_agent, sleeptime_agent)
    
    # Step 4: Update main agent with group reference
    main_agent.multi_agent_group_id = group.id
    
    # Step 5: Update tools if needed
    await self._update_sleeptime_tools(session, main_agent, actor)
```

### Phase 3: Background Agent Creation

**New Method**: `_create_sleeptime_agent()`

```python
async def _create_sleeptime_agent(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    actor: PydanticUser
) -> AgentModel:
    """Create the background sleeptime agent"""
    
    sleeptime_agent = AgentModel(
        name=f"{main_agent.name}_sleeptime",
        agent_type=AgentType.sleeptime_agent,
        system=derive_system_message(
            agent_type=AgentType.sleeptime_agent,
            enable_sleeptime=True
        ),
        llm_config=main_agent.llm_config,
        embedding_config=main_agent.embedding_config,
        organization_id=main_agent.organization_id,
        description=f"Sleeptime agent for {main_agent.name}",
        enable_sleeptime=True,
        created_by_id=actor.id,
        last_updated_by_id=actor.id,
        project_id=main_agent.project_id,
        template_id=main_agent.template_id,
    )
    
    session.add(sleeptime_agent)
    await session.flush()
    
    # Add sleeptime-specific tools
    await self._attach_sleeptime_tools(session, sleeptime_agent, actor)
    
    return sleeptime_agent
```

### Phase 4: Group Creation

**New Method**: `_create_sleeptime_group()`

```python
async def _create_sleeptime_group(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    sleeptime_agent: AgentModel, 
    actor: PydanticUser
) -> GroupModel:
    """Create the sleeptime multi-agent group"""
    
    from letta.orm.group import Group as GroupModel
    
    group = GroupModel(
        name=f"{main_agent.name}_sleeptime_group",
        description=f"Sleeptime group for {main_agent.name}",
        manager_type=ManagerType.sleeptime,
        agent_ids=[main_agent.id, sleeptime_agent.id],
        sleeptime_agent_frequency=30,  # Default frequency
        organization_id=main_agent.organization_id,
        created_by_id=actor.id,
        last_updated_by_id=actor.id,
    )
    
    session.add(group)
    await session.flush()
    
    return group
```

### Phase 5: Memory Block Sharing

**New Method**: `_share_memory_blocks()`

```python
async def _share_memory_blocks(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    sleeptime_agent: AgentModel
) -> None:
    """Share memory blocks between main and sleeptime agents"""
    
    # Get main agent's memory blocks
    main_blocks_result = await session.execute(
        select(BlocksAgents.block_id, BlocksAgents.block_label)
        .where(BlocksAgents.agent_id == main_agent.id)
    )
    
    # Create block associations for sleeptime agent
    block_rows = [
        {
            "agent_id": sleeptime_agent.id,
            "block_id": block_id,
            "block_label": block_label
        }
        for block_id, block_label in main_blocks_result.all()
    ]
    
    if block_rows:
        await self._bulk_insert_pivot_async(
            session, 
            BlocksAgents.__table__, 
            block_rows
        )
```

### Phase 6: Tool Management

**New Method**: `_attach_sleeptime_tools()` and `_update_sleeptime_tools()`

```python
async def _attach_sleeptime_tools(
    self, 
    session: AsyncSession, 
    sleeptime_agent: AgentModel, 
    actor: PydanticUser
) -> None:
    """Attach sleeptime-specific tools to the background agent"""
    
    from letta.functions.function_sets.builtin import BASE_SLEEPTIME_TOOLS
    
    # Resolve tool names to IDs
    tool_names = set(BASE_SLEEPTIME_TOOLS)
    name_to_id, _ = self._resolve_tools(
        session, tool_names, set(), actor.organization_id
    )
    
    # Create tool associations
    tool_rows = [
        {"agent_id": sleeptime_agent.id, "tool_id": tool_id}
        for tool_id in name_to_id.values()
    ]
    
    await self._bulk_insert_pivot_async(
        session,
        ToolsAgents.__table__,
        tool_rows
    )

async def _update_sleeptime_tools(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    actor: PydanticUser
) -> None:
    """Update main agent tools for sleeptime compatibility"""
    
    from letta.functions.function_sets.builtin import BASE_SLEEPTIME_CHAT_TOOLS
    
    # Add sleeptime chat tools to main agent if not present
    current_tools = {tool.name for tool in main_agent.tools}
    needed_tools = set(BASE_SLEEPTIME_CHAT_TOOLS) - current_tools
    
    if needed_tools:
        name_to_id, _ = self._resolve_tools(
            session, needed_tools, set(), actor.organization_id
        )
        
        tool_rows = [
            {"agent_id": main_agent.id, "tool_id": tool_id}
            for tool_id in name_to_id.values()
        ]
        
        await self._bulk_insert_pivot_async(
            session,
            ToolsAgents.__table__,
            tool_rows
        )
        
        session.expire(main_agent, ["tools"])
```

### Phase 7: Error Handling and Rollback

**Enhanced Error Handling**:

```python
async def _create_sleeptime_infrastructure(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    actor: PydanticUser
) -> None:
    """Create sleeptime infrastructure with proper error handling"""
    
    try:
        # Create infrastructure
        sleeptime_agent = await self._create_sleeptime_agent(session, main_agent, actor)
        group = await self._create_sleeptime_group(session, main_agent, sleeptime_agent, actor)
        await self._share_memory_blocks(session, main_agent, sleeptime_agent)
        
        # Update main agent
        main_agent.multi_agent_group_id = group.id
        await self._update_sleeptime_tools(session, main_agent, actor)
        
        # Validate the setup
        await self._validate_sleeptime_setup(session, main_agent, sleeptime_agent, group)
        
    except Exception as e:
        # Rollback will happen automatically due to session.begin()
        logger.error(f"Failed to create sleeptime infrastructure for agent {main_agent.id}: {e}")
        raise ValueError(f"Sleeptime migration failed: {e}")

async def _validate_sleeptime_setup(
    self, 
    session: AsyncSession, 
    main_agent: AgentModel, 
    sleeptime_agent: AgentModel, 
    group: GroupModel
) -> None:
    """Validate that sleeptime infrastructure was created correctly"""
    
    # Check group has both agents
    assert len(group.agent_ids) == 2
    assert main_agent.id in group.agent_ids
    assert sleeptime_agent.id in group.agent_ids
    
    # Check main agent references group
    assert main_agent.multi_agent_group_id == group.id
    
    # Check memory blocks are shared
    main_blocks = await session.execute(
        select(BlocksAgents.block_id).where(BlocksAgents.agent_id == main_agent.id)
    )
    sleeptime_blocks = await session.execute(
        select(BlocksAgents.block_id).where(BlocksAgents.agent_id == sleeptime_agent.id)
    )
    
    main_block_ids = {bid for (bid,) in main_blocks.all()}
    sleeptime_block_ids = {bid for (bid,) in sleeptime_blocks.all()}
    
    assert main_block_ids == sleeptime_block_ids, "Memory blocks not properly shared"
```

## API Changes Required

### UpdateAgent Schema

**Location**: `letta/schemas/agent.py`

The `UpdateAgent` schema already includes `enable_sleeptime: Optional[bool]`, so no changes needed.

### REST API Documentation

**Location**: `letta/server/rest_api/routers/v1/agents.py`

Update the `modify_agent` endpoint documentation to mention sleeptime migration:

```python
@router.patch("/{agent_id}", response_model=AgentState, operation_id="modify_agent")
async def modify_agent(
    agent_id: str,
    update_agent: UpdateAgent = Body(...),
    server: "SyncServer" = Depends(get_letta_server),
    actor_id: Optional[str] = Header(None, alias="user_id"),
):
    """
    Update an existing agent
    
    When setting enable_sleeptime=True on an agent that doesn't have sleeptime enabled,
    this will automatically create:
    - A background sleeptime agent for memory processing
    - A multi-agent group to coordinate between them
    - Shared memory blocks between the agents
    
    This migration is irreversible through the API.
    """
```

## Database Migrations

### New Migration Required

**File**: `alembic/versions/XXXX_add_sleeptime_migration_support.py`

```python
"""Add sleeptime migration support

Revision ID: XXXX
Revises: YYYY
Create Date: 2024-XX-XX

"""
from alembic import op
import sqlalchemy as sa

# No schema changes needed - existing tables support sleeptime migration
# This migration serves as a marker for when sleeptime migration was added

def upgrade():
    # Add any indexes that might help with sleeptime queries
    op.create_index(
        'ix_agents_enable_sleeptime_group',
        'agents',
        ['enable_sleeptime', 'multi_agent_group_id']
    )

def downgrade():
    op.drop_index('ix_agents_enable_sleeptime_group', 'agents')
```

## Testing Strategy

### Unit Tests

**File**: `tests/test_sleeptime_migration.py`

```python
async def test_sleeptime_migration():
    """Test migrating an existing agent to sleeptime"""
    
    # Create normal agent
    agent = await agent_manager.create_agent_async(
        CreateAgent(
            name="test_agent",
            agent_type=AgentType.memgpt_agent,
            enable_sleeptime=False,
            # ... other config
        ),
        actor=user
    )
    
    assert not agent.enable_sleeptime
    assert agent.multi_agent_group is None
    
    # Migrate to sleeptime
    updated_agent = await agent_manager.update_agent_async(
        agent_id=agent.id,
        agent_update=UpdateAgent(enable_sleeptime=True),
        actor=user
    )
    
    # Verify infrastructure was created
    assert updated_agent.enable_sleeptime
    assert updated_agent.multi_agent_group is not None
    assert updated_agent.multi_agent_group.manager_type == ManagerType.sleeptime
    assert len(updated_agent.multi_agent_group.agent_ids) == 2
    
    # Verify background agent exists
    group_agents = [
        await agent_manager.get_agent_by_id(aid, actor=user)
        for aid in updated_agent.multi_agent_group.agent_ids
    ]
    sleeptime_agents = [a for a in group_agents if a.agent_type == AgentType.sleeptime_agent]
    assert len(sleeptime_agents) == 1
    
    # Verify memory blocks are shared
    main_blocks = updated_agent.memory.blocks
    sleeptime_blocks = sleeptime_agents[0].memory.blocks
    assert len(main_blocks) == len(sleeptime_blocks)
    
async def test_sleeptime_migration_errors():
    """Test error cases for sleeptime migration"""
    
    # Try to migrate voice agent (should fail)
    voice_agent = await agent_manager.create_agent_async(
        CreateAgent(
            agent_type=AgentType.voice_convo_agent,
            # ... config
        ),
        actor=user
    )
    
    with pytest.raises(ValueError, match="Cannot migrate agent_type"):
        await agent_manager.update_agent_async(
            agent_id=voice_agent.id,
            agent_update=UpdateAgent(enable_sleeptime=True),
            actor=user
        )
```

### Integration Tests

**File**: `tests/integration_test_sleeptime_migration.py`

```python
async def test_end_to_end_sleeptime_migration():
    """Test complete sleeptime migration flow through API"""
    
    # Create agent via API
    response = client.post("/v1/agents", json={
        "name": "migration_test",
        "agent_type": "memgpt_agent",
        "enable_sleeptime": False
    })
    agent = response.json()
    
    # Migrate to sleeptime via API
    response = client.patch(f"/v1/agents/{agent['id']}", json={
        "enable_sleeptime": True
    })
    updated_agent = response.json()
    
    # Test functionality
    response = client.post(f"/v1/agents/{agent['id']}/messages", json={
        "messages": [{"role": "user", "content": "Hello"}]
    })
    
    # Verify sleeptime agent receives work
    sleeptime_agent_id = [
        aid for aid in updated_agent['multi_agent_group']['agent_ids']
        if aid != agent['id']
    ][0]
    
    # Check sleeptime agent has messages
    response = client.get(f"/v1/agents/{sleeptime_agent_id}/messages")
    assert len(response.json()) > 0
```

## Considerations and Edge Cases

### 1. Irreversible Migration
- Sleeptime migration creates new infrastructure that can't be easily removed
- Consider adding a warning in the API documentation
- May want to implement a "disable sleeptime" feature later

### 2. Memory Block Conflicts
- What if memory blocks are already attached to other agents?
- Should clone blocks vs share references?
- Handle orphaned blocks if migration fails

### 3. Tool Compatibility
- Some tools may not work well with sleeptime agents
- Need to validate tool compatibility during migration
- May need tool-specific migration logic

### 4. Performance Impact
- Creating sleeptime infrastructure during update adds latency
- Consider making it an async background task
- Add progress tracking for long migrations

### 5. Concurrent Updates
- Handle race conditions if multiple updates happen simultaneously
- Use database locks or unique constraints to prevent duplicate infrastructure

## Future Enhancements

### 1. Migration Preview
- Add an API endpoint to preview what sleeptime migration would create
- Show cost/resource implications

### 2. Rollback Support
- Implement ability to disable sleeptime and remove infrastructure
- Archive vs delete sleeptime agents

### 3. Custom Sleeptime Configuration
- Allow specifying sleeptime frequency during migration
- Custom sleeptime agent configuration

### 4. Batch Migration
- Support migrating multiple agents to sleeptime in one operation
- Progress tracking and error reporting

## Implementation Timeline

1. **Week 1**: Core infrastructure creation methods
2. **Week 2**: Integration with update_agent methods
3. **Week 3**: Error handling and validation
4. **Week 4**: Testing and documentation
5. **Week 5**: API documentation and edge case handling

This plan ensures that updating an agent with `enable_sleeptime=True` will create all necessary sleeptime infrastructure, making the migration seamless for users.