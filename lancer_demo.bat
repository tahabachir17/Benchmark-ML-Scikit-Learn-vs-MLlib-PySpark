@echo off
rem Lance l'interface de démonstration et ouvre le navigateur sur http://localhost:8501
cd /d "%~dp0"
".venv\Scripts\python.exe" demo\server.py
pause
