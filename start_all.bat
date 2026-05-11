@echo off
setlocal
echo 🚀 LAUNCHING HYBRID AI ECOSYSTEM
echo -----------------------------------

:: 1. SET ENVIRONMENT
set PYTHONIOENCODING=utf-8
set OPENAI_API_BASE_URL=http://localhost:8000/v1
set OPENAI_API_KEY=antigravity_admin_key_2026

:: 2. START THE BRAIN (ROUTER)
echo [1/2] Starting Hybrid Router on port 8000...
start /min "Hybrid Router" cmd /c "uvicorn src.server:app --host 0.0.0.0 --port 8000 --log-level info"

:: Wait for router to warm up
timeout /t 5 /nobreak > nul

:: 3. START THE FACE (WEBUI)
echo [2/2] Starting Open WebUI on port 8080...
echo 🔗 DASHBOARD: http://localhost:8000/dashboard
echo 🔗 WEBUI:    http://localhost:8080
echo -----------------------------------
"C:\Users\zacca\AppData\Local\Programs\Python\Python311\Scripts\open-webui.exe" serve
pause
