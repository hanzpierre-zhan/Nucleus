"""Ficha manual de sustento, propia de cada cotización y WO."""
import json
import unicodedata
from functools import lru_cache
from models import Proyecto, NucleusData

CAMPOS = ('wo','ajb_ejb','expense','site_name','site_id','site_address','site_type','district','province','region','work_responsible')

def ficha(datos, wo):
    return dict(datos.get('_SUSTENTO_FICHAS', {}).get(wo.strip().casefold(), {}))

def fuente(datos, wo):
    return datos.get('_SUSTENTO_ORIGENES', {}).get(wo.strip().casefold(), wo)

def validar(datos, wo, claves, cambios):
    if not isinstance(cambios, dict) or set(cambios) - set(CAMPOS) - {'item_details'}:
        raise ValueError('Campos manuales inválidos.')
    out = ficha(datos, wo)
    for k, v in cambios.items():
        if k == 'item_details':
            if not isinstance(v,dict):raise ValueError('Datos de ítems inválidos.')
            permitidos={item['key'] for item in items_cotizacion(datos)}
            limites={'unique_code':300,'quantity':100,'unit':100,'description_es':5000,'description_en':5000,'activity':10000,'remarks':10000}
            nuevos=dict(out.get('item_details',{}))
            for item_key, fields in v.items():
                if item_key not in permitidos or not isinstance(fields,dict) or set(fields)-set(limites):raise ValueError('El ítem o sus campos no son válidos.')
                if any(not isinstance(value,str) or len(value)>limites[field] for field,value in fields.items()):raise ValueError('El texto del ítem supera el tamaño permitido.')
                quantity=fields.get('quantity','').strip()
                if quantity:
                    from decimal import Decimal, InvalidOperation
                    try:
                        numero=Decimal(quantity.replace(',','.'))
                        if not numero.is_finite() or numero<0:raise InvalidOperation
                    except InvalidOperation:raise ValueError('La cantidad debe ser un número mayor o igual a cero.')
                nuevos[item_key]={**nuevos.get(item_key,{}),**{field:value.strip() for field,value in fields.items()}}
            out['item_details']=nuevos
            continue
        if not isinstance(v, str) or len(v) > (2000 if k == 'site_address' else 300):
            raise ValueError('El campo manual supera el tamaño permitido.')
        out[k] = v.strip()
    definida = out.get('wo', wo).strip()
    if len(definida) > 100 or any(c in definida for c in ',;\n\r'):
        raise ValueError('Indica un solo número de WO para esta ficha.')
    if definida.casefold() != wo.casefold():
        if not definida and len(claves) > 1:
            raise ValueError('No se puede dejar una ficha sin WO mientras existen otras WOs en la cotización.')
        if any(c.casefold() == definida.casefold() for c in claves if c.casefold() != wo.casefold()):
            raise ValueError('Ese WO ya tiene otra ficha en esta cotización.')
    out['wo'] = definida
    return out

def guardar(datos, wo, claves, manual):
    nuevo = manual['wo']
    previo = fuente(datos, wo)
    datos.setdefault('_SUSTENTO_FICHAS', {}).pop(wo.casefold(), None)
    datos['_SUSTENTO_FICHAS'][nuevo.casefold()] = manual
    if nuevo != wo:
        datos.setdefault('_SUSTENTO_ORIGENES', {}).pop(wo.casefold(), None)
        datos['_SUSTENTO_ORIGENES'][nuevo.casefold()] = previo
        datos['NUMERO WO'] = ', '.join(nuevo if c.casefold() == wo.casefold() else c for c in claves) if claves else nuevo
    if len(claves) <= 1:
        datos['NOMBRE SITE'] = manual.get('site_name', '')
        datos['CODIGO SITE'] = manual.get('site_id', '')
    return nuevo

