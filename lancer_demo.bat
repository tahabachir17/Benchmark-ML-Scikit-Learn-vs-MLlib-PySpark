@echo off
rem Lance l'interface de démonstration Streamlit sur http://localhost:8501
cd /d "%~dp0"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
pause
