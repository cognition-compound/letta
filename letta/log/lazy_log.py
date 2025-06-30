"""
Lazy logging utilities for performance optimization.

This module provides classes and functions to defer expensive logging operations
until they are actually needed, reducing CPU overhead in high-frequency logging scenarios.
"""

import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, Union


class LazyEvaluable(ABC):
    """Abstract base class for lazy evaluation objects."""

    @abstractmethod
    def evaluate(self) -> Any:
        """Evaluate and return the actual value."""
        pass


class LazyValue(LazyEvaluable):
    """Lazy wrapper for expensive computations."""

    def __init__(self, func: Callable[[], Any], *args, **kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._cached_result = None
        self._evaluated = False

    def evaluate(self) -> Any:
        """Evaluate the lazy value, caching the result."""
        if not self._evaluated:
            self._cached_result = self._func(*self._args, **self._kwargs)
            self._evaluated = True
        return self._cached_result

    def __str__(self) -> str:
        """String representation that triggers evaluation."""
        return str(self.evaluate())

    def __repr__(self) -> str:
        """Repr that triggers evaluation."""
        return repr(self.evaluate())


class LazyString(LazyEvaluable):
    """Lazy string formatting to defer expensive string operations."""

    def __init__(self, template: str, *args, **kwargs):
        self._template = template
        self._args = args
        self._kwargs = kwargs
        self._cached_result = None
        self._evaluated = False

    def evaluate(self) -> str:
        """Evaluate the string formatting."""
        if not self._evaluated:
            # Handle mixed positional and keyword arguments
            if self._args and self._kwargs:
                self._cached_result = self._template.format(*self._args, **self._kwargs)
            elif self._args:
                self._cached_result = self._template.format(*self._args)
            elif self._kwargs:
                self._cached_result = self._template.format(**self._kwargs)
            else:
                self._cached_result = self._template
            self._evaluated = True
        return self._cached_result

    def __str__(self) -> str:
        """String representation that triggers evaluation."""
        return self.evaluate()


class LazyJsonString(LazyEvaluable):
    """Lazy JSON serialization for complex objects."""

    def __init__(self, obj: Any, indent: Optional[int] = None):
        self._obj = obj
        self._indent = indent
        self._cached_result = None
        self._evaluated = False

    def evaluate(self) -> str:
        """Evaluate the JSON serialization."""
        if not self._evaluated:
            import json

            try:
                self._cached_result = json.dumps(self._obj, indent=self._indent, default=str)
            except (TypeError, ValueError) as e:
                self._cached_result = f"<JSON serialization failed: {e}>"
            self._evaluated = True
        return self._cached_result

    def __str__(self) -> str:
        """String representation that triggers evaluation."""
        return self.evaluate()


class LazyLogContext:
    """
    Context manager for lazy evaluation of expensive logging operations.

    This class defers expensive computations (like JSON serialization,
    string formatting, data structure traversal) until the log level
    is actually enabled.
    """

    def __init__(self, logger: logging.Logger, level: int = logging.INFO):
        self.logger = logger
        self.level = level
        self._context_data: Dict[str, Any] = {}
        self._is_enabled = None

    @property
    def is_enabled(self) -> bool:
        """Check if logging is enabled for this level."""
        if self._is_enabled is None:
            self._is_enabled = self.logger.isEnabledFor(self.level)
        return self._is_enabled

    def add_lazy_value(self, key: str, func: Callable[[], Any], *args, **kwargs) -> "LazyLogContext":
        """Add a lazy value that will be computed only if logging is enabled."""
        self._context_data[key] = LazyValue(func, *args, **kwargs)
        return self

    def add_lazy_string(self, key: str, template: str, *args, **kwargs) -> "LazyLogContext":
        """Add a lazy string that will be formatted only if logging is enabled."""
        self._context_data[key] = LazyString(template, *args, **kwargs)
        return self

    def add_lazy_json(self, key: str, obj: Any, indent: Optional[int] = None) -> "LazyLogContext":
        """Add a lazy JSON serialization that will be computed only if logging is enabled."""
        self._context_data[key] = LazyJsonString(obj, indent)
        return self

    def add_value(self, key: str, value: Any) -> "LazyLogContext":
        """Add a regular value (not lazy)."""
        self._context_data[key] = value
        return self

    def log(self, message: Union[str, LazyEvaluable], **extra_kwargs) -> None:
        """Log the message with lazy evaluation."""
        if not self.is_enabled:
            return

        # Evaluate lazy values
        evaluated_context = {}
        for key, value in self._context_data.items():
            if isinstance(value, LazyEvaluable):
                evaluated_context[key] = value.evaluate()
            else:
                evaluated_context[key] = value

        # Evaluate message if it's lazy
        if isinstance(message, LazyEvaluable):
            message = message.evaluate()

        # Merge context data with extra kwargs
        evaluated_context.update(extra_kwargs)

        # Log with the appropriate level
        self.logger.log(self.level, message, extra=evaluated_context)

    def debug(self, message: Union[str, LazyEvaluable], **extra_kwargs) -> None:
        """Log at DEBUG level."""
        self.level = logging.DEBUG
        self._is_enabled = None  # Reset cache
        self.log(message, **extra_kwargs)

    def info(self, message: Union[str, LazyEvaluable], **extra_kwargs) -> None:
        """Log at INFO level."""
        self.level = logging.INFO
        self._is_enabled = None  # Reset cache
        self.log(message, **extra_kwargs)

    def warning(self, message: Union[str, LazyEvaluable], **extra_kwargs) -> None:
        """Log at WARNING level."""
        self.level = logging.WARNING
        self._is_enabled = None  # Reset cache
        self.log(message, **extra_kwargs)

    def error(self, message: Union[str, LazyEvaluable], **extra_kwargs) -> None:
        """Log at ERROR level."""
        self.level = logging.ERROR
        self._is_enabled = None  # Reset cache
        self.log(message, **extra_kwargs)


class PerformanceLogTimer:
    """Timer for measuring and logging performance metrics."""

    def __init__(self, logger: logging.Logger, operation_name: str, level: int = logging.DEBUG):
        self.logger = logger
        self.operation_name = operation_name
        self.level = level
        self.start_time = None
        self.end_time = None

    def __enter__(self) -> "PerformanceLogTimer":
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        if self.logger.isEnabledFor(self.level):
            duration_ms = round((self.end_time - self.start_time) * 1000, 2)

            extra_data = {"operation": self.operation_name, "duration_ms": duration_ms, "success": exc_type is None}

            if exc_type is not None:
                extra_data["error_type"] = exc_type.__name__
                extra_data["error_message"] = str(exc_val)
                self.logger.error(f"Operation '{self.operation_name}' failed after {duration_ms}ms", extra=extra_data)
            else:
                self.logger.log(self.level, f"Operation '{self.operation_name}' completed in {duration_ms}ms", extra=extra_data)


def lazy_log_enabled(logger: logging.Logger, level: int) -> bool:
    """Fast check if logging is enabled for the given level."""
    return logger.isEnabledFor(level)


def create_lazy_context(logger: logging.Logger, level: int = logging.INFO) -> LazyLogContext:
    """Create a lazy log context for the given logger and level."""
    return LazyLogContext(logger, level)


@contextmanager
def performance_timer(logger: logging.Logger, operation_name: str, level: int = logging.DEBUG):
    """Context manager for timing operations and logging the results."""
    timer = PerformanceLogTimer(logger, operation_name, level)
    with timer:
        yield timer


# Async logging support
_async_log_executor: Optional[ThreadPoolExecutor] = None
_async_logging_enabled = False


def setup_async_logging(max_workers: int = 2) -> None:
    """Set up async logging with ThreadPoolExecutor."""
    global _async_log_executor, _async_logging_enabled

    if _async_log_executor is not None:
        _async_log_executor.shutdown(wait=False)

    _async_log_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="async_log")
    _async_logging_enabled = True


