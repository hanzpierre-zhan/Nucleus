"""Consulta y control informativo de solicitudes acumuladas por cotización."""
import json
import re
from decimal import Decimal, InvalidOperation
from models import Proyecto, NucleusData
from sqlalchemy import func, or_, cast, String
from services.alcance_proyectos import _valor
from services.recursos_flm import familia
from services.rendicion_estados import etapa_de


def importe(value):
    text=str(value if value is not None else '').strip()
    text=re.sub(r'^S/\s*','',text,flags=re.I).replace(' ','')
    if not text or not re.fullmatch(r'\d[\d.,]*',text):
        raise ValueError('Ingresa un monto válido en soles, mayor o igual a cero.')
    if ',' in text and '.' in text:
        text=text.replace(',','') if text.rfind('.')>text.rfind(',') else text.replace('.','').replace(',','.')
    elif ',' in text:
        text=text.replace(',','') if re.fullmatch(r'\d{1,3}(,\d{3})+',text) else text.replace(',','.')
    try:
        number=Decimal(text)
        if not number.is_finite() or number<0:raise InvalidOperation
        return number.quantize(Decimal('0.01'))
    except InvalidOperation:
        raise ValueError('Ingresa un monto válido en soles, mayor o igual a cero.')


def numero(value):return str(value or '').strip().upper()


def proyecto(row):
    return familia(row.get('Nombre del proyecto') or row.get('CLIENTE') or row.get('PROYECTO'))


def catalogo(row,consulta):
    proy=Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not proy or not proyecto(row):return []
    result=[];q=numero(consulta)
    raw=NucleusData.data_json
    codigo=_valor(raw,'N° COTIZACION')
    query=NucleusData.query.filter_by(proyecto_id=proy.id)
    if q:query=query.filter(func.upper(codigo).contains(q,autoescape=True))
    # Solo los campos necesarios, nunca las fotos, partidas ni historial completo.
    query=query.with_entities(NucleusData.id,NucleusData.key_value,codigo,
                              _valor(raw,'SUB TOTAL + FEE'),_valor(raw,'CLIENTE'),
                              _valor(raw,'Nombre del proyecto'),_valor(raw,'PROYECTO'))
    for rid,key,code,monto,cliente,nombre,proyecto_nombre in query.order_by(NucleusData.id.desc()).all():
        data={'CLIENTE':cliente,'Nombre del proyecto':nombre,'PROYECTO':proyecto_nombre}
        code=str(code or '').strip()
        if not code or proyecto(data)!=proyecto(row):continue
        result.append({'id':rid,'numero':code,'monto':monto,'key':key})
    return result


def encontrar(row,code,opciones=None):
    matches=[c for c in (catalogo(row,code) if opciones is None else opciones) if numero(c['numero'])==numero(code)]
    if len(matches)!=1:
        raise ValueError('Cotización no encontrada en este proyecto.' if not matches else 'Hay más de una cotización con ese número; revisa el registro.')
    return matches[0]


def resumen(row,key,cotizacion,solicitado=None):
    try:limite=importe(cotizacion['monto'])
    except ValueError:raise ValueError('La cotización no tiene un SUB TOTAL + FEE válido; revisa su importe.')
    actual=importe(row.get('Monto total del depósito') if solicitado is None else solicitado)
    proy=Proyecto.query.filter_by(nombre='Rendicion').first()
    acumulado=Decimal('0');cantidad=0;invalidos=0
    raw=NucleusData.data_json
    codigo=func.upper(func.trim(_valor(raw,'N° COTIZACION')))
    vinculo_id=cast(_valor(_valor(raw,'_COTIZACION_VINCULO'),'id'),String)
    query=NucleusData.query.filter_by(proyecto_id=proy.id).filter(
        NucleusData.key_value!=key,
        or_(codigo==numero(cotizacion['numero']),vinculo_id==str(cotizacion['id'])))
    for record in query.all():
        if record.key_value==key:continue
        other=json.loads(record.data_json or '{}')
        if proyecto(other)!=proyecto(row) or etapa_de(other)=='ANULADO':continue
        vinculo=other.get('_COTIZACION_VINCULO') or {}
        if not isinstance(vinculo,dict):vinculo={}
        coincide=(vinculo.get('id')==cotizacion['id']) if vinculo else numero(other.get('N° COTIZACION'))==numero(cotizacion['numero'])
        if not coincide:continue
        try:acumulado+=importe(other.get('Monto total del depósito'))
        except ValueError:invalidos+=1
        cantidad+=1
    total=acumulado+actual
    return {'cotizacion':cotizacion['numero'],'cotizacion_id':cotizacion['id'],
            'cotizado':str(limite),'otras_solicitudes':str(acumulado),'solicitud_actual':str(actual),
            'acumulado':str(total),'saldo':str(limite-total),'excede':total>limite,
            'cantidad_otras':cantidad,'importes_sin_interpretar':invalidos}


def preparar(row,key,datos):
    if 'presupuesto' not in datos and 'cotizacion' not in datos:return {}
    presupuesto=str(datos.get('presupuesto') or '').strip()
    code=str(datos.get('cotizacion') or '').strip()
    if len(code)>100:raise ValueError('El número de cotización es demasiado largo.')
    cambios={'PRESUPUESTO':str(importe(presupuesto)) if presupuesto else '', 'N° COTIZACION':code,
             '_COTIZACION_VINCULO':{},'_CONTROL_COTIZACION':{}}
    if code:
        cot=encontrar(row,code)
        control=resumen(row,key,cot)
        cambios.update({'N° COTIZACION':cot['numero'],'_COTIZACION_VINCULO':{'id':cot['id'],'numero':cot['numero']},'_CONTROL_COTIZACION':control})
    return cambios
