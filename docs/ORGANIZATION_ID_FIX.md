# Organization ID Error Fix

**Date**: 2025-01-28  
**Issue**: SDK clients sending messages with `organization_id` field causing marshmallow validation errors  
**Fix Applied**: Update `SerializedMessageSchema` to ignore unknown fields

## Problem

When SDK clients (e.g., `@letta-ai/letta-client@0.1.164`) send async messages to agents, they include an `organization_id` field that the marshmallow schema doesn't expect, resulting in:

```
"Message" object has no field "organization_id"
```

## Root Cause

1. SDK clients are sending messages with the `organization_id` field
2. The `SerializedMessageSchema` in marshmallow was using strict validation
3. When deserializing messages, marshmallow rejected the unknown field

## Solution

Updated `letta/serialize_schemas/marshmallow_message.py` to ignore unknown fields:

```python
class Meta(BaseSchema.Meta):
    model = Message
    exclude = BaseSchema.Meta.exclude + ("step", "job_message", "otid", "is_deleted", "organization")
    unknown = "exclude"  # Ignore unknown fields for backward compatibility with older SDK versions
```

## Testing

Created comprehensive tests in:
- `tests/test_organization_id_error.py` - Full integration test reproducing the error
- `tests/test_marshmallow_organization_id_fix.py` - Unit tests for the fix

## Verification

The fix has been verified to:
1. Accept messages with `organization_id` field without errors
2. Ignore any other unknown fields from older SDK versions
3. Still validate required fields properly

## Backward Compatibility

This fix ensures backward compatibility with:
- Older SDK versions that send `organization_id`
- Future unknown fields that might be added
- Existing validation for required fields remains intact

## Related Work

This is part of the broader cleanup effort to remove `organization_id` from API responses:
- See `docs/MESSAGE_ORGANIZATION_ID_INVESTIGATION.md` for the full investigation
- The Pydantic `MessageCreate` already has backward compatibility for `organization_id`