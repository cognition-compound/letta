# Fix for Parallel Tool Execution Foreign Key Constraint Violation

## Problem

When executing tools in parallel with the default `NoopStepManager`, Letta was encountering foreign key constraint violations:

```
DBAPIError: insert or update on table "messages" violates foreign key constraint "fk_messages_step_id"
DETAIL: Key (step_id)=(step-48cbabeb-e193-4c33-92b9-f04455ddef7d) is not present in table "steps".
```

## Root Cause

1. The `LettaAgent` generates a `step_id` for each agent step using `generate_step_id()`
2. This `step_id` is passed to messages created during tool execution
3. The `messages` table has a foreign key constraint on `step_id` referencing the `steps` table
4. When using `NoopStepManager` (the default), no step record is created in the database
5. This causes a foreign key violation when messages try to reference a non-existent step

## Solution

The fix involves three changes:

### 1. Conditional Step ID Generation (letta/agents/letta_agent.py)

```python
# Generate step_id only if we're using a real StepManager
# NoopStepManager is a singleton, so check by class name
step_id = generate_step_id() if self.step_manager.__class__.__name__ != 'NoopStepManager' else None
```

### 2. Conditional Step ID Assignment in Messages (letta/server/rest_api/utils.py)

```python
# Only set step_id if it's not None (i.e., when using a real StepManager, not NoopStepManager)
# This prevents foreign key constraint violations when using NoopStepManager
if step_id is not None:
    for message in messages:
        message.step_id = step_id
```

### 3. Conditional Step Logging (letta/agents/letta_agent.py)

```python
# Log step only if we're using a real StepManager
if step_id is not None:
    logged_step = await self.step_manager.log_step_async(...)
```

## Technical Notes

- `NoopStepManager` is a singleton decorated class, which makes `isinstance()` checks fail
- We use `self.step_manager.__class__.__name__ != 'NoopStepManager'` to check the manager type
- The fix preserves backward compatibility while preventing database errors

## Testing

Two test files verify the fix:
- `tests/test_parallel_tools_noop_step.py` - Tests step_id generation logic
- `tests/test_parallel_tools_step_id_fix.py` - Tests message creation with and without step_id

All tests pass, confirming that:
- Messages created with `step_id=None` don't have step_id set
- Messages created with a valid step_id have it properly set
- NoopStepManager correctly returns None from log_step methods