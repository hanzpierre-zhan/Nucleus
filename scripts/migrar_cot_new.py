"""Ordena las cotizaciones para Cot_New sin tocar lo que usa el módulo Cotización.

Solo agrega o completa campos que lee Cot_New:
  * TIPO DE CONCEPTO   ← "TIPO DE COTIZACION" pasado a la lista oficial (si está vacío).
  * SOLICITADO POR     ← GESTOR (si está vacío).
  * PROYECTO FLM        ← CLIENTE (ENTEL → "FLM - ENTEL"), si está vacío.
  * TIPO GASTO APROBACION: "Caja chica" → "Caja Chica" (mismo valor, otra escritura).
Aplicado en producción el 2026-11-16 (respaldo: app_config backup_cotizaciones_20261116_premigracion).
No cambia números, estados, montos ni "TIPO DE GASTO".

Uso:
    python scripts/migrar_cot_new.py --url sqlite:///copia.db            # solo reporte
    python scripts/migrar_cot_new.py --url sqlite:///copia.db --aplicar  # aplica y guarda respaldo
"""
import argparse
import json
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

RAIZ = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# "Tipo de cotización" (texto libre del módulo antiguo) → lista oficial de Cot_New.
CONCEPTOS = {
    'servicio': 'Servicio', 'servicios varios': 'Servicio', 'servicio de grua': 'Servicio',
    'alquiler': 'Alquiler', 'alquileres': 'Alquiler',
    'acarreo': 'Acarreo',
    'suministros': 'Compras y suministros', 'compras': 'Compras y suministros', 'compra': 'Compras y suministros',
    'compras y suministros': 'Compras y suministros',
    'desplazamiento fuera de zona': 'Desplazamiento fuera de zona',
    'transporte fluvial': 'Transporte fluvial', 'bandeo fluvial': 'Transporte fluvial',
    'resguardos': 'Custodio y resguardo', 'custodio y resguardo': 'Custodio y resguardo',
    'personal y mano de obra': 'Personal y mano de obra',
    'otros': 'Otros',
}
ATENCION = {'caja chica': 'Caja Chica', 'proveedor': 'Proveedor', 'transito': 'Tránsito'}


def plano(texto):
    texto = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(texto.lower().split())


def cambios_de(datos):
    """Campos a escribir en una cotización (vacío si ya está ordenada)."""
    cambios = {}
    if not str(datos.get('TIPO DE CONCEPTO') or '').strip():
        concepto = CONCEPTOS.get(plano(datos.get('TIPO DE COTIZACION')))
        if concepto:
            cambios['TIPO DE CONCEPTO'] = concepto
    if not str(datos.get('SOLICITADO POR') or '').strip() and str(datos.get('GESTOR') or '').strip():
        cambios['SOLICITADO POR'] = str(datos['GESTOR']).strip()
    cliente = str(datos.get('CLIENTE') or '').strip().upper()
    if not str(datos.get('PROYECTO FLM') or '').strip() and cliente in ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT'):
        cambios['PROYECTO FLM'] = 'FLM - ' + cliente
    atencion = str(datos.get('TIPO GASTO APROBACION') or '').strip()
    canonica = ATENCION.get(plano(atencion))
    if atencion and canonica and canonica != atencion:
        cambios['TIPO GASTO APROBACION'] = canonica
    return cambios


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', required=True, help='Base de datos (sqlite:///… o postgresql://…)')
    parser.add_argument('--aplicar', action='store_true', help='Escribe los cambios (sin esto, solo reporte)')
    args = parser.parse_args()
    url = args.url.replace('postgres://', 'postgresql://', 1)
    motor = create_engine(url)
    with motor.begin() as con:
        pid = con.execute(text("SELECT id FROM proyectos WHERE nombre = 'Cotizaciones'")).scalar()
        if pid is None:
            raise SystemExit('No existe el módulo Cotizaciones en esa base.')
        filas = con.execute(text('SELECT id, key_value, data_json FROM nucleus_data WHERE proyecto_id = :p'), {'p': pid}).all()
        resumen, sin_mapa, respaldo, pendientes = Counter(), Counter(), [], []
        for rid, clave, crudo in filas:
            try:
                datos = json.loads(crudo or '{}')
            except ValueError:
                resumen['JSON inválido (sin tocar)'] += 1
                continue
            cambios = cambios_de(datos)
            tipo = str(datos.get('TIPO DE COTIZACION') or '').strip()
            if tipo and not str(datos.get('TIPO DE CONCEPTO') or '').strip() and plano(tipo) not in CONCEPTOS:
                sin_mapa[tipo] += 1
            if not cambios:
                continue
            for campo, valor in cambios.items():
                resumen['%s → %s' % (campo, valor) if campo != 'SOLICITADO POR' else 'SOLICITADO POR ← GESTOR'] += 1
            respaldo.append({'id': rid, 'key': clave, 'antes': {c: datos.get(c) for c in cambios}})
            pendientes.append((rid, json.dumps({**datos, **cambios}, ensure_ascii=False)))
        print('Cotizaciones: %d · a modificar: %d' % (len(filas), len(pendientes)))
        for linea, n in sorted(resumen.items()):
            print('  %4d  %s' % (n, linea))
        if sin_mapa:
            print('Tipos de cotización sin equivalencia (quedan sin concepto):')
            for tipo, n in sin_mapa.most_common():
                print('  %4d  %s' % (n, tipo))
        if not args.aplicar:
            print('Solo reporte. Usa --aplicar para escribir.')
            return
        carpeta = RAIZ / 'backups'
        carpeta.mkdir(exist_ok=True)
        archivo = carpeta / ('migrar_cot_new_%s.json' % datetime.now().strftime('%Y%m%d_%H%M%S'))
        archivo.write_text(json.dumps(respaldo, ensure_ascii=False, indent=1), encoding='utf-8')
        for rid, nuevo in pendientes:
            con.execute(text('UPDATE nucleus_data SET data_json = :d WHERE id = :i'), {'d': nuevo, 'i': rid})
        print('Aplicado. Respaldo de valores anteriores: %s' % archivo)


if __name__ == '__main__':
    sys.exit(main())
