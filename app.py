"""
Multiconsulta - Sistema de Gestión de Incidencias y Cotizaciones
================================================================
Aplicación web Flask para la gestión de incidencias técnicas de campo,
cotizaciones con flujo de aprobación, y seguimiento de montos.

Características principales:
  - CRUD completo de incidencias con historial de cambios (bitácora)
  - Flujo de aprobación de cotizaciones (Supervisor/Admin)
  - Gestión de usuarios con roles: Admin, Supervisor, Usuario
  - Exportación/importación de datos vía CSV
  - Carga de evidencia fotográfica (ImgBB o local)
  - Campos de monto aprobado y monto gastado con restricciones de edición

Roles del sistema:
  - Admin: Acceso total. Puede crear/borrar usuarios, configurar opciones,
           importar CSV, borrar incidencias, aprobar cotizaciones y editar montos.
  - Supervisor: Puede aprobar/rechazar cotizaciones y editar montos aprobados.
  - Usuario: Puede crear y editar incidencias. No puede modificar el monto
             aprobado una vez validado por un supervisor.
"""

import os, csv, base64, requests, json
from io import StringIO
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# =============================================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# =============================================================================
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "multiconsulta.db")

# Soporte para PostgreSQL (Heroku/Render) y SQLite (desarrollo local)
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'multiconsulta_secret_very_secure'

# Carpeta para respaldo local de evidencias fotográficas
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# =============================================================================
# MODELOS DE BASE DE DATOS
# =============================================================================

class Usuario(db.Model):
    """Modelo de usuario del sistema.
    Roles disponibles: 'Admin', 'Supervisor', 'Usuario'.
    """
    __tablename__ = 'usuarios'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    nombre        = db.Column(db.String(100), nullable=True)   # Nombre completo para mostrar
    password_hash = db.Column(db.String(255), nullable=False)
    rol           = db.Column(db.String(20), nullable=False, default='Usuario')

    def to_dict(self):
        """Serializa el usuario a diccionario (sin contraseña)."""
        return {'id': self.id, 'username': self.username,
                'nombre': self.nombre or self.username, 'rol': self.rol}

class OpcionDesplegable(db.Model):
    """Opciones configurables para los desplegables del formulario.
    Categorías: Departamento, Contrata, SLA, Estado, Proyecto, Servicio, Técnico.
    Se administran desde el panel de configuración (Admin).
    """
    __tablename__ = 'opciones_desplegables'
    id        = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(50), nullable=False)
    valor     = db.Column(db.String(100), nullable=False)

    def to_dict(self):
        return {'id': self.id, 'categoria': self.categoria, 'valor': self.valor}

class Incidencia(db.Model):
    """Modelo principal de incidencias/tickets.
    Representa un registro de trabajo de campo con seguimiento de estados,
    montos de cotización y evidencia fotográfica.

    Campos de cotización:
      - monto_aprobado: Monto validado por Supervisor/Admin (protegido tras aprobación)
      - monto_gastado: Monto real utilizado (siempre editable)
      - aprobado_por: Nombre del usuario que aprobó la cotización
    """
    __tablename__ = 'incidencias'
    id               = db.Column(db.Integer, primary_key=True)
    numero_ticket    = db.Column(db.String(50), nullable=False)   # Puede repetirse (múltiples registros por ticket)
    departamento     = db.Column(db.String(100), nullable=True)
    ciudad           = db.Column(db.String(100), nullable=True)
    site_name        = db.Column(db.String(150), nullable=True)   # Ingreso manual libre
    fecha_ticket     = db.Column(db.DateTime, nullable=True)       # Fecha/hora ingresada por el agente
    fecha_captura    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)  # Timestamp automático del sistema
    descripcion      = db.Column(db.Text, nullable=False)
    tecnico_asignado = db.Column(db.String(100), nullable=True)
    contrata         = db.Column(db.String(100), nullable=True)
    gestor           = db.Column(db.String(100), nullable=True)   # Se asigna automáticamente desde el usuario logueado
    sla              = db.Column(db.String(50), nullable=True)
    estado           = db.Column(db.String(50), nullable=False, default='Pendiente')
    evidencia        = db.Column(db.Text, nullable=True)          # URLs de fotos separadas por coma
    usuario_creador  = db.Column(db.String(50), nullable=True)
    proyecto         = db.Column(db.String(50), nullable=True)    # FLM, PEXT, etc.
    servicio         = db.Column(db.String(100), nullable=True)   # PREVENTIVO, CORRECTIVO, COTIZACION, etc.
    monto_aprobado   = db.Column(db.Float, nullable=True)         # Monto validado (protegido tras aprobación)
    monto_gastado    = db.Column(db.Float, nullable=True)         # Monto real gastado (siempre editable)
    aprobado_por     = db.Column(db.String(100), nullable=True)   # Usuario que aprobó la cotización
    prioridad        = db.Column(db.String(50), nullable=True, default='Sin prioridad')

    def to_dict(self):
        """Serializa la incidencia a diccionario para respuestas JSON y snapshots."""
        return {
            'id': self.id,
            'numero_ticket': self.numero_ticket,
            'departamento': self.departamento,
            'ciudad': self.ciudad,
            'site_name': self.site_name,
            'fecha_ticket':  self.fecha_ticket.strftime('%Y-%m-%d %H:%M') if self.fecha_ticket else '-',
            'fecha_captura': self.fecha_captura.strftime('%Y-%m-%d %H:%M') if self.fecha_captura else '-',
            'descripcion': self.descripcion,
            'tecnico_asignado': self.tecnico_asignado,
            'contrata': self.contrata,
            'gestor': self.gestor,
            'sla': self.sla,
            'estado': self.estado,
            'evidencia': self.evidencia,
            'usuario_creador': self.usuario_creador,
            'proyecto': self.proyecto,
            'servicio': self.servicio,
            'monto_aprobado': self.monto_aprobado if self.monto_aprobado is not None else None,
            'monto_gastado': self.monto_gastado if self.monto_gastado is not None else None,
            'aprobado_por': self.aprobado_por,
            'prioridad': self.prioridad or 'Sin prioridad'
        }

