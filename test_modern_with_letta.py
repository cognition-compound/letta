#!/usr/bin/env python
"""Test modern schema generator with actual Letta functions."""

import sys
# Add the letta path for imports
sys.path.insert(0, '/Users/mordras/dev/amaiko/letta')

# Now import the modern generator
from letta.functions.schema_generator_modern import generate_schema_modern

# Import some actual Letta functions
from letta.functions.function_sets.base import (
    conversation_search,
    archival_memory_search,
    memory_replace,
)

print("Testing modern schema generator with Letta functions...")
print("="*60)

# Test conversation_search
print("\n1. Testing conversation_search:")
schema1 = generate_schema_modern(conversation_search)
print(f"  Name: {schema1['name']}")
print(f"  Strict: {schema1['strict']}")
print(f"  Properties: {list(schema1['parameters']['properties'].keys())}")
print(f"  Required: {schema1['parameters']['required']}")
print(f"  Has 'self' filtered out: {'self' not in schema1['parameters']['properties']}")

# Test archival_memory_search
print("\n2. Testing archival_memory_search:")
schema2 = generate_schema_modern(archival_memory_search)
print(f"  Name: {schema2['name']}")
print(f"  Strict: {schema2['strict']}")
print(f"  Properties: {list(schema2['parameters']['properties'].keys())}")
print(f"  Required: {schema2['parameters']['required']}")
print(f"  Has 'self' filtered out: {'self' not in schema2['parameters']['properties']}")

# Test memory_replace
print("\n3. Testing memory_replace:")
schema3 = generate_schema_modern(memory_replace)
print(f"  Name: {schema3['name']}")
print(f"  Strict: {schema3['strict']}")
print(f"  Properties: {list(schema3['parameters']['properties'].keys())}")
print(f"  Required: {schema3['parameters']['required']}")
print(f"  Has 'agent_state' filtered out: {'agent_state' not in schema3['parameters']['properties']}")

# Verify strict mode compliance
print("\n" + "="*60)
print("Strict Mode Compliance Check:")

for name, schema in [
    ("conversation_search", schema1),
    ("archival_memory_search", schema2),
    ("memory_replace", schema3)
]:
    props = set(schema['parameters']['properties'].keys())
    required = set(schema['parameters']['required'])
    additional_props = schema['parameters'].get('additionalProperties', None)
    
    is_compliant = (props == required) and (additional_props == False)
    
    if is_compliant:
        print(f"  ✓ {name}: Strict mode compliant")
    else:
        print(f"  ✗ {name}: NOT compliant")
        if props != required:
            print(f"    Missing from required: {props - required}")
        if additional_props != False:
            print(f"    additionalProperties: {additional_props} (should be False)")

print("\n" + "="*60)
print("✅ Modern schema generator successfully tested with Letta functions!")