import ast
from pathlib import Path

def fuente(s,nombre):
 n=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name==nombre);return ast.get_source_segment(s,n)
def quitar(s,nombre):
 n=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name==nombre);l=s.splitlines(keepends=True);return ''.join(l[:n.lineno-1]+l[n.end_lineno:])
p=Path('blueprints/rendicion.py');s=p.read_text(encoding='utf-8');func=fuente(s,'_etapa_de').replace('def _etapa_de(', 'def etapa_de(').replace('_estado_de(', 'estado_de(');s=quitar(s,'_etapa_de');s=s.replace('estado_de as _estado_de','estado_de as _estado_de, etapa_de as _etapa_de');p.write_text(s,encoding='utf-8')
p=Path('services/rendicion_estados.py');p.write_text(p.read_text(encoding='utf-8')+'\n\n'+func+'\n',encoding='utf-8')
p=Path('services/dashboard_rendicion.py');s=quitar(p.read_text(encoding='utf-8'),'_etapa_de');s=s.replace('estado_de as _estado_de','estado_de as _estado_de, etapa_de as _etapa_de');p.write_text(s,encoding='utf-8')

p=Path('blueprints/asistencia.py');original=p.read_text(encoding='utf-8')
# Autorización aislada, conservando las dos vías de permisos existentes.
permisos='''"""Autorización de asistencia: permisos actuales y proyectos seleccionados."""
from flask import abort,request,session
from db import db
from models import Usuario,CuentaEspacio
from services import espacios
from services.utilidades import get_menu_proyectos

'''+fuente(original,'ambitos')+'\n\n'+fuente(original,'seleccion')+'\n'
Path('services/asistencia_permisos.py').write_text(ast.unparse(ast.parse(permisos))+'\n',encoding='utf-8')

# Exportadores independientes de la consulta y de los permisos.
mensual=fuente(original,'mensual');start=mensual.index("    if request.args.get('formato')=='xlsx':");end=mensual.index('    return jsonify(mes=',start)
exports=mensual[start:end].replace("request.args.get('formato')",'formato').replace('ps[','proyectos[')
exp='''"""Exportaciones de asistencia. El llamador entrega únicamente filas autorizadas."""
import csv
import io
from flask import Response
from services.asistencia import ESTADOS


def exportar(formato,filas,proyectos,inicio):
'''+exports+'    return None\n'
Path('services/asistencia_exportacion.py').write_text(ast.unparse(ast.parse(exp))+'\n',encoding='utf-8')

# Consultas y combinación del catálogo con las instantáneas históricas.
base='''"""Consultas de asistencia y catálogo; sin respuestas HTTP ni controladores."""
import calendar
import json
from datetime import datetime,date
from flask import abort
from models import Proyecto,NucleusData,AsistenciaDiaria
from services import espacios

ESTADOS = {'PRESENTE':'Presente','FALTA':'Falta','PERMISO':'Permiso','DESCANSO':'Descanso','VACACIONES':'Vacaciones','LICENCIA':'Licencia','PENDIENTE':'Sin marcar'}

'''+fuente(original,'roster')+'\n\n'+fuente(original,'datos_registro')+'''


def periodo_mensual(valor):
    try:
        inicio=datetime.strptime(valor,'%Y-%m').date()
        dias=calendar.monthrange(inicio.year,inicio.month)[1]
        return inicio,date(inicio.year,inicio.month,dias),dias
    except (ValueError,TypeError):
        abort(400,'Mes inválido.')


def filtro_personal(valor):
    if valor not in ('activos','cesados','ambos'):
        abort(400,'Filtro de personal inválido.')
    return valor


def registros_periodo(proyectos,inicio,fin):
    return AsistenciaDiaria.query.filter(AsistenciaDiaria.proyecto_id.in_(proyectos),AsistenciaDiaria.fecha>=inicio,AsistenciaDiaria.fecha<=fin)
'''
# Cuerpos diarios/planilla trasladados literalmente; los controladores serializan.
diario=fuente(original,'dia');body=diario[diario.index('    base=roster'):diario.index('    return jsonify')]
base+='\n\ndef consultar_dia(ps,escritura,fecha):\n'+body+'    return salida\n'
plan=fuente(original,'planilla');body=plan[plan.index('    base=roster'):plan.index('    return jsonify')]
body=body.replace("filtro=request.args.get('personal','activos')","filtro=filtro_personal(filtro)").replace("    if filtro not in ('activos','cesados','ambos'):abort(400,'Filtro de personal inválido.')\n",'')
body=body.replace('AsistenciaDiaria.query.filter(AsistenciaDiaria.proyecto_id.in_(ps),AsistenciaDiaria.fecha>=inicio,AsistenciaDiaria.fecha<=fin).all()', 'registros_periodo(ps,inicio,fin).all()')
base+='\n\ndef consultar_planilla(ps,escritura,inicio,fin,filtro):\n'+body+"    return sorted(personas,key=lambda p:(p['proyecto'],p['nombre'].casefold()))\n"
resumen=mensual[mensual.index('    resumen={}'):start]
base+='\n\ndef resumir(filas,ps):\n'+resumen+'    return list(resumen.values())\n'
filtrar=mensual[mensual.index('    filtro=request.args'):mensual.index('    resumen={}')]
filtrar=filtrar.replace("    filtro=request.args.get('personal')\n",'').replace("        if filtro not in ('activos','cesados','ambos'):abort(400,'Filtro de personal inválido.')",'        filtro_personal(filtro)')
base+='\n\ndef filtrar_registros(filas,ps,filtro):\n'+filtrar+'    return filas\n'
Path('services/asistencia.py').write_text(ast.unparse(ast.parse(base))+'\n',encoding='utf-8')

