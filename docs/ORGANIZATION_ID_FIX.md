# Organization ID Error Fix

**Date**: 2025-01-28  
**Issue**: SDK clients sending messages with `organization_id` field causing Pydantic validation errors  
**Fix Applied**: Update both Pydantic `Message` model and marshmallow `SerializedMessageSchema` to handle unknown fields

## Problem

When SDK clients (e.g., `@letta-ai/letta-client@0.1.164`) send async messages to agents, they include an `organization_id` field that the Pydantic Message model doesn't expect, resulting in:

```
"Message" object has no field "organization_id"
```

## Root Cause Analysis

**Corrected Analysis**: The issue was NOT SDK clients sending `organization_id` fields. The actual root cause is:

1. **Internal field assignment**: Letta itself assigns `organization_id` to Message objects during processing in `letta/agents/helpers.py:280`:
   ```python
   for message in messages:
       message.organization_id = actor.organization_id
   ```

2. **Pydantic validation failure**: The `Message` Pydantic model was rejecting this internally-assigned field during serialization/deserialization in async processing

3. **Async processing pipeline**: During async message processing, Message objects are serialized and deserialized, causing validation errors when the model encountered the `organization_id` field

4. **Missing model configuration**: The `Message` model didn't have the `organization_id` field or `extra="ignore"` configuration like `MessageCreate`

## Solution

### 1. Pydantic Message Model Fix

Updated `letta/schemas/message.py` to add backward compatibility to the `Message` class:

```python
class Message(BaseMessage):
    # ... existing fields ...
    
    # Backward compatibility: Accept organization_id from old SDK versions but ignore it
    organization_id: Optional[str] = Field(default=None, description="Organization ID (deprecated, ignored for backward compatibility)")

    model_config = ConfigDict(extra="ignore")  # Allow extra fields for backward compatibility
```

### 2. Marshmallow Schema Fix (Additional Layer)

Also updated `letta/serialize_schemas/marshmallow_message.py` to ignore unknown fields:

```python
class Meta(BaseSchema.Meta):
    model = Message
    exclude = BaseSchema.Meta.exclude + ("step", "job_message", "otid", "is_deleted", "organization")
    unknown = "exclude"  # Ignore unknown fields for backward compatibility with older SDK versions
```

## Testing

Created comprehensive tests in:
- `tests/test_internal_organization_id_assignment.py` - Tests the actual root cause scenario (internal field assignment)
- `tests/test_pydantic_organization_id_fix.py` - Unit tests for the Pydantic Message model fix
- `tests/test_sdk_organization_id_compatibility.py` - Tests simulating SDK client scenarios (still valid for backward compatibility)
- `tests/test_marshmallow_organization_id_fix.py` - Unit tests for the marshmallow schema fix
- `tests/test_organization_id_error.py` - Original integration test (deprecated)

## Verification

The fix has been verified to:
1. Accept messages with `organization_id` field without errors at both Pydantic and marshmallow layers
2. Ignore any other unknown fields from older SDK versions
3. Still validate required fields properly
4. Handle async message serialization/deserialization correctly
5. Maintain compatibility with existing `MessageCreate` behavior

## Key Test Results

✅ **Internal organization_id assignment works** - The core issue is resolved  
✅ **Message async serialization/deserialization works** - Async processing no longer fails  
✅ **create_input_messages function works** - The exact function that assigns organization_id  
✅ SDK message with organization_id is accepted successfully (backward compatibility)  
✅ MessageCreate with organization_id works correctly  
✅ Pydantic Message model ignores unknown fields  
✅ Required field validation still functions properly  

## Backward Compatibility

This fix ensures backward compatibility with:
- Older SDK versions that send `organization_id` (like `@letta-ai/letta-client@0.1.164`)
- Future unknown fields that might be added by SDK clients
- Existing validation for required fields remains intact
- Both request-time validation (MessageCreate) and async processing (Message) scenarios

## Impact

This fix resolves the production error:
```
Failed to send async message to agent agent-b37f29c9-a9ea-48a2-84d7-a8166cbcaa71 via SDK: 400 Status code: 400
Body: {
 "detail": "\"Message\" object has no field \"organization_id\""
}
```

## Related Work

This is part of the broader cleanup effort to remove `organization_id` from API responses:
- See `docs/MESSAGE_ORGANIZATION_ID_INVESTIGATION.md` for the full investigation
- The Pydantic `MessageCreate` already had backward compatibility for `organization_id`
- This fix extends the same compatibility to the core `Message` model used in async processing