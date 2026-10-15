@echo off
cd /d "%~dp0"
py -3 -m pip install -q -r requirements.txt
echo CraDocs running at http://127.0.0.1:5000  (Ctrl+C to stop)
py -3 app.py
