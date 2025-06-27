# Letta Logging System Migration Guide

This guide provides step-by-step instructions for upgrading to Letta's modern logging system with performance optimizations, structured logging, and enhanced observability features.

## 🎯 Overview

The new logging system provides:
- **70-90% performance improvement** when logging is disabled
- **Non-blocking async logging** for high-throughput scenarios
- **Automatic security sanitization** of sensitive data
- **Structured JSON logging** for Kubernetes environments
- **OpenTelemetry integration** for distributed tracing
- **Production-ready configurations** with proper retention policies

## 🔄 Migration Strategy

### Phase 1: Basic Compatibility (Zero Downtime)

The new logging system is **100% backwards compatible**. Your existing code will continue to work without any changes:

```python
# ✅ This continues to work exactly as before
from letta.log import get_logger

logger = get_logger(__name__)
logger.info("This works without changes")
logger.error("Error message", extra={"key": "value"})
```

### Phase 2: Performance Optimization (Gradual)

Incrementally adopt performance optimizations:

#### 2.1 Add Conditional Checks

Before:
```python
# ❌ Always calculates expensive data
complex_data = serialize_complex_object()
logger.debug(f"Complex data: {complex_data}")
```

After:
```python
# ✅ Only calculates if debug logging enabled
from letta.log import lazy_log_enabled

if lazy_log_enabled(logger, logging.DEBUG):
    complex_data = serialize_complex_object()
    logger.debug(f"Complex data: {complex_data}")
```

#### 2.2 Use Lazy Contexts

Before:
```python
# ❌ Always performs expensive operations
metrics = calculate_metrics()
request_data = request.dict()
logger.info("Request processed", extra={
    "metrics": metrics,
    "request_data": request_data
})
```

After:
```python
# ✅ Lazy evaluation with deferred operations
from letta.log import create_lazy_context, lazy_log_enabled

if lazy_log_enabled(logger, logging.INFO):
    lazy_ctx = create_lazy_context(logger, logging.INFO)
    lazy_ctx.add_lazy_value("metrics", lambda: calculate_metrics())
    lazy_ctx.add_lazy_json("request_data", request)
    lazy_ctx.info("Request processed")
```

### Phase 3: Advanced Features (Optional)

Adopt advanced features as needed:

#### 3.1 Database Operation Decorators

Before:
```python
async def create_agent(self, agent_data):
    logger.info("Creating agent", extra={"agent_type": agent_data.type})
    try:
        result = await self.db.create(agent_data)
        logger.info("Agent created", extra={"agent_id": result.id})
        return result
    except Exception as e:
        logger.error("Failed to create agent", extra={"error": str(e)})
        raise
```

After:
```python
from letta.utils.logging_decorators import db_create_logger

@db_create_logger(include_timing=True, include_result_info=True)
async def create_agent(self, agent_data):
    # Automatic logging of:
    # - Operation start/completion
    # - Timing metrics
    # - Result information  
    # - Error handling with context
    return await self.db.create(agent_data)
```

#### 3.2 Async Logging for High-Throughput

Before:
```python
# ❌ Synchronous logging can block request processing
for i in range(1000):
    logger.info(f"Processing item {i}")
```

After:
```python
from letta.log import get_async_logger

# ✅ Non-blocking async logging
async_logger = get_async_logger(__name__)
for i in range(1000):
    async_logger.info(f"Processing item {i}")
```

## 🚀 Quick Start Migration

### Step 1: Update Configuration

Add performance settings to your environment:

```bash
# Add to your .env or environment variables
LETTA_LOGGING_ASYNC_LOGGING_ENABLED=true
LETTA_LOGGING_ASYNC_LOGGING_MAX_WORKERS=2
LETTA_LOGGING_ASYNC_LOGGING_QUEUE_SIZE=1000
LETTA_LOGGING_LAZY_LOGGING_ENABLED=true
LETTA_LOGGING_LAZY_LOGGING_THRESHOLD_MS=1.0
```

### Step 2: Setup Async Logging (Optional)

Add to your application startup:

```python
from letta.log import setup_async_logging

# Configure async logging at startup
setup_async_logging(
    max_workers=2,
    queue_size=1000,
    batch_size=10,
    flush_interval=1.0
)
```

### Step 3: Test the Migration

Run the performance test to verify improvements:

```bash
python examples/logging_performance_demo.py
```

## 📋 Migration Checklist

### ✅ Immediate Actions (Zero Risk)

- [ ] Update environment variables with new logging settings
- [ ] Verify existing logging continues to work
- [ ] Check log file locations (`~/.letta/logs/`)
- [ ] Test logging configuration with demo script
- [ ] Review log retention policies

### ✅ Performance Optimization Actions (Low Risk)

- [ ] Add conditional checks (`lazy_log_enabled`) for expensive operations
- [ ] Replace complex string formatting with lazy contexts
- [ ] Setup async logging for high-throughput components
- [ ] Apply database operation decorators to service methods
- [ ] Monitor performance improvements with built-in metrics

