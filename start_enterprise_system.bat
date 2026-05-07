@echo off
echo 🚀 STARTING HYBRID AI ECOSYSTEM
echo -----------------------------------

:: 1. SET THE BRAIN CONNECTION
set OPENAI_API_BASE_URL=http://localhost:8000/v1
set OPENAI_API_KEY=antigravity_admin_key_2026

:: 2. ENSURE SYSTEM ENCODING
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo 🧠 Connecting Open WebUI to Hybrid Router at port 8000...
echo 📱 Telegram Bot and State Sync are active in the background.
echo -----------------------------------

"C:\Users\zacca\AppData\Local\Programs\Python\Python311\Scripts\open-webui.exe" serve
pause