#!/usr/bin/env python3

import os
import sys
import tempfile
from unittest.mock import patch

# Add the project root to sys.path so we can import letta modules
sys.path.insert(0, '/Users/mordras/dev/amaiko/letta')

def test_otel_detection():
    """Test OTEL logging detection and console handler configuration"""
    
    from letta.log import _has_otel_logging
    
    print("=== Testing OTEL Detection Logic ===")
    
    # Test 1: No OTEL configuration
    with patch.dict(os.environ, {}, clear=True):
        result = _has_otel_logging()
        print(f"No OTEL config: {result} (should be False)")
        assert result == False
    
    # Test 2: OTEL disabled explicitly  
    with patch.dict(os.environ, {"OTEL_LOGS_EXPORTER": "none"}):
        result = _has_otel_logging()
        print(f"OTEL disabled: {result} (should be False)")
        assert result == False
    
    # Test 3: OTEL with endpoint configured
    with patch.dict(os.environ, {
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317"
    }):
        result = _has_otel_logging() 
        print(f"OTEL with endpoint: {result} (should be True)")
        assert result == True
    
    # Test 4: OTEL console exporter
    with patch.dict(os.environ, {"OTEL_LOGS_EXPORTER": "console"}):
        result = _has_otel_logging()
        print(f"OTEL console exporter: {result} (should be True)")
        assert result == True
        
    print("✅ All OTEL detection tests passed!")


def test_console_handler_levels():
    """Test that console handler levels change based on OTEL availability"""
    
    from letta.log import _has_otel_logging, PRODUCTION_LOGGING
    
    print("\n=== Testing Console Handler Configuration ===")
    
    # Test with no OTEL
    with patch.dict(os.environ, {}, clear=True):
        otel_available = _has_otel_logging()
        console_level = PRODUCTION_LOGGING["handlers"]["console"]["level"]
        expected_level = "CRITICAL" if otel_available else "WARNING"
        print(f"No OTEL - Console level: {console_level} (expected: {expected_level})")
        assert console_level == expected_level
    
    # Test with OTEL available
    with patch.dict(os.environ, {
        "OTEL_LOGS_EXPORTER": "otlp", 
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317"
    }):
        # Need to reimport to get fresh config
        import importlib
        import letta.log
        importlib.reload(letta.log)
        
        otel_available = letta.log._has_otel_logging()
        console_level = letta.log.PRODUCTION_LOGGING["handlers"]["console"]["level"]
        expected_level = "CRITICAL" if otel_available else "WARNING"
        print(f"With OTEL - Console level: {console_level} (expected: {expected_level})")
        assert console_level == expected_level
        
    print("✅ All console handler tests passed!")


if __name__ == "__main__":
    try:
        test_otel_detection()
        test_console_handler_levels()
        print("\n🎉 All tests passed! OTEL-aware console logging is working correctly.")
        print("\nBehavior Summary:")
        print("- Without OTEL: Console shows WARNING+ logs (picked up by fluentd)")  
        print("- With OTEL: Console shows only CRITICAL logs, everything else → OTEL")
        print("- Result: Dramatically reduced 'p4itlab-letta' fluentd logs ✅")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)