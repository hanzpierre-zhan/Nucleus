"""Unificación OFFLINE de copias locales, sin modificar las fuentes.

Solo para ensayo. Conserva una copia JSON de cada fila fuente y el mapa de IDs.
Los conflictos de claves de registro se renombran, no sobrescriben datos.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def identificador(nombre):
    return '"' + nombre.replace('"', '""') + '"'


def unificar(base, fuentes, destino):
    destino = Path(destino).resolve()
    with destino.open('xb'):
        pass
    with sqlite3.connect('file:' + Path(base).resolve().as_posix() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(destino) as copia:
            original.backup(copia)
    informe = {'alcance':'ENSAYO con respaldos LOCALES; no descarga de Neon', 'origenes':{}, 'incidencias':[]}
    con = sqlite3.connect(destino)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('''CREATE TABLE IF NOT EXISTS ensayo_procedencia(
            sistema TEXT NOT NULL, tabla TEXT NOT NULL, id_original TEXT NOT NULL,
            id_destino TEXT, original_json TEXT NOT NULL,
            PRIMARY KEY(sistema,tabla,id_original))''')
        con.execute('BEGIN')
        for sistema, ruta in fuentes.items():
            with sqlite3.connect('file:' + Path(ruta).resolve().as_posix() + '?mode=ro', uri=True) as src:
                src.row_factory = sqlite3.Row
                src.execute('BEGIN')
                tablas = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                mapas = {}
                pendientes = set(tablas)
                orden = []
                while pendientes:
                    listas = [t for t in sorted(pendientes) if all(f[2] not in pendientes
                        for f in src.execute('PRAGMA foreign_key_list('+identificador(t)+')'))
                        and not (t == 'liquidacion_numero' and 'nucleus_data' in pendientes)]
                    if not listas:
                        raise ValueError('Dependencias cíclicas: revisión manual requerida.')
                    orden.extend(listas); pendientes.difference_update(listas)
                conteos = {}
                for tabla in orden:
                    q = identificador(tabla)
                    info = list(src.execute('PRAGMA table_info('+q+')'))
                    pk = [r['name'] for r in sorted(info,key=lambda r:r['pk']) if r['pk']]
                    if len(pk) != 1:
                        raise ValueError('Tabla sin clave simple: '+tabla)
                    pk = pk[0]
                    destinos = {r['name'] for r in con.execute('PRAGMA table_info('+q+')')}
                    if not destinos:
                        raise ValueError('Tabla ausente en destino: '+tabla)
                    fks = {r['from']:(r['table'],r['to']) for r in src.execute('PRAGMA foreign_key_list('+q+')')}
                    if tabla == 'notificaciones':fks['proyecto_id'] = ('proyectos','id')
                    if tabla == 'liquidacion_numero':fks['origen_id'] = ('nucleus_data','id')
                    mapas[tabla] = {}
                    conteos[tabla] = 0
                    for registro in src.execute('SELECT * FROM '+q):
                        original = dict(registro); antiguo = original[pk]
                        datos = {k:v for k,v in original.items() if k in destinos}
                        for columna,(padre,_) in fks.items():
                            valor = datos.get(columna)
                            if valor is None:continue
                            nuevo = mapas.get(padre,{}).get(valor)
                            if nuevo is None:
                                nullable = next(r['notnull'] == 0 for r in info if r['name'] == columna)
                                if not nullable:
                                    raise ValueError('Referencia obligatoria ausente en '+tabla)
                                informe['incidencias'].append({'sistema':sistema,'tabla':tabla,'id':antiguo,
                                    'campo':columna,'referencia_original':valor,'tratamiento':'NULL en ensayo; original preservado'})
                            datos[columna] = nuevo
                        existente = None
                        if tabla == 'proyectos':
                            if datos['nombre'] == 'PEXT':datos['nombre'] = 'FLM - PEXT'
                            existente = con.execute('SELECT * FROM proyectos WHERE nombre=?',(datos['nombre'],)).fetchone()
                        elif tabla == 'usuarios':
                            existente = con.execute('SELECT * FROM usuarios WHERE lower(username)=lower(?)',(datos['username'],)).fetchone()
                            if existente and (existente['password_hash'] != datos['password_hash'] or existente['rol'] != datos['rol']):
                                datos['username'] = sistema.lower()+'__'+str(antiguo)+'__'+datos['username']
                                informe['incidencias'].append({'sistema':sistema,'tabla':tabla,'id':antiguo,
                                    'tratamiento':'Cuenta distinta conservada con prefijo de origen'})
                                existente = None
                        elif tabla == 'app_config':
                            existente = con.execute('SELECT * FROM app_config WHERE proyecto_id=? AND clave=?',(datos['proyecto_id'],datos['clave'])).fetchone()
                            if existente and datos['clave'] in ('app_schema','manual_columns'):
                                a,b = json.loads(existente['valor']),json.loads(datos['valor'])
                                if isinstance(a,list) and isinstance(b,list):
                                    if datos['clave'] == 'app_schema':valor = sorted(set(a)|set(b))
                                    else:
                                        valor = list(a); nombres = {x.get('nombre') for x in a if isinstance(x,dict)}
                                        valor.extend(x for x in b if isinstance(x,dict) and x.get('nombre') not in nombres)
                                    con.execute('UPDATE app_config SET valor=? WHERE id=?',(json.dumps(valor,ensure_ascii=False),existente['id']))
                        elif tabla == 'nucleus_data':
                            existente = con.execute('SELECT * FROM nucleus_data WHERE proyecto_id=? AND key_value=?',(datos['proyecto_id'],datos['key_value'])).fetchone()
                            if existente and existente['data_json'] != datos['data_json']:
                                datos['key_value'] = datos['key_value'][:65]+' ['+sistema+' '+str(antiguo)+']'
                                informe['incidencias'].append({'sistema':sistema,'tabla':tabla,'id':antiguo,
                                    'tratamiento':'Clave repetida conservada con sufijo de origen'})
                                existente = None
                        elif tabla == 'accesos_proyecto':
                            existente = con.execute('SELECT * FROM accesos_proyecto WHERE usuario_id=? AND proyecto_id=?',(datos['usuario_id'],datos['proyecto_id'])).fetchone()
                        elif tabla in ('token_store',):
                            existente = con.execute('SELECT * FROM '+q+' WHERE clave=?',(datos['clave'],)).fetchone()
                        elif pk != 'id':
                            existente = con.execute('SELECT * FROM '+q+' WHERE '+identificador(pk)+'=?',(datos[pk],)).fetchone()
                        if existente is None and tabla not in ('usuarios','nucleus_data'):
                            # Maestros con claves naturales repetidas no deben
                            # interrumpir el ensayo ni reemplazar reglas vigentes.
                            for indice in con.execute('PRAGMA index_list('+q+')').fetchall():
                                if not indice['unique']:continue
                                claves_unicas=[r['name'] for r in con.execute('PRAGMA index_info('+identificador(indice['name'])+')')]
                                if not claves_unicas or claves_unicas == [pk] or any(datos.get(k) is None for k in claves_unicas):continue
                                existente=con.execute('SELECT * FROM '+q+' WHERE '+' AND '.join(identificador(k)+'=?' for k in claves_unicas),[datos[k] for k in claves_unicas]).fetchone()
                                if existente:break
                        if existente:
                            nuevo_id = existente[pk]
                        else:
                            if pk == 'id':datos.pop(pk,None)
                            columnas = list(datos)
                            cur = con.execute('INSERT INTO '+q+' ('+','.join(map(identificador,columnas))+') VALUES ('+','.join('?' for _ in columnas)+')',[datos[k] for k in columnas])
                            nuevo_id = cur.lastrowid if pk == 'id' else datos[pk]
                        mapas[tabla][antiguo] = nuevo_id
                        con.execute('INSERT INTO ensayo_procedencia VALUES(?,?,?,?,?)',
                            (sistema,tabla,str(antiguo),str(nuevo_id),json.dumps(original,ensure_ascii=False)))
                        conteos[tabla] += 1
                informe['origenes'][sistema] = conteos
        # Nunca reutilizar credenciales de integración en la copia de trabajo.
        con.execute('DELETE FROM token_store')
        for r in con.execute('SELECT id,clave FROM app_config').fetchall():
            if any(s in r['clave'].lower() for s in ('token','secret','password','sync_key')):
                con.execute('UPDATE app_config SET valor=? WHERE id=?',('',r['id']))
        if con.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('La copia unificada tiene relaciones sin destino.')
        con.commit()
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Falló integridad de la copia unificada.')
        tablas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        informe['tablas'] = {t:con.execute('SELECT COUNT(*) FROM '+identificador(t)).fetchone()[0] for t in tablas}
    except Exception:
        con.rollback();raise
    finally:
        con.close()
    with destino.open('rb') as f:informe['sha256'] = hashlib.file_digest(f,'sha256').hexdigest()
    destino.with_suffix('.manifest.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
    return informe


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for argumento in ('base','anton','modus','destino'):parser.add_argument('--'+argumento,required=True)
    a=parser.parse_args()
    r=unificar(a.base,{'Modus':a.modus,'Anton':a.anton},a.destino)
    print('Ensayo unificado verificado. Registros:',r['tablas']['nucleus_data'],'usuarios:',r['tablas']['usuarios'])
    print('Incidencias preservadas en el manifiesto:',len(r['incidencias']))