### ✅ Advanced Integration Actions (Medium Risk)

- [ ] Enable OpenTelemetry integration for distributed tracing
- [ ] Configure structured JSON logging for Kubernetes
- [ ] Setup audit logging for security compliance
- [ ] Implement request correlation across microservices
- [ ] Configure log aggregation and monitoring

## 🔧 Configuration Migration

### Old Configuration Pattern

Before:
```python
import logging

# Basic logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
```

### New Configuration Pattern

After:
```python
from letta.log import get_logger, setup_async_logging
from letta.settings import settings

# Modern logging setup with async support
if settings.log_settings.async_logging_enabled:
    setup_async_logging(
        max_workers=settings.log_settings.async_logging_max_workers,
        queue_size=settings.log_settings.async_logging_queue_size,
        batch_size=settings.log_settings.async_logging_batch_size,
        flush_interval=settings.log_settings.async_logging_flush_interval
    )

logger = get_logger(__name__)
```

## 🏗️ Code Patterns Migration

### 1. High-Frequency Logging

**LLM API Calls (High Impact)**

Before:
```python
# ❌ Always calculates metrics even if logging disabled
def _log_llm_request(self, messages, provider):
    num_messages = len(messages)
    total_chars = sum(len(str(msg.text)) for msg in messages if hasattr(msg, 'text'))
    avg_length = total_chars / num_messages if num_messages > 0 else 0
    
    self.logger.info("LLM request", extra={
        "provider": provider,
        "num_messages": num_messages,
        "total_chars": total_chars,
        "avg_length": avg_length
    })
```

After:
```python
# ✅ Lazy evaluation - only calculates if logging enabled
from letta.log import lazy_log_enabled, create_lazy_context

def _log_llm_request(self, messages, provider):
    if lazy_log_enabled(self.logger, logging.INFO):
        def calculate_metrics():
            num_messages = len(messages)
            total_chars = sum(len(str(msg.text)) for msg in messages if hasattr(msg, 'text'))
            return {
                "provider": provider,
                "num_messages": num_messages,
                "total_chars": total_chars,
                "avg_length": total_chars / num_messages if num_messages > 0 else 0
            }
        
        lazy_ctx = create_lazy_context(self.logger, logging.INFO)
        lazy_ctx.add_lazy_value("metrics", calculate_metrics)
        lazy_ctx.info("LLM request")
```

### 2. Request Logging

**HTTP Middleware (Medium Impact)**

Before:
```python
# ❌ Synchronous logging can block requests
def log_request(self, request, response, duration):
    logger.info(
        f"HTTP {request.method} {request.url.path} -> {response.status_code} in {duration:.2f}ms",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration,
            "user_id": getattr(request.state, "user_id", None)
        }
    )
```

After:
```python
# ✅ Async logging with automatic sanitization
from letta.log import get_async_logger

def __init__(self):
    self.async_logger = get_async_logger(__name__)

def log_request(self, request, response, duration):
    # Non-blocking async logging with automatic sanitization
    self.async_logger.info(
        f"HTTP {request.method} {request.url.path} -> {response.status_code} in {duration:.2f}ms",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code, 
            "duration_ms": duration,
            "user_id": getattr(request.state, "user_id", None),
            "request_id": getattr(request.state, "request_id", None)
        }
    )
```

### 3. Database Operations

**Service Methods (High Impact)**

Before:
```python
# ❌ Manual logging with inconsistent patterns
async def create_agent(self, actor, agent_state):
    correlation_id = str(uuid.uuid4())
    
    logger.info("Creating agent", extra={
        "user_id": actor.id,
        "agent_type": agent_state.agent_type,
        "correlation_id": correlation_id
    })
    
    start_time = time.time()
    try:
        result = await self.agent_orm.create(agent_state)
        duration = time.time() - start_time
        
        logger.info("Agent created successfully", extra={
            "agent_id": result.id,
            "user_id": actor.id,
            "duration_ms": duration * 1000,
            "correlation_id": correlation_id
        })
        
        return result
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error("Failed to create agent", extra={
            "user_id": actor.id,
            "error": str(e),
            "error_type": type(e).__name__,
            "duration_ms": duration * 1000,
            "correlation_id": correlation_id
        }, exc_info=True)
        raise
```

After:
```python
# ✅ Decorator-based logging with automatic context
from letta.utils.logging_decorators import db_create_logger

@db_create_logger(
    operation_type="create_agent",
    include_timing=True,
    include_result_info=True
)
async def create_agent(self, actor, agent_state):
    # Automatic logging provides:
    # - Operation start/completion messages
    # - Timing metrics and performance monitoring
    # - Result information (ID, count, etc.)
    # - Error handling with full context
    # - Correlation IDs and trace integration
    # - User and organization context
    return await self.agent_orm.create(agent_state)
```

## 🔍 Monitoring and Validation

