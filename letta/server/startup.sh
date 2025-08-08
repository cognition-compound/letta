#!/bin/sh
set -e  # Exit on any error

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8283}"

# Enhanced logging for better debugging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to validate environment variables
validate_env() {
    # Check if individual database variables are set
    if [ -n "$LETTA_PG_HOST" ] && [ -n "$LETTA_PG_PORT" ] && [ -n "$LETTA_PG_USER" ] && [ -n "$LETTA_PG_PASSWORD" ] && [ -n "$LETTA_PG_DB" ]; then
        log "Using individual PostgreSQL configuration:"
        log "  Host: $LETTA_PG_HOST"
        log "  Port: $LETTA_PG_PORT"
        log "  Database: $LETTA_PG_DB"
        log "  User: $LETTA_PG_USER"
        log "  Password: ****"
    elif [ -n "$LETTA_PG_URI" ]; then
        log "Using PostgreSQL URI: ${LETTA_PG_URI%:*}:****@${LETTA_PG_URI##*@}"
    else
        log "ERROR: Database configuration is required"
        log "Please provide either:"
        log "  1. Individual variables: LETTA_PG_HOST, LETTA_PG_PORT, LETTA_PG_USER, LETTA_PG_PASSWORD, LETTA_PG_DB"
        log "  2. Complete URI: LETTA_PG_URI (postgresql://user:password@host:port/database)"
        exit 1
    fi
}

# Function to wait for external PostgreSQL to be ready
wait_for_external_postgres() {
    local max_attempts=30
    local attempt=0
    local host
    local port
    local user
    
    log "Waiting for external PostgreSQL to be ready..."
    
    # Use individual variables if available, otherwise extract from URI
    if [ -n "$LETTA_PG_HOST" ] && [ -n "$LETTA_PG_PORT" ] && [ -n "$LETTA_PG_USER" ]; then
        host="$LETTA_PG_HOST"
        port="$LETTA_PG_PORT"
        user="$LETTA_PG_USER"
    elif [ -n "$LETTA_PG_URI" ]; then
        # Extract connection details from LETTA_PG_URI for pg_isready
        host=$(echo "$LETTA_PG_URI" | sed -n 's/.*@\([^:]*\):.*/\1/p')
        port=$(echo "$LETTA_PG_URI" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
        user=$(echo "$LETTA_PG_URI" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    else
        log "ERROR: No database configuration found"
        exit 1
    fi
    
    while [ $attempt -lt $max_attempts ]; do
        if pg_isready -h "$host" -p "$port" -U "$user" > /dev/null 2>&1; then
            log "PostgreSQL is ready!"
            return 0
        fi
        
        log "PostgreSQL not ready yet, retrying in 2 seconds... (attempt $((attempt + 1))/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    log "ERROR: PostgreSQL did not become ready within $((max_attempts * 2)) seconds"
    exit 1
}

# Validate required environment variables
validate_env

# Wait for external PostgreSQL to be ready
wait_for_external_postgres

# Attempt database migration
log "Attempting database migration..."
cd /app
if ! python -m alembic upgrade head; then
    log "ERROR: Database migration failed!"
    log "Please check your database connection and try again."
    if [ -n "$LETTA_PG_HOST" ] && [ -n "$LETTA_PG_PORT" ] && [ -n "$LETTA_PG_USER" ] && [ -n "$LETTA_PG_DB" ]; then
        log "Connection: $LETTA_PG_USER@$LETTA_PG_HOST:$LETTA_PG_PORT/$LETTA_PG_DB"
    elif [ -n "$LETTA_PG_URI" ]; then
        log "Connection string: ${LETTA_PG_URI%:*}:****@${LETTA_PG_URI##*@}"
    fi
    exit 1
fi
log "Database migration completed successfully."

# Set permissions for tool execution directory if configured
if [ -n "$LETTA_SANDBOX_MOUNT_PATH" ]; then
    log "Setting permissions for tool execution directory: $LETTA_SANDBOX_MOUNT_PATH"
    if ! chmod 777 "$LETTA_SANDBOX_MOUNT_PATH"; then
        log "ERROR: Failed to set permissions for tool execution directory at: $LETTA_SANDBOX_MOUNT_PATH"
        log "Please check that the directory exists and is accessible"
        exit 1
    fi
fi

# Enhanced signal handling for graceful shutdown with tini
graceful_shutdown() {
    log "Received shutdown signal, terminating gracefully..."
    exit 0
}

# Register signal handlers (tini will forward signals properly)
trap graceful_shutdown TERM INT

log "Starting Letta Server at http://$HOST:$PORT..."
log "Letta version: ${LETTA_VERSION:-unknown}"
log "Environment: ${LETTA_ENVIRONMENT:-PRODUCTION}"

# Execute the server (tini will handle PID 1 responsibilities)
if [ "${SECURE:-false}" = "true" ]; then
    log "Secure mode enabled"
    exec python -c "from letta.main import app; import sys; sys.argv = ['letta', 'server', '--host', '$HOST', '--port', '$PORT', '--secure']; app()"
else
    exec python -c "from letta.main import app; import sys; sys.argv = ['letta', 'server', '--host', '$HOST', '--port', '$PORT']; app()"
fi
