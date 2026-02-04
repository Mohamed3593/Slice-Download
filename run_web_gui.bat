@echo off
cd web_gui
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing requirements...
pip install -r requirements.txt
echo Starting Web Server...
python app.py
pause
