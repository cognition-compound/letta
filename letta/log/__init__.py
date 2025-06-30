"""
Letta logging infrastructure.

This module provides the core logging functionality for Letta.
Enhanced logging features are temporarily disabled to resolve circular imports.
"""

# Import logging functions from the parent log.py module
import logging
import os
import sys

# Get the parent directory where log.py resides
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_module_path = os.path.join(_parent_dir, 'log.py')

# Import functions from log.py if it exists
if os.path.exists(_log_module_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("_letta_log", _log_module_path)
    _log_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_log_module)
    
    get_logger = _log_module.get_logger
    get_audit_logger = _log_module.get_audit_logger
else:
    # Fallback implementation
    def get_logger(name=None):
        """Get a logger instance."""
        if name:
            return logging.getLogger(f"Letta.{name}")
        return logging.getLogger("Letta")
    
    def get_audit_logger():
        """Get the audit logger instance."""
        return logging.getLogger("Letta.audit")

# Stub implementations for enhanced features (to be implemented later)
class LazyLogContext:
    """Stub for LazyLogContext - minimal implementation."""
    def __init__(self, *args, **kwargs):
        self.data = kwargs
    
    def __getitem__(self, key):
        return self.data.get(key)
    
    def __setitem__(self, key, value):
        self.data[key] = value
    
    def get(self, key, default=None):
        return self.data.get(key, default)

def create_lazy_context(*args, **kwargs):
    """Stub for lazy context - not implemented yet."""
    return LazyLogContext(*args, **kwargs)

def lazy_log_enabled(*args, **kwargs):
    """Stub for lazy log check - always returns False for now."""
    return False

def performance_timer():
    """Stub for performance timer - returns a simple context manager."""
    import time
    from contextlib import contextmanager
    
    @contextmanager
    def timer():
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            # Could log performance metrics here
            pass
    
    return timer()

def get_async_logger(name=None):
    """Stub for async logger - returns regular logger for now."""
    return get_logger(name)

def lazy_log_with_context(logger, level, message, expensive_context=None):
    """
    Log a message with context that is only evaluated if logging is enabled.
    
    Args:
        logger: The logger instance
        level: The log level (e.g., logging.INFO)
        message: The log message
        expensive_context: A function that returns a dict or a dict with expensive values
    """
    if logger.isEnabledFor(level):
        context = {}
        if expensive_context:
            try:
                if callable(expensive_context):
                    context = expensive_context()
                else:
                    context = expensive_context
                # Ensure context is a dict
                if not isinstance(context, dict):
                    context = {"context": context}
            except Exception as e:
                # If context evaluation fails, log the error but don't crash
                context = {"context_error": f"Failed to evaluate context: {str(e)}"}
        logger.log(level, message, extra=context)

__all__ = [
    "get_logger",
    "get_audit_logger", 
    "LazyLogContext",
    "create_lazy_context",
    "lazy_log_enabled",
    "performance_timer",
    "get_async_logger",
    "lazy_log_with_context",
]