def shutdown_async_logging() -> None:
    """Shutdown async logging executor."""
    global _async_log_executor, _async_logging_enabled

    if _async_log_executor is not None:
        _async_log_executor.shutdown(wait=True)
        _async_log_executor = None

    _async_logging_enabled = False


def async_log(logger: logging.Logger, level: int, message: str, **kwargs) -> None:
    """
    Log a message asynchronously using ThreadPoolExecutor.

    Falls back to synchronous logging if async logging is not enabled.
    """
    if not _async_logging_enabled or _async_log_executor is None:
        # Fallback to sync logging
        logger.log(level, message, **kwargs)
        return

    def _log():
        try:
            logger.log(level, message, **kwargs)
        except Exception as e:
            # If async logging fails, try sync logging as fallback
            try:
                logger.error(f"Async logging failed: {e}", exc_info=True)
            except:
                pass  # Avoid logging loops

    _async_log_executor.submit(_log)


def async_log_context(context: LazyLogContext) -> None:
    """Log a lazy context asynchronously."""
    if not _async_logging_enabled or _async_log_executor is None:
        # Fallback to sync logging
        context.log("")
        return

    def _log():
        try:
            context.log("")
        except Exception as e:
            # If async logging fails, try sync logging as fallback
            try:
                context.logger.error(f"Async lazy logging failed: {e}", exc_info=True)
            except:
                pass  # Avoid logging loops

    _async_log_executor.submit(_log)
