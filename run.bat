@echo off
cd /d "C:\Users\rafi\mimo-farmer"
set "PYTHONPATH="
set "PYTHONHOME="
"C:\Users\rafi\AppData\Local\Programs\Python\Python312\python.exe" -m mimo_farmer create --referral DMRFJP --continuous --fast
pause
