import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry._logs import get_logger_provider, set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, OTEL_SERVICE_NAME

# Standard OTEL env var names (not in SDK constants)
OTEL_LOGS_EXPORTER = "OTEL_LOGS_EXPORTER"
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from letta.log import get_logger
from letta.otel.resource import is_pytest_environment
from letta.settings import settings

logger = get_logger(__name__)
_is_logging_initialized = False


class OTLPLogHandler(LoggingHandler):
    """Custom OTLP log handler that adds trace context to log records."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record with trace context if available."""
        # Add trace context to the log record if we're currently in a span
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_context = span.get_span_context()
            record.trace_id = format(span_context.trace_id, "032x")
            record.span_id = format(span_context.span_id, "016x")
            record.trace_flags = span_context.trace_flags

        # Call parent emit
        super().emit(record)


def setup_logging() -> None:
    """Set up OpenTelemetry logging export using standard OTEL configuration.

    This function respects standard OTEL environment variables:
    - OTEL_LOGS_EXPORTER: The logs exporter to use (default: "otlp")
    - OTEL_EXPORTER_OTLP_ENDPOINT: The OTLP endpoint
    - OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: Specific endpoint for logs
    - OTEL_SERVICE_NAME: The service name
    - OTEL_RESOURCE_ATTRIBUTES: Additional resource attributes
    """
    if is_pytest_environment():
        return

    global _is_logging_initialized

    # Check if OTEL is configured via environment
    logs_exporter = os.environ.get(OTEL_LOGS_EXPORTER, "otlp")
    otlp_endpoint = os.environ.get(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT) or os.environ.get(OTEL_EXPORTER_OTLP_ENDPOINT)

    # Skip if no endpoint configured and using OTLP
    if logs_exporter == "otlp" and not otlp_endpoint:
        logger.debug("No OTLP endpoint configured, skipping OpenTelemetry logging setup")
        return

    # Use standard OTEL resource configuration
    from letta.otel.resource import get_resource
    resource = get_resource()

    # Create logger provider with resource
    logger_provider = LoggerProvider(resource=resource)

    # Configure exporter based on OTEL_LOGS_EXPORTER
    if logs_exporter == "none":
        logger.info("OpenTelemetry logging disabled (OTEL_LOGS_EXPORTER=none)")
        return
    elif logs_exporter == "console":
        exporter = ConsoleLogExporter()
    elif logs_exporter == "otlp":
        # Let OTLPLogExporter handle endpoint configuration from env vars
        exporter = OTLPLogExporter()
    else:
        logger.warning(f"Unknown logs exporter: {logs_exporter}, defaulting to OTLP")
        exporter = OTLPLogExporter()

    # Add batch processor
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    # Set the global logger provider
    set_logger_provider(logger_provider)

    # Create and configure the OTLP handler
    log_level = getattr(logging, settings.otel_log_level.upper(), logging.INFO)
    otlp_handler = OTLPLogHandler(level=log_level, logger_provider=logger_provider)

    # Add handler to root logger if console logs should be included
    if settings.otel_include_console_logs:
        root_logger = logging.getLogger()
        root_logger.addHandler(otlp_handler)

    # Always add to Letta logger
    letta_logger = logging.getLogger("Letta")
    letta_logger.addHandler(otlp_handler)

    _is_logging_initialized = True
    logger.info(f"OpenTelemetry logging initialized with exporter: {logs_exporter}")