def normalizar(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')).upper() if c.isalnum())

SITE_ALIASES={'site_name':('Nombre','NOMBRE SITE','SITE NAME'), 'site_id':('Código','Codigo','SITE ID','CODIGO SITE','ID SITE','Código del sitio'),
              'site_address':('Dirección','DIRECCION SITE','Ubicación','SITE ADDRESS'), 'site_type':('Tipo de site','TIPO SITE','SITE TYPE','Tipo'),
              'district':('Distrito','DISTRICT'), 'province':('Provincia','PROVINCE'), 'region':('Región','REGION','Departamento')}
for _key,_header in zip(('site_name','site_id','site_address','site_type','district','province','region'),
    ('Nombre del sitio | Site name','Código del sitio | Site ID','Ubicación del sitio | Site address','Tipo de site | Site type','Distrito | District','Provincia | Provincia','Region | Region')):
    SITE_ALIASES[_key]=(_header,)+SITE_ALIASES[_key]

@lru_cache(maxsize=30000)
def _site_sugerencia(data_json, key_value):
    # La clave incluye el contenido: editar una fila invalida su entrada sin TTL.
    from services.recursos_flm import familia
    try:d=json.loads(data_json or '{}')
    except (TypeError,ValueError):return None
    if not isinstance(d,dict):return None
    nd={normalizar(k):str(v or '') for k,v in d.items()}
    item={k:next((nd[normalizar(a)] for a in names if nd.get(normalizar(a))), '') for k,names in SITE_ALIASES.items()}
    item['site_id']=item['site_id'] or key_value
    item['site_key']=str(d.get('Site') or key_value)
    return familia(d.get('Proyecto') or d.get('PROYECTO')),item,{k:normalizar(v) for k,v in item.items()}

def sitios(query, field='', proyecto=''):
    maestro = Proyecto.query.filter_by(nombre='SITE').first()
    if not maestro: return []
    resultado=[]; q=normalizar(query)
    from services.recursos_flm import familia
    family=familia(proyecto)
    if field and field not in SITE_ALIASES:return []
    seen=set()
    # Consumir el cursor antes de limitar las sugerencias: no dejar una lectura
    # abierta que bloquee guardados concurrentes en SQLite.
    rows=NucleusData.query.with_entities(NucleusData.key_value,NucleusData.data_json).filter_by(proyecto_id=maestro.id).all()
    for row in rows:
        parsed=_site_sugerencia(row.data_json,row.key_value)
        if not parsed:continue
        row_family,item,normalized=parsed
        if family and row_family!=family:continue
        matches=[normalized[field]] if field else [normalized['site_name'],normalized['site_id'],normalized['site_key']]
        if any(q in value for value in matches):
            if field and field not in ('site_name','site_id'):
                if not item[field] or item[field] in seen:continue
                seen.add(item[field])
            resultado.append(item)
            if len(resultado)>=40:break
    return resultado


def items_cotizacion(datos):
    """Identidad por contenido, no por posición: reordenar no reasigna fotos."""
    import hashlib
    raw=datos.get('ITEMS_JSON') or '[]'
    try: items=json.loads(raw) if isinstance(raw,str) else raw
    except (TypeError,ValueError):items=[]
    if not isinstance(items,list):return []
    resultado=[];repetidos={}
    for index,item in enumerate(items):
        if not isinstance(item,dict):continue
        firma=json.dumps([str(item.get(k) or '').strip() for k in ('tipo','texto','und')],ensure_ascii=False)
        repetidos[firma]=repetidos.get(firma,0)+1
        clave=hashlib.sha256((firma+'#'+str(repetidos[firma])).encode()).hexdigest()[:32]
        resultado.append({'key':clave,'numero':str(item.get('correlativo') or index+1),
                          'texto':str(item.get('texto') or 'Ítem sin descripción'),
                          'unique_code':str(item.get('codigo_unico') or item.get('codigo') or ''),
                          'cantidad':str(item.get('cantidad') or ''),'und':str(item.get('und') or '')})
    return resultado


def usa_ficha(datos,proyecto_nombre=''):
    return 'PEXT' not in normalizar(proyecto_nombre) and 'PEXT' not in normalizar(datos.get('CLIENTE'))
