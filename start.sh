#!/bin/bash
set -e
PORT="${PORT:-8080}"
echo "Starting gunicorn on port ${PORT}"
exec gunicorn run:app --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120 --preload --log-level info
