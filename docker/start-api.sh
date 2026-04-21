#!/bin/sh
set -eu

echo "Applying database migrations..."

attempt=0
until alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    echo "Migration failed after ${attempt} attempts."
    exit 1
  fi
  echo "Database not ready yet. Retrying in 2 seconds..."
  sleep 2
done

echo "Starting CAMO API..."
exec uvicorn camo.api.main:app --host 0.0.0.0 --port 8000
