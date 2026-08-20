@echo off
cd /d "%~dp0"
echo [%date% %time%] Inicio WOs Descargar FLM + PEXT -> Importar >> WOs_run.log
python "WOs_descargar_y_importar.py" >> WOs_run.log 2>&1
echo [%date% %time%] Fin (codigo %errorlevel%) >> WOs_run.log