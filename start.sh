#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Start the Uvicorn server immediately so health checks pass
echo "--- Starting Uvicorn server ---"
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
