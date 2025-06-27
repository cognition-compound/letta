"""
Database and service layer logging decorators and utilities.

This module provides comprehensive logging decorators for database operations,
exception handling, and performance monitoring with OpenTelemetry integration.
"""

import asyncio
import inspect
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from opentelemetry import trace
from sqlalchemy.exc import SQLAlchemyError

from letta.log import get_logger

# Import OpenTelemetry functions dynamically to avoid circular imports
def _get_trace_id():
    try:
        from letta.otel.tracing import get_trace_id
        return get_trace_id()
    except ImportError:
        return None

def _log_attributes(attributes):
    try:
        from letta.otel.tracing import log_attributes
        log_attributes(attributes)
    except ImportError:
        pass

def _log_event(name, attributes=None, timestamp=None):
    try:
        from letta.otel.tracing import log_event
        log_event(name, attributes, timestamp)
    except ImportError:
        pass

F = TypeVar("F", bound=Callable[..., Any])

logger = get_logger(__name__)


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid.uuid4())


@contextmanager
def performance_timer():
    """Context manager for timing operations."""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        end_time = time.perf_counter()
        duration_ms = round((end_time - start_time) * 1000, 2)
        return duration_ms


def get_operation_context(func: Callable, args: tuple, kwargs: dict) -> Dict[str, Any]:
    """Extract operation context from function signature and arguments."""
    context = {
        "operation": f"{func.__module__}.{func.__qualname__}",
        "method": func.__name__,
    }
    
    # Add class name if this is a method
    if args and hasattr(args[0], "__class__"):
        context["service"] = args[0].__class__.__name__
    
    # Extract common identifiers from function signature
    try:
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        # Skip 'self' parameter
        param_items = list(bound_args.arguments.items())
        if args and hasattr(args[0], "__class__"):
            param_items = param_items[1:]
        
        # Extract key identifiers
        for name, value in param_items:
            if name in ("agent_id", "user_id", "message_id", "block_id", "source_id", "tool_id"):
                context[name] = str(value) if value is not None else None
            elif name == "actor" and hasattr(value, "id"):
                context["actor_id"] = str(value.id)
                context["organization_id"] = getattr(value, "organization_id", None)
                
    except Exception:
        # Don't fail if we can't extract parameters
        pass
        
    return context


