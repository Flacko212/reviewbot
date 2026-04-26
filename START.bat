@echo off
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting ReviewBot...
echo Open your browser and go to: http://localhost:5000
echo.
python server.py
pause
