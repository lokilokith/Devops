#!/bin/bash
set -e

echo "Starting backend entrypoint script..."

# Ensure APP_ENV is set; if not, default to development (fail-safe for local)
if [ -z "$APP_ENV" ]; then
    echo "Warning: APP_ENV is not set. Defaulting to 'development'."
    export APP_ENV=development
fi

# Run database migrations
echo "Running Flask database migrations..."
flask db upgrade

echo "Starting application with command: $@"
exec "$@"
