#!/bin/bash
set -e
PORT="${PORT:-5000}"
exec gunicorn run:app --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120
