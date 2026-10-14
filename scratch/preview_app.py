"""App de PRUEBA para verificar el dashboard: BD temporal, no toca nucleus.db."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(r'C:\Mega\Proyect\Nucleus')
TMP = Path(tempfile.mkdtemp(prefix='nucleus_dash_preview_'))
os.environ['DATABASE_URL'] = 'sqlite:///' + str(TMP / 'preview.db').replace('\\', '/')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'preview-secret')
sys.path.insert(0, str(ROOT))

from app import create_app                      # noqa: E402
from config import TestingConfig                # noqa: E402


class PreviewConfig(TestingConfig):
    EVIDENCIA_DIR = str(TMP / 'evidencia')
    SQLALCHEMY_ENGINE_OPTIONS = {}


app = create_app(PreviewConfig)

with app.app_context():
    from db import db
    from models import Proyecto, NucleusData
    db.create_all()
    rend = Proyecto.query.filter_by(nombre='Rendicion').first()
    cot = Proyecto.query.filter_by(nombre='Cotizaciones').first()

    REND = [
        ('R1', '', '70.36', 'Integratel', 'NO REFACTURABLE', 'Movilidad', 'hvargas'),
        ('R2', '', '120.00', 'Integratel', 'REFACTURABLE', 'Materiales', 'n_flm'),
        ('R3', '', '45.50', 'Claro', 'NO REFACTURABLE', 'Alimentación', 'hvargas'),
        ('R4', 'VALIDADO', '300.00', 'Claro', 'REFACTURABLE', 'Servicio', 'laracca'),
        ('R5', 'VALIDADO', '150.25', 'Integratel', 'NO REFACTURABLE', 'Movilidad', 'n_flm'),
        ('R6', 'DEPOSITADO', '210.00', 'Integratel', 'REFACTURABLE', 'Materiales', 'hvargas'),
        ('R7', 'DEPOSITADO', '90.00', 'Claro', 'NO REFACTURABLE', 'Movilidad', 'laracca'),
        ('R8', 'CON SUSTENTO', '80.00', 'Claro', 'REFACTURABLE', 'Servicio', 'hvargas'),
        ('R9', 'OBSERVADO', '60.00', 'Integratel', 'NO REFACTURABLE', 'Alimentación', 'n_flm'),
        ('R10', 'SUSTENTADO', '500.00', 'Claro', 'REFACTURABLE', 'Servicio', 'laracca'),
        ('R11', 'ARCHIVADO', '25.00', 'Integratel', 'NO REFACTURABLE', 'Movilidad', 'hvargas'),
        ('R12', 'ANULADO', '400.00', 'Claro', 'REFACTURABLE', 'Materiales', 'n_flm'),
        ('R13', 'RECHAZADO', '75.00', 'Integratel', 'NO REFACTURABLE', 'Movilidad', 'laracca'),
    ]
    for key, estado, monto, proy, presu, gasto, quien in REND:
        d = {'ESTADO': estado, 'Marca temporal': '2026-10-%02d 10:%02d' % (int(key[1:]) + 1, int(key[1:]) * 3 % 60),
             'Monto total del depósito': monto, 'Nombre de site': 'SITE ' + key,
             'Nombre del proyecto': proy, 'Tipo de presupuesto': presu, 'Tipo de gasto': gasto,
             'INTERACCION': quien, 'Técnico beneficiario': 'TEC ' + key,
             'Número CM / PM / PLM': 'CM-' + key, 'Supervisor encargado': 'sup_' + quien,
             'OBSERVACIONES': 'Motivo de prueba ' + key}
        if estado == 'DEPOSITADO':
            d.update({'MONTO PAGO': monto, 'FOTO PAGO': '/x/foto.jpg', 'DEPOSITADO POR': quien,
                      'FECHA PAGO': '2026-10-20 11:00'})
        if estado == 'VALIDADO':
            d.update({'VALIDADO POR': quien, 'FECHA VALIDACION': '2026-10-18 09:00'})
        if estado == 'RECHAZADO':
            d.update({'RECHAZADO POR': quien, 'FECHA RECHAZO': '2026-10-19 09:00', 'VECES RECHAZADO': '2',
                      'RECHAZADO DESDE': 'VALIDADO'})
        db.session.add(NucleusData(proyecto_id=rend.id, key_value=key, data_json=json.dumps(d, ensure_ascii=False)))

    # Fila con evidencias para revisar el modal "Detalle de Evidencia"
    d_ev = {'ESTADO': 'CON SUSTENTO', 'Marca temporal': '2026-10-11 09:00',
            'Monto total del depósito': '22', 'Nombre de site': 'SITE ALTO',
            'Nombre del proyecto': 'Integratel', 'Tipo de presupuesto': 'REFACTURABLE',
            'Tipo de gasto': 'PEAJE', 'INTERACCION': 'hvargas',
            'Técnico beneficiario': 'TEC ALTO', 'Número CM / PM / PLM': 'CM-EV-1',
            'FOTO PAGO': '/static/img/cobra-logo.png',
            'SUSTENTO_TIPO DE COMPROBANTE': 'Factura',
            'SUSTENTO_PRECIO TOTAL': '22',
            'SUSTENTO_INGRESE RUC DE PROVEDOR': '20452694690',
            'SUSTENTO_ADJUNTAR COMPROBANTE': '/static/img/cobra-logo.png',
            'SUSTENTO_CARGAR EVIDENCIAS': '/static/logo.png',
            'SUSTENTO_TIPO DE PROYECTO': 'Integratel',
            'SUSTENTO_NUMERO DE COMPROBANTE': 'F001-1234',
            'COMENTARIOS SUSTENTO': 'Comprobante conforme'}
    db.session.add(NucleusData(proyecto_id=rend.id, key_value='R-EVIDENCIA',
                               data_json=json.dumps(d_ev, ensure_ascii=False)))

    COT = [('C1', 'Pdt. Cotización', '1050.00', 'ENTEL', 'hvargas'),
           ('C2', 'Pdt. Cotización', '105.00', 'ENTEL', 'hvargas'),
           ('C3', 'En Aprobación', '904.05', 'CLARO', 'hvargas'),
           ('C4', 'En Aprobación', '250.00', 'CLARO', 'laracca'),
           ('C5', 'Aprobado', '1500.00', 'ENTEL', 'n_flm'),
           ('C6', 'Aprobado', '300.00', 'CLARO', 'hvargas'),
           ('C7', 'Atendido', '2200.00', 'ENTEL', 'hvargas'),
           ('C8', 'Validado', '105.00', 'ENTEL', 'n_flm'),
           ('C9', 'Cancelado', '80.00', 'CLARO', 'laracca'),
           ('C10', 'Pendiente de Aprobación', '640.00', 'CLARO', 'hvargas')]
    for i, (key, estado, monto, cliente, quien) in enumerate(COT):
        d = {'N° COTIZACION': 'HW-2026-0000%02d' % (i + 10), 'ESTADO COTIZACION': estado,
             'SUB TOTAL + FEE': monto, 'CLIENTE': cliente, 'GESTOR': quien, 'COTIZADO POR': quien,
             'FECHA': '2026-10-%02d 09:00' % (i + 1), 'NOMBRE SITE': 'SITE ' + key,
             'TIPO DE COTIZACION': ['Acarreo', 'Suministros', 'Servicio'][i % 3],
             'GENERADA': '1' if i > 1 else '', 'NUMERO WO': 'CM-100%d' % i,
             'ADJUNTO CORREO CLIENTE': '/x/correo.msg' if i % 2 else '',
             'ADJUNTO FACTURA PROVEEDOR': '/x/factura.pdf' if i % 3 == 0 else '',
             'ADJUNTO COTIZACION PROVEEDOR': '/x/cotprov.pdf' if i % 2 == 0 else '',
             'SUBTOTAL FACTURA PROVEEDOR': monto if i % 3 == 0 else '',
             'FECHA APROBACION': '2026-10-15 10:00' if estado in ('Aprobado', 'Atendido', 'Validado') else '',
             'FECHA ATENCION': '2026-10-19 10:00' if estado in ('Atendido', 'Validado') else '',
             'SOLICITADO POR': quien}
        db.session.add(NucleusData(proyecto_id=cot.id, key_value=d['N° COTIZACION'], data_json=json.dumps(d, ensure_ascii=False)))
    db.session.commit()
    print('PREVIEW OK ->', TMP, flush=True)

if __name__ == '__main__':
    app.run(port=5055, debug=False, use_reloader=False)
