# syntax=docker/dockerfile:1

# Multi-stage build for optimized Letta container with tini init system
# Integrates optimizations from mithrilmind while maintaining pgvector compatibility

# ================================
# Builder stage - compile dependencies
# ================================
FROM python:3.12-slim AS builder

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        python3-dev \
        git \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Set up build environment
ARG LETTA_ENVIRONMENT=PRODUCTION
ENV LETTA_ENVIRONMENT=${LETTA_ENVIRONMENT} \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Install Poetry with caching
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install poetry==2.1.3

# Copy dependency files for better caching
COPY pyproject.toml poetry.lock ./

# Install dependencies only (no root project) with caching
RUN --mount=type=cache,target=/tmp/poetry_cache,sharing=locked \
    --mount=type=cache,target=/root/.cache/pypoetry,sharing=locked \
    poetry install --all-extras --no-root

# Copy source code
COPY . .

# Now install the project and build
RUN --mount=type=cache,target=/tmp/poetry_cache,sharing=locked \
    --mount=type=cache,target=/root/.cache/pypoetry,sharing=locked \
    poetry install --all-extras && \
    poetry build

# ================================
# Runtime stage - optimized production image
# ================================
FROM python:3.12-slim AS runtime

# Metadata
LABEL org.opencontainers.image.source="https://github.com/letta-ai/letta"
LABEL org.opencontainers.image.description="Letta AI server with pgvector support and OpenTelemetry"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Set versions as build args for better caching
ARG NODE_VERSION=22
ARG LETTA_VERSION
ARG LETTA_ENVIRONMENT=PRODUCTION

# Install tini for proper init system
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
        postgresql-client \
        libpq5 \
        ca-certificates \
        curl \
        && \
    # Install Node.js for frontend/tooling support
    curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    # Clean up
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up Python environment
ENV LETTA_ENVIRONMENT=${LETTA_ENVIRONMENT} \
    LETTA_VERSION=${LETTA_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COMPOSIO_DISABLE_VERSION_CHECK=true \
    LETTA_OPENAPI_DIR=/tmp \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy the complete virtual environment from builder stage
# This preserves Poetry's exact dependency resolution and avoids version conflicts
COPY --from=builder /build/.venv /app/.venv

# Copy application source selectively (avoid copying builder artifacts)
COPY --from=builder /build/letta ./letta
COPY --from=builder /build/alembic ./alembic
COPY --from=builder /build/alembic.ini ./alembic.ini
COPY --from=builder /build/tests ./tests
COPY --from=builder /build/pyproject.toml ./pyproject.toml

# Copy and setup startup script
COPY letta/server/startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

# Create app directories and set permissions
RUN mkdir -p /app/.letta/logs /app/.letta/tool_execution_dir /app/openapi && \
    chmod 755 /app/.letta/logs /app/.letta/tool_execution_dir /app/openapi

# Create non-root user for security (commented out for backward compatibility)
# RUN useradd -m -u 1000 letta && \
#     chown -R letta:letta /app /app/.letta
# USER letta

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8283/v1/health/ || exit 1

# Expose ports
EXPOSE 8283

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/startup.sh"]