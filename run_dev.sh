@echo off
rem run_dev.bat
rem Point uvicorn to the socket_app in main.py
uvicorn app.main:socket_app --reload --port 8000