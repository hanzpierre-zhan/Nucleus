# -*- coding: utf-8 -*-
import os, io, re, json, time, glob, zipfile, gzip, mimetypes, tempfile
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timedelta
from collections import Counter
from flask import (Blueprint, request, jsonify, session, redirect, url_for,
                   render_template, current_app, make_response,
                   send_from_directory, send_file, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
import pandas as pd
from PIL import Image, ImageOps
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
from db import db
from models import (ConformidadUsuario, Usuario, Proyecto, AppConfig, TokenStore, NucleusData,
                    NucleusHistory, FiltroMaestro, TablaMaestra,
                    ReglaEstadoManual, AccesoProyecto, KpiConfig,
                    HistorialCambios, Tecnico, Cotizacion)
from services import *


bp = Blueprint('auth', __name__)



def _es_ruta_interna(target):
    """Verdadero SOLO para rutas locales tipo '/ruta'.

    Bloquea URL absolutas (http://dominio), protocol-relative (//dominio),
    esquemas raros (javascript:) y barras invertidas, cerrando el open redirect.
    """
    try:
        if not isinstance(target, str):
            return False
        if not target.startswith('/'):
            return False
        if target.startswith('//') or '\\' in target:
            return False
        from urllib.parse import urlparse
        parsed = urlparse(target)
        return not (parsed.scheme or parsed.netloc)
    except Exception:
        return False



LEGAL_VERSION = '2026-10-09'


def _iniciar_sesion(user, conformidad):
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['rol'] = str(user.rol).strip().lower()
    session['legal_acceptance'] = {
        'version': conformidad.version,
        'accepted_at': conformidad.aceptado_en.isoformat(timespec='seconds') + 'Z',
    }
    proyectos = get_menu_proyectos(user.id, session['rol'])
    if proyectos:
        session['current_proyecto_id'] = proyectos[0].id
        session['current_proyecto_nombre'] = proyectos[0].nombre
    return redirect(url_for('pages.analytics'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    pendiente = session.get('legal_pending') or {}
    vigente = (isinstance(pendiente, dict)
               and time.time() - pendiente.get('verified_at', 0) < 300)
    if pendiente and not vigente:
        session.pop('legal_pending', None)
    if request.method == 'POST':
        if request.form.get('consent_step') == '1':
            user = db.session.get(Usuario, pendiente.get('user_id')) if vigente else None
            if not user:
                return render_template('login.html', error='La verificación expiró. Inicia sesión de nuevo.'), 400
            if request.form.get('legal_accept') != '1':
                return render_template('login.html', consent_required=True,
                                       error='Confirma tu conformidad para continuar.'), 400
            conformidad = db.session.get(ConformidadUsuario, user.id)
            if conformidad is None:
                conformidad = ConformidadUsuario(usuario_id=user.id, version=LEGAL_VERSION)
                db.session.add(conformidad)
            conformidad.version = LEGAL_VERSION
            conformidad.aceptado_en = datetime.utcnow()
            db.session.commit()
            return _iniciar_sesion(user, conformidad)

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = Usuario.query.filter(func.lower(Usuario.username) == username.lower()).first()
        if not user:
            user = Usuario.query.filter(func.lower(Usuario.nombre) == username.lower()).first()
        if not user or not check_password_hash(user.password_hash, password):
            session.pop('legal_pending', None)
            return render_template('login.html', error='Credenciales inválidas', username=username)
        conformidad = db.session.get(ConformidadUsuario, user.id)
        if conformidad and conformidad.version == LEGAL_VERSION:
            return _iniciar_sesion(user, conformidad)
        session.clear()
        session['legal_pending'] = {'user_id': user.id, 'verified_at': time.time()}
        return render_template('login.html', consent_required=True)
    return render_template('login.html', consent_required=bool(pendiente and vigente))


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@bp.route('/api/cambiar-password', methods=['POST'])
@login_required
def cambiar_password():
    data = request.json or {}
    actual = (data.get('actual') or '').strip()
    nueva = (data.get('nueva') or '').strip()
    if not actual or not nueva:
        return jsonify({'error': 'Actual y nueva requeridas'}), 400
    if len(nueva) < 4:
        return jsonify({'error': 'La nueva contraseña debe tener al menos 4 caracteres'}), 400
    u = db.session.get(Usuario, session.get('user_id'))
    if not u or not check_password_hash(u.password_hash, actual):
        return jsonify({'error': 'Contraseña actual incorrecta'}), 403
    u.password_hash = generate_password_hash(nueva)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/api/auth/cambiar-password', methods=['POST'])
def cambiar_password_public():
    """Cambio de contraseña desde la pantalla de login (sin sesión):
    lo usa templates/login.html con {username, actual, nueva}."""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    actual = (data.get('actual') or '').strip()
    nueva = (data.get('nueva') or '').strip()
    if not username or not actual or not nueva:
        return jsonify({'error': 'Usuario, actual y nueva requeridas'}), 400
    if len(nueva) < 4:
        return jsonify({'error': 'Mínimo 4 caracteres'}), 400
    u = Usuario.query.filter(func.lower(Usuario.username) == username.lower()).first()
    if not u or not check_password_hash(u.password_hash, actual):
        return jsonify({'error': 'Usuario o contraseña actual incorrecta'}), 403
    u.password_hash = generate_password_hash(nueva)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/switch_project/<int:pid>')
@login_required
def switch_project(pid):
    # Check permission
    if session.get('rol') not in ['zeno', 'suport']:
        acceso = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id'), proyecto_id=pid).first()
        if not acceso:
            # Gestor y Contrata solo pueden operar en los proyectos que tienen asignados.
            if session.get('rol') in ('gestor', 'contrata'):
                return redirect(url_for('pages.index'))
            # Dataper/Material: permitir si el usuario tiene FLM o PEXT asignado.
            # Site Name: permitir solo si el usuario tiene FLM asignado.
            proy = db.session.get(Proyecto, pid)
            if proy and proy.nombre in ('Dataper', 'Material'):
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'PEXT', 'Claro', 'Integratel'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Site Name':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Generadores':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Combustible':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Cotizaciones':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'SITE':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            else:
                return redirect(url_for('pages.index'))
            
    proj = db.session.get(Proyecto, pid)
    if proj:
        session['current_proyecto_id'] = int(proj.id)
        session['current_proyecto_nombre'] = proj.nombre
    
    # Redirect back to specified page, referrer, or index
    target = request.args.get('next') or request.referrer or url_for('pages.index')
    # Validar open redirect (A1): solo permitir rutas internas
    if not _es_ruta_interna(target):
        target = url_for('pages.index')
    return redirect(target)
