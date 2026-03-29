#!/bin/bash
set -ex

# Ensure PORT is a valid number
if [ -z "$PORT" ] || ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "WARNING: PORT='$PORT' is invalid, defaulting to 8080"
    export PORT=8080
fi

echo "=== Samba Fête Starting ==="
echo "PORT: $PORT"
echo "FLASK_ENV: ${FLASK_ENV:-not set}"
echo "DATABASE_URL set: $([ -n \"$DATABASE_URL\" ] && echo YES || echo NO)"
echo "SECRET_KEY set: $([ -n \"$SECRET_KEY\" ] && echo YES || echo NO)"
echo "==========================="

exec gunicorn run:app \
    --bind "0.0.0.0:${PORT}" \
    --workers 2 \
    --timeout 120 \
    --preload \
    --log-level info \
    --access-logfile -
