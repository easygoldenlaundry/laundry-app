# Emergency Runbook

This document outlines procedures for common emergency and maintenance scenarios.

**IMPORTANT**: Always stop the application before performing any manual interventions.

---

## 1. Wiping and Resetting the Database (Supabase)

If you need to start from a clean slate (e.g., for testing or if the database is in a bad state), the easiest method is to reset your Supabase database and let the application re-create the tables and seed data.

**WARNING: This will permanently delete all data in your Supabase database.**

1.  **Stop the application on Render.**
2.  Go to your Supabase Project Dashboard.
3.  Navigate to **Database** -> **Tables**.
4.  Manually delete all the tables that the application created (e.g., `order`, `user`, `customer`, `machine`, etc.).
5.  **Restart the application on Render.** The application will automatically run the `create_db_and_tables()` and `seed_database()` functions on startup, creating a fresh, clean set of tables with default data.

---

## 2. Restoring from a Supabase Backup

Supabase automatically handles backups.

1.  Go to your Supabase Project Dashboard.
2.  Navigate to **Database** -> **Backups**.
3.  You can see a list of Point-in-Time-Recovery (PITR) options. Choose a time to restore to and follow the instructions.

---

## 3. Advanced: Manual Database Interventions (Supabase)

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
---

### **Step 5: How to Create the Database Schema in Supabase**

After you deploy these code changes to Render (and have set the environment variables), your application will connect to your Supabase database. However, the tables (`user`, `customer`, `order`, etc.) might not exist yet, or they might be named incorrectly (like `users`).

**Here is the recommended way to fix this:**

1.  **Backup Data (If Necessary):** If you have any important data in your Supabase tables, go to the Supabase Dashboard, select each table, and export it to a CSV file.
2.  **Clear Old Tables:** Go to the **SQL Editor** in your Supabase dashboard. Run the following command to delete the old tables. **This is a destructive action.**

    ```sql
    -- DANGER: This will delete all your data.
    DROP TABLE IF EXISTS "order", "user", customer, basket, bag, item, driver, station, machine, event, image, claim, setting, inventoryitem, withdrawal, financeentry, message CASCADE;
    ```
    *(Note: If you have a `users` table instead of `user`, add `DROP TABLE IF EXISTS "users" CASCADE;`)*

3.  **Restart Your Render Service:** Simply restart the application from your Render dashboard. When the Python backend starts up, the `on_startup` event in `main.py` will trigger the `create_db_and_tables()` function. This function reads your Python models (like `User`, `Customer`) and **automatically creates the correctly named tables (`user`, `customer`) and columns in your Supabase database.**
4.  **Seed Data:** The startup script will also run `seed_database()`, which will populate your new tables with the default admin user, stations, etc.

By following these steps, your Python backend becomes the "source of truth" for your database schema, resolving the `user` vs `users` table name conflict and ensuring everything works together.