def db_operation_logger(
    operation_type: str = "database_operation",
    log_level: str = "INFO",
    include_timing: bool = True,
    include_result_info: bool = True
):
    """
    Decorator for comprehensive database operation logging.
    
    Args:
        operation_type: Type of operation (e.g., "create", "read", "update", "delete")
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        include_timing: Whether to include timing metrics
        include_result_info: Whether to log result information
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            correlation_id = generate_correlation_id()
            context = get_operation_context(func, args, kwargs)
            trace_id = _get_trace_id()
            
            # Base logging context
            log_context = {
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "operation_type": operation_type,
                **context
            }
            
            # Log operation start
            logger.log(
                getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 20,
                f"Starting {operation_type}: {context.get('method', 'unknown')}",
                extra=log_context
            )
            
            # Add OpenTelemetry attributes
            if trace_id:
                _log_attributes({
                    "db.operation": operation_type,
                    "correlation.id": correlation_id,
                    **{k: v for k, v in context.items() if v is not None}
                })
            
            start_time = time.perf_counter()
            error_occurred = False
            
            try:
                result = await func(*args, **kwargs)
                
                if include_timing:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    log_context["duration_ms"] = duration_ms
                
                # Add result information
                if include_result_info and result is not None:
                    if hasattr(result, "__len__"):
                        try:
                            log_context["result_count"] = len(result)
                        except TypeError:
                            pass
                    if hasattr(result, "id"):
                        log_context["result_id"] = str(result.id)
                
                # Log successful completion
                logger.log(
                    getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 20,
                    f"Completed {operation_type}: {context.get('method', 'unknown')} successfully",
                    extra=log_context
                )
                
                # Add OpenTelemetry event
                if trace_id:
                    _log_event(f"db_operation_completed", {
                        "operation_type": operation_type,
                        "success": True,
                        "duration_ms": log_context.get("duration_ms")
                    })
                
                return result
                
            except Exception as e:
                error_occurred = True
                if include_timing:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    log_context["duration_ms"] = duration_ms
                
                log_context.update({
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "success": False
                })
                
                # Log error
                logger.error(
                    f"Failed {operation_type}: {context.get('method', 'unknown')}",
                    extra=log_context,
                    exc_info=True
                )
                
                # Add OpenTelemetry event
                if trace_id:
                    _log_event(f"db_operation_failed", {
                        "operation_type": operation_type,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "duration_ms": log_context.get("duration_ms")
                    })
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            correlation_id = generate_correlation_id()
            context = get_operation_context(func, args, kwargs)
            trace_id = _get_trace_id()
            
            # Base logging context
            log_context = {
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "operation_type": operation_type,
                **context
            }
            
            # Log operation start
            logger.log(
                getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 20,
                f"Starting {operation_type}: {context.get('method', 'unknown')}",
                extra=log_context
            )
            
            # Add OpenTelemetry attributes
            if trace_id:
                _log_attributes({
                    "db.operation": operation_type,
                    "correlation.id": correlation_id,
                    **{k: v for k, v in context.items() if v is not None}
                })
            
            start_time = time.perf_counter()
            
            try:
                result = func(*args, **kwargs)
                
                if include_timing:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    log_context["duration_ms"] = duration_ms
                
                # Add result information
                if include_result_info and result is not None:
                    if hasattr(result, "__len__"):
                        try:
                            log_context["result_count"] = len(result)
                        except TypeError:
                            pass
                    if hasattr(result, "id"):
                        log_context["result_id"] = str(result.id)
                
                # Log successful completion
                logger.log(
                    getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 20,
                    f"Completed {operation_type}: {context.get('method', 'unknown')} successfully",
                    extra=log_context
                )
                
                # Add OpenTelemetry event
                if trace_id:
                    _log_event(f"db_operation_completed", {
                        "operation_type": operation_type,
                        "success": True,
                        "duration_ms": log_context.get("duration_ms")
                    })
                
                return result
                
            except Exception as e:
                if include_timing:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    log_context["duration_ms"] = duration_ms
                
                log_context.update({
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "success": False
                })
                
                # Log error
                logger.error(
                    f"Failed {operation_type}: {context.get('method', 'unknown')}",
                    extra=log_context,
                    exc_info=True
                )
                
                # Add OpenTelemetry event
                if trace_id:
                    _log_event(f"db_operation_failed", {
                        "operation_type": operation_type,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "duration_ms": log_context.get("duration_ms")
                    })
                
                raise
        
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator


def exception_handler(
    log_level: str = "ERROR",
    reraise: bool = True,
    fallback_value: Any = None,
    handle_sql_errors: bool = True
):
    """
    Decorator for standardized exception handling with structured logging.
    
    Args:
        log_level: Logging level for exceptions
        reraise: Whether to re-raise the exception after logging
        fallback_value: Value to return if not re-raising
        handle_sql_errors: Whether to provide special handling for SQLAlchemy errors
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            correlation_id = generate_correlation_id()
            context = get_operation_context(func, args, kwargs)
            trace_id = _get_trace_id()
            
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Build error context
                error_context = {
                    "correlation_id": correlation_id,
                    "trace_id": trace_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "function": func.__name__,
                    **context
                }
                
                # Add SQLAlchemy specific context
                if handle_sql_errors and isinstance(e, SQLAlchemyError):
                    error_context["sql_error"] = True
                    if hasattr(e, "orig"):
                        error_context["original_error"] = str(e.orig)
                
                # Log the exception
                logger.log(
                    getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 40,
                    f"Exception in {context.get('service', 'unknown')}.{func.__name__}: {str(e)}",
                    extra=error_context,
                    exc_info=True
                )
                
                # Add OpenTelemetry event
                if trace_id:
                    _log_event("exception_occurred", {
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "function": func.__name__
                    })
                
                if reraise:
                    raise
                else:
                    return fallback_value
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            correlation_id = generate_correlation_id()
            context = get_operation_context(func, args, kwargs)
            trace_id = _get_trace_id()
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Build error context
                error_context = {
                    "correlation_id": correlation_id,
                    "trace_id": trace_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "function": func.__name__,
                    **context
                }
                
                # Add SQLAlchemy specific context
                if handle_sql_errors and isinstance(e, SQLAlchemyError):
                    error_context["sql_error"] = True
                    if hasattr(e, "orig"):
                        error_context["original_error"] = str(e.orig)
                
                # Log the exception
                logger.log(
                    getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 40,
                    f"Exception in {context.get('service', 'unknown')}.{func.__name__}: {str(e)}",
                    extra=error_context,
                    exc_info=True
                )
                
                # Add OpenTelemetry event
                if trace_id:
                    _log_event("exception_occurred", {
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "function": func.__name__
                    })
                
                if reraise:
                    raise
                else:
                    return fallback_value
        
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator


