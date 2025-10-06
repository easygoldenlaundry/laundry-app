#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Run the database seeder
echo "--- Running database seeder ---"
python -m app.seed_db

# Start the Uvicorn server
echo "--- Starting Uvicorn server ---"
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
