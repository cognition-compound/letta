"""
Asynchronous logging infrastructure for high-throughput operations.

This module provides non-blocking logging capabilities using ThreadPoolExecutor
to prevent logging from blocking request processing threads.
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from contextlib import contextmanager
from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable, Dict, List, Optional, Union

from letta.log import get_logger
from letta.settings import settings


@dataclass
class AsyncLogEntry:
    """Represents a log entry to be processed asynchronously."""
    logger_name: str
    level: int
    message: str
    args: tuple
    kwargs: dict
    timestamp: float
    thread_id: int
    
    def __post_init__(self):
        # Ensure we have a timestamp
        if not self.timestamp:
            self.timestamp = time.time()
        
        # Ensure we have a thread ID
        if not self.thread_id:
            self.thread_id = threading.get_ident()


class AsyncLoggingHandler(logging.Handler):
    """
    Logging handler that queues log records for asynchronous processing.
    
    This handler prevents logging from blocking the main application threads
    by queuing log records and processing them in a separate thread pool.
    """
    
    def __init__(
        self,
        max_workers: int = 2,
        queue_size: int = 1000,
        batch_size: int = 10,
        flush_interval: float = 1.0,
        level: int = logging.INFO
    ):
        super().__init__(level)
        self.max_workers = max_workers
        self.queue_size = queue_size
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        # Thread pool for async processing
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="async_log"
        )
        
        # Queue for log entries
        self.log_queue: Queue[AsyncLogEntry] = Queue(maxsize=queue_size)
        
        # Background thread for processing queue
        self._processing_thread = None
        self._shutdown_event = threading.Event()
        self._start_processing_thread()
        
        # Track metrics
        self.metrics = {
            'entries_processed': 0,
            'entries_dropped': 0,
            'processing_errors': 0,
            'queue_full_events': 0
        }
    
    def _start_processing_thread(self):
        """Start the background thread for processing log entries."""
        self._processing_thread = threading.Thread(
            target=self._process_log_queue,
            name="async_log_processor",
            daemon=True
        )
        self._processing_thread.start()
    
    def _process_log_queue(self):
        """Process log entries from the queue in batches."""
        batch = []
        last_flush = time.time()
        
        while not self._shutdown_event.is_set():
            try:
                # Try to get a log entry with timeout
                try:
                    entry = self.log_queue.get(timeout=0.1)
                    batch.append(entry)
                except:
                    # Timeout - check if we should flush
                    pass
                
                # Check if we should process the batch
                should_flush = (
                    len(batch) >= self.batch_size or
                    (batch and time.time() - last_flush >= self.flush_interval)
                )
                
                if should_flush and batch:
                    self._process_batch(batch)
                    batch = []
                    last_flush = time.time()
                    
            except Exception as e:
                self.metrics['processing_errors'] += 1
                # Try to log the error, but avoid infinite loops
                try:
                    logger = get_logger(__name__)
                    logger.error(f"Error processing async log queue: {e}", exc_info=True)
                except:
                    pass
        
        # Process remaining entries on shutdown
        if batch:
            self._process_batch(batch)
    
    def _process_batch(self, batch: List[AsyncLogEntry]):
        """Process a batch of log entries."""
        futures = []
        
        for entry in batch:
            future = self.executor.submit(self._process_log_entry, entry)
            futures.append(future)
        
        # Wait for all entries in the batch to complete
        for future in futures:
            try:
                future.result(timeout=5.0)  # 5 second timeout per entry
                self.metrics['entries_processed'] += 1
            except Exception as e:
                self.metrics['processing_errors'] += 1
                # Log processing error without creating a loop
                try:
                    logger = get_logger(__name__)
                    logger.error(f"Error processing async log entry: {e}")
                except:
                    pass
    
    def _process_log_entry(self, entry: AsyncLogEntry):
        """Process a single log entry."""
        try:
            # Get the logger and emit the record
            logger = logging.getLogger(entry.logger_name)
            
            # Create a log record
            record = logging.LogRecord(
                name=entry.logger_name,
                level=entry.level,
                pathname="",
                lineno=0,
                msg=entry.message,
                args=entry.args,
                exc_info=None
            )
            
            # Add extra attributes
            for key, value in entry.kwargs.items():
                setattr(record, key, value)
            
            # Set timestamp and thread info
            record.created = entry.timestamp
            record.thread = entry.thread_id
            
            # Emit to the logger's handlers (but skip async handlers to avoid loops)
            for handler in logger.handlers:
                if not isinstance(handler, AsyncLoggingHandler):
                    handler.emit(record)
                    
        except Exception as e:
            self.metrics['processing_errors'] += 1
            raise
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record by queueing it for async processing."""
        try:
            # Extract extra attributes
            extra = {}
            for key, value in record.__dict__.items():
                if key not in {'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                              'filename', 'module', 'lineno', 'funcName', 'created', 
                              'msecs', 'relativeCreated', 'thread', 'threadName', 
                              'processName', 'process', 'message', 'exc_info', 'exc_text', 
                              'stack_info', 'getMessage'}:
                    extra[key] = value
            
            # Create async log entry
            entry = AsyncLogEntry(
                logger_name=record.name,
                level=record.levelno,
                message=record.getMessage(),
                args=(),
                kwargs=extra,
                timestamp=record.created,
                thread_id=record.thread
            )
            
            # Try to queue the entry
            try:
                self.log_queue.put_nowait(entry)
            except:
                # Queue is full - increment counter and drop the entry
                self.metrics['queue_full_events'] += 1
                self.metrics['entries_dropped'] += 1
                
        except Exception as e:
            self.metrics['processing_errors'] += 1
            # Fallback to synchronous logging
            try:
                super().emit(record)
            except:
                pass
    
    def close(self):
        """Close the handler and clean up resources."""
        # Signal shutdown
        self._shutdown_event.set()
        
        # Wait for processing thread to finish
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=5.0)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        super().close()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics about async logging performance."""
        return {
            **self.metrics,
            'queue_size': self.log_queue.qsize(),
            'max_queue_size': self.queue_size,
            'executor_threads': len(self.executor._threads) if hasattr(self.executor, '_threads') else 0
        }


class AsyncLogger:
    """
    Wrapper around a regular logger that provides async logging capabilities.
    """
    
    def __init__(self, logger: logging.Logger, async_handler: Optional[AsyncLoggingHandler] = None):
        self.logger = logger
        self.async_handler = async_handler
        self._sync_fallback = True
    
    def _should_use_async(self) -> bool:
        """Determine if async logging should be used."""
        return (
            self.async_handler is not None and
            not self.async_handler._shutdown_event.is_set()
        )
    
    def debug(self, message: str, *args, **kwargs):
        """Log a debug message."""
        self._log(logging.DEBUG, message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log an info message."""
        self._log(logging.INFO, message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log a warning message."""
        self._log(logging.WARNING, message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log an error message."""
        self._log(logging.ERROR, message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log a critical message."""
        self._log(logging.CRITICAL, message, *args, **kwargs)
    
    def _log(self, level: int, message: str, *args, **kwargs):
        """Internal logging method."""
        if not self.logger.isEnabledFor(level):
            return
        
        if self._should_use_async():
            # Create log record and emit through async handler
            record = self.logger.makeRecord(
                self.logger.name, level, "", 0, message, args, None, 
                func=None, extra=kwargs.get('extra', {})
            )
            self.async_handler.emit(record)
        else:
            # Fallback to sync logging
            self.logger.log(level, message, *args, **kwargs)


# Global async logging infrastructure
_global_async_handler: Optional[AsyncLoggingHandler] = None
_async_loggers: Dict[str, AsyncLogger] = {}


def setup_async_logging(
    max_workers: int = 2,
    queue_size: int = 1000,
    batch_size: int = 10,
    flush_interval: float = 1.0,
    level: int = logging.INFO
) -> AsyncLoggingHandler:
    """Set up global async logging infrastructure."""
    global _global_async_handler
    
    # Shutdown existing handler if present
    if _global_async_handler:
        _global_async_handler.close()
    
    # Create new handler
    _global_async_handler = AsyncLoggingHandler(
        max_workers=max_workers,
        queue_size=queue_size,
        batch_size=batch_size,
        flush_interval=flush_interval,
        level=level
    )
    
    return _global_async_handler


def get_async_logger(name: str) -> AsyncLogger:
    """Get an async logger for the given name."""
    if name not in _async_loggers:
        regular_logger = get_logger(name)
        _async_loggers[name] = AsyncLogger(regular_logger, _global_async_handler)
    
    return _async_loggers[name]


def shutdown_async_logging():
    """Shutdown global async logging infrastructure."""
    global _global_async_handler, _async_loggers
    
    if _global_async_handler:
        _global_async_handler.close()
        _global_async_handler = None
    
    _async_loggers.clear()


def get_async_logging_metrics() -> Optional[Dict[str, Any]]:
    """Get metrics about async logging performance."""
    if _global_async_handler:
        return _global_async_handler.get_metrics()
    return None


@contextmanager
def async_logging_context(
    max_workers: int = 2,
    queue_size: int = 1000,
    batch_size: int = 10,
    flush_interval: float = 1.0
):
    """Context manager for async logging."""
    handler = setup_async_logging(
        max_workers=max_workers,
        queue_size=queue_size,
        batch_size=batch_size,
        flush_interval=flush_interval
    )
    
    try:
        yield handler
    finally:
        shutdown_async_logging()


# Auto-setup based on settings
def auto_setup_async_logging():
    """Auto-setup async logging based on settings."""
    if hasattr(settings, 'async_logging_enabled') and settings.async_logging_enabled:
        max_workers = getattr(settings, 'async_logging_max_workers', 2)
        queue_size = getattr(settings, 'async_logging_queue_size', 1000)
        batch_size = getattr(settings, 'async_logging_batch_size', 10)
        flush_interval = getattr(settings, 'async_logging_flush_interval', 1.0)
        
        setup_async_logging(
            max_workers=max_workers,
            queue_size=queue_size,
            batch_size=batch_size,
            flush_interval=flush_interval
        )