### Performance Monitoring

Monitor the impact of your migration:

```python
from letta.log import get_async_logging_metrics, get_global_performance_stats

# Check async logging performance
async_metrics = get_async_logging_metrics()
print(f"Queue size: {async_metrics['queue_size']}")
print(f"Entries processed: {async_metrics['entries_processed']}")
print(f"Average processing time: {async_metrics['avg_processing_time_ms']:.2f}ms")

# Check overall performance statistics
perf_stats = get_global_performance_stats()
for operation, metrics in perf_stats.items():
    print(f"{operation}: {metrics['avg_ms']:.2f}ms avg, {metrics['count']} calls")
```

### Cache Performance

Monitor sanitization cache effectiveness:

```python
from letta.server.rest_api.utils.logging_sanitizer import LoggingSanitizer

cache_stats = LoggingSanitizer.get_cache_info()
print(f"Cache hit rate: {cache_stats['hit_rate']:.2%}")
print(f"Cache utilization: {cache_stats['currsize']}/{cache_stats['maxsize']}")

# Clear cache if needed (rare)
if cache_stats['hit_rate'] < 0.8:
    LoggingSanitizer.clear_cache()
```

## 🐛 Troubleshooting

### Common Issues

#### Issue 1: Performance Not Improved

**Symptom**: No performance improvement after migration

**Solution**: 
```python
# Check if lazy logging is actually enabled
from letta.log import lazy_log_enabled
import logging

logger = get_logger(__name__)
print(f"Lazy logging enabled: {lazy_log_enabled(logger, logging.DEBUG)}")

# Verify conditional checks are being used
if not lazy_log_enabled(logger, logging.DEBUG):
    print("Expensive operations should be skipped")
```

#### Issue 2: Missing Log Entries

**Symptom**: Some log entries are missing with async logging

**Solution**:
```python
# Ensure proper shutdown to flush async logs
import atexit
from letta.log import shutdown_async_logging

atexit.register(shutdown_async_logging)

# Or manually flush before exit
shutdown_async_logging()
```

#### Issue 3: High Memory Usage

**Symptom**: Memory usage increases with async logging

**Solution**:
```bash
# Reduce queue size
LETTA_LOGGING_ASYNC_LOGGING_QUEUE_SIZE=500

# Reduce batch size
LETTA_LOGGING_ASYNC_LOGGING_BATCH_SIZE=5

# Reduce worker count
LETTA_LOGGING_ASYNC_LOGGING_MAX_WORKERS=1
```

### Validation Checklist

After migration, verify:

- [ ] **Performance**: Run `python examples/logging_performance_demo.py`
- [ ] **Functionality**: All existing log messages still appear
- [ ] **Format**: Log format matches expectations (JSON in production)
- [ ] **Files**: Log files created in `~/.letta/logs/` directory
- [ ] **Rotation**: Log files rotate according to size limits
- [ ] **Sanitization**: Sensitive data is properly masked
- [ ] **Correlation**: Request IDs appear in related log entries
- [ ] **Traces**: OpenTelemetry traces correlate with logs (if enabled)

## 🎯 Best Practices After Migration

### 1. Gradual Rollout

- Start with low-risk, high-impact components (database operations)
- Monitor performance improvements before expanding
- Keep fallback options available during migration

### 2. Performance Monitoring

- Set up regular performance monitoring
- Track cache hit rates and async queue metrics
- Monitor log file sizes and rotation

### 3. Security Considerations

- Verify sensitive data sanitization in production
- Review audit log retention policies
- Ensure proper access controls on log files

### 4. Operational Excellence

- Document any custom logging patterns
- Train team on new logging capabilities
- Update monitoring and alerting based on new log structure

## 📚 Additional Resources

- [Logging Modern Best Practices](LOGGING_MODERN_BEST_PRACTICES.md)
- [Logging Performance Optimizations](LOGGING_PERFORMANCE_OPTIMIZATIONS.md)
- [Logging Improvements Summary](LOGGING_IMPROVEMENTS_SUMMARY.md)
- [OpenTelemetry Integration Guide](../letta/otel/README.md)

## 🎉 Success Metrics

After successful migration, you should see:

- **70-90% performance improvement** in high-frequency logging scenarios
- **Reduced request latency** due to non-blocking async logging
- **Better observability** with structured logs and correlation IDs
- **Enhanced security** with automatic data sanitization
- **Improved troubleshooting** with rich error context and tracing

## 🔄 Rollback Plan

If issues arise, you can safely rollback:

1. **Disable performance features**:
   ```bash
   LETTA_LOGGING_ASYNC_LOGGING_ENABLED=false
   LETTA_LOGGING_LAZY_LOGGING_ENABLED=false
   ```

2. **Remove decorators** and use manual logging temporarily

3. **Revert to basic logging** patterns while addressing issues

4. **Gradually re-enable features** once issues are resolved

The migration is designed to be safe and reversible at any stage.