# Emergency Runbook

This document outlines procedures for common emergency and maintenance scenarios for the Supabase production environment.

**IMPORTANT**: Always stop the application on Render before performing any manual interventions on the database.

---

## 1. Full Application Reset (Wipe and Re-seed)

Use this procedure if you need to start from a clean slate (e.g., for testing or if the database is in a bad, unrecoverable state). This is the "source of truth" method for ensuring your database schema matches your Python models.

**WARNING: This will permanently delete all data in your Supabase database.**

1.  **Stop the application on Render.**
2.  **(Optional) Backup Data:** If you have any important data in your Supabase tables, go to the Supabase Dashboard, select each table, and export it to a CSV file.
3.  **Clear Old Tables:** Go to the **SQL Editor** in your Supabase dashboard. Run the following command to delete all application-managed tables.

    ```sql
    -- DANGER: This is a destructive action that will delete all your data.
    DROP TABLE IF EXISTS "order", "user", customer, basket, bag, item, driver, station, machine, event, image, claim, setting, inventoryitem, withdrawal, financeentry, message CASCADE;
    ```

4.  **Restart Your Render Service:** Simply restart the application from your Render dashboard.
    -   When the Python backend starts up, the `on_startup` event will trigger `create_db_and_tables()`. This function reads your Python models (like `User`, `Order`) and **automatically creates the correctly named tables and columns in your Supabase database.**
    -   The startup script will then run `seed_database()`, which populates your new tables with the default admin user, settings, stations, etc.

---

## 2. Restoring from a Supabase Backup

Use this procedure if you need to restore the database to a previous point in time due to data corruption or accidental deletion.

1.  Go to your Supabase Project Dashboard.
2.  Navigate to **Database** -> **Backups**.
3.  You will see a list of Point-in-Time-Recovery (PITR) options.
4.  Choose a time to restore to and follow the on-screen instructions provided by Supabase.

---

## 3. Advanced: Manual Database Interventions (Supabase SQL Editor)

These procedures require using the **SQL Editor** in your Supabase dashboard.

### Releasing a Stuck Machine

**Symptom:** A machine (washer, dryer) is shown as "running" in the UI, but the cycle is actually complete. A new basket cannot be started in it.

**Fix:**
Go to the Supabase **SQL Editor** and run the following command. Replace `<MACHINE_ID>` with the ID of the stuck machine.

```sql
-- Replace <MACHINE_ID> with the ID of the stuck machine
UPDATE machine 
SET 
  current_basket_id = NULL, 
  state = 'idle', 
  cycle_started_at = NULL 
WHERE 
  id = <MACHINE_ID>;