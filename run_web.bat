@echo off
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
for /f %%i in ('py -c "import secrets; print(secrets.token_hex(32))"') do set BSV_SECRET_KEY=%%i
python app.py
pause
