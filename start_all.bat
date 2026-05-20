@echo off
setlocal
echo 🚀 LAUNCHING HYBRID AI ECOSYSTEM
echo -----------------------------------

:: 1. SET ENVIRONMENT
set PYTHONIOENCODING=utf-8
set OPENAI_API_BASE_URL=http://localhost:8001/v1
set OPENAI_API_KEY=antigravity_admin_key_2026

:: 2. PRE-FLIGHT CHECK (Automated Schema Migration)
echo [1/3] Initializing DuckDB Silver Layer...
python -c "import duckdb, os; con=duckdb.connect('data/pipeline_metrics.db'); con.execute(open('data/sql_silver_layer.sql').read()) if os.path.exists('data/sql_silver_layer.sql') else print('SQL not found, skipping.')"

:: 3. START THE BRAIN (ROUTER)
echo [2/3] Starting Hybrid Router on port 8001...
start /min "Hybrid Router" cmd /c "uvicorn src.server:app --host 0.0.0.0 --port 8001 --log-level info"

:: Wait for router to warm up
timeout /t 5 /nobreak > nul

:: 4. START THE FACE (WEBUI)
echo [3/3] Starting Open WebUI on port 8080...
echo 🔗 DASHBOARD: http://localhost:8001/dashboard
echo 🔗 WEBUI:    http://localhost:8080
echo 🔗 CQRS API: http://localhost:8001/api/v1/pipeline/invoices
echo -----------------------------------
"C:\Users\zacca\AppData\Local\Programs\Python\Python311\Scripts\open-webui.exe" serve
pause