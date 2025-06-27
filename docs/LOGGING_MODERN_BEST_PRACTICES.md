# Letta Modern Logging Best Practices

This document provides comprehensive guidance on using Letta's modern logging system with performance optimizations, structured logging, and observability best practices.

## 🎯 Overview

Letta's logging system provides enterprise-grade observability with:
- **Performance-optimized** lazy evaluation and async processing
- **Structured logging** with JSON output and OpenTelemetry integration
- **Security-first** approach with automatic data sanitization
- **Production-ready** configuration with proper rotation and retention policies

## 🚀 Getting Started

### Basic Setup

```python
from letta.log import get_logger, get_async_logger

# Standard logger (backwards compatible)
logger = get_logger(__name__)
logger.info("Application started")

# Async logger for high-throughput scenarios
async_logger = get_async_logger(__name__)
async_logger.info("High-frequency operation")
```

### Configuration

```python
from letta.log import setup_async_logging

# Configure async logging at application startup
setup_async_logging(
    max_workers=2,
    queue_size=1000,
    batch_size=10,
    flush_interval=1.0
)
```

## 📈 Performance Optimization

### Lazy Log Evaluation

Use lazy evaluation for expensive operations to eliminate unnecessary work when logging is disabled:

```python
from letta.log import get_logger, create_lazy_context, lazy_log_enabled

logger = get_logger(__name__)

# ✅ Optimized: Only executes expensive operations if logging enabled
if lazy_log_enabled(logger, logging.INFO):
    lazy_ctx = create_lazy_context(logger, logging.INFO)
    lazy_ctx.add_lazy_value("metrics", lambda: calculate_expensive_metrics())
    lazy_ctx.add_lazy_json("request_data", complex_object)
    lazy_ctx.info("Operation completed")

# ❌ Avoid: Always executes expensive operations
metrics = calculate_expensive_metrics()  # Always runs
logger.info("Operation completed", extra={"metrics": metrics})
```

### Conditional Logging

Check log levels before expensive operations:

```python
from letta.log import lazy_log_enabled

# ✅ Optimized: Fast conditional check
if lazy_log_enabled(logger, logging.DEBUG):
    expensive_debug_data = serialize_complex_object()
    logger.debug("Debug info", extra={"data": expensive_debug_data})

# ❌ Avoid: Always processes data
expensive_debug_data = serialize_complex_object()  # Always runs
logger.debug("Debug info", extra={"data": expensive_debug_data})
```

### Async Logging for High-Throughput

Use async logging for operations that generate many log entries:

```python
from letta.log import get_async_logger

# ✅ For high-frequency operations
async_logger = get_async_logger("high_frequency_component")

# Non-blocking logging
for i in range(1000):
    async_logger.info(f"Processing item {i}")
```

## 🏗️ Structured Logging

### Consistent Extra Fields

Use consistent field names across your application:

```python
# ✅ Standard fields
logger.info("User action", extra={
    "user_id": "user_123",
    "organization_id": "org_456", 
    "request_id": "req_789",
    "correlation_id": "corr_abc",
    "action": "create_agent",
    "resource_id": "agent_def"
})
```

### Correlation IDs

Use correlation IDs to track operations across services:

```python
from letta.utils.logging_decorators import generate_correlation_id

correlation_id = generate_correlation_id()

logger.info("Starting operation", extra={
    "correlation_id": correlation_id,
    "operation": "agent_creation"
})

# Pass correlation_id through the call chain
result = await create_agent(correlation_id=correlation_id)

logger.info("Operation completed", extra={
    "correlation_id": correlation_id,
    "operation": "agent_creation",
    "result_id": result.id
})
```

## 🔧 Database Operation Logging

### Using Decorators

Apply logging decorators to database operations:

```python
from letta.utils.logging_decorators import db_create_logger, db_read_logger

class AgentManager:
    @db_create_logger(include_timing=True)
    async def create_agent(self, agent_data):
        # Automatically logs:
        # - Operation start/completion
        # - Timing metrics
        # - Result information
        # - Error handling
        return await self.db.create(agent_data)
    
    @db_read_logger(log_level="DEBUG")
    async def get_agent(self, agent_id):
        return await self.db.get(agent_id)
```

### Manual Logging with Context

For complex operations, use manual logging with rich context:

```python
from letta.utils.logging_decorators import get_operation_context

async def complex_agent_operation(self, agent_id, user_id):
    context = {
        "operation": "complex_agent_operation",
        "agent_id": agent_id,
        "user_id": user_id,
        "correlation_id": generate_correlation_id()
    }
    
    logger.info("Starting complex operation", extra=context)
    
    try:
        # Step 1
        logger.debug("Step 1: Validating agent", extra=context)
        agent = await self.validate_agent(agent_id)
        
        # Step 2  
        logger.debug("Step 2: Processing data", extra=context)
        result = await self.process_data(agent)
        
        # Success
        logger.info("Complex operation completed", extra={
            **context,
            "result_id": result.id,
            "steps_completed": 2
        })
        
        return result
        
    except Exception as e:
        logger.error("Complex operation failed", extra={
            **context,
            "error_type": type(e).__name__,
            "error_message": str(e)
        }, exc_info=True)
        raise
```

