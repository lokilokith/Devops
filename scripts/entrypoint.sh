#!/usr/bin/env bash
set -e

# Wait for PostgreSQL to be ready if POSTGRES_HOST is provided
if [ -n "$POSTGRES_HOST" ]; then
    echo "Waiting for PostgreSQL at $POSTGRES_HOST:$POSTGRES_PORT..."
    while ! pg_isready -q -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
        sleep 1
    done
    echo "PostgreSQL is ready!"
fi

# Run database migrations
echo "Running database migrations..."
flask db upgrade

# Seed database if necessary
# flask run-seeders (or equivalent command, currently omitted unless needed)

# Execute the main process
echo "Starting application..."
exec "$@"
