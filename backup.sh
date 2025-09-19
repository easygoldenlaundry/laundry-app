#!/bin/bash
set -e

# --- Configuration ---
BACKUP_DIR="backups"
DB_FILE="brain.db"
DATA_DIR="data"
KEEP_COUNT=14

# --- Logic ---
echo "--- Starting backup process ---"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Get current timestamp
TIMESTAMP=$(date +"%Y%m%d-%H%M")

# Backup the database
DB_BACKUP_NAME="brain-${TIMESTAMP}.db"
echo "Backing up database to ${BACKUP_DIR}/${DB_BACKUP_NAME}..."
cp "$DB_FILE" "${BACKUP_DIR}/${DB_BACKUP_NAME}"
echo "Database backup complete."

# Backup the data/images directory
IMAGES_BACKUP_NAME="images-${TIMESTAMP}.tar.gz"
echo "Backing up images to ${BACKUP_DIR}/${IMAGES_BACKUP_NAME}..."
tar -czf "${BACKUP_DIR}/${IMAGES_BACKUP_NAME}" "$DATA_DIR"
echo "Image backup complete."

# Clean up old backups
echo "Cleaning up old backups (keeping the last ${KEEP_COUNT})..."

# Cleanup DB backups
ls -1t "${BACKUP_DIR}/brain-"*.db 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs -I {} rm -- {}
# Cleanup Image backups
ls -1t "${BACKUP_DIR}/images-"*.tar.gz 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs -I {} rm -- {}

echo "Cleanup complete."
echo "--- Backup process finished successfully ---"