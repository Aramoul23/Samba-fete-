#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing system dependencies for WeasyPrint..."
apt-get update -qq
apt-get install -y -qq libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev > /dev/null

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Build complete."
