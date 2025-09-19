# Emergency Runbook

This document outlines procedures for common emergency and maintenance scenarios.

**IMPORTANT**: Always stop the application before performing any manual interventions.

---

## 1. Full Application Reset (Easiest Method)

If you need to start from a clean slate (e.g., for testing or if the database is in a bad state), the easiest method is to run the provided reset script. This will **delete all existing data** (orders, images, etc.) and re-populate the database with fresh sample data.

1.  **Stop the application.**
2.  Run the appropriate script for your operating system:
    -   **On Linux/macOS**: `bash scripts/reset_and_seed.sh`
    -   **On Windows**: `scripts\reset_and_seed.bat`
3.  Restart the application.

---

## 2. Restoring from a Backup

Use this procedure if the database or image data becomes corrupted and you need to restore to a previous state.

1.  **Stop the Application**
    -   If running in a terminal, press `Ctrl+C`.
    -   If running as a service, use `systemctl stop your-service-name`.

2.  **Identify the Latest Backup**
    -   Backups are stored in the `backups/` directory.
    -   Database backups are named `brain-YYYYMMDD-HHMM.db`.
    -   Image backups are named `images-YYYYMMDD-HHMM.tar.gz`.
    -   Find the most recent files you want to restore from.

3.  **Restore the Files**

    *   **Restore Database:**
        ```bash
        # Replace with the actual backup filename
        cp backups/brain-20231027-1430.db brain.db
        ```

    *   **Restore Images:**
        ```bash
        # This will extract the 'data' directory into the current location, overwriting if needed.
        # Replace with the actual backup filename
        tar -xzf backups/images-20231027-1430.tar.gz
        ```

4.  **Restart the Application**
    -   Run the application again using the standard command.

---

## 3. Advanced: Manual Database Interventions

These procedures require using the `sqlite3` command-line tool.

**Prerequisite:** You must have the `sqlite3` command-line tool installed on your system. It is **not** part of Python or this project's dependencies. You can download it from the official SQLite website. If the `sqlite3` command is not found, you will not be able to run these commands.

**Command Syntax:** `sqlite3 brain.db "SQL_COMMAND;"`

### Releasing a Stuck Machine

**Symptom:** A machine (washer, dryer) is shown as "running" in the UI, but the cycle is actually complete. A new basket cannot be started in it.

**Fix:**
```bash
# --- THIS IS THE FIX ---
# Machines are now associated with baskets, not orders.
# Replace <MACHINE_ID> with the ID of the stuck machine
sqlite3 brain.db "UPDATE machine SET current_basket_id = NULL, state = 'idle', cycle_started_at = NULL WHERE id = <MACHINE_ID>;"