#!/usr/bin/env python3
"""
Demonstration of Letta's performance-optimized logging features.

This script shows how to use the lazy evaluation and asynchronous logging
capabilities to improve performance in high-throughput scenarios.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any

# Import Letta's performance-optimized logging utilities
from letta.log import (
    get_logger,
    create_lazy_context,
    lazy_log_enabled,
    setup_async_logging,
    get_async_logger,
    performance_timer,
    LazyJsonString,
    ConditionalLogger,
    create_conditional_logger,
    log_performance_summary,
    get_global_performance_stats
)


def simulate_expensive_data_creation() -> Dict[str, Any]:
    """Simulate creating expensive data for logging."""
    # Simulate work by sleeping briefly
    time.sleep(0.001)  # 1ms of work
    
    return {
        "complex_data": {
            "nested_structure": {
                "items": [f"item_{i}" for i in range(100)],
                "metadata": {
                    "processed_at": time.time(),
                    "processor_info": {
                        "version": "1.0.0",
                        "capabilities": ["feature_a", "feature_b", "feature_c"]
                    }
                }
            }
        },
        "performance_metrics": {
            "processing_time_ms": 42.5,
            "memory_usage_mb": 128.7,
            "cpu_utilization": 0.65
        }
    }


def demo_traditional_logging():
    """Demonstrate traditional logging performance issues."""
    logger = get_logger("traditional_demo")
    
    print("🐌 Traditional Logging Demo (with performance issues)")
    
    start_time = time.time()
    
    # This will always execute the expensive operation, even if logging is disabled
    for i in range(100):
        expensive_data = simulate_expensive_data_creation()
        logger.debug(f"Processing item {i}: {json.dumps(expensive_data, indent=2)}")
    
    duration = time.time() - start_time
    print(f"   Traditional logging took: {duration:.3f} seconds")
    return duration


def demo_lazy_logging():
    """Demonstrate lazy logging with performance improvements."""
    logger = get_logger("lazy_demo")
    
    print("🚀 Lazy Logging Demo (performance optimized)")
    
    start_time = time.time()
    
    # Only create expensive data if logging is actually enabled
    for i in range(100):
        if lazy_log_enabled(logger, logging.DEBUG):
            lazy_ctx = create_lazy_context(logger, logging.DEBUG)
            lazy_ctx.add_value("item_number", i)
            lazy_ctx.add_lazy_json("expensive_data", lambda: simulate_expensive_data_creation())
            lazy_ctx.debug(f"Processing item {i}")
    
    duration = time.time() - start_time
    print(f"   Lazy logging took: {duration:.3f} seconds")
    return duration


def demo_conditional_logger():
    """Demonstrate the ConditionalLogger wrapper."""
    logger = get_logger("conditional_demo")
    conditional_logger = create_conditional_logger(logger, performance_monitoring=True)
    
    print("🎯 Conditional Logger Demo")
    
    start_time = time.time()
    
    for i in range(100):
        # Only execute the lambda if debug logging is enabled
        conditional_logger.debug_if_enabled(
            lambda: f"Processing item {i}: {json.dumps(simulate_expensive_data_creation(), indent=2)}"
        )
    
    duration = time.time() - start_time
    print(f"   Conditional logging took: {duration:.3f} seconds")
    
    # Show performance stats
    stats = conditional_logger.get_operation_stats()
    if stats:
        print(f"   Performance stats: {stats}")
    
    return duration


async def demo_async_logging():
    """Demonstrate asynchronous logging."""
    print("⚡ Async Logging Demo")
    
    # Setup async logging
    setup_async_logging(max_workers=2, queue_size=1000)
    async_logger = get_async_logger("async_demo")
    
    start_time = time.time()
    
    # Log many messages asynchronously
    tasks = []
    for i in range(100):
        # Create expensive data
        expensive_data = simulate_expensive_data_creation()
        
        # Log asynchronously (non-blocking)
        async_logger.info(f"Async processing item {i}: {json.dumps(expensive_data)}")
    
    # Wait a moment for async logging to process
    await asyncio.sleep(0.1)
    
    duration = time.time() - start_time
    print(f"   Async logging took: {duration:.3f} seconds")
    return duration


def demo_performance_monitoring():
    """Demonstrate performance monitoring capabilities."""
    logger = get_logger("performance_demo")
    
    print("📊 Performance Monitoring Demo")
    
    # Use performance timer context manager
    with performance_timer(logger, "complex_operation", logging.INFO):
        # Simulate some work
        time.sleep(0.05)  # 50ms of work
        
        # Log with lazy evaluation
        if lazy_log_enabled(logger, logging.INFO):
            lazy_ctx = create_lazy_context(logger, logging.INFO)
            lazy_ctx.add_lazy_value("result", simulate_expensive_data_creation)
            lazy_ctx.info("Complex operation completed")


def demo_lazy_json_serialization():
    """Demonstrate lazy JSON serialization."""
    logger = get_logger("json_demo")
    
    print("📝 Lazy JSON Serialization Demo")
    
    start_time = time.time()
    
    for i in range(100):
        if lazy_log_enabled(logger, logging.DEBUG):
            # JSON serialization only happens if logging is enabled
            lazy_json = LazyJsonString(simulate_expensive_data_creation(), indent=2)
            logger.debug(f"Item {i}: {lazy_json}")
    
    duration = time.time() - start_time
    print(f"   Lazy JSON serialization took: {duration:.3f} seconds")
    return duration


async def main():
    """Run all logging performance demonstrations."""
    print("🚀 Letta Logging Performance Optimization Demo")
    print("=" * 60)
    
    # Set logging level to WARNING to see the performance difference
    # (DEBUG logs will be skipped, showing the optimization benefit)
    logging.getLogger().setLevel(logging.WARNING)
    print("ℹ️  Note: Logging level set to WARNING to demonstrate optimization benefits")
    print()
    
    # Run traditional vs optimized logging comparisons
    traditional_time = demo_traditional_logging()
    print()
    
    lazy_time = demo_lazy_logging()
    print()
    
    conditional_time = demo_conditional_logger()
    print()
    
    await demo_async_logging()
    print()
    
    demo_performance_monitoring()
    print()
    
    json_time = demo_lazy_json_serialization()
    print()
    
    # Calculate performance improvements
    print("📈 Performance Summary")
    print("-" * 40)
    print(f"Traditional logging:     {traditional_time:.3f}s")
    print(f"Lazy logging:           {lazy_time:.3f}s")
    print(f"Conditional logging:    {conditional_time:.3f}s")
    print(f"Lazy JSON:              {json_time:.3f}s")
    
    if traditional_time > 0:
        lazy_improvement = ((traditional_time - lazy_time) / traditional_time) * 100
        conditional_improvement = ((traditional_time - conditional_time) / traditional_time) * 100
        json_improvement = ((traditional_time - json_time) / traditional_time) * 100
        
        print()
        print("🎯 Performance Improvements:")
        print(f"Lazy logging:        {lazy_improvement:.1f}% faster")
        print(f"Conditional logging: {conditional_improvement:.1f}% faster")
        print(f"Lazy JSON:          {json_improvement:.1f}% faster")
    
    # Show global performance statistics
    print()
    print("📊 Global Performance Stats:")
    stats = get_global_performance_stats()
    for operation, metrics in stats.items():
        print(f"   {operation}: avg={metrics['avg_ms']:.2f}ms, count={metrics['count']}")
    
    # Log performance summary
    log_performance_summary()
    
    print()
    print("✨ Demo completed! The performance optimizations significantly reduce")
    print("   CPU overhead when logging is disabled or when processing expensive data.")


if __name__ == "__main__":
    asyncio.run(main())