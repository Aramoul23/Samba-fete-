#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Build complete."
