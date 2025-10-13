#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Start the Uvicorn server with optimized settings for production
echo "--- Starting Uvicorn server ---"
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-10000} \
    --workers 1 \
    --timeout-keep-alive 30 \
    --timeout-graceful-shutdown 30 \
    --access-log \
    --log-level info
