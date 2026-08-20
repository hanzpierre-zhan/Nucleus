@echo off
REM ============================================================
REM  Nucleus - Descarga WOs List FLM y PEXT (secuencial)
REM  Corre cada script en su propia sesion de Chrome.
REM  Programa este .bat con el Programador de tareas de Windows.
REM ============================================================
setlocal

set "PYTHON=C:\Users\Planta Externa\AppData\Local\Programs\Python\Python312\python.exe"
set "DIR=C:\Onedrive\Python\Nucleus\scripts"
set "LOG=%DIR%\WOs_run.log"

echo [%date% %time%] === INICIO ===>> "%LOG%"

echo [%date% %time%] Ejecutando FLM...>> "%LOG%"
"%PYTHON%" "%DIR%\WOs Report Console FLM.py">> "%LOG%" 2>&1

echo [%date% %time%] Ejecutando PEXT...>> "%LOG%"
"%PYTHON%" "%DIR%\WOs Report Console PEXT.py">> "%LOG%" 2>&1

echo [%date% %time%] === FIN ===>> "%LOG%"

endlocal