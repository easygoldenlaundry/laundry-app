@echo off
echo Starting the development server with live reload...

:: --- THIS IS THE FIX: The server must now run the main "app" instance ---
uvicorn app.main:app --reload