# El guardado conserva transacción, validación completa y control de versiones.
# Sigue en el controlador por ahora: se evitan cambios del contrato de errores.
s=original
for nombre in ['ambitos','seleccion','roster','datos_registro']:s=quitar(s,nombre)
s=s.replace("ESTADOS={'PRESENTE':'Presente','FALTA':'Falta','PERMISO':'Permiso','DESCANSO':'Descanso','VACACIONES':'Vacaciones','LICENCIA':'Licencia','PENDIENTE':'Sin marcar'}",'''from services.asistencia_permisos import ambitos,seleccion
from services.asistencia import (ESTADOS,roster,datos_registro,periodo_mensual,registros_periodo,filtrar_registros,resumir,consultar_dia,consultar_planilla)
from services.asistencia_exportacion import exportar''')
a=s.index('    base=roster(ps);registros=',s.index('def dia():'));b=s.index('\n\n\n@bp.route',a)
s=s[:a]+"    return jsonify(fecha=fecha.isoformat(),registros=consultar_dia(ps,escritura,fecha))"+s[b:]
a=s.index('    try:',s.index('def mensual():'));b=s.index('\n\n\n@bp.route',a)
s=s[:a]+'''    inicio,fin,_=periodo_mensual(request.args.get('mes',''))
    filas=registros_periodo(ps,inicio,fin).order_by(AsistenciaDiaria.fecha,AsistenciaDiaria.nombre).all()
    filas=filtrar_registros(filas,ps,request.args.get('personal'))
    respuesta=exportar(request.args.get('formato'),filas,ps,inicio)
    if respuesta is not None:return respuesta
    return jsonify(mes=inicio.strftime('%Y-%m'),resumen=resumir(filas,ps),marcas=len(filas),aviso='Solo se cuentan días marcados; no se infieren faltas ni se calculan remuneraciones.')'''+s[b:]
a=s.index('    try:',s.index('def planilla():'))
s=s[:a]+'''    inicio,fin,dias=periodo_mensual(request.args.get('mes',''))
    personas=consultar_planilla(ps,escritura,inicio,fin,request.args.get('personal','activos'))
    return jsonify(mes=inicio.strftime('%Y-%m'),dias=dias,registros=personas)
'''
s=s.replace('import calendar,csv,io,json,secrets','import json,secrets').replace('abort,current_app,jsonify','abort,jsonify').replace(',session,Response',',session').replace('Usuario,Proyecto,NucleusData,CuentaEspacio,','').replace('from services import espacios\n','')
p.write_text(ast.unparse(ast.parse(s))+'\n',encoding='utf-8')
print('Servicios compartidos y asistencia separados')