def performance_monitor(
    threshold_ms: Optional[float] = None,
    log_all: bool = False,
    warn_threshold_ms: Optional[float] = None
):
    """
    Decorator for monitoring function performance with configurable thresholds.
    
    Args:
        threshold_ms: Log operations taking longer than this threshold
        log_all: Log all operations regardless of duration
        warn_threshold_ms: Log warnings for operations exceeding this threshold
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            context = get_operation_context(func, args, kwargs)
            trace_id = _get_trace_id()
            
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                
                # Determine if we should log this operation
                should_log = log_all
                log_level = "INFO"
                
                if threshold_ms and duration_ms >= threshold_ms:
                    should_log = True
                    
                if warn_threshold_ms and duration_ms >= warn_threshold_ms:
                    log_level = "WARNING"
                    should_log = True
                
                if should_log:
                    perf_context = {
                        "duration_ms": duration_ms,
                        "trace_id": trace_id,
                        "performance_monitoring": True,
                        **context
                    }
                    
                    message = f"Performance: {context.get('method', 'unknown')} took {duration_ms}ms"
                    if warn_threshold_ms and duration_ms >= warn_threshold_ms:
                        message = f"SLOW OPERATION: {message}"
                    
                    logger.log(
                        getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 20,
                        message,
                        extra=perf_context
                    )
                    
                    # Add OpenTelemetry event
                    if trace_id:
                        _log_event("performance_metric", {
                            "duration_ms": duration_ms,
                            "function": func.__name__,
                            "slow_operation": duration_ms >= (warn_threshold_ms or float('inf'))
                        })
                
                return result
                
            except Exception as e:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                # Always log performance for failed operations
                perf_context = {
                    "duration_ms": duration_ms,
                    "trace_id": trace_id,
                    "performance_monitoring": True,
                    "operation_failed": True,
                    "error_type": type(e).__name__,
                    **context
                }
                
                logger.warning(
                    f"Performance (FAILED): {context.get('method', 'unknown')} failed after {duration_ms}ms",
                    extra=perf_context
                )
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            context = get_operation_context(func, args, kwargs)
            trace_id = _get_trace_id()
            
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                
                # Determine if we should log this operation
                should_log = log_all
                log_level = "INFO"
                
                if threshold_ms and duration_ms >= threshold_ms:
                    should_log = True
                    
                if warn_threshold_ms and duration_ms >= warn_threshold_ms:
                    log_level = "WARNING"
                    should_log = True
                
                if should_log:
                    perf_context = {
                        "duration_ms": duration_ms,
                        "trace_id": trace_id,
                        "performance_monitoring": True,
                        **context
                    }
                    
                    message = f"Performance: {context.get('method', 'unknown')} took {duration_ms}ms"
                    if warn_threshold_ms and duration_ms >= warn_threshold_ms:
                        message = f"SLOW OPERATION: {message}"
                    
                    logger.log(
                        getattr(logger, log_level.lower()).__self__.level if hasattr(logger, log_level.lower()) else 20,
                        message,
                        extra=perf_context
                    )
                    
                    # Add OpenTelemetry event
                    if trace_id:
                        _log_event("performance_metric", {
                            "duration_ms": duration_ms,
                            "function": func.__name__,
                            "slow_operation": duration_ms >= (warn_threshold_ms or float('inf'))
                        })
                
                return result
                
            except Exception as e:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                # Always log performance for failed operations
                perf_context = {
                    "duration_ms": duration_ms,
                    "trace_id": trace_id,
                    "performance_monitoring": True,
                    "operation_failed": True,
                    "error_type": type(e).__name__,
                    **context
                }
                
                logger.warning(
                    f"Performance (FAILED): {context.get('method', 'unknown')} failed after {duration_ms}ms",
                    extra=perf_context
                )
                
                raise
        
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator


# Convenience decorators combining common patterns
def db_create_logger(**kwargs):
    """Specialized decorator for database create operations."""
    return db_operation_logger(operation_type="create", **kwargs)


def db_read_logger(**kwargs):
    """Specialized decorator for database read operations."""
    return db_operation_logger(operation_type="read", log_level="DEBUG", **kwargs)


def db_update_logger(**kwargs):
    """Specialized decorator for database update operations."""
    return db_operation_logger(operation_type="update", **kwargs)


def db_delete_logger(**kwargs):
    """Specialized decorator for database delete operations."""
    return db_operation_logger(operation_type="delete", **kwargs)


def service_method_logger(include_performance: bool = True, warn_threshold_ms: float = 1000, **kwargs):
    """
    Combined decorator for service methods with logging, exception handling, and performance monitoring.
    
    Args:
        include_performance: Whether to include performance monitoring
        warn_threshold_ms: Threshold for warning about slow operations
        **kwargs: Additional arguments passed to underlying decorators
    """
    def decorator(func: F) -> F:
        # Apply multiple decorators
        decorated_func = func
        
        # Apply exception handling
        decorated_func = exception_handler(**kwargs)(decorated_func)
        
        # Apply performance monitoring if requested
        if include_performance:
            decorated_func = performance_monitor(warn_threshold_ms=warn_threshold_ms)(decorated_func)
        
        return decorated_func
    
    return decorator