## 🔒 Security and Data Sanitization

### Automatic Sanitization

The logging system automatically sanitizes sensitive data:

```python
from letta.server.rest_api.utils.logging_sanitizer import sanitize_log_data

# Automatically sanitizes API keys, passwords, etc.
logger.info("User login", extra={
    "email": "user@example.com",  # Sanitized
    "api_key": "sk-1234567890",   # Masked as "sk-***90"
    "password": "secret123"       # Masked as "sec***"
})

# Manual sanitization
sensitive_data = {
    "user_input": "My API key is sk-abcdefghijk",
    "headers": {"Authorization": "Bearer token123"}
}
clean_data = sanitize_log_data(sensitive_data)
logger.info("Processing request", extra=clean_data)
```

### Audit Logging

Use the audit logger for security-sensitive operations:

```python
from letta.log import get_audit_logger

audit_logger = get_audit_logger(__name__)

# Authentication events
audit_logger.info("User authentication", extra={
    "event_type": "authentication",
    "user_id": user_id,
    "client_ip": request_ip,
    "user_agent": user_agent,
    "success": True,
    "timestamp": datetime.utcnow().isoformat()
})

# Authorization events
audit_logger.warning("Access denied", extra={
    "event_type": "authorization_denied",
    "user_id": user_id,
    "resource": "agent_123",
    "action": "delete",
    "reason": "insufficient_permissions"
})
```

## 📊 Performance Monitoring

### Service Method Monitoring

Use the combined service method decorator for comprehensive monitoring:

```python
from letta.utils.logging_decorators import service_method_logger

class AgentService:
    @service_method_logger(
        include_performance=True,
        warn_threshold_ms=1000,
        log_level="INFO"
    )
    async def create_agent(self, agent_data):
        # Automatically provides:
        # - Exception handling with context
        # - Performance monitoring
        # - Slow operation warnings
        return await self._create_agent_impl(agent_data)
```

### Manual Performance Tracking

For fine-grained performance monitoring:

```python
from letta.utils.logging_decorators import performance_monitor

@performance_monitor(
    threshold_ms=100,        # Log operations > 100ms
    warn_threshold_ms=500,   # Warn for operations > 500ms
    log_all=False           # Only log slow operations
)
async def process_llm_request(self, messages):
    return await self.llm_client.complete(messages)
```

## 🌐 HTTP Request Logging

### Middleware Configuration

Configure request logging middleware with optimal settings:

```python
from letta.server.rest_api.middleware.logging_middleware import RequestLoggingMiddleware

app.add_middleware(
    RequestLoggingMiddleware,
    log_level="INFO",
    log_request_body=False,      # Enable only for debugging
    log_response_body=False,     # Enable only for error responses
    max_body_size=10240,         # 10KB limit
    skip_paths={"/health", "/metrics"},
    enable_sampling=True,        # Prevent log flooding
    use_async_logging=True,      # Non-blocking logging
    use_lazy_logging=True        # Lazy evaluation
)
```

### Request Context Propagation

Use request context for consistent logging:

```python
from fastapi import Request

async def api_endpoint(request: Request):
    # Context automatically available
    user_id = getattr(request.state, "user_id", None)
    request_id = getattr(request.state, "request_id", None)
    
    logger.info("API endpoint called", extra={
        "user_id": user_id,
        "request_id": request_id,
        "endpoint": "/v1/agents/create"
    })
```

## 🔍 OpenTelemetry Integration

### Trace Correlation

Integrate with OpenTelemetry for distributed tracing:

```python
from letta.otel.tracing import get_trace_id, add_trace_attributes

# Get current trace context
trace_id = get_trace_id()

logger.info("Operation started", extra={
    "trace_id": trace_id,
    "operation": "agent_creation"
})

# Add custom attributes to trace
add_trace_attributes({
    "agent.id": agent_id,
    "user.id": user_id,
    "operation.type": "create"
})
```

### Span Events

Log important events within spans:

```python
from letta.otel.tracing import log_event

# Log span events
log_event("agent_validation_completed", {
    "agent_id": agent_id,
    "validation_time_ms": 45
})

log_event("database_operation_started", {
    "operation": "create_agent",
    "table": "agents"
})
```

## 📝 Error Handling

### Structured Error Logging

Provide rich context for errors:

