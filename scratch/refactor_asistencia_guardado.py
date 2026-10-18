import ast,re
from pathlib import Path
p=Path('blueprints/asistencia.py');s=p.read_text(encoding='utf-8')
a=s.index('    base = roster(ps)',s.index('def guardar():'));b=s.index('    except (ValueError',a)
body=s[a:b];body=body.replace('    try:\n','',1)
lines=body.splitlines();lines=[lines[0]]+[line[4:] if line.startswith('    ') else line for line in lines[1:]]
# The declarations before try were already at the function level.
lines[1]='    pendientes = []';lines[2]='    vistos = set()'
body='\n'.join(lines)+'\n'
body=body.replace("            db.session.rollback()\n            return (jsonify(error='Otro usuario cambió la asistencia. Actualiza antes de guardar.'), 409)","            raise ConflictoVersion('Otro usuario cambió la asistencia. Actualiza antes de guardar.')")
body=body.replace("session['user_id']",'usuario_id').replace('    return jsonify(success=True, guardados=len(pendientes))','    return len(pendientes)')
serv=Path('services/asistencia.py');t=serv.read_text(encoding='utf-8');t=t.replace('from datetime import datetime, date','from datetime import datetime, date\nfrom db import db').replace('from models import Proyecto, NucleusData, AsistenciaDiaria','from models import Proyecto, NucleusData, AsistenciaDiaria, AsistenciaCambio')
t+='\n\nclass ConflictoVersion(Exception):\n    """El cliente intenta guardar sobre una versión que ya cambió."""\n\n\ndef guardar_marcas(ps,escritura,fecha,cambios,usuario_id):\n'+body
ast.parse(t);serv.write_text(t,encoding='utf-8')
s=s[:a]+'''    try:
        guardados=guardar_marcas(ps,escritura,fecha,cambios,session['user_id'])
        return jsonify(success=True,guardados=guardados)
    except ConflictoVersion as error:
        db.session.rollback()
        return jsonify(error=str(error)),409
'''+s[b:]
s=s.replace('import json, secrets','import secrets').replace('from datetime import date, datetime','from datetime import date').replace('AsistenciaDiaria, AsistenciaCambio','AsistenciaDiaria')
s=s.replace('ESTADOS, roster, datos_registro,','ConflictoVersion, guardar_marcas, ESTADOS,')
s=s.replace("bp = Blueprint('asistencia', __name__)\n",'');needle='from services.asistencia_exportacion import exportar';s=s.replace(needle,needle+"\n\nbp = Blueprint('asistencia', __name__)")
p.write_text(s,encoding='utf-8')
# Remove obsolete section headings left by infrastructure extraction.
p=Path('app.py');s=p.read_text(encoding='utf-8');a=s.index('# ─',s.index("mimetypes.add_type('font/ttf'"));b=s.index('# Invalidación del cache',a);b=s.rfind('# ─',a,b);s=s[:a]+s[b:];s=s.replace('app.py          ← este archivo (≈80 líneas)','app.py          ← composición y arranque').replace('  config.py       ← configuración por entorno','  infrastructure/ ← HTTP y registro de módulos\n  config.py       ← configuración por entorno');p.write_text(s,encoding='utf-8')
