# Database Connection Pooling Analysis

## Executive Summary

Letta is experiencing excessive database connections (25+ concurrent connections observed). This analysis identifies root causes and provides a prioritized fix plan.

## Current Configuration

### Connection Pool Settings (from `settings.py`)
```python
pg_pool_size: int = 25         # Concurrent connections in the pool
pg_max_overflow: int = 10      # Overflow connections allowed above pool_size
pg_pool_timeout: int = 30      # Seconds to wait for a connection from pool
pg_pool_recycle: int = 1800    # Recycle connections after 30 minutes
pg_echo: bool = False          # SQL logging
pool_pre_ping: bool = True     # Check connections before use
pool_use_lifo: bool = True     # LIFO connection recycling (sync only)
disable_sqlalchemy_pooling: bool = False  # Option to disable pooling entirely
```

### Architecture
- **Two Database Engines**: Sync and async engines created at startup
- **Maximum Connections**: (25 + 10) × 2 = 70 connections per worker
- **Drivers**: `pg8000` for sync, `asyncpg` for async

## Root Causes of Excessive Connections

### 1. Dual Engine Architecture
- Both sync and async engines maintain separate connection pools
- Each pool can have up to 35 connections (25 pool + 10 overflow)
- Total: 70 possible connections per worker process

### 2. Connection Multiplication in Service Layer

Each manager creates its own database session, leading to connection multiplication:

```
AgentManager.create_agent()
├── Creates main session (1 connection)
├── BlockManager.create_blocks() → New session (+1)
├── SourceManager.create_source() → New session (+1)
├── MessageManager.create_messages() → New session (+1)
└── ToolManager.register_tools() → New session (+1)
Total: 5+ connections per agent operation
```

**Key Issue**: No session sharing between managers - each nested operation creates a new session.

### 3. Critical Session Management Bug

In `/letta/orm/sqlalchemy_base.py`, the `update()` and `update_async()` methods have a problematic pattern:

```python
def update(self, db_session: Session, actor: Optional["User"] = None, no_commit: bool = False) -> "SqlalchemyBase":
    # remove the context manager:  <-- Deliberate removal noted
    db_session.add(self)
    if no_commit:
        db_session.flush()
    else:
        db_session.commit()
    db_session.refresh(self)
    return self
```

**Problems**:
- No context manager wrapping the session operations
- Sessions may not be properly closed on exceptions
- Contrast with `hard_delete()` which properly uses context managers

### 4. Async Event Loop Issues

Multiple locations create new event loops with `asyncio.run()`:
- `/letta/functions/function_sets/multi_agent.py:126`
- `/letta/utils.py:1082`

**Impact**: Each new event loop may create its own connection pool, leading to connection multiplication.

### 5. Fire-and-Forget Pattern Issues

The `fire_and_forget_send_to_agent` function creates new event loops in background threads:
```python
def run_in_background_thread(coro):
    def runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
        loop.close()
```

Each background thread potentially creates its own connection pool.

## Recommended Fixes

### Priority 1: Fix Session Leak in Update Methods

```python
# Fix for sqlalchemy_base.py
def update(self, db_session: Session, actor: Optional["User"] = None, no_commit: bool = False) -> "SqlalchemyBase":
    with db_session as session:  # Add proper context manager
        try:
            if actor:
                self._set_created_and_updated_by_fields(actor.id)
            self.set_updated_at()
            
            session.add(self)
            if no_commit:
                session.flush()
            else:
                session.commit()
            session.refresh(self)
            return self
        except Exception:
            session.rollback()
            raise
```

### Priority 2: Implement Session Sharing Pattern

Add optional session parameters to manager methods:

```python
class AgentManager:
    async def create_agent(self, request: CreateAgent, 
                          actor: User, 
                          db_session: Optional[AsyncSession] = None) -> Agent:
        if db_session:
            return await self._create_agent_internal(request, actor, db_session)
        else:
            async with db_registry.async_session() as session:
                return await self._create_agent_internal(request, actor, session)
    
    async def _create_agent_internal(self, request, actor, session):
        # Pass session to nested managers
        blocks = await self.block_manager.create_blocks(data, session=session)
        source = await self.source_manager.create_source(data, session=session)
        # etc...
```

### Priority 3: Fix Async Event Loop Creation

Replace `asyncio.run()` with proper async/await:

```python
# Before (creates new event loop):
def send_message_to_all_agents_in_group(self, message: str) -> str:
    return asyncio.run(_send_message_to_all_agents_in_group_async(self, message))

# After (uses existing event loop):
async def send_message_to_all_agents_in_group(self, message: str) -> str:
    return await _send_message_to_all_agents_in_group_async(self, message)
```

### Priority 4: Optimize Pool Configuration

For immediate relief, adjust environment variables:
```bash
# Reduce pool sizes
LETTA_PG_POOL_SIZE=10        # Down from 25
LETTA_PG_MAX_OVERFLOW=5      # Down from 10
LETTA_PG_POOL_TIMEOUT=10     # Down from 30 seconds

# Consider disabling async pooling
LETTA_DISABLE_SQLALCHEMY_POOLING=true  # For async connections only
```

### Priority 5: Add Connection Monitoring

Implement connection pool monitoring:

```python
import logging
from sqlalchemy.pool import QueuePool

def log_pool_statistics(engine):
    """Log connection pool statistics for monitoring"""
    if isinstance(engine.pool, QueuePool):
        stats = {
            "size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
            "overflow": engine.pool.overflow(),
            "total": engine.pool.checkedout() + engine.pool.overflow()
        }
        logger.info(f"Connection pool stats: {stats}")
        
        if stats["total"] > engine.pool._pool.maxsize * 0.8:
            logger.warning(f"Connection pool usage high: {stats['total']}/{engine.pool._pool.maxsize}")
```

## Implementation Strategy

### Phase 1: Quick Wins (1-2 days)
1. Reduce pool size via environment variables
2. Fix the session leak in update methods
3. Add basic connection monitoring

### Phase 2: Session Optimization (3-5 days)
1. Implement session sharing pattern in managers
2. Create unit-of-work pattern for complex operations
3. Batch database operations where possible

### Phase 3: Async Improvements (1 week)
1. Replace all `asyncio.run()` with proper async/await
2. Fix fire-and-forget patterns to use existing event loops
3. Consider separate pool configurations for sync vs async

### Phase 4: Long-term Improvements
1. Implement connection pool metrics and alerting
2. Consider connection multiplexing for read operations
3. Evaluate moving to a single (async-only) engine architecture

## Monitoring and Validation

### Metrics to Track
- Active connections per pool (sync/async)
- Connection wait times
- Pool exhaustion events
- Connection lifetime distribution

### Validation Tests
1. Load test with concurrent agent creation
2. Monitor PostgreSQL connection count: `SELECT count(*) FROM pg_stat_activity WHERE datname = 'letta';`
3. Check for connection leaks during exception scenarios
4. Verify connection reuse patterns

## Expected Outcomes

After implementing these fixes:
- **Current**: 25+ connections under normal load
- **Expected**: 5-10 connections under normal load
- **Peak**: 20-30 connections under heavy concurrent usage
- **Improved**: Better connection reuse, no leaks, faster response times