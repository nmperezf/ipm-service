@echo off
REM Activar entorno virtual y correr todo de una vez

call venv\Scripts\activate
pip install -r requirements.txt
python seed_demo.py
python run.py