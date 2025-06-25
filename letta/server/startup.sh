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
    if [ -z "$LETTA_PG_URI" ]; then
        log "ERROR: LETTA_PG_URI environment variable is required"
        log "Please set LETTA_PG_URI to your PostgreSQL connection string"
        log "Example: postgresql://user:password@host:port/database"
        exit 1
    fi
    
    log "Using PostgreSQL database: ${LETTA_PG_URI%:*}:****@${LETTA_PG_URI##*@}"
}

# Function to wait for external PostgreSQL to be ready
wait_for_external_postgres() {
    local max_attempts=30
    local attempt=0
    
    log "Waiting for external PostgreSQL to be ready..."
    
    while [ $attempt -lt $max_attempts ]; do
        # Extract connection details from LETTA_PG_URI for pg_isready
        local host=$(echo "$LETTA_PG_URI" | sed -n 's/.*@\([^:]*\):.*/\1/p')
        local port=$(echo "$LETTA_PG_URI" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
        local user=$(echo "$LETTA_PG_URI" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
        
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
if ! alembic upgrade head; then
    log "ERROR: Database migration failed!"
    log "Please check your database connection and try again."
    log "Connection string: ${LETTA_PG_URI%:*}:****@${LETTA_PG_URI##*@}"
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

# Build server command
CMD="letta server --host $HOST --port $PORT"
if [ "${SECURE:-false}" = "true" ]; then
    CMD="$CMD --secure"
    log "Secure mode enabled"
fi

# Enhanced signal handling for graceful shutdown with tini
graceful_shutdown() {
    log "Received shutdown signal, terminating gracefully..."
    exit 0
}

# Register signal handlers (tini will forward signals properly)
trap graceful_shutdown TERM INT

log "Starting Letta Server at http://$HOST:$PORT..."
log "Server command: $CMD"
log "Letta version: ${LETTA_VERSION:-unknown}"
log "Environment: ${LETTA_ENVIRONMENT:-PRODUCTION}"

# Execute the server (tini will handle PID 1 responsibilities)
exec $CMD
