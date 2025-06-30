"""
Performance helpers for optimizing logging operations.

This module provides utilities to monitor and optimize logging performance,
including conditional checks and performance tracking.
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from letta.log import get_logger, create_lazy_context, lazy_log_enabled

logger = get_logger(__name__)


def log_if_enabled(log_level: int, logger: logging.Logger):
    """
    Decorator to conditionally execute logging only if the log level is enabled.
    
    This prevents expensive operations from being performed when the log level
    is not enabled for the logger.
    
    Args:
        log_level: The logging level to check
        logger: The logger instance to check
    
    Usage:
        @log_if_enabled(logging.DEBUG, logger)
        def expensive_debug_operation():
            # This will only execute if DEBUG logging is enabled
            complex_data = serialize_complex_object()
            logger.debug(f"Complex data: {complex_data}")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if lazy_log_enabled(logger, log_level):
                return func(*args, **kwargs)
            return None
        return wrapper
    return decorator


def lazy_log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    expensive_context: Optional[Callable[[], Dict[str, Any]]] = None,
    **static_context
) -> None:
    """
    Log a message with lazy evaluation of expensive context data.
    
    Args:
        logger: The logger to use
        level: The logging level
        message: The log message
        expensive_context: Optional callable that returns expensive context data
        **static_context: Static context data that doesn't need lazy evaluation
    """
    if not lazy_log_enabled(logger, level):
        return
    
    lazy_ctx = create_lazy_context(logger, level)
    
    # Add static context
    for key, value in static_context.items():
        lazy_ctx.add_value(key, value)
    
    # Add expensive context with lazy evaluation
    if expensive_context:
        lazy_ctx.add_lazy_value("context", expensive_context)
        # Flatten context into main logging context
        context_data = lazy_ctx._context_data["context"].evaluate()
        for key, value in context_data.items():
            lazy_ctx.add_value(key, value)
    
    lazy_ctx.log(message)


def performance_monitored_log(
    operation_name: str,
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG,
    threshold_ms: float = 10.0
):
    """
    Decorator to monitor logging performance and log warnings for slow operations.
    
    Args:
        operation_name: Name of the operation being monitored
        logger: Logger to use (defaults to module logger)
        level: Log level for performance reports
        threshold_ms: Threshold in milliseconds above which to log warnings
    """
    if logger is None:
        logger = globals()['logger']
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                if duration_ms > threshold_ms and lazy_log_enabled(logger, logging.WARNING):
                    lazy_log_with_context(
                        logger,
                        logging.WARNING,
                        f"Slow logging operation detected: {operation_name}",
                        operation=operation_name,
                        duration_ms=round(duration_ms, 2),
                        threshold_ms=threshold_ms
                    )
                elif lazy_log_enabled(logger, level):
                    lazy_log_with_context(
                        logger,
                        level,
                        f"Logging operation completed: {operation_name}",
                        operation=operation_name,
                        duration_ms=round(duration_ms, 2)
                    )
        return wrapper
    return decorator