class HistorialIncidencia(db.Model):
    """Bitácora/historial de cambios de cada incidencia.
    Cada edición, cambio de estado o aprobación genera un registro aquí.
    El campo detalle_snapshot almacena un JSON completo del estado de la
    incidencia en ese momento (incluyendo montos y aprobador).
    """
    __tablename__ = 'historial_incidencias'
    id            = db.Column(db.Integer, primary_key=True)
    incidencia_id = db.Column(db.Integer, db.ForeignKey('incidencias.id', ondelete='CASCADE'), nullable=False)
    fecha         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    estado        = db.Column(db.String(50), nullable=False)
    gestor        = db.Column(db.String(100), nullable=True)
    comentario    = db.Column(db.Text, nullable=True)
    evidencia     = db.Column(db.Text, nullable=True)          # Copia de las URLs de evidencia al momento del cambio
    detalle_snapshot = db.Column(db.Text, nullable=True)       # JSON serializado con todos los datos de la incidencia

    incidencia    = db.relationship('Incidencia', backref=db.backref('historial', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        """Serializa el registro de historial a diccionario."""
        return {
            'id': self.id,
            'incidencia_id': self.incidencia_id,
            'fecha': self.fecha.strftime('%Y-%m-%d %H:%M') if self.fecha else '-',
            'estado': self.estado,
            'gestor': self.gestor or '-',
            'comentario': self.comentario or '',
            'evidencia': self.evidencia,
            'detalle_snapshot': self.detalle_snapshot
        }


# =============================================================================
# UTILIDADES
# =============================================================================

from PIL import Image
import io

def compress_image_to_base64(file_bytes, max_size=(800, 800), quality=70):
    """Comprime la imagen en memoria y la retorna como data URI en base64 para guardado persistente."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        # Convertir a RGB si tiene transparencia
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = out.getvalue()
        b64_str = base64.b64encode(compressed_bytes).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_str}"
    except Exception as e:
        print("Error al comprimir imagen:", e)
        b64_str = base64.b64encode(file_bytes).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_str}"

def guardar_archivos_evidencia(files):
    """Sube archivos de evidencia a ImgBB (prioridad) o los guarda comprimidos en Base64 en base de datos.

    Args:
        files: Lista de objetos FileStorage del request.

    Returns:
        String con URLs / data URIs separadas por coma, o None si no hay archivos.
    """
    api_key = os.environ.get('IMGBB_API_KEY', 'cb81e9e13ace655a6c16c147d0d704c8')
    urls = []
    if not files:
        return None
    for file in files:
        if not file or not file.filename:
            continue
        try:
            filename = secure_filename(file.filename)
            file_bytes = file.read()
            if not file_bytes:
                continue

            subido = False
            if api_key:
                try:
                    b64_image = base64.b64encode(file_bytes).decode('utf-8')
                    res = requests.post(
                        'https://api.imgbb.com/1/upload',
                        data={'key': api_key, 'image': b64_image},
                        timeout=15
                    )
                    data = res.json()
                    if data.get('success') and 'data' in data and 'url' in data['data']:
                        urls.append(data['data']['url'])
                        subido = True
                except Exception as ex_imgbb:
                    print("Error subiendo a ImgBB, usando respaldo en base de datos:", ex_imgbb)

            # Respaldo en Base de Datos (en vez de local efímero) si ImgBB falló o no hay API key
            if not subido:
                data_uri = compress_image_to_base64(file_bytes)
                urls.append(data_uri)
        except Exception as e:
            print("Error procesando evidencia:", e)

    return ','.join(urls) if urls else None



# =============================================================================
# DECORADORES DE AUTENTICACIÓN Y AUTORIZACIÓN
# =============================================================================

def login_required(f):
    """Requiere que el usuario haya iniciado sesión."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Requiere rol de Administrador."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_rol') != 'Admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def supervisor_required(f):
    """Requiere rol de Supervisor o Administrador."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_rol') not in ('Admin', 'Supervisor'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# CONTEXTO GLOBAL DE PLANTILLAS
# =============================================================================

@app.context_processor
def inject_user():
    """Inyecta el usuario actual en todas las plantillas como 'current_user'."""
    user = None
    if 'user_id' in session:
        user = Usuario.query.get(session['user_id'])
    return dict(current_user=user)



# =============================================================================
# RUTAS WEB (Páginas HTML)
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de inicio de sesión. Valida credenciales y crea la sesión."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_rol'] = user.rol
            return redirect(url_for('index'))
        return render_template('login.html', error='Credenciales inválidas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Cierra la sesión del usuario actual."""
    session.clear()
    return redirect(url_for('login'))

@app.route('/cambiar_password', methods=['GET', 'POST'])
def cambiar_password():
    """Página para que el usuario cambie su contraseña (requiere la actual)."""
    if request.method == 'POST':
        username = request.form.get('username')
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, old_password):
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            return render_template('login.html', error='Contraseña cambiada exitosamente. Por favor, inicia sesión con tu nueva contraseña.')
        return render_template('cambiar_password.html', error='Usuario o contraseña actual inválidos')
    return render_template('cambiar_password.html')

@app.route('/')
@login_required
def index():
    """Página principal - Consolidado de incidencias."""
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Página de Dashboard consolidado."""
    return render_template('dashboard.html')


@app.route('/admin/usuarios')
@admin_required
def admin_usuarios():
    """Panel de administración de usuarios (solo Admin)."""
    return render_template('admin_usuarios.html')

@app.route('/admin/configuracion')
@admin_required
def admin_configuracion():
    """Panel de configuración de opciones desplegables (solo Admin)."""
    return render_template('admin_config.html')

@app.route('/cotizaciones')
@supervisor_required
def cotizaciones():
    """Panel de aprobación de cotizaciones (Admin y Supervisor)."""
    return render_template('cotizaciones.html')


# =============================================================================
# API REST - INCIDENCIAS (CRUD)
# =============================================================================

@app.route('/api/incidencias', methods=['GET', 'POST'])
@login_required
def api_incidencias():
    """GET: Lista todas las incidencias. POST: Crea una nueva incidencia."""
    if request.method == 'POST':
        data = request.form

        # Guardar archivos de evidencia si existen (hasta 5)
        files = request.files.getlist('evidencia_files') or request.files.getlist('evidencia_file')
        evidencia_url = guardar_archivos_evidencia(files)

        if not evidencia_url and data.get('evidencia_text'):
            evidencia_url = data.get('evidencia_text')

        # Gestor y creador desde el usuario logueado
        user = Usuario.query.get(session['user_id'])
        creador = user.username if user else 'Desconocido'
        gestor_auto = (user.nombre or user.username) if user else 'Desconocido'

        # Parsear fecha_ticket ingresada por el agente
        fecha_ticket_str = data.get('fecha_ticket', '')
        fecha_ticket_val = None
        if fecha_ticket_str:
            try:
                fecha_ticket_val = datetime.strptime(fecha_ticket_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        monto_aprobado_val = None
        if data.get('monto_aprobado'):
            try: monto_aprobado_val = float(data.get('monto_aprobado'))
            except ValueError: pass

        monto_gastado_val = None
        if data.get('monto_gastado'):
            try: monto_gastado_val = float(data.get('monto_gastado'))
            except ValueError: pass

        nueva = Incidencia(
            numero_ticket    = data.get('numero_ticket'),
            departamento     = data.get('departamento'),
            ciudad           = data.get('ciudad'),
            site_name        = data.get('site_name'),
            fecha_ticket     = fecha_ticket_val,
            descripcion      = data.get('descripcion'),
            tecnico_asignado = data.get('tecnico_asignado'),
            contrata         = data.get('contrata'),
            gestor           = gestor_auto,
            sla              = data.get('sla'),
            estado           = data.get('estado', 'Pendiente'),
            evidencia        = evidencia_url,
            usuario_creador  = creador,
            proyecto         = data.get('proyecto'),
            servicio         = data.get('servicio'),
            monto_aprobado   = monto_aprobado_val,
            monto_gastado    = monto_gastado_val,
            prioridad        = data.get('prioridad', 'Sin prioridad')
        )
        db.session.add(nueva)
        try:
            db.session.flush() # Para obtener nueva.id
            comentario_creacion = data.get('comentario', '').strip() or f"Registro inicial del ticket en estado: {nueva.estado}"
            hist = HistorialIncidencia(
                incidencia_id=nueva.id,
                estado=nueva.estado,
                gestor=gestor_auto,
                comentario=comentario_creacion,
                evidencia=nueva.evidencia,
                detalle_snapshot=json.dumps(nueva.to_dict())
            )
            db.session.add(hist)
            db.session.commit()
            return jsonify({'success': True, 'incidencia': nueva.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    incidencias = Incidencia.query.order_by(Incidencia.fecha_captura.desc()).all()
    return jsonify([i.to_dict() for i in incidencias])


@app.route('/api/incidencias/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def api_incidencia_detail(id):
    """PUT: Actualiza una incidencia. DELETE: Elimina una incidencia (solo Admin).

    Restricción de edición de montos:
      - monto_aprobado: Si ya tiene valor y el usuario no es Admin/Supervisor,
        el campo se ignora en la actualización (protección backend).
      - monto_gastado: Siempre editable por cualquier usuario.
    """
    inc = Incidencia.query.get_or_404(id)
    if request.method == 'DELETE':
        if session.get('user_rol') != 'Admin':
            return jsonify({'error': 'No autorizado'}), 403
        db.session.delete(inc)
        db.session.commit()
        return jsonify({'success': True})

    if request.method == 'PUT':
        data = request.form
        user = Usuario.query.get(session['user_id'])
        gestor_actual = (user.nombre or user.username) if user else 'Desconocido'

        estado_previo = inc.estado

        files = request.files.getlist('evidencia_files') or request.files.getlist('evidencia_file')
        nuevas_urls = guardar_archivos_evidencia(files)
        if nuevas_urls:
            inc.evidencia = nuevas_urls

        fecha_ticket_str = data.get('fecha_ticket', '')
        if fecha_ticket_str:
            try: inc.fecha_ticket = datetime.strptime(fecha_ticket_str, '%Y-%m-%dT%H:%M')
            except ValueError: pass

        inc.numero_ticket = data.get('numero_ticket', inc.numero_ticket)
        inc.departamento = data.get('departamento', inc.departamento)
        inc.ciudad = data.get('ciudad', inc.ciudad)
        inc.site_name = data.get('site_name', inc.site_name)
        inc.descripcion = data.get('descripcion', inc.descripcion)
        inc.tecnico_asignado = data.get('tecnico_asignado', inc.tecnico_asignado)
        inc.contrata = data.get('contrata', inc.contrata)
        inc.sla = data.get('sla', inc.sla)
        inc.estado = data.get('estado', inc.estado)
        inc.proyecto = data.get('proyecto', inc.proyecto)
        inc.servicio = data.get('servicio', inc.servicio)
        inc.prioridad = data.get('prioridad', inc.prioridad)
        inc.gestor = gestor_actual

        if 'monto_aprobado' in data:
            val = data.get('monto_aprobado', '').strip()
            new_val = float(val) if val else None
            # Si ya tenía monto aprobado y el usuario no es Admin/Supervisor, no permitimos cambiarlo
            if inc.monto_aprobado is not None and session.get('user_rol') not in ('Admin', 'Supervisor'):
                pass
            else:
                inc.monto_aprobado = new_val
        if 'monto_gastado' in data:
            val = data.get('monto_gastado', '').strip()
            inc.monto_gastado = float(val) if val else None

        # Historial de cambios: Guardar historial para CUALQUIER edición
        comentario_ingresado = data.get('comentario', '').strip()
        if not comentario_ingresado:
            if inc.estado != estado_previo:
                comentario_ingresado = f"Cambio de estado: {estado_previo} ➔ {inc.estado}"
            else:
                comentario_ingresado = "Edición de datos del ticket"
        elif inc.estado != estado_previo:
            comentario_ingresado = f"[{estado_previo} ➔ {inc.estado}] {comentario_ingresado}"
            
        hist = HistorialIncidencia(
            incidencia_id=inc.id,
            estado=inc.estado,
            gestor=gestor_actual,
            comentario=comentario_ingresado,
            evidencia=inc.evidencia,
            detalle_snapshot=json.dumps(inc.to_dict())
        )
        db.session.add(hist)

        try:
            db.session.commit()
            return jsonify({'success': True, 'incidencia': inc.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400


@app.route('/api/incidencias/<int:id>/historial', methods=['GET'])
@login_required
def api_incidencia_historial(id):
    """Retorna la bitácora completa de cambios de una incidencia, ordenada de más reciente a más antigua."""
    historial = HistorialIncidencia.query.filter_by(incidencia_id=id).order_by(HistorialIncidencia.fecha.desc()).all()
    return jsonify([h.to_dict() for h in historial])


@app.route('/api/incidencias/<int:id>/eliminar-foto', methods=['POST'])
@login_required
def api_eliminar_foto(id):
    """Elimina una foto específica de la evidencia de una incidencia.
    
    Body JSON: { "foto_index": 0 }  (índice 0-based de la foto a eliminar)
    """
    inc = Incidencia.query.get_or_404(id)
    data = request.json or {}
    foto_index = data.get('foto_index')
    
    if foto_index is None:
        return jsonify({'error': 'foto_index requerido'}), 400
    
    if not inc.evidencia:
        return jsonify({'error': 'No hay evidencias para eliminar'}), 400
    
    urls = [u.strip() for u in inc.evidencia.split(',') if u.strip()]
    
    try:
        foto_index = int(foto_index)
    except (ValueError, TypeError):
        return jsonify({'error': 'foto_index debe ser un número'}), 400
    
    if foto_index < 0 or foto_index >= len(urls):
        return jsonify({'error': 'Índice de foto fuera de rango'}), 400
    
    urls.pop(foto_index)
    inc.evidencia = ','.join(urls) if urls else None
    
    # Registrar en historial
    user = Usuario.query.get(session['user_id'])
    gestor = (user.nombre or user.username) if user else 'Desconocido'
    hist = HistorialIncidencia(
        incidencia_id=inc.id,
        estado=inc.estado,
        gestor=gestor,
        comentario=f'Foto {foto_index + 1} eliminada manualmente.',
        evidencia=inc.evidencia,
        detalle_snapshot=json.dumps(inc.to_dict())
    )
    db.session.add(hist)
    
    try:
        db.session.commit()
        return jsonify({'success': True, 'incidencia': inc.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# API REST - EXPORTAR / IMPORTAR INCIDENCIAS (CSV)
# =============================================================================

@app.route('/api/incidencias/export')
@login_required
def export_incidencias():
    """Genera y descarga un archivo CSV con todas las incidencias."""
    incidencias = Incidencia.query.order_by(Incidencia.fecha_captura.desc()).all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow([
        'Ticket', 'Fecha Ticket (Agente)', 'Proyecto', 'Servicio', 'Estado', 'Fecha Captura (Sistema)',
        'Gestor/Registrador', 'Departamento', 'Ciudad', 'Site Name', 'Descripcion',
        'Tecnico', 'Contrata', 'SLA', 'Monto Aprobado', 'Monto Gastado', 'Prioridad'
    ])
    for i in incidencias:
        writer.writerow([
            i.numero_ticket,
            i.fecha_ticket.strftime('%Y-%m-%d %H:%M') if i.fecha_ticket else '',
            i.proyecto or '', i.servicio or '',
            i.estado,
            i.fecha_captura.strftime('%Y-%m-%d %H:%M') if i.fecha_captura else '',
            i.gestor, i.departamento, i.ciudad or '', i.site_name or '',
            i.descripcion, i.tecnico_asignado, i.contrata, i.sla,
            i.monto_aprobado if i.monto_aprobado is not None else '',
            i.monto_gastado if i.monto_gastado is not None else '',
            i.prioridad or 'Sin prioridad'
        ])
    output = si.getvalue()
    return Response(
        output,
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename=incidencias_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'}
    )

@app.route('/api/incidencias/import', methods=['POST'])
@admin_required
def api_incidencias_import():
    """Importa incidencias desde un archivo CSV subido (solo Admin)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Archivo no seleccionado'}), 400
    
    try:
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        user = Usuario.query.get(session['user_id'])
        creador = user.username if user else 'Desconocido'
        count = 0
        for row in csv_input:
            ticket = row.get('Ticket') or row.get('numero_ticket')
            if not ticket: continue
            
            fecha_ticket_str = row.get('Fecha Ticket (Agente)') or row.get('fecha_ticket')
            fecha_ticket_val = None
            if fecha_ticket_str:
                try:
                    fecha_ticket_val = datetime.strptime(fecha_ticket_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    pass

            # Parsear montos si están en el CSV
            monto_aprobado_val = None
            monto_gastado_val = None
            try:
                ma = row.get('Monto Aprobado') or row.get('monto_aprobado')
                if ma: monto_aprobado_val = float(ma)
            except ValueError: pass
            try:
                mg = row.get('Monto Gastado') or row.get('monto_gastado')
                if mg: monto_gastado_val = float(mg)
            except ValueError: pass

            nueva = Incidencia(
                numero_ticket    = ticket,
                departamento     = row.get('Departamento') or row.get('departamento'),
                ciudad           = row.get('Ciudad') or row.get('ciudad'),
                site_name        = row.get('Site Name') or row.get('site_name'),
                fecha_ticket     = fecha_ticket_val,
                descripcion      = row.get('Descripcion') or row.get('descripcion') or 'Importado',
                tecnico_asignado = row.get('Tecnico') or row.get('tecnico_asignado'),
                contrata         = row.get('Contrata') or row.get('contrata'),
                gestor           = row.get('Gestor/Registrador') or row.get('gestor') or creador,
                sla              = row.get('SLA') or row.get('sla'),
                estado           = row.get('Estado') or row.get('estado') or 'Pendiente',
                usuario_creador  = creador,
                proyecto         = row.get('Proyecto') or row.get('proyecto'),
                servicio         = row.get('Servicio') or row.get('servicio'),
                monto_aprobado   = monto_aprobado_val,
                monto_gastado    = monto_gastado_val,
                prioridad        = row.get('Prioridad') or row.get('prioridad') or 'Sin prioridad'
            )
            db.session.add(nueva)
            count += 1
        db.session.commit()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


# =============================================================================
# API REST - COTIZACIONES (Aprobación / Rechazo)
# =============================================================================

@app.route('/api/cotizaciones/<int:id>/aprobar', methods=['POST'])
@supervisor_required
def api_cotizacion_aprobar(id):
    """Aprueba una cotización: asigna monto, cambia estado a 'Asignado',
    registra quién aprobó y genera entrada en el historial.
    Requiere rol Supervisor/Admin. Funciona para cualquier tipo de servicio.
    """
    inc = Incidencia.query.get_or_404(id)
    data = request.json or {}
    user = Usuario.query.get(session['user_id'])
    gestor_actual = (user.nombre or user.username) if user else 'Desconocido'

    monto_str = str(data.get('monto_aprobado', '')).strip()
    if monto_str:
        try:
            inc.monto_aprobado = float(monto_str)
        except ValueError:
            return jsonify({'error': 'Monto inválido'}), 400

    inc.estado = 'Asignado'
    inc.aprobado_por = gestor_actual
    comentario = data.get('comentario', '').strip() or f'Cotización APROBADA por {gestor_actual}. Monto: S/ {inc.monto_aprobado:.2f}'
    hist = HistorialIncidencia(
        incidencia_id=inc.id,
        estado=inc.estado,
        gestor=gestor_actual,
        comentario=comentario,
        evidencia=inc.evidencia,
        detalle_snapshot=json.dumps(inc.to_dict())
    )
    db.session.add(hist)
    try:
        db.session.commit()
        return jsonify({'success': True, 'incidencia': inc.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/cotizaciones/<int:id>/rechazar', methods=['POST'])
@supervisor_required
def api_cotizacion_rechazar(id):
    """Rechaza una cotización: devuelve el estado a 'Pendiente' y registra en historial.
    Requiere rol Supervisor/Admin. Funciona para cualquier tipo de servicio.
    """
    inc = Incidencia.query.get_or_404(id)
    data = request.json or {}
    user = Usuario.query.get(session['user_id'])
    gestor_actual = (user.nombre or user.username) if user else 'Desconocido'

    inc.estado = 'Pendiente'
    comentario = data.get('comentario', '').strip() or f'Cotización RECHAZADA por {gestor_actual}.'
    hist = HistorialIncidencia(
        incidencia_id=inc.id,
        estado=inc.estado,
        gestor=gestor_actual,
        comentario=comentario,
        evidencia=inc.evidencia,
        detalle_snapshot=json.dumps(inc.to_dict())
    )
    db.session.add(hist)
    try:
        db.session.commit()
        return jsonify({'success': True, 'incidencia': inc.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

# =============================================================================
# API REST - USUARIOS (solo Admin)
# =============================================================================

@app.route('/api/usuarios', methods=['GET', 'POST'])
@admin_required
def api_usuarios():
    """GET: Lista todos los usuarios. POST: Crea un nuevo usuario."""
    if request.method == 'POST':
        data     = request.json
        username = data.get('username')
        password = data.get('password')
        nombre   = data.get('nombre', '')
        rol      = data.get('rol', 'Usuario')

        if Usuario.query.filter_by(username=username).first():
            return jsonify({'error': 'El usuario ya existe'}), 400

        nuevo = Usuario(
            username      = username,
            nombre        = nombre,
            password_hash = generate_password_hash(password),
            rol           = rol
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({'success': True, 'usuario': nuevo.to_dict()})

    users = Usuario.query.all()
    return jsonify([u.to_dict() for u in users])

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
@admin_required
def api_usuario_delete(id):
    """Elimina un usuario. No permite auto-eliminación."""
    if id == session['user_id']:
        return jsonify({'error': 'No te puedes borrar a ti mismo'}), 400
    user = Usuario.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/usuarios/<int:id>/password', methods=['PUT'])
@admin_required
def api_usuario_password(id):
    """Permite al Admin restablecer la contraseña de cualquier usuario."""
    data = request.json
    new_password = data.get('new_password')
    if not new_password:
        return jsonify({'error': 'Contraseña requerida'}), 400
    user = Usuario.query.get_or_404(id)
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({'success': True})


# =============================================================================
# API REST - OPCIONES DESPLEGABLES
# =============================================================================

@app.route('/api/opciones', methods=['GET', 'POST'])
def api_opciones():
    """GET: Retorna opciones agrupadas por categoría. POST: Crea nueva opción (solo Admin)."""
    if request.method == 'POST':
        if session.get('user_rol') != 'Admin':
            return jsonify({'error': 'No autorizado'}), 403
        data  = request.json
        nueva = OpcionDesplegable(categoria=data.get('categoria'), valor=data.get('valor'))
        db.session.add(nueva)
        db.session.commit()
        return jsonify({'success': True, 'opcion': nueva.to_dict()})

    todas    = OpcionDesplegable.query.all()
    resultado = {'Departamento': [], 'Contrata': [], 'SLA': [], 'Estado': [], 'Proyecto': [], 'Servicio': [], 'Técnico': []}
    for op in todas:
        if op.categoria in resultado:
            resultado[op.categoria].append(op.to_dict())
    return jsonify(resultado)

@app.route('/api/opciones/<int:id>', methods=['DELETE'])
@admin_required
def api_delete_opciones(id):
    """Elimina una opción desplegable (solo Admin)."""
    op = OpcionDesplegable.query.get_or_404(id)
    db.session.delete(op)
    db.session.commit()
    return jsonify({'success': True})

# =============================================================================
# MIGRACIÓN Y SEED DE BASE DE DATOS
# =============================================================================

def migrate_db():
    """Ejecuta migraciones incrementales para agregar columnas nuevas.
    Compatible con SQLite (desarrollo) y PostgreSQL (producción).
    Se ejecuta automáticamente al iniciar la app.
    """
    from sqlalchemy import text
    if db.engine.name != 'sqlite':
        with db.engine.connect() as conn:
            # Cambiar el tipo de datos de evidencia a TEXT en incidencias e historial_incidencias si existieran como VARCHAR(255)
            try:
                conn.execute(text("ALTER TABLE incidencias ALTER COLUMN evidencia TYPE TEXT"))
                conn.commit()
            except Exception: pass
            try:
                conn.execute(text("ALTER TABLE historial_incidencias ALTER COLUMN evidencia TYPE TEXT"))
                conn.commit()
            except Exception: pass

            try:
                conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nombre VARCHAR(100)"))
                conn.commit()
            except Exception: pass
            for col, tipo in [
                ('evidencia',     'TEXT'),
                ('detalle_snapshot', 'TEXT')
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE historial_incidencias ADD COLUMN IF NOT EXISTS {col} {tipo}"))
                    conn.commit()
                except Exception: pass
            for col, tipo in [
                ('fecha_ticket',  'TIMESTAMP'),
                ('fecha_captura', 'TIMESTAMP'),
                ('ciudad',        'VARCHAR(100)'),
                ('site_name',     'VARCHAR(150)'),
                ('proyecto',      'VARCHAR(50)'),
                ('servicio',      'VARCHAR(100)'),
                ('monto_aprobado', 'FLOAT'),
                ('monto_gastado',  'FLOAT'),
                ('aprobado_por',   'VARCHAR(100)'),
                ('prioridad',      'VARCHAR(50)'),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE incidencias ADD COLUMN IF NOT EXISTS {col} {tipo}"))
                    conn.commit()
                except Exception: pass
        return
    with db.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN nombre TEXT"))
            conn.commit()
        except Exception: pass
        
        # Migración de historial_incidencias
        try:
            col_info_h = conn.execute(text("PRAGMA table_info(historial_incidencias)")).fetchall()
            existing_cols_h = [r[1] for r in col_info_h]
            for col, tipo in [
                ('evidencia', 'TEXT'),
                ('detalle_snapshot', 'TEXT'),
            ]:
                if col not in existing_cols_h:
                    conn.execute(text(f"ALTER TABLE historial_incidencias ADD COLUMN {col} {tipo}"))
                    conn.commit()
        except Exception as e:
            print("Error migrando historial_incidencias:", e)

        row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='incidencias'")).fetchone()
        if not row or not row[0]: return
        
        col_info = conn.execute(text("PRAGMA table_info(incidencias)")).fetchall()
        existing_cols = [r[1] for r in col_info]
        
        for col, tipo in [
            ('fecha_ticket',  'DATETIME'),
            ('fecha_captura', 'DATETIME'),
            ('ciudad',        'VARCHAR(100)'),
            ('site_name',     'VARCHAR(150)'),
            ('proyecto',      'VARCHAR(50)'),
            ('servicio',      'VARCHAR(100)'),
            ('monto_aprobado', 'FLOAT'),
            ('monto_gastado',  'FLOAT'),
            ('aprobado_por',   'VARCHAR(100)'),
            ('prioridad',      'VARCHAR(50)'),
        ]:
            if col not in existing_cols:
                try:
                    conn.execute(text(f"ALTER TABLE incidencias ADD COLUMN {col} {tipo}"))
                    conn.commit()
                except Exception: pass

def init_db():
    """Inicializa la base de datos: crea tablas, ejecuta migraciones,
    crea el usuario Admin por defecto y puebla las opciones desplegables.
    """
    db.create_all()
    migrate_db()
    # Crear usuario administrador por defecto si no existe
    if not Usuario.query.filter_by(username='hvargas').first():
        admin = Usuario(username='hvargas', nombre='Hector Vargas', password_hash=generate_password_hash('123456'), rol='Admin')
        db.session.add(admin)
    # Poblar opciones por defecto solo si la tabla está vacía (primera ejecución)
    if OpcionDesplegable.query.count() == 0:
        opciones_defecto = [
            ('Departamento','Amazonas'),('Departamento','Ancash'),('Departamento','Apurimac'),
            ('Departamento','Arequipa'),('Departamento','Ayacucho'),('Departamento','Cajamarca'),
            ('Departamento','Callao'),('Departamento','Cusco'),('Departamento','Huancavelica'),
            ('Departamento','Huanuco'),('Departamento','Ica'),('Departamento','Junin'),
            ('Departamento','La Libertad'),('Departamento','Lambayeque'),('Departamento','Lima'),
            ('Departamento','Loreto'),('Departamento','Madre de Dios'),('Departamento','Moquegua'),
            ('Departamento','Pasco'),('Departamento','Piura'),('Departamento','Puno'),
            ('Departamento','San Martin'),('Departamento','Tacna'),('Departamento','Tumbes'),
            ('Departamento','Ucayali'),
            ('Contrata','Jius'),('Contrata','Gesitel'),('Contrata','HBA Proyect'),
            ('Contrata','Satelecom'),('Contrata','Cobra'),('Contrata','Nastel'),
            ('SLA','8HRS'),('SLA','16HRS'),('SLA','48HRS'),
            ('Estado','Pendiente'),('Estado','Asignado'),('Estado','Parada de Reloj'),
            ('Estado','Cierre Operativo'),('Estado','Liquidado'),
            ('Proyecto','FLM'),('Proyecto','PEXT'),
            ('Servicio','PREVENTIVO'),('Servicio','CORRECTIVO'),('Servicio','PREDICTIVO'),
            ('Servicio','AVAST DE COMBUSTIBLE'),('Servicio','ADICIONALES'),
            ('Técnico','Juan Pérez'),('Técnico','Carlos López'),('Técnico','María García'),('Técnico','Pedro Ramírez')
        ]
        for cat, val in opciones_defecto:
            db.session.add(OpcionDesplegable(categoria=cat, valor=val))
    db.session.commit()


@app.route('/api/admin/limpiar-evidencias-locales', methods=['POST'])
@admin_required
def limpiar_evidencias_locales():
    """Limpia las referencias a imágenes locales (rutas /static/uploads/) que no
    están disponibles en Render. Solo accesible para Administradores.
    Devuelve cuántos registros fueron afectados.
    """
    incidencias = Incidencia.query.filter(Incidencia.evidencia.isnot(None)).all()
    afectados = 0
    for inc in incidencias:
        if not inc.evidencia:
            continue
        urls = [u.strip() for u in inc.evidencia.split(',') if u.strip()]
        urls_validas = [u for u in urls if not (u.startswith('/static/uploads/') or u.startswith('static/uploads/'))]
        urls_locales = len(urls) - len(urls_validas)
        if urls_locales > 0:
            inc.evidencia = ','.join(urls_validas) if urls_validas else None
            afectados += 1
    try:
        db.session.commit()
        return jsonify({'success': True, 'afectados': afectados})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# ARRANQUE DE LA APLICACIÓN
# =============================================================================

# Inicializar BD al importar el módulo (compatible con gunicorn y ejecución directa)
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
