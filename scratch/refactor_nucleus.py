"""Extracciones mecánicas: conserva cuerpos, orden y nombres públicos."""
import ast,re
from pathlib import Path

def quitar_funcion(texto,nombre):
    nodo=next(n for n in ast.parse(texto).body if isinstance(n,ast.FunctionDef) and n.name==nombre)
    lineas=texto.splitlines(keepends=True)
    return ''.join(lineas[:nodo.lineno-1]+lineas[nodo.end_lineno:]),''.join(lineas[nodo.lineno-1:nodo.end_lineno])

# Los imports explícitos hacen visibles las dependencias reales de cada módulo.
init=ast.parse(Path('services/__init__.py').read_text(encoding='utf-8-sig'))
exports=ast.literal_eval(next(n.value for n in init.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__all__' for t in n.targets)))
for p in Path('blueprints').glob('*.py'):
    s=p.read_text(encoding='utf-8-sig')
    if 'from services import *' not in s:continue
    usados={n.id for n in ast.walk(ast.parse(s)) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
    nombres=[n for n in exports if n in usados]
    s=s.replace('from services import *','from services import (\n'+''.join('    '+n+',\n' for n in nombres)+')')
    p.write_text(s,encoding='utf-8')

# Una sola implementación de normalización, conservando los imports antiguos.
normal=Path('services/normalizacion.py')
src=Path('services/recursos_flm.py').read_text(encoding='utf-8');_,func=quitar_funcion(src,'normalizar')
normal.write_text('"""Normalización compartida; no interpreta proyectos ni modifica documentos."""\nimport re\nimport unicodedata\n\n'+func+'\n',encoding='utf-8')
for nombre in ['recursos_flm','espacios','rendicion_personal']:
    p=Path('services')/(nombre+'.py');s,_=quitar_funcion(p.read_text(encoding='utf-8'),'normalizar');s+='\n' if not s.endswith('\n') else ''
    s=s.replace('import unicodedata','from services.normalizacion import normalizar')
    p.write_text(s,encoding='utf-8')
p=Path('services/dashboard_cotizaciones.py');s,func=quitar_funcion(p.read_text(encoding='utf-8'),'_txt');s=s.replace('import re','import re\nfrom services.normalizacion import primer_texto as _txt',1);p.write_text(s,encoding='utf-8')
with normal.open('a',encoding='utf-8') as f:f.write('\n\n'+func.replace('def _txt(', 'def primer_texto(')+'\n')
p=Path('services/dashboard_rendicion.py');s,_=quitar_funcion(p.read_text(encoding='utf-8'),'_txt');s=s.replace('from datetime import datetime','from datetime import datetime\nfrom services.normalizacion import primer_texto as _txt',1);s,func=quitar_funcion(s,'_estado_de');s=s.replace('from datetime import datetime','from datetime import datetime\nfrom services.rendicion_estados import estado_de as _estado_de',1);p.write_text(s,encoding='utf-8')
Path('services/rendicion_estados.py').write_text('"""Lectura canónica del estado de rendición, compartida con Analytics."""\n\n'+func.replace('def _estado_de(', 'def estado_de(')+'\n',encoding='utf-8')
p=Path('blueprints/rendicion.py');s,_=quitar_funcion(p.read_text(encoding='utf-8'),'_estado_de');s=s.replace('from services.sustento import','from services.rendicion_estados import estado_de as _estado_de\nfrom services.sustento import',1) if 'from services.sustento import' in s else 'from services.rendicion_estados import estado_de as _estado_de\n'+s;p.write_text(s,encoding='utf-8')

# Infraestructura HTTP separada de la composición de la aplicación.
Path('infrastructure').mkdir(exist_ok=True);Path('infrastructure/__init__.py').write_text('"""Composición e infraestructura de la aplicación Flask."""\n',encoding='utf-8')
p=Path('app.py');s=p.read_text(encoding='utf-8');http=[]
for nombre in ['_pagina_error_http','_register_error_handlers','_register_compress','_register_no_cache_html']:
    s,cuerpo=quitar_funcion(s,nombre);http.append(cuerpo)
Path('infrastructure/http.py').write_text('"""Errores, compresión y caché HTTP; sin reglas de negocio."""\nimport gzip\nfrom flask import request,jsonify,Response,current_app\nfrom werkzeug.exceptions import HTTPException\n\n'+'\n\n'.join(http)+'\n',encoding='utf-8')
s,bp=quitar_funcion(s,'_register_blueprints')
Path('infrastructure/blueprints.py').write_text('"""Registro de módulos y contexto de las plantillas. Imports diferidos para evitar ciclos."""\n\n'+bp+'\n',encoding='utf-8')
s=s.replace('from config import Config, get_default_config','from config import Config, get_default_config\nfrom infrastructure.http import (_pagina_error_http, _register_error_handlers, _register_compress, _register_no_cache_html)\nfrom infrastructure.blueprints import _register_blueprints')
s=s.replace('import gzip\n','').replace('from flask import Flask, request, jsonify, Response, current_app','from flask import Flask').replace('from werkzeug.exceptions import HTTPException\n','')
p.write_text(s,encoding='utf-8')

# Extracción literal de estilos y scripts, preservando un único scope y orden JS.
p=Path('templates/index.html');s=p.read_text(encoding='utf-8');directorio=Path('templates/index');directorio.mkdir(exist_ok=True)
partes=['table-controller','wo-detail-controller','rendicion-notifications'];contador=0
patron=re.compile(r'<(script|style)\b[^>]*>([\s\S]*?)</\1>')
def extraer(m):
    global contador
    tag,contenido=m.group(1),m.group(2)
    if tag=='style' and len(contenido)>10000:
        Path('static/css/index.css').write_text(contenido,encoding='utf-8')
        return '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/index.css\', v=1) }}">'
    if tag=='script' and len(contenido)>1000:
        nombre=partes[contador];contador+=1
        (directorio/(nombre+'.html')).write_text(contenido,encoding='utf-8')
        return '<script>\n{% include "index/'+nombre+'.html" %}\n</script>'
    return m.group(0)
s=patron.sub(extraer,s);p.write_text(s,encoding='utf-8')
print('Extracciones completadas; scripts:',contador)
