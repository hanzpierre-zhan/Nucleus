"""Una fuente de evidencia por WO, compartida por FLM y Cotizaciones."""
import json
import hashlib
from datetime import datetime
from flask import session
from models import NucleusData,Proyecto
from services.utilidades import puede_cotizaciones,safe_json_dumps

FASES=('INICIO','PROCESO','CIERRE')
CAMPOS=tuple('_EVIDENCIA_'+t for t in FASES)+tuple('_BITACORA_'+t for t in FASES)+('INICIO EJECUCION','FIN EJECUCION')
MARCAS=('_SUSTENTO_APROBADO','_SUSTENTO_APROBADO_COT')

class SustentoAdicional:
    """Evidencia por código, guardada dentro de su cotización sin inventar una WO FLM."""
    def __init__(self,cot,wo):
        self.cot=cot;self.wo=wo.strip().casefold()
        self.key_value='COTAD-%s-%s'%(cot.id,hashlib.sha256(self.wo.encode()).hexdigest()[:20])
    @property
    def data_json(self):
        d=json.loads(self.cot.data_json or '{}')
        return safe_json_dumps(d.get('_SUSTENTOS_ADICIONALES',{}).get(self.wo,{}))
    @data_json.setter
    def data_json(self,valor):
        d=json.loads(self.cot.data_json or '{}')
        d.setdefault('_SUSTENTOS_ADICIONALES',{})[self.wo]=json.loads(valor)
        self.cot.data_json=safe_json_dumps(d)

def registro_evidencia(pid,key):
    fila=NucleusData.query.filter_by(proyecto_id=pid,key_value=key).first()
    if fila or not str(key).startswith('COTAD-'):return fila
    try:cot_id=int(key.split('-')[1])
    except (ValueError,IndexError):return None
    cot=NucleusData.query.filter_by(proyecto_id=pid,id=cot_id).first()
    if not cot:return None
    from blueprints.cotizacion import _split_wos
    for wo in _split_wos(json.loads(cot.data_json or '{}').get('NUMERO WO')):
        from services.cotizacion_ficha import fuente
        registro=SustentoAdicional(cot,fuente(json.loads(cot.data_json or '{}'),wo))
        if registro.key_value==key:return registro
    return None

def bloqueado(datos):
    return any(str(datos.get(c) or '').strip() not in ('','0') for c in MARCAS)

def cambio_bloqueado(datos,cambios):
    if any(k in cambios for k in ('_SUSTENTOS_ADICIONALES','_SUSTENTO_FICHAS','_SUSTENTO_ORIGENES','_SUSTENTO_MANUAL')):return True
    if any(c in cambios for c in MARCAS): return True
    if not bloqueado(datos): return False
    for campo in CAMPOS:
        if campo not in cambios: continue
        anterior=datos.get(campo) or '';nuevo=cambios[campo] or ''
        if campo.startswith('_EVIDENCIA_'):
            try: anterior=json.loads(anterior) if isinstance(anterior,str) and anterior else (anterior or [])
            except ValueError: pass
            try: nuevo=json.loads(nuevo) if isinstance(nuevo,str) and nuevo else (nuevo or [])
            except ValueError: pass
        if campo.startswith('_EVIDENCIA_'):
            if isinstance(anterior,list):
                anterior=list(anterior)
                while anterior and not anterior[-1]:anterior.pop()
            if isinstance(nuevo,list):
                nuevo=list(nuevo)
                while nuevo and not nuevo[-1]:nuevo.pop()
        if anterior!=nuevo: return True
    return False

def acceso_desde_cotizacion(pid,wo,cot_key,lectura=False):
    if not cot_key or not puede_cotizaciones(session.get('user_id'),session.get('rol'),session.get('current_proyecto_nombre')): return False
    from blueprints.cotizacion import _split_wos,_resolver_sustento_cot
    p=Proyecto.query.filter_by(nombre='Cotizaciones').first()
    cot=NucleusData.query.filter_by(proyecto_id=p.id,key_value=cot_key).first() if p else None
    if not cot:return False
    d=json.loads(cot.data_json or '{}')
    if (bloqueado(d) and not lectura) or str(d.get('ESTADO COTIZACION') or '') not in ('Aprobado','Atendido','Validado'):return False
    for codigo in (_split_wos(d.get('NUMERO WO')) or ['']):
        origen=_resolver_sustento_cot(cot,codigo,d)
        if origen[0].id==pid and origen[1].key_value.casefold()==wo.casefold():return True
    return False

def efectivos(cot,wo,unico):
    out=dict(wo)
    # `_COT_EVIDENCIA_MIGRADA` protege las fotos y bitácoras antiguas (no
    # pertenecen a un WO concreto). Las fechas de ejecución sí son datos del
    # trabajo: si el WO no las tiene, se recuperan de la cotización aunque su
    # evidencia ya esté migrada. Así el reporte nunca pierde lo que se ingresó.
    if unico:
        if not wo.get('_COT_EVIDENCIA_MIGRADA'):
            for campo in CAMPOS:
                if not out.get(campo) and cot.get(campo):out[campo]=cot[campo]
        for fuente,destino in [('INICIO EJECUCION','INICIO EJECUCION'),('FIN EJECUCION','FIN EJECUCION'),
                               ('FECHA INICIO OBRA','INICIO EJECUCION'),('FECHA FIN OBRA','FIN EJECUCION')]:
            if not out.get(destino) and cot.get(fuente):
                valor=str(cot[fuente]).strip()
                # La obra guarda solo la fecha (YYYY-MM-DD): se completa la hora
                # para que el campo datetime-local no quede vacío.
                if len(valor)==10:valor+=' 00:00:00'
                out[destino]=valor
    return out

def actualizar_slot(pid,key,tipo,indice,url):
    if tipo.upper() not in FASES:return
    fila=registro_evidencia(pid,key)
    if not fila:return
    d=json.loads(fila.data_json or '{}')
    campo='_EVIDENCIA_'+tipo.upper()
    try: fotos=json.loads(d.get(campo) or '[]')
    except (ValueError,TypeError):fotos=[]
    if not isinstance(fotos,list):fotos=[]
    while len(fotos)<=indice:fotos.append('')
    fotos[indice]=url
    d[campo]=safe_json_dumps(fotos)
    fila.data_json=safe_json_dumps(d)


def preparar_wo_desde_cotizacion(pid,key,cot_key):
    if not cot_key:return
    from blueprints.cotizacion import _split_wos
    cp=Proyecto.query.filter_by(nombre='Cotizaciones').first()
    cot=NucleusData.query.filter_by(proyecto_id=cp.id,key_value=cot_key).first() if cp else None
    wo=registro_evidencia(pid,key)
    if not cot or not wo:return
    d=json.loads(cot.data_json or '{}');actual=json.loads(wo.data_json or '{}')
    nuevo=efectivos(d,actual,len(_split_wos(d.get('NUMERO WO')))==1)
    nuevo['_COT_EVIDENCIA_MIGRADA']='1';wo.data_json=safe_json_dumps(nuevo)
