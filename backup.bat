@echo off
setlocal

:: --- Configuration ---
set "BACKUP_DIR=backups"
set "DB_FILE=brain.db"
set "DATA_DIR=data"
set "KEEP_COUNT=14"

:: --- Logic ---
echo --- Starting backup process ---

:: Create backup directory if it doesn't exist
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

:: Get current timestamp (YYYYMMDD-HHMM)
for /f "tokens=1-4 delims=. " %%i in ('wmic os get LocalDateTime ^| find "20"') do (
    set "dt=%%i"
)
set "TIMESTAMP=%dt:~0,8%-%dt:~8,4%"

:: Backup the database
set "DB_BACKUP_NAME=brain-%TIMESTAMP%.db"
echo Backing up database to %BACKUP_DIR%\%DB_BACKUP_NAME%...
copy "%DB_FILE%" "%BACKUP_DIR%\%DB_BACKUP_NAME%"
echo Database backup complete.

:: Backup the data/images directory (assumes tar is in PATH, e.g., from Git for Windows)
set "IMAGES_BACKUP_NAME=images-%TIMESTAMP%.tar.gz"
echo Backing up images to %BACKUP_DIR%\%IMAGES_BACKUP_NAME%...
tar -czf "%BACKUP_DIR%\%IMAGES_BACKUP_NAME%" "%DATA_DIR%"
echo Image backup complete.

:: Clean up old backups
echo Cleaning up old backups (keeping the last %KEEP_COUNT%)...

:: Cleanup DB backups
for /f "skip=%KEEP_COUNT% delims=" %%F in ('dir /b /o-d "%BACKUP_DIR%\brain-*.db"') do (
    echo Deleting old DB backup: %%F
    del "%BACKUP_DIR%\%%F"
)

:: Cleanup Image backups
for /f "skip=%KEEP_COUNT% delims=" %%F in ('dir /b /o-d "%BACKUP_DIR%\images-*.tar.gz"') do (
    echo Deleting old image backup: %%F
    del "%BACKUP_DIR%\%%F"
)

echo Cleanup complete.
echo --- Backup process finished successfully ---

endlocal