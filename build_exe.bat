@echo off
echo Installing PyInstaller...
python -m pip install pyinstaller

echo Building EXE...
python -m PyInstaller --noconsole --onefile --name "DL-Master" gui.py

echo.
echo Build Complete! Look in the 'dist' folder.
pause
