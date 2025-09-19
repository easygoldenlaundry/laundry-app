@echo off
echo --- Resetting Application State ---

echo Deleting old database...
if exist brain.db (
    del brain.db
) else (
    echo brain.db not found, skipping.
)

echo Deleting old backups...
if exist backups (
    rmdir /s /q backups
) else (
    echo backups/ directory not found, skipping.
)

echo Deleting old logs...
if exist logs (
    rmdir /s /q logs
) else (
    echo logs/ directory not found, skipping.
)

echo.
echo Re-seeding database with sample data...
python -m app.seed_db

echo.
echo --- Reset and Seed Complete! ---