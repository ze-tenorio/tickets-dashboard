@echo off
cd /d "%~dp0"
set STREAMLIT_SERVER_HEADLESS=true
echo Iniciando o dashboard...
echo.
echo Quando aparecer "You can now view your Streamlit app", abra no navegador:
echo   http://localhost:8501
echo.
python -m streamlit run app.py --server.port 8501
pause
