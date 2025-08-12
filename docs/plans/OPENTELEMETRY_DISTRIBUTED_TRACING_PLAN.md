# OpenTelemetry Distributed Tracing Implementation Plan

## Technical Overview

This plan adds OpenTelemetry distributed tracing to complement the existing structured logging system, providing visual workflow representation and automatic performance monitoring for multi-agent workflows.

## Current State Analysis

### Existing Infrastructure
- **Structured Logging**: Business flow events with correlation IDs (`letta/log/workflow_tracker.py`)
- **OTEL Integration**: Basic OpenTelemetry setup in logging system (`letta/log.py`)
- **Correlation System**: Request and workflow IDs (`letta/server/rest_api/middleware/logging_middleware.py`)
- **Business Events**: Agent steps, tool execution, communication flow logging

### Missing Components
- Distributed trace context propagation across agent boundaries
- Span hierarchy for workflow visualization
- Automatic timing instrumentation for performance bottlenecks
- Cross-agent trace correlation

## Trace Architecture Design

### Span Hierarchy Structure
```
HTTP Request (root span)
├── Agent Workflow
│   ├── Agent Step 1
│   │   ├── Tool Execution (parallel group)
│   │   │   ├── send() tool
│   │   │   │   └── Agent Message Processing (distributed)
│   │   │   ├── search_files() tool
│   │   │   └── archival_memory_insert() tool
│   │   └── LLM Request
│   └── Agent Step 2 (if heartbeat continues)
└── Response Generation
```

### Trace Context Flow
1. **Inbound HTTP**: Root span created in middleware
2. **Agent Workflows**: Child spans with agent context
3. **Tool Execution**: Parallel spans for concurrent tools
4. **Cross-Agent Messages**: Distributed spans with trace propagation
5. **Database Operations**: Infrastructure spans for query timing

## Phase 1: Core Tracing Infrastructure

### Files to Modify
- `letta/log/workflow_tracker.py`: Add span creation utilities
- `letta/log/__init__.py`: Initialize OTEL tracer instances
- `letta/server/rest_api/middleware/logging_middleware.py`: Root span creation

### Trace Context Integration
- Extend correlation context variables to include trace context
- Modify `WorkflowTracker.get_correlation_context()` to include span context
- Add trace context to all structured log events

### Tracer Configuration
- Create tracer instances for each service layer
- Configure span processors and exporters
- Set up sampling strategies for performance

## Phase 2: Agent Workflow Tracing

### Files to Modify
- `letta/agents/letta_agent.py`: Agent step span instrumentation
- `letta/services/tool_executor/tool_execution_manager.py`: Tool execution spans
- `letta/services/tool_executor/multi_agent_tool_executor.py`: Communication spans

### Agent Step Instrumentation
- Wrap `LettaAgent._step()` method with workflow span
- Create child spans for each step iteration
- Add span attributes: agent_id, step_number, max_steps, continuation_reason

### Tool Execution Spans
- Individual spans for each tool in parallel execution
- Span timing for performance analysis
- Tool-specific attributes: tool_name, parameters (sanitized), heartbeat_requested

## Phase 3: Distributed Agent Communication

### Files to Modify
- `letta/services/tool_executor/multi_agent_tool_executor.py`: Trace propagation
- `letta/schemas/message.py`: Trace context in message metadata
- `letta/functions/function_sets/multi_agent.py`: send() function tracing

### Cross-Agent Trace Propagation
- Inject trace context into agent messages
- Extract trace context when processing received messages
- Link source and target agent spans in distributed traces

### Message Processing Spans
- Span for job creation and execution (`_process_agent`)
- Child spans for agent step execution in target agent
- Span completion timing for async fire-and-forget messaging

## Phase 4: Database and Infrastructure Tracing

### Files to Modify
- `letta/services/agent_manager.py`: Database operation spans
- `letta/services/message_manager.py`: Message persistence spans
- `letta/services/block_manager.py`: Memory operation spans

### Database Instrumentation
- Wrap SQLAlchemy session operations with spans
- Query timing and parameter logging (sanitized)
- Connection pool monitoring spans

### LLM Provider Tracing
- `letta/llm_api/llm_client_base.py`: LLM request/response spans
- Provider-specific timing (OpenAI, Anthropic, etc.)
- Token usage and cost tracking attributes

## Phase 5: Advanced Tracing Features

### Sampling Strategy Implementation
- Dynamic sampling based on workflow complexity
- Always sample error traces and slow operations
- Reduced sampling for routine successful operations

### Custom Span Processors
- Business event correlation processor
- Sensitive data sanitization processor
- Performance anomaly detection processor

### Trace Enrichment
- Add business context to spans (user_id, organization_id)
- Workflow outcome classification (success/failure/timeout)
- Agent performance metrics as span attributes

## Integration Points with Existing Systems

### Structured Logging Coordination
- Preserve all existing structured log events
- Add span context to log event metadata
- Use same event names for spans and logs for correlation

### Correlation ID Enhancement
- Include trace_id and span_id in correlation context
- Maintain backward compatibility with existing correlation system
- Cross-reference traces and logs in SignOz queries

### Error Handling Integration
- Span status marking for failures
- Exception details in span attributes
- Error spans linked to structured error logs

## Configuration Requirements

### Environment Variables
- `OTEL_TRACES_EXPORTER`: Set to "otlp" for SignOz
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`: SignOz collector endpoint
- `OTEL_TRACE_SAMPLER`: Sampling strategy configuration
- `LETTA_TRACING_ENABLED`: Feature flag for tracing

### Instrumentation Setup
- Auto-instrumentation for FastAPI and SQLAlchemy
- Custom instrumentation for agent and tool execution
- Span processor configuration for performance

## Observability Integration

### SignOz Configuration
- Trace visualization dashboards
- Service map for agent communication
- Performance monitoring alerts

### Monitoring Metrics
- Trace volume and sampling rates
- Span duration percentiles
- Error rate tracking by service

## Deployment Considerations

### Performance Impact
- Minimal overhead with proper sampling
- Async span export to avoid blocking
- Memory management for long-running traces

### Rollout Strategy
- Feature flag for gradual enablement
- Per-environment configuration
- Performance monitoring during rollout

## Success Metrics

### Debugging Effectiveness
- Time to identify workflow failures (target: < 1 minute vs current hours)
- Visual workflow representation completeness
- Cross-agent communication visibility

### Performance Insights
- Tool execution bottleneck identification
- Agent step timing analysis
- Database query performance monitoring

### Operational Benefits
- Reduced debugging session duration
- Proactive performance issue detection
- Improved system observability