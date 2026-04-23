#!/bin/sh
set -eu

echo "Applying database migrations for worker..."

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

echo "Starting CAMO worker..."
exec arq camo.tasks.worker.WorkerSettings