```python
try:
    result = await risky_operation()
except SpecificError as e:
    logger.error("Specific error occurred", extra={
        "error_type": "SpecificError",
        "error_code": e.code,
        "operation": "risky_operation",
        "retry_count": retry_count,
        "user_id": user_id,
        "correlation_id": correlation_id
    }, exc_info=True)
    
except Exception as e:
    logger.critical("Unexpected error", extra={
        "error_type": type(e).__name__,
        "operation": "risky_operation",
        "user_id": user_id,
        "correlation_id": correlation_id,
        "system_state": get_system_state()
    }, exc_info=True)
```

### Exception Decorator

Use the exception handling decorator for consistent error logging:

```python
from letta.utils.logging_decorators import exception_handler

@exception_handler(
    log_level="ERROR",
    reraise=True,
    handle_sql_errors=True
)
async def database_operation(self):
    # Automatic exception handling with:
    # - Structured error context
    # - SQLAlchemy error details
    # - Correlation IDs
    # - Trace information
    pass
```

## 🎛️ Configuration Management

### Environment Variables

Configure logging via environment variables:

```bash
# Production settings
LETTA_DEBUG=false
LETTA_LOG_LEVEL=INFO

# Performance optimizations
LETTA_LOGGING_ASYNC_LOGGING_ENABLED=true
LETTA_LOGGING_ASYNC_LOGGING_MAX_WORKERS=2
LETTA_LOGGING_ASYNC_LOGGING_QUEUE_SIZE=1000
LETTA_LOGGING_LAZY_LOGGING_ENABLED=true

# OpenTelemetry
OTEL_SERVICE_NAME=letta-server
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_LOGS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp
```

### Programmatic Configuration

Configure logging programmatically:

```python
from letta.settings import settings
from letta.log import setup_async_logging

# Configure based on settings
if settings.log_settings.async_logging_enabled:
    setup_async_logging(
        max_workers=settings.log_settings.async_logging_max_workers,
        queue_size=settings.log_settings.async_logging_queue_size,
        batch_size=settings.log_settings.async_logging_batch_size,
        flush_interval=settings.log_settings.async_logging_flush_interval
    )
```

## 🧪 Testing and Monitoring

### Performance Testing

Test logging performance with the demo script:

```bash
python examples/logging_performance_demo.py
```

### Monitoring Metrics

Monitor logging system health:

```python
from letta.log import get_async_logging_metrics, get_global_performance_stats

# Async logging metrics
async_metrics = get_async_logging_metrics()
print(f"Queue size: {async_metrics['queue_size']}")
print(f"Entries processed: {async_metrics['entries_processed']}")
print(f"Processing time: {async_metrics['avg_processing_time_ms']:.2f}ms")

# Performance statistics
perf_stats = get_global_performance_stats()
for operation, metrics in perf_stats.items():
    print(f"{operation}:")
    print(f"  Average: {metrics['avg_ms']:.2f}ms")
    print(f"  95th percentile: {metrics['p95_ms']:.2f}ms")
    print(f"  Count: {metrics['count']}")
```

### Cache Monitoring

Monitor sanitization cache performance:

```python
from letta.server.rest_api.utils.logging_sanitizer import LoggingSanitizer

# Check cache statistics
cache_stats = LoggingSanitizer.get_cache_info()
print(f"Cache hit rate: {cache_stats['hit_rate']:.2%}")
print(f"Cache size: {cache_stats['currsize']}/{cache_stats['maxsize']}")

# Clear cache if needed
LoggingSanitizer.clear_cache()
```

## 📋 Best Practices Summary

### ✅ Do's

1. **Use lazy evaluation** for expensive operations
2. **Check log levels** before expensive calculations
3. **Use async logging** for high-throughput scenarios
4. **Include correlation IDs** for request tracking
5. **Use structured logging** with consistent field names
6. **Apply security sanitization** for sensitive data
7. **Monitor performance** with built-in metrics
8. **Use decorators** for consistent database logging
9. **Leverage OpenTelemetry** for distributed tracing
10. **Configure retention policies** for compliance

### ❌ Don'ts

1. **Don't perform expensive operations** without conditional checks
2. **Don't log sensitive data** without sanitization
3. **Don't use print statements** in production code
4. **Don't ignore correlation IDs** in multi-step operations
5. **Don't log at DEBUG level** in production without good reason
6. **Don't create loggers** with direct `logging.getLogger()`
7. **Don't skip error context** in exception handlers
8. **Don't forget to configure** log rotation and retention
9. **Don't block request threads** with synchronous logging
10. **Don't ignore performance metrics** and monitoring

## 🔗 Related Documentation

- [Logging Performance Optimizations](LOGGING_PERFORMANCE_OPTIMIZATIONS.md)
- [Logging Improvements Summary](LOGGING_IMPROVEMENTS_SUMMARY.md)
- [OpenTelemetry Integration](../letta/otel/README.md)
- [Security Best Practices](SECURITY_BEST_PRACTICES.md)
- [Development Environment Setup](../CLAUDE.md)

This comprehensive guide provides the foundation for implementing modern, performant, and secure logging practices in your Letta applications.