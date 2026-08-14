#!/usr/bin/env bash
set -euo pipefail

# Render supplies PORT. Running uvicorn directly keeps the service simple.
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-5000}"