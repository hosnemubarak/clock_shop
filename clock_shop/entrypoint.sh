#!/bin/bash
# =============================================================================
# Clock Shop - Docker Entrypoint Script
# =============================================================================
set -e

echo "=== Clock Shop Starting ==="

# Wait for database to be ready (if using PostgreSQL)
if [ -n "$DATABASE_URL" ] || [ "$DB_ENGINE" = "postgresql" ]; then
    echo "Waiting for PostgreSQL..."
    
    # Extract host and port from DATABASE_URL or use DB_HOST/DB_PORT
    if [ -n "$DATABASE_URL" ]; then
        DB_HOST=$(echo $DATABASE_URL | sed -e 's/.*@\(.*\):.*/\1/')
        DB_PORT=$(echo $DATABASE_URL | sed -e 's/.*:\([0-9]*\)\/.*/\1/')
    fi
    
    DB_HOST=${DB_HOST:-db}
    DB_PORT=${DB_PORT:-5432}
    
    while ! python -c "import socket; socket.create_connection(('$DB_HOST', $DB_PORT), timeout=1)" 2>/dev/null; do
        echo "PostgreSQL is unavailable - waiting..."
        sleep 2
    done
    echo "PostgreSQL is ready!"
fi

# Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files (if not already done)
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "=== Clock Shop Ready ==="
echo "Starting Gunicorn server on port 8000..."

# Start Gunicorn
exec gunicorn clock_shop.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --threads 2 \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --log-level info
