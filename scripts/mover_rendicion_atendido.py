"""Devuelve a "Atendido" un registro de Rendición rechazado por error.

Busca el registro por su código de depósito (por ejemplo COB-00435) dentro del
proyecto Rendicion y, solo con --aplicar, lo deja en ESTADO=SUSTENTADO
(hoja Atendido), limpia el subestado y deja la corrección anotada en
_HISTORIAL_FLUJO. No borra el rechazo: RECHAZADO POR, MOTIVO RECHAZO y
VECES RECHAZADO quedan como historial.

Uso (en Render Shell o local apuntando a producción):
    python scripts/mover_rendicion_atendido.py --codigo COB-00435
    python scripts/mover_rendicion_atendido.py --codigo COB-00435 --aplicar

La conexión sale de DATABASE_URL (o de --url). La URL nunca se imprime.
Sin --aplicar no escribe nada: solo muestra lo que haría.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from services.rendicion_estados import etapa_de  # noqa: E402


def motor(url):
    parsed = make_url(url)
    if parsed.drivername in ('postgres', 'postgresql'):
        parsed = parsed.set(drivername='postgresql+psycopg2')
    return create_engine(parsed, pool_pre_ping=True)


def buscar(conn, codigo):
    pid = conn.execute(text(
        "select id from proyectos where lower(trim(nombre)) = 'rendicion'"
    )).scalar()
    if not pid:
        raise SystemExit('No existe el proyecto Rendicion en esta base.')
    filas = conn.execute(text(
        "select id, key_value, data_json from nucleus_data where proyecto_id = :pid"
    ), {'pid': pid}).mappings()
    encontrados = []
    for fila in filas:
        crudo = fila['data_json'] or ''
        if codigo.upper() not in crudo.upper():
            continue
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            continue
        if str(datos.get('CODIGO DEPOSITO') or '').strip().upper() == codigo.upper():
            encontrados.append((fila['id'], fila['key_value'], crudo, datos))
    return encontrados


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--codigo', required=True, help='Código de depósito, ej. COB-00435')
    parser.add_argument('--url', default=os.environ.get('DATABASE_URL', '').strip(),
                        help='URL de la base (por defecto DATABASE_URL)')
    parser.add_argument('--aplicar', action='store_true',
                        help='Escribe el cambio. Sin esta bandera solo muestra el plan.')
    parser.add_argument('--forzar', action='store_true',
                        help='Permite mover un registro que no está en RECHAZADO.')
    parser.add_argument('--motivo', default='Corrección: rechazo por error, se devuelve a Atendido.')
    args = parser.parse_args()

    codigo = args.codigo.strip().upper()
    if not args.url:
        raise SystemExit('Falta DATABASE_URL (o --url).')

    motor_bd = motor(args.url)
    try:
        with motor_bd.begin() as conn:
            encontrados = buscar(conn, codigo)
            if not encontrados:
                raise SystemExit('No encontré ningún registro con CODIGO DEPOSITO %s.' % codigo)
            if len(encontrados) > 1:
                print('Hay %d registros con ese código. No toco nada:' % len(encontrados))
                for fila_id, clave, _, _ in encontrados:
                    print('  id=%s  key=%s' % (fila_id, clave))
                raise SystemExit('Repite el proceso indicando el registro exacto.')

            fila_id, clave, crudo, datos = encontrados[0]
            estado = str(datos.get('ESTADO') or '').strip().upper() or 'PENDIENTE'
            print('Registro id=%s  key=%s' % (fila_id, clave))
            print('  ESTADO actual     : %s' % estado)
            print('  Hoja actual       : %s' % etapa_de(datos))
            print('  Rechazado desde   : %s' % (datos.get('RECHAZADO DESDE') or '-'))
            print('  Motivo del rechazo: %s' % (datos.get('MOTIVO RECHAZO') or '-'))
            print('  Código depósito   : %s' % codigo)

            if estado == 'SUSTENTADO':
                print('\nYa está en Atendido. No hay nada que cambiar.')
                return
            if not estado == 'RECHAZADO':
                print('\nOjo: el registro no está rechazado (está en %s).' % estado)
                print('Revisa antes de moverlo: este script está pensado para deshacer un rechazo.')
                if args.aplicar and not args.forzar:
                    raise SystemExit('No lo moví. Si estás seguro, repite con --forzar.')

            if not args.aplicar:
                print('\nPlan: ESTADO -> SUSTENTADO (Atendido), SUBESTADO vacío, historial con la corrección.')
                print('No se escribió nada. Agrega --aplicar para hacerlo.')
                return

            antes = estado
            datos['ESTADO'] = 'SUSTENTADO'
            datos['SUBESTADO'] = ''
            historial = datos.get('_HISTORIAL_FLUJO')
            if not isinstance(historial, list):
                historial = []
            historial.append({
                'accion': 'correccion_atendido',
                'desde': antes,
                'hasta': 'SUSTENTADO',
                'subestado_desde': '',
                'subestado_hasta': '',
                'usuario': 'correccion-admin',
                'fecha': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'motivo': args.motivo,
            })
            datos['_HISTORIAL_FLUJO'] = historial
            nuevo = json.dumps(datos, ensure_ascii=False)
            cambiadas = conn.execute(text(
                "update nucleus_data set data_json = :d where id = :i and data_json = :antes"
            ), {'d': nuevo, 'i': fila_id, 'antes': crudo}).rowcount
            if cambiadas != 1:
                raise SystemExit('No se actualizó ninguna fila (¿cambió mientras corría?).')
            print('\nListo: %s pasó de %s a Atendido (SUSTENTADO).' % (codigo, antes))
    finally:
        motor_bd.dispose()


if __name__ == '__main__':
    main()
