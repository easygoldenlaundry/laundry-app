#!/bin/bash

# One-time database seeding script
# Run this once after deploying to initialize the database

set -e

echo "--- Running database seeder ---"
python -m app.seed_db
echo "--- Database seeding complete ---"

