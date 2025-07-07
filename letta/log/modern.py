"""Modern logging interface for Letta.

This module provides a clean, intuitive API wrapper around the existing logging system,
inspired by structlog/loguru while maintaining full compatibility.
"""

import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, Type, Union

from letta.log import get_logger as _get_base_logger
from letta.log.lazy_log import create_lazy_context, lazy_log_enabled


class ModernLogger:
    """Modern logging interface with clean API and performance optimizations."""

    def __init__(self, logger: logging.Logger):
        """Initialize with an existing logger instance."""
        self._logger = logger
        self._context: Dict[str, Any] = {}

    def bind(self, **kwargs) -> "ModernLogger":
        """Bind contextual data to all subsequent log calls.

        Args:
            **kwargs: Key-value pairs to add to the logging context

        Returns:
            A new logger instance with the bound context

        Example:
            log = get_logger(__name__)
            user_log = log.bind(user_id=user_id, session_id=session_id)
            user_log.info("User action", action="login")
        """
        new_logger = ModernLogger(self._logger)
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def _log(self, level: int, msg: str, **kwargs):
        """Internal logging method that merges context."""
        if not self._logger.isEnabledFor(level):
            return

        # Merge bound context with call-specific kwargs
        extra = {**self._context, **kwargs}

        # Use structured logging format if extra data exists
        if extra:
            self._logger.log(level, msg, extra={"structured_data": extra})
        else:
            self._logger.log(level, msg)

    def debug(self, msg: str, **kwargs):
        """Log a debug message with optional structured data."""
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs):
        """Log an info message with optional structured data."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        """Log a warning message with optional structured data."""
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs):
        """Log an error message with optional structured data."""
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs):
        """Log a critical message with optional structured data."""
        self._log(logging.CRITICAL, msg, **kwargs)

    def lazy(self, level: int, func: Callable[[], str], **kwargs):
        """Log with lazy evaluation for expensive operations.

        The function is only called if the log level is enabled.

        Args:
            level: Logging level (e.g., logging.DEBUG)
            func: Function that returns the log message
            **kwargs: Additional structured data

        Example:
            log.lazy(logging.DEBUG, lambda: f"Complex: {expensive_calculation()}")
        """
        if not lazy_log_enabled(self._logger, level):
            return

        # Use the existing lazy logging infrastructure
        lazy_ctx = create_lazy_context(self._logger, level)

        # Add lazy message
        lazy_ctx.add_lazy_value("_message", func)

        # Add any additional kwargs as lazy values if they're callables
        for key, value in kwargs.items():
            if callable(value):
                lazy_ctx.add_lazy_value(key, value)
            else:
                lazy_ctx.add_static_value(key, value)

        # Add bound context as static values
        for key, value in self._context.items():
            lazy_ctx.add_static_value(key, value)

        # Log with the lazy context
        lazy_ctx.log(level, "")  # Message will come from _message lazy value

    @contextmanager
    def timed(self, operation: str, level: int = logging.INFO, **kwargs):
        """Context manager for timing operations.

        Args:
            operation: Name of the operation being timed
            level: Log level for the timing message
            **kwargs: Additional structured data

        Example:
            with log.timed("database_query", query_type="select"):
                result = db.execute(query)
        """
        start_time = time.perf_counter()

        # Log start if debug level
        if self._logger.isEnabledFor(logging.DEBUG):
            self._log(logging.DEBUG, f"Starting {operation}", operation=operation, **kwargs)

        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log(level, f"Completed {operation}", operation=operation, duration_ms=round(duration_ms, 2), **kwargs)

    def catch(
        self, exception: Type[Exception] = Exception, message: Optional[str] = None, level: int = logging.ERROR, reraise: bool = True
    ):
        """Decorator for automatic exception logging.

        Args:
            exception: Exception type to catch
            message: Optional custom error message
            level: Log level for the error
            reraise: Whether to re-raise the exception

        Example:
            @log.catch(ValueError, "Invalid user input")
            def process_input(data):
                return json.loads(data)
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exception as e:
                    error_msg = message or f"Exception in {func.__name__}"
                    self._log(
                        level, error_msg, function=func.__name__, exception_type=type(e).__name__, exception_message=str(e), exc_info=True
                    )
                    if reraise:
                        raise
                    return None

            return wrapper

        return decorator

    @contextmanager
    def suppress(self, exception: Type[Exception] = Exception, message: Optional[str] = None):
        """Context manager that suppresses and logs exceptions.

        Args:
            exception: Exception type to suppress
            message: Optional custom error message

        Example:
            with log.suppress(FileNotFoundError, "Config file missing"):
                config = load_config()
        """
        try:
            yield
        except exception as e:
            error_msg = message or f"Suppressed {type(e).__name__}"
            self._log(logging.WARNING, error_msg, exception_type=type(e).__name__, exception_message=str(e))

    def exception(self, msg: str, **kwargs):
        """Log an exception with traceback.

        Should be called from an exception handler.
        """
        self._logger.exception(msg, extra={"structured_data": {**self._context, **kwargs}})

    # Performance monitoring helpers
    def log_if_slow(self, threshold_ms: float = 100.0):
        """Decorator that logs if a function takes longer than threshold.

        Args:
            threshold_ms: Threshold in milliseconds

        Example:
            @log.log_if_slow(50.0)
            def process_data(data):
                return transform(data)
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    if duration_ms > threshold_ms:
                        self._log(
                            logging.WARNING,
                            f"Slow operation: {func.__name__}",
                            function=func.__name__,
                            duration_ms=round(duration_ms, 2),
                            threshold_ms=threshold_ms,
                        )

                    return result
                except Exception:
                    # Still log timing on exception
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    self._log(
                        logging.ERROR,
                        f"Failed operation: {func.__name__}",
                        function=func.__name__,
                        duration_ms=round(duration_ms, 2),
                        exc_info=True,
                    )
                    raise

            return wrapper

        return decorator

    # Compatibility methods
    def isEnabledFor(self, level: int) -> bool:
        """Check if a log level is enabled."""
        return self._logger.isEnabledFor(level)

    @property
    def name(self) -> str:
        """Get the logger name."""
        return self._logger.name

    @property
    def level(self) -> int:
        """Get the current log level."""
        return self._logger.level


def get_logger(name: str) -> ModernLogger:
    """Get a modern logger instance for the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        ModernLogger instance with enhanced API

    Example:
        log = get_logger(__name__)
        log.info("Application started", version="1.0.0")
    """
    base_logger = _get_base_logger(name)
    return ModernLogger(base_logger)


# Convenience function for module-level logger
def get_module_logger() -> ModernLogger:
    """Get a logger for the current module.

    This should be called at module level:
        log = get_module_logger()
    """
    import inspect

    frame = inspect.currentframe()
    if frame and frame.f_back:
        module = frame.f_back.f_globals.get("__name__", "unknown")
    else:
        module = "unknown"
    return get_logger(module)


# Example usage patterns
if __name__ == "__main__":
    # Get a logger
    log = get_logger("example")

    # Simple logging with structured data
    log.info("User logged in", user_id="123", ip_address="192.168.1.1")

    # Lazy evaluation for expensive operations
    log.lazy(logging.DEBUG, lambda: f"Debug info: {sum(range(1000000))}")

    # Timing operations
    with log.timed("database_operation", query="SELECT * FROM users"):
        time.sleep(0.1)  # Simulate work

    # Exception handling
    @log.catch(ValueError, "Failed to parse input")
    def parse_data(data):
        return int(data)

    # Bound context
    request_log = log.bind(request_id="abc123", user_id="456")
    request_log.info("Processing request")
    request_log.error("Request failed", error_code=500)

    # Performance monitoring
    @log.log_if_slow(10.0)
    def slow_function():
        time.sleep(0.02)
        return "done"

    slow_function()
