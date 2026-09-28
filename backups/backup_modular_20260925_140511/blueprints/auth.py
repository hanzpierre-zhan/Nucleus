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
from models import (Usuario, Proyecto, AppConfig, TokenStore, NucleusData,
                    NucleusHistory, FiltroMaestro, TablaMaestra,
                    ReglaEstadoManual, AccesoProyecto, KpiConfig,
                    HistorialCambios, Tecnico, Cotizacion)
from services import *


bp = Blueprint('auth', __name__)



@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        from sqlalchemy import func
        user = Usuario.query.filter(func.lower(Usuario.username) == username.lower()).first()
        if not user:
            # Tolerancia: también permitir entrar con el nombre visible (campo "nombre").
            user = Usuario.query.filter(func.lower(Usuario.nombre) == username.lower()).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['rol'] = str(user.rol).strip().lower()
            
            # Default to first project with access if none active
            if 'current_proyecto_id' not in session:
                if user.rol in ['zeno', 'suport']:
                    proj = Proyecto.query.first()
                else:
                    acceso = AccesoProyecto.query.filter_by(usuario_id=user.id).first()
                    proj = db.session.get(Proyecto, acceso.proyecto_id) if acceso else None
                
                if proj:
                    session['current_proyecto_id'] = int(proj.id)
                    session['current_proyecto_nombre'] = proj.nombre
                    
            return redirect(url_for('pages.index'))
        return render_template('login.html', error="Credenciales inválidas")
    return render_template('login.html')


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
                    if ap and ap.nombre in ('FLM', 'PEXT', 'Claro', 'Integratel'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Site Name':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Generadores':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Combustible':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'Cotizaciones':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            elif proy and proy.nombre == 'SITE':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('pages.index'))
            else:
                return redirect(url_for('pages.index'))
            
    proj = db.session.get(Proyecto, pid)
    proj = db.session.get(Proyecto, pid)
    if proj:
        session['current_proyecto_id'] = int(proj.id)
        session['current_proyecto_nombre'] = proj.nombre
    
    # Redirect back to specified page, referrer, or index
    target = request.args.get('next') or request.referrer or url_for('pages.index')
    return redirect(target)