class ConditionalLogger:
    """
    Logger wrapper that provides conditional logging capabilities.
    
    This class adds performance optimizations by checking log levels
    before performing expensive operations.
    """
    
    def __init__(self, logger: logging.Logger, performance_monitoring: bool = True):
        self.logger = logger
        self.performance_monitoring = performance_monitoring
        self._operation_timings = {}
    
    def debug_if_enabled(self, message_func: Callable[[], str], **context):
        """Log debug message only if debug logging is enabled."""
        if lazy_log_enabled(self.logger, logging.DEBUG):
            message = message_func() if callable(message_func) else str(message_func)
            if context:
                lazy_log_with_context(self.logger, logging.DEBUG, message, **context)
            else:
                self.logger.debug(message)
    
    def info_if_enabled(self, message_func: Callable[[], str], **context):
        """Log info message only if info logging is enabled."""
        if lazy_log_enabled(self.logger, logging.INFO):
            message = message_func() if callable(message_func) else str(message_func)
            if context:
                lazy_log_with_context(self.logger, logging.INFO, message, **context)
            else:
                self.logger.info(message)
    
    def warning_if_enabled(self, message_func: Callable[[], str], **context):
        """Log warning message only if warning logging is enabled."""
        if lazy_log_enabled(self.logger, logging.WARNING):
            message = message_func() if callable(message_func) else str(message_func)
            if context:
                lazy_log_with_context(self.logger, logging.WARNING, message, **context)
            else:
                self.logger.warning(message)
    
    def error_if_enabled(self, message_func: Callable[[], str], **context):
        """Log error message only if error logging is enabled."""
        if lazy_log_enabled(self.logger, logging.ERROR):
            message = message_func() if callable(message_func) else str(message_func)
            if context:
                lazy_log_with_context(self.logger, logging.ERROR, message, **context)
            else:
                self.logger.error(message)
    
    def log_operation_timing(self, operation_name: str, duration_ms: float):
        """Track and log operation timing if performance monitoring is enabled."""
        if not self.performance_monitoring:
            return
        
        # Store timing for analysis
        if operation_name not in self._operation_timings:
            self._operation_timings[operation_name] = []
        
        self._operation_timings[operation_name].append(duration_ms)
        
        # Log slow operations
        if duration_ms > 50:  # 50ms threshold
            self.warning_if_enabled(
                lambda: f"Slow operation detected: {operation_name}",
                operation=operation_name,
                duration_ms=round(duration_ms, 2)
            )
    
    def get_operation_stats(self) -> Dict[str, Dict[str, float]]:
        """Get performance statistics for all tracked operations."""
        stats = {}
        for operation, timings in self._operation_timings.items():
            if timings:
                stats[operation] = {
                    'count': len(timings),
                    'avg_ms': sum(timings) / len(timings),
                    'min_ms': min(timings),
                    'max_ms': max(timings),
                    'total_ms': sum(timings)
                }
        return stats


def create_conditional_logger(logger: logging.Logger, performance_monitoring: bool = True) -> ConditionalLogger:
    """Create a conditional logger wrapper for the given logger."""
    return ConditionalLogger(logger, performance_monitoring)


# Global performance tracking
_global_performance_tracker = {}


def track_logging_performance(operation_name: str, duration_ms: float):
    """Track logging performance globally."""
    if operation_name not in _global_performance_tracker:
        _global_performance_tracker[operation_name] = []
    
    _global_performance_tracker[operation_name].append(duration_ms)
    
    # Keep only last 1000 entries per operation to prevent memory growth
    if len(_global_performance_tracker[operation_name]) > 1000:
        _global_performance_tracker[operation_name] = _global_performance_tracker[operation_name][-1000:]


def get_global_performance_stats() -> Dict[str, Dict[str, float]]:
    """Get global performance statistics for all tracked operations."""
    stats = {}
    for operation, timings in _global_performance_tracker.items():
        if timings:
            stats[operation] = {
                'count': len(timings),
                'avg_ms': sum(timings) / len(timings),
                'min_ms': min(timings),
                'max_ms': max(timings),
                'total_ms': sum(timings)
            }
    return stats


def log_performance_summary(logger: Optional[logging.Logger] = None, level: int = logging.INFO):
    """Log a summary of logging performance statistics."""
    if logger is None:
        logger = globals()['logger']
    
    if not lazy_log_enabled(logger, level):
        return
    
    stats = get_global_performance_stats()
    if not stats:
        return
    
    lazy_ctx = create_lazy_context(logger, level)
    lazy_ctx.add_value("event_type", "logging_performance_summary")
    lazy_ctx.add_value("total_operations", len(stats))
    
    for operation, op_stats in stats.items():
        lazy_ctx.add_value(f"{operation}_count", op_stats['count'])
        lazy_ctx.add_value(f"{operation}_avg_ms", round(op_stats['avg_ms'], 2))
        lazy_ctx.add_value(f"{operation}_max_ms", round(op_stats['max_ms'], 2))
    
    lazy_ctx.log("Logging performance summary")