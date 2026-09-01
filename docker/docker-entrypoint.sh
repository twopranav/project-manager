#!/bin/bash
set -e

echo "Waiting for PostgreSQL database..."
while ! nc -z $POSTGRES_SERVER 5432; do
  sleep 0.5
done
echo "PostgreSQL is online."

# Only the web container (running uvicorn) runs migrations, to avoid
# two containers racing to apply DDL (enum swaps aren't safe concurrently)
if [[ "$*" == *"uvicorn"* ]]; then
  echo "Running Alembic migrations..."
  python -m alembic upgrade head
fi

# Execute container's main CMD
exec "$@"