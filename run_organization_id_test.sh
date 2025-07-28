#!/bin/bash

# Script to run the organization_id error test with postgres

echo "Starting PostgreSQL with docker-compose..."
docker compose -f dev-compose.yaml up -d letta_db

# Wait for postgres to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Set environment variables for the test
export LETTA_PG_URI="postgresql://letta:letta@localhost:5432/letta"
export LETTA_DISABLE_SQLALCHEMY_POOLING="true"
export OPENAI_API_KEY="${OPENAI_API_KEY}"

# Run database migrations
echo "Running database migrations..."
poetry run alembic upgrade head

# Run the specific test
echo "Running organization_id error test..."
poetry run pytest tests/test_organization_id_error.py -v -s

# Capture the exit code
TEST_EXIT_CODE=$?

# Clean up
echo "Cleaning up..."
docker compose -f dev-compose.yaml down

exit $TEST_EXIT_CODE