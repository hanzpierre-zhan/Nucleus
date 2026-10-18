"""Inicia el piloto en localhost con una copia de trabajo o datos ficticios."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument('--backup', type=Path, help='Copia SQLite con manifiesto verificado')
    origen.add_argument('--demo', action='store_true', help='Datos ficticios, NO producción')
    parser.add_argument('--port', type=int, default=5058)
    args = parser.parse_args()
    carpeta = RAIZ / 'backups'
    carpeta.mkdir(exist_ok=True)
    ensayo = Path(tempfile.mkdtemp(prefix='ensayo-espacios-', dir=carpeta))
    destino = ensayo / 'trabajo.db'
    if args.backup:
        original = args.backup.resolve(strict=True)
        manifiesto = json.loads(original.with_suffix('.manifest.json').read_text(encoding='utf-8'))
        if manifiesto.get('apto_para_ensayo') is False or manifiesto.get('relaciones_pendientes', 0):
            raise SystemExit('Este respaldo conserva relaciones pendientes. Revisa el informe antes del ensayo.')
        with original.open('rb') as archivo:
            if hashlib.file_digest(archivo, 'sha256').hexdigest() != manifiesto['sha256']:
                raise SystemExit('La huella del respaldo no coincide. No se inicia el ensayo.')
        with sqlite3.connect('file:' + original.as_posix() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(destino) as dst:
                src.backup(dst)
    os.environ['DATABASE_URL'] = 'sqlite:///' + destino.as_posix()
    os.environ['SECRET_KEY'] = secrets.token_urlsafe(48)
    os.environ['ESPACIOS_HABILITADOS'] = '1'
    # La aplicación solo recibirá credenciales de la base local, nunca servicios reales.
    for clave in list(os.environ):
        if clave.startswith(('B2_', 'OD_', 'RENDER_API_', 'NEON_')):
            os.environ.pop(clave)
    from services.sandbox import instalar_bloqueo_red, instalar_guardas_http
    instalar_bloqueo_red()
    from app import app
    from db import db
    from models import (Usuario, Proyecto, NucleusData, PerfilEspacio, AccesoEspacio,
                        CuentaEspacio, TokenStore, AppConfig, ConformidadUsuario)
    from werkzeug.security import generate_password_hash
    from services.espacios import MODULOS, PROYECTOS
    app.config['EVIDENCIA_DIR'] = str(ensayo / 'adjuntos-locales')
    app.config['SESSION_COOKIE_NAME'] = 'nucleus_ensayo_' + str(args.port)
    os.makedirs(app.config['EVIDENCIA_DIR'], exist_ok=True)
    instalar_guardas_http(app)
    with app.app_context():
        TokenStore.query.delete()
        for cfg in AppConfig.query.all():
            if any(s in cfg.clave.lower() for s in ('token', 'secret', 'password', 'sync_key')):
                cfg.valor = ''
        nombre_admin = 'ensayo-admin-' + secrets.token_hex(3)
        clave_admin = secrets.token_urlsafe(16)
        admin = Usuario(username=nombre_admin, nombre='Administrador de pruebas',
                        password_hash=generate_password_hash(clave_admin), rol='zeno')
        db.session.add(admin); db.session.flush()
        db.session.add(ConformidadUsuario(usuario_id=admin.id, version='2026-10-09'))
        if args.demo:
            perfil = PerfilEspacio(nombre='Gestor de demostración', permisos_json=json.dumps({
                m: ['consultar', 'exportar'] for m in MODULOS}))
            db.session.add(perfil); db.session.flush()
            gestor = Usuario(username='ensayo-gestor-claro', nombre='Gestor de Claro (demostración)',
                             password_hash=generate_password_hash(clave_admin), rol='gestor')
            db.session.add(gestor); db.session.flush()
            db.session.add(CuentaEspacio(usuario_id=gestor.id))
            for nombre, etiqueta in PROYECTOS.items():
                p = Proyecto.query.filter_by(nombre=nombre).one()
                if etiqueta == 'Claro':
                    db.session.add(AccesoEspacio(usuario_id=gestor.id, proyecto_id=p.id, perfil_id=perfil.id))
                db.session.add(NucleusData(proyecto_id=p.id,key_value='DEMO-WO-' + etiqueta,
                    data_json=json.dumps({'Nombre de Site':'Site de demostración ' + etiqueta,
                                          'ESTADO DE EJECUCION':'Pendiente','FECHA':'2026-10-17'})))
                for modulo, (_, catalogo) in MODULOS.items():
                    if not catalogo or modulo == 'liquidaciones':
                        continue
                    fuente = Proyecto.query.filter_by(nombre=catalogo).one()
                    datos = {'PROYECTO':etiqueta, 'Nombre del proyecto':etiqueta,
                             'TECNICO':'Técnico de demostración ' + etiqueta,
                             'NOMBRE DE SITE':'Site de demostración ' + etiqueta,
                             'DESCRIPCION_MATERIAL':'Material de demostración',
                             'Marca temporal':'17/10/2026 10:00:00', 'ESTADO':'PENDIENTE',
                             'ESTADO COTIZACION':'En Aprobación', 'GENERADA':'1',
                             'SUB TOTAL + FEE':'100.00','OBSERVACIONES':'Registro ficticio para pruebas'}
                    db.session.add(NucleusData(proyecto_id=fuente.id,
                        key_value='DEMO-' + modulo + '-' + etiqueta, data_json=json.dumps(datos)))
        db.session.commit()
    acceso = {'url':'http://127.0.0.1:%d/espacios' % args.port,
              'usuario':nombre_admin,'clave':clave_admin,
              'datos':'FICTICIOS' if args.demo else 'COPIA LOCAL',
              'gestor_demo':'ensayo-gestor-claro' if args.demo else None}
    (ensayo / 'acceso-local.json').write_text(json.dumps(acceso, indent=2), encoding='utf-8')
    (RAIZ / 'backups' / 'ultimo-ensayo-espacios.json').write_text(
        json.dumps({'carpeta':str(ensayo)}, indent=2), encoding='utf-8')
    print('Ensayo local: ' + str(ensayo), flush=True)
    print('Datos: ' + acceso['datos'] + '. Salidas de red bloqueadas. Acceso en acceso-local.json.', flush=True)
    app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
