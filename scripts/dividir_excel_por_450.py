import os
import sys
from datetime import datetime
import pandas as pd

REGISTROS_POR_ARCHIVO = 450


def elegir_archivo():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        ruta = filedialog.askopenfilename(
            title="Selecciona el archivo Excel a dividir",
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("Todos", "*.*")]
        )
        root.destroy()
        if not ruta:
            print("No se selecciono ningun archivo.")
            return None
        return ruta
    except Exception as e:
        print("No se pudo abrir la ventana:", e)
        return None


def dividir(ruta_original):
    ruta_aprobada = os.path.normpath(os.path.abspath(ruta_original))
    try:
        df = pd.read_excel(ruta_aprobada)
    except Exception as e:
        print("No se pudo leer el archivo:", e)
        return

    total = len(df)
    print("Total de registros: %d" % total)
    if total == 0:
        print("El archivo no tiene registros.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.splitext(os.path.basename(ruta_original))[0]
    dir_original = os.path.dirname(ruta_aprobada)
    carpeta_salida = os.path.join(dir_original, "divididos_%s_%s" % (base, stamp))
    os.makedirs(carpeta_salida, exist_ok=True)
    print("Guardando en: %s" % carpeta_salida)

    n_archivos = (total + REGISTROS_POR_ARCHIVO - 1) // REGISTROS_POR_ARCHIVO
    for i in range(n_archivos):
        inicio = i * REGISTROS_POR_ARCHIVO
        fin = min((i + 1) * REGISTROS_POR_ARCHIVO, total)
        parte = df.iloc[inicio:fin]
        nombre = "%s_%0*d-%0*d.xlsx" % (
            base, len(str(n_archivos)), i + 1, len(str(n_archivos)), fin)
        ruta = os.path.join(carpeta_salida, nombre)
        parte.to_excel(ruta, index=False)
        print("  %s  (%d registros)" % (nombre, fin - inicio))

    print("\nListo. Se generaron %d archivos de maximo %d registros cada uno."
          % (n_archivos, REGISTROS_POR_ARCHIVO))


def main():
    ruta = elegir_archivo()
    if ruta:
        dividir(ruta)


if __name__ == "__main__":
    main()
