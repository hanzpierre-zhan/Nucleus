# -*- coding: utf-8 -*-
"""Módulo de migraciones y arranque de base de datos.
Se ejecuta una sola vez al iniciar la app (idempotente).
"""
import json
import time
import re
from datetime import datetime
from sqlalchemy import inspect


def run_migrations(app, database_url=''):
    from db import db
    from models import (Usuario, Proyecto, AppConfig, NucleusData, NucleusHistory,
                        FiltroMaestro, TablaMaestra, ReglaEstadoManual, AccesoProyecto,
                        KpiConfig, HistorialCambios, Tecnico, Cotizacion, TokenStore)
    from werkzeug.security import generate_password_hash

    def _sane_data_key(k):
        return str(k).replace('.', '_')

    def _sane_dict(d):
        return {_sane_data_key(k): v for k, v in d.items()}

    with app.app_context():
        # ── Lock de migración (solo PostgreSQL) ──────────────────────────────
        _using_pooler = '-pooler' in (database_url or '')
        _mig_lock_conn = None
        try:
            if db.engine.dialect.name == 'postgresql' and not _using_pooler:
                _cand = db.engine.connect()
                for _ in range(30):
                    if _cand.execute(db.text("SELECT pg_try_advisory_lock(917348261)")).scalar():
                        _mig_lock_conn = _cand
                        break
                    time.sleep(1)
                if _mig_lock_conn is None:
                    _cand.close()
        except Exception as e:
            print("Warning: lock de migración no disponible:", e)

        is_sqlite = db.engine.dialect.name == 'sqlite'
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        has_old = 'nucleus_data_old' in tables
        needs_migration = False
        if 'nucleus_data' in tables:
            cols = [c['name'] for c in inspector.get_columns('nucleus_data')]
            if 'proyecto_id' not in cols:
                needs_migration = True

        if is_sqlite and needs_migration and not has_old:
            print("Migrating database to Multi-Project schema...")
            db.session.execute(db.text("ALTER TABLE nucleus_data RENAME TO nucleus_data_old"))
            db.session.execute(db.text("ALTER TABLE app_config RENAME TO app_config_old"))
            db.session.execute(db.text("ALTER TABLE filtros_maestros RENAME TO filtros_maestros_old"))
            db.session.execute(db.text("ALTER TABLE tablas_maestras RENAME TO tablas_maestras_old"))
            db.session.commit()
            has_old = True

        db.create_all()

        # ── Índices de rendimiento ─────────────────────────────────────────
        _perf_indexes = [
            "CREATE INDEX IF NOT EXISTS ix_nucleus_data_proyecto_id ON nucleus_data (proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_nucleus_data_proy_key ON nucleus_data (proyecto_id, key_value)",
            "CREATE INDEX IF NOT EXISTS ix_app_config_proy_clave ON app_config (proyecto_id, clave)",
            "CREATE INDEX IF NOT EXISTS ix_hist_cambios_proy_campo_key ON historial_cambios (proyecto_id, campo_modificado, key_value)",
            "CREATE INDEX IF NOT EXISTS ix_accesos_proyecto_usuario ON accesos_proyecto (usuario_id)",
            "CREATE INDEX IF NOT EXISTS ix_accesos_proyecto_user_proy ON accesos_proyecto (usuario_id, proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_cotizaciones_proy_key ON cotizaciones (proyecto_id, key_value)",
            "CREATE INDEX IF NOT EXISTS ix_filtros_maestros_proy ON filtros_maestros (proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_tablas_maestras_proy ON tablas_maestras (proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_reglas_estado_manual_proy ON reglas_estado_manual (proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_kpi_configs_proy ON kpi_configs (proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_tecnicos_proy ON tecnicos (proyecto_id)",
            "CREATE INDEX IF NOT EXISTS ix_nucleus_history_proy_key ON nucleus_history (proyecto_id, key_value)",
        ]
        for _idx_sql in _perf_indexes:
            try:
                db.session.execute(db.text(_idx_sql))
            except Exception as e:
                print("Warning: no se pudo crear índice:", e)
        db.session.commit()

        # ── Columna 'nombre' en usuarios ───────────────────────────────────
        try:
            ucols = [c['name'] for c in inspect(db.engine).get_columns('usuarios')]
            if 'nombre' not in ucols:
                db.session.execute(db.text("ALTER TABLE usuarios ADD COLUMN nombre VARCHAR(100) DEFAULT ''"))
                db.session.commit()
                print("Added 'nombre' column to usuarios")
        except Exception as e:
            print("Warning: could not add nombre column:", e)

        # ── Admin por defecto ─────────────────────────────────────────────
        if not Usuario.query.first():
            admin = Usuario(username='zeno', password_hash=generate_password_hash('zeno123'), rol='zeno')
            db.session.add(admin)
            db.session.commit()

        # ── Migración de roles ────────────────────────────────────────────
        try:
            db.session.execute(db.text("UPDATE usuarios SET rol='zeno' WHERE rol='admin'"))
            db.session.execute(db.text("UPDATE usuarios SET rol = 'supervisor' WHERE rol = 'editor'"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # ── Cotizaciones: quitar unique constraint _proj_key_coti_uc ─────
        try:
            cot_tables = inspect(db.engine).get_table_names()
            if 'cotizaciones' in cot_tables:
                if is_sqlite:
                    sql = db.session.execute(db.text(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cotizaciones'"
                    )).scalar() or ''
                    if '_proj_key_coti_uc' in sql:
                        db.session.execute(db.text("ALTER TABLE cotizaciones RENAME TO cotizaciones_old"))
                        db.session.commit()
                        db.create_all()
                        cols = [c['name'] for c in inspect(db.engine).get_columns('cotizaciones_old')]
                        collist = ', '.join(cols)
                        db.session.execute(db.text(f"INSERT INTO cotizaciones ({collist}) SELECT {collist} FROM cotizaciones_old"))
                        db.session.execute(db.text("DROP TABLE cotizaciones_old"))
                        db.session.commit()
                else:
                    db.session.execute(db.text("ALTER TABLE cotizaciones DROP CONSTRAINT IF EXISTS _proj_key_coti_uc"))
                    db.session.commit()
        except Exception as e:
            print("Warning: cotizaciones migration:", e)

        # ── Cotizaciones: columnas formato Cobra ──────────────────────────
        try:
            if 'cotizaciones' in inspect(db.engine).get_table_names():
                cot_cols = [c['name'] for c in inspect(db.engine).get_columns('cotizaciones')]
                with db.engine.begin() as conn:
                    if 'formato' not in cot_cols:
                        conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN formato VARCHAR(20) DEFAULT ''"))
                    if 'site' not in cot_cols:
                        conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN site VARCHAR(200) DEFAULT ''"))
                    if 'supervisor' not in cot_cols:
                        conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN supervisor VARCHAR(120) DEFAULT ''"))
                    if 'items_json' not in cot_cols:
                        conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN items_json TEXT DEFAULT '[]'"))
        except Exception as e:
            print("Warning: cotizaciones cobra migration:", e)

        # ── Proyecto inicial ──────────────────────────────────────────────
        if not Proyecto.query.first():
            pangeaco = Proyecto(nombre='Pangeaco', descripcion='Proyecto inicial migrado')
            db.session.add(pangeaco)
            db.session.commit()
        else:
            pangeaco = Proyecto.query.first()

        if is_sqlite and has_old:
            pid = pangeaco.id
            print("Restoring data from old tables...")
            try:
                db.session.execute(db.text(f"INSERT OR IGNORE INTO nucleus_data (proyecto_id, key_value, data_json) SELECT {pid}, key_value, data_json FROM nucleus_data_old"))
                db.session.execute(db.text(f"INSERT OR IGNORE INTO app_config (proyecto_id, clave, valor) SELECT {pid}, clave, valor FROM app_config_old"))
                db.session.execute(db.text(f"INSERT OR IGNORE INTO filtros_maestros (proyecto_id, columna, valor) SELECT {pid}, columna, valor FROM filtros_maestros_old"))
                db.session.execute(db.text(f"INSERT OR IGNORE INTO tablas_maestras (proyecto_id, columna_criterio, valor_criterio, nueva_columna, nuevo_valor) SELECT {pid}, columna_criterio, valor_criterio, nueva_columna, nuevo_valor FROM tablas_maestras_old"))
            except Exception as e:
                print(f"Error restoring data: {e}")
            db.session.execute(db.text("DROP TABLE IF EXISTS nucleus_data_old"))
            db.session.execute(db.text("DROP TABLE IF EXISTS app_config_old"))
            db.session.execute(db.text("DROP TABLE IF EXISTS filtros_maestros_old"))
            db.session.execute(db.text("DROP TABLE IF EXISTS tablas_maestras_old"))
            db.session.commit()

        # ── Eliminar proyectos retirados ──────────────────────────────────
        # NOTA: 'FLM' NO se incluye aquí porque se renombra a 'FLM - ENTEL' más abajo.
        PROYECTOS_RETIRADOS = ('PEXT', 'PEXT (old)', 'Claro', 'Integratel', 'CLARO', 'INTEGRATEL')
        for _del_name in PROYECTOS_RETIRADOS:
            try:
                _dp = Proyecto.query.filter_by(nombre=_del_name).first()
                if _dp:
                    _dpid = _dp.id
                    for _dtbl in (NucleusData, AppConfig, AccesoProyecto, KpiConfig,
                                  HistorialCambios, FiltroMaestro, TablaMaestra,
                                  ReglaEstadoManual, Cotizacion, Tecnico, NucleusHistory):
                        _dtbl.query.filter_by(proyecto_id=_dpid).delete()
                    db.session.delete(_dp)
                    db.session.commit()
                    print(f"Eliminado proyecto '{_del_name}' (id={_dpid}) y toda su data.")
            except Exception as e:
                print(f"Warning: no se pudo eliminar '{_del_name}':", e)
                db.session.rollback()

        # ── Renombrar FLM -> FLM - ENTEL (idempotente) ─────────────────────
        try:
            _old_f = Proyecto.query.filter_by(nombre='FLM').first()
            _already_f = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
            if _old_f and not _already_f:
                _old_f.nombre = 'FLM - ENTEL'
                db.session.commit()
                print("Renombrado FLM -> FLM - ENTEL")
        except Exception as e:
            print("Warning: rename FLM:", e)
            db.session.rollback()

        # ── Proyectos fijos ───────────────────────────────────────────────
        fixed = [
            ('FLM - ENTEL', 'FLM – Proyecto Entel'),
            ('Dataper', 'DataPer S.A.C.'),
            ('Material', 'Materiales Disponibles'),
            ('Site Name', 'Sitios (solo FLM)'),
            ('Generadores', 'Grupos Electrógenos (solo FLM)'),
            ('Combustible', 'Consumo de Combustible (solo FLM)'),
            ('Cotizaciones', 'Registro de Cotizaciones (solo FLM)'),
            ('SITE', 'Maestro de Sites – COBRA SITES (10 columnas)'),
        ]
        for nombre, desc in fixed:
            if not Proyecto.query.filter_by(nombre=nombre).first():
                db.session.add(Proyecto(nombre=nombre, descripcion=desc))
        db.session.commit()

        # ── Sanear claves data_json (Tabulator rompe con '.') ─────────────
        try:
            for _prj in Proyecto.query.all():
                _changed = True
                _rounds = 0
                while _changed and _rounds < 10:
                    _changed = False
                    _rows = NucleusData.query.filter_by(proyecto_id=_prj.id).all()
                    for _r in _rows:
                        try:
                            _d = json.loads(_r.data_json)
                        except Exception:
                            continue
                        if any('.' in str(k) for k in _d.keys()):
                            _r.data_json = json.dumps(_sane_dict(_d), ensure_ascii=False)
                            _changed = True
                    db.session.commit()
                    _rounds += 1
        except Exception as e:
            print("Warning: saneo de data_json:", e)
            try:
                db.session.rollback()
            except Exception:
                pass

        # ── Migraciones de app_schema y column_layout saneados ────────────
        for _prj in Proyecto.query.all():
            try:
                _schema_c = AppConfig.query.filter_by(proyecto_id=_prj.id, clave='app_schema').first()
                if _schema_c and _schema_c.valor and '"."' in _schema_c.valor:
                    _lista = json.loads(_schema_c.valor)
                    _sane = sorted({_sane_data_key(c) for c in _lista})
                    _schema_c.valor = json.dumps(_sane, ensure_ascii=False)
                    db.session.commit()
            except Exception:
                pass
        for _prj in Proyecto.query.all():
            try:
                _lay_c = AppConfig.query.filter_by(proyecto_id=_prj.id, clave='column_layout').first()
                if _lay_c and _lay_c.valor and '"."' in _lay_c.valor:
                    _lay = json.loads(_lay_c.valor)
                    for _lc in _lay:
                        if isinstance(_lc, dict) and '.' in str(_lc.get('field', '')):
                            _lc['field'] = _sane_data_key(_lc.get('field'))
                    _lay_c.valor = json.dumps(_lay, ensure_ascii=False)
                    db.session.commit()
            except Exception:
                pass

        # ── Configurar proyectos de apoyo (Dataper, Material, SITE, etc.) ─
        _configurar_proyectos_apoyo(db, app, Proyecto, AppConfig, NucleusData, TablaMaestra)

        # ── PK de FLM - ENTEL ───────────────────────────────────────────────
        for _flm_nombre, _flm_pk in (('FLM - ENTEL', 'Número de WO'),):
            _fp = Proyecto.query.filter_by(nombre=_flm_nombre).first()
            if not _fp:
                continue
            _pk_cfg = AppConfig.query.filter_by(proyecto_id=_fp.id, clave='primary_key').first()
            if not _pk_cfg:
                db.session.add(AppConfig(proyecto_id=_fp.id, clave='primary_key', valor=_flm_pk))
            elif str(_pk_cfg.valor or '').strip() in ('', 'Contractor'):
                _pk_cfg.valor = _flm_pk
        db.session.commit()

        # ── GESTOR y EDITADO POR en FLM - ENTEL ────────────────────────────
        try:
            for proy_g in ('FLM - ENTEL',):
                proy_g_obj = Proyecto.query.filter_by(nombre=proy_g).first()
                if not proy_g_obj:
                    continue
                _schema_p = AppConfig.query.filter_by(proyecto_id=proy_g_obj.id, clave='app_schema').first()
                try:
                    _schema_set = set(json.loads(_schema_p.valor)) if _schema_p and _schema_p.valor else set()
                except Exception:
                    _schema_set = set()
                for _col in ('EDITADO POR', 'GESTOR'):
                    if _col not in _schema_set:
                        _schema_set.add(_col)
                if _schema_p:
                    _schema_p.valor = json.dumps(list(_schema_set), ensure_ascii=False)
                else:
                    db.session.add(AppConfig(proyecto_id=proy_g_obj.id, clave='app_schema',
                                             valor=json.dumps(list(_schema_set), ensure_ascii=False)))
                for r in NucleusData.query.filter_by(proyecto_id=proy_g_obj.id).all():
                    try:
                        d = json.loads(r.data_json)
                    except Exception:
                        continue
                    if not d.get('GESTOR'):
                        d['GESTOR'] = d.get('EDITADO POR') or d.get('_ultimo_usuario_manual') or ''
                        r.data_json = json.dumps(d, ensure_ascii=False)
                db.session.commit()
        except Exception as _e:
            db.session.rollback()

        # ── Backfill historial de estado inicial ─────────────────────────
        WO_STATE_COL_BF = 'Estado de la tarea (WO State)'
        STATE_TS_COL_BF = 'FECHA CAMBIO ESTADO'
        for proy in Proyecto.query.all():
            bf_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='historial_backfill_done').first()
            if bf_cfg:
                continue
            hist_keys = set(kv for (kv,) in db.session.query(HistorialCambios.key_value).filter(
                HistorialCambios.proyecto_id == proy.id,
                HistorialCambios.campo_modificado == WO_STATE_COL_BF).distinct().all())
            n = 0
            for r in NucleusData.query.filter_by(proyecto_id=proy.id).all():
                if r.key_value in hist_keys:
                    continue
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                st = str(d.get(WO_STATE_COL_BF, '')).strip()
                if not st:
                    continue
                fecha = datetime.utcnow()
                fec_txt = str(d.get(STATE_TS_COL_BF, '')).strip()
                if fec_txt:
                    try:
                        fecha = datetime.strptime(fec_txt[:19], '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass
                db.session.add(HistorialCambios(
                    proyecto_id=proy.id, usuario_id=None, username='IMPORT',
                    key_value=r.key_value, campo_modificado=WO_STATE_COL_BF,
                    valor_anterior='', valor_nuevo=st, fecha=fecha))
                n += 1
            if n:
                print(f"Backfill historial de estado: {n} registros (proyecto {proy.nombre})")
            db.session.add(AppConfig(proyecto_id=proy.id, clave='historial_backfill_done', valor='1'))
            db.session.commit()

        # ── Liberar lock de migración ─────────────────────────────────────
        try:
            if _mig_lock_conn is not None:
                _mig_lock_conn.execute(db.text("SELECT pg_advisory_unlock(917348261)"))
                _mig_lock_conn.commit()
                _mig_lock_conn.close()
        except Exception:
            pass


def _configurar_proyectos_apoyo(db, app, Proyecto, AppConfig, NucleusData, TablaMaestra):
    """Configura las columnas y PKs de los proyectos de apoyo (Dataper, Material, SITE, Generadores, etc.)"""
    import json

    # ── Dataper ────────────────────────────────────────────────────────────
    dataper = Proyecto.query.filter_by(nombre='Dataper').first()
    if dataper:
        dataper_cols = [
            {'nombre': 'TECNICO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DOCUMENTO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CONTRATA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CELULAR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CARGO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DEPARTAMENTO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'PROYECTO', 'tipo': 'lista', 'opciones': ['FLM - ENTEL', 'PEXT', 'CLARO', 'INTEGRATEL']},
            {'nombre': 'ESTADO', 'tipo': 'lista', 'opciones': ['ACTIVO', 'CESADO']},
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=dataper.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(dataper_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=dataper.id, clave='manual_columns',
                                     valor=json.dumps(dataper_cols, ensure_ascii=False)))
        if not AppConfig.query.filter_by(proyecto_id=dataper.id, clave='primary_key').first():
            db.session.add(AppConfig(proyecto_id=dataper.id, clave='primary_key', valor='DOCUMENTO'))
        if not AppConfig.query.filter_by(proyecto_id=dataper.id, clave='app_schema').first():
            db.session.add(AppConfig(proyecto_id=dataper.id, clave='app_schema', valor='[]'))
        db.session.commit()

    # ── Material ───────────────────────────────────────────────────────────
    material_proy = Proyecto.query.filter_by(nombre='Material').first()
    if material_proy:
        material_proy.icono = 'fa-boxes-stacked'
        material_cols = [
            {'nombre': 'COD_MATERIAL', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DESCRIPCION_MATERIAL', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'PROYECTO', 'tipo': 'lista', 'opciones': ['FLM - ENTEL', 'PEXT', 'CLARO', 'INTEGRATEL']},
            {'nombre': 'UM', 'tipo': 'lista', 'opciones': ['UN', 'MT']},
            {'nombre': 'TIPO', 'tipo': 'lista', 'opciones': ['SAP', 'BUCLE']},
        ]
        mc = AppConfig.query.filter_by(proyecto_id=material_proy.id, clave='manual_columns').first()
        if mc:
            mc.valor = json.dumps(material_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=material_proy.id, clave='manual_columns',
                                     valor=json.dumps(material_cols, ensure_ascii=False)))
        pk = AppConfig.query.filter_by(proyecto_id=material_proy.id, clave='primary_key').first()
        if pk:
            pk.valor = 'COD_MATERIAL'
        else:
            db.session.add(AppConfig(proyecto_id=material_proy.id, clave='primary_key', valor='COD_MATERIAL'))
        if not AppConfig.query.filter_by(proyecto_id=material_proy.id, clave='app_schema').first():
            db.session.add(AppConfig(proyecto_id=material_proy.id, clave='app_schema', valor='[]'))
        db.session.commit()

    # ── SITE (maestro COBRA SITES) ─────────────────────────────────────────
    site_proy = Proyecto.query.filter_by(nombre='SITE').first()
    if site_proy:
        site_proy.icono = 'fa-location-dot'
        site_cols = [
            {'nombre': 'Código', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Nombre', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Prioridad', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Departamento', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Provincia', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Distrito', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Dirección', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Latitud (°)', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Longitud (°)', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Región', 'tipo': 'texto', 'opciones': []},
        ]
        mc = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='manual_columns').first()
        if mc:
            mc.valor = json.dumps(site_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='manual_columns',
                                     valor=json.dumps(site_cols, ensure_ascii=False)))
        pk = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='primary_key').first()
        if pk:
            pk.valor = 'Código'
        else:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='primary_key', valor='Código'))
        if not AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='app_schema').first():
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='app_schema', valor='[]'))
        db.session.commit()

    # ── Generadores ────────────────────────────────────────────────────────
    gen_proy = Proyecto.query.filter_by(nombre='Generadores').first()
    if gen_proy:
        gen_proy.icono = 'fa-bolt'
        gen_cols = [
            {'nombre': 'QR ASIGNADO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SERIE DE EQUIPO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'TIPO', 'tipo': 'lista', 'opciones': ['PROPIO', 'ALQUILADO', 'ENTEL', 'CLARO', 'INTEGRATEL']},
            {'nombre': 'TIPO DE COMBUSTIBLE', 'tipo': 'lista', 'opciones': ['GASOLINA', 'PETROLEO', 'DIESEL']},
            {'nombre': 'TECNICO ASIGNADO', 'tipo': 'lista', 'opciones': []},
            {'nombre': 'ZONA', 'tipo': 'texto', 'opciones': []},
        ]
        mc = AppConfig.query.filter_by(proyecto_id=gen_proy.id, clave='manual_columns').first()
        if mc:
            mc.valor = json.dumps(gen_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=gen_proy.id, clave='manual_columns',
                                     valor=json.dumps(gen_cols, ensure_ascii=False)))
        # Eliminar PK fija — llave auto-generada
        pk = AppConfig.query.filter_by(proyecto_id=gen_proy.id, clave='primary_key').first()
        if pk:
            db.session.delete(pk)
        if not AppConfig.query.filter_by(proyecto_id=gen_proy.id, clave='app_schema').first():
            db.session.add(AppConfig(proyecto_id=gen_proy.id, clave='app_schema', valor='[]'))
        db.session.commit()

    # ── Combustible ────────────────────────────────────────────────────────
    comb_proy = Proyecto.query.filter_by(nombre='Combustible').first()
    if comb_proy:
        comb_proy.icono = 'fa-gas-pump'
        comb_cols = [
            {'nombre': 'N° ORDEN', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'FECHA', 'tipo': 'fecha', 'opciones': []},
            {'nombre': 'QR ASIGNADO', 'tipo': 'lista', 'opciones': []},
            {'nombre': 'TIPO', 'tipo': 'lista', 'opciones': ['PROPIO', 'ALQUILADO', 'ENTEL', 'CLARO', 'INTEGRATEL']},
            {'nombre': 'TECNICO ASIGNADO', 'tipo': 'lista', 'opciones': []},
            {'nombre': 'ZONA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'NOMBRE DE SITE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'MOVIMIENTO', 'tipo': 'lista', 'opciones': ['INGRESO', 'GASTO']},
            {'nombre': 'NUMERO FACTURA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GALONES', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'WO NUMBER', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'ID DE REPORTE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GESTOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'COMENTARIOS', 'tipo': 'texto', 'opciones': []},
        ]
        mc = AppConfig.query.filter_by(proyecto_id=comb_proy.id, clave='manual_columns').first()
        if mc:
            try:
                existing = json.loads(mc.valor)
                if not any(c.get('nombre') == 'N° ORDEN' for c in existing):
                    existing = [{'nombre': 'N° ORDEN', 'tipo': 'texto', 'opciones': []}] + existing
                    mc.valor = json.dumps(existing, ensure_ascii=False)
                else:
                    mc.valor = json.dumps(comb_cols, ensure_ascii=False)
            except Exception:
                mc.valor = json.dumps(comb_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=comb_proy.id, clave='manual_columns',
                                     valor=json.dumps(comb_cols, ensure_ascii=False)))
        pk = AppConfig.query.filter_by(proyecto_id=comb_proy.id, clave='primary_key').first()
        if pk:
            db.session.delete(pk)
        if not AppConfig.query.filter_by(proyecto_id=comb_proy.id, clave='app_schema').first():
            db.session.add(AppConfig(proyecto_id=comb_proy.id, clave='app_schema', valor='[]'))
        db.session.commit()

    # ── Cotizaciones ───────────────────────────────────────────────────────
    cot_proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if cot_proy:
        cot_proy.icono = 'fa-file-invoice-dollar'
        cot_cols = [
            {'nombre': 'N° ORDEN', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'FECHA', 'tipo': 'fecha', 'opciones': []},
            {'nombre': 'CLIENTE', 'tipo': 'lista', 'opciones': ['ENTEL', 'CLARO', 'INTEGRATEL']},
            {'nombre': 'N° COTIZACION', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'NUMERO WO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'NOMBRE SITE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUPERVISOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'OBJETIVO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUB TOTAL + FEE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'ESTADO COTIZACION', 'tipo': 'lista',
             'opciones': ['Pendiente de Aprobacion', 'Cotizacion Aprobada', 'Cotizacion Cancelada', 'Cotizacion Rechazada']},
            {'nombre': 'GESTOR', 'tipo': 'texto', 'opciones': []},
        ]
        mc = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='manual_columns').first()
        if mc:
            try:
                existing = json.loads(mc.valor)
                if not any(c.get('nombre') == 'N° ORDEN' for c in existing):
                    existing = [{'nombre': 'N° ORDEN', 'tipo': 'texto', 'opciones': []}] + existing
                    mc.valor = json.dumps(existing, ensure_ascii=False)
                else:
                    mc.valor = json.dumps(cot_cols, ensure_ascii=False)
            except Exception:
                mc.valor = json.dumps(cot_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='manual_columns',
                                     valor=json.dumps(cot_cols, ensure_ascii=False)))
        pk = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='primary_key').first()
        if pk:
            pk.valor = 'N° COTIZACION'
        else:
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='primary_key', valor='N° COTIZACION'))
        if not AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='app_schema').first():
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='app_schema', valor='[]'))
        if not AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='cotizacion_next_seq').first():
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='cotizacion_next_seq', valor='61'))
        db.session.commit()
