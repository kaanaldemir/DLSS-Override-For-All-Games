@echo off
REM Build the executable from DLSS Override+.py and DLSS Override+.ico
pyinstaller --onefile --windowed --icon="DLSS Override+.ico" "DLSS Override+.py"
pause
