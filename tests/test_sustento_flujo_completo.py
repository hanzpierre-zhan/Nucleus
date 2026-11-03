import io, json
import pytest
from db import db
from models import NucleusData
from test_sustento_por_wo import caso, foto  # noqa: F401

ITEMS = json.dumps([{'tipo': 'REEMBOLSABLE', 'texto': 'personal de custodio', 'und': 'EACH', 'cantidad': 1},
                    {'tipo': 'REEMBOLSABLE', 'texto': 'traslado', 'und': 'EACH', 'cantidad': 1}])


def _prep(app, caso, wos):
    with app.app_context():
        f = db.session.get(NucleusData, caso['ids'][2]); d = json.loads(f.data_json)
        d.update({'NUMERO WO': wos, 'ITEMS_JSON': ITEMS, 'CLIENTE': 'CLARO', 'NOMBRE SITE': 'Rio tambo'})
        f.data_json = json.dumps(d); db.session.commit()


def _abrir(c):
    r = c.get('/api/cotizacion/sustento?key=COT-SUST-TEST'); assert r.status_code == 200, r.json
    return r.json


def _manual(entry, items, **extra):
    m = {k: '' for k in ('wo', 'ajb_ejb', 'expense', 'site_name', 'site_id', 'site_type', 'site_address',
                         'district', 'province', 'region', 'work_responsible')}
    m.update(wo=entry['wo'], site_name='Rio tambo', **extra)
    m['item_details'] = {i['key']: {'unique_code': '8828126757', 'unit': 'EACH', 'remarks': '', 'description_es': 'x',
                                    'description_en': 'y', 'activity': 'z'} for i in items}
    return m


def _vista(entry):
    w = entry['wo_data']
    return {k: w.get(k, '') or '' for k in ('_EVIDENCIA_INICIO', '_EVIDENCIA_PROCESO', '_EVIDENCIA_CIERRE',
                                             '_BITACORA_INICIO', '_BITACORA_PROCESO', '_BITACORA_CIERRE',
                                             'INICIO EJECUCION', 'FIN EJECUCION')}


def _subir_item(c, wo, item, fase):
    r = c.post('/api/cotizacion/sustento/item-foto', data={'key': 'COT-SUST-TEST', 'wo': wo, 'item_key': item,
               'phase': fase, 'foto': (foto(), 'f.png')}, content_type='multipart/form-data')
    assert r.status_code == 200, r.json


def _estado(c, wo):
    g = _abrir(c); e = next(x for x in g['wos'] if x['wo'] == wo); m = e['wo_data'].get('_SUSTENTO_MANUAL') or {}
    return {'fotos_item': sum(len(v) for v in (m.get('item_photos') or {}).values()), 'ubicacion': bool(m.get('location_picture')),
            'bit': e['wo_data'].get('_BITACORA_INICIO'), 'inicio': e['wo_data'].get('INICIO EJECUCION'),
            'resp': m.get('work_responsible'), 'pestania': g['pestania']}


@pytest.mark.parametrize('wos,wo', [('WO-SUST-1', 'WO-SUST-1'), ('WO-NO-FLM', 'WO-NO-FLM'),
                                    ('WO-SUST-1, WO-SUST-2', 'WO-SUST-1'), ('', '')])
def test_flujo_completo(app, auth_client, caso, monkeypatch, tmp_path, wos, wo):
    app.config['EVIDENCIA_DIR'] = str(tmp_path)
    _prep(app, caso, wos); c = auth_client; c.get('/switch_project/%s' % caso['cot'])
    g = _abrir(c); entry = next(x for x in g['wos'] if x['wo'] == wo); items = g['items']
    base = _vista(entry)
    # Fotos subidas con el modal abierto (cada una se guarda al instante)
    r = c.post('/api/cotizacion/sustento/ubicacion', data={'key': 'COT-SUST-TEST', 'wo': wo, 'foto': (foto(), 'u.png')},
               content_type='multipart/form-data'); assert r.status_code == 200, r.json
    for fase in ('before', 'during', 'after'): _subir_item(c, wo, items[0]['key'], fase)
    _subir_item(c, wo, items[1]['key'], 'before')
    pasos = []
    # 1) Guardar (disquete) con textos y fechas
    ev = {'_BITACORA_INICIO': 'Antecedentes', 'INICIO EJECUCION': '2026-11-02 07:15:00', 'FIN EJECUCION': '2026-11-02 18:00:00'}
    r = c.post('/api/cotizacion/sustento/wo', json={'key': 'COT-SUST-TEST', 'wo': wo, 'evidencia': ev, 'base_evidencia': base,
               'manual': _manual(entry, items, work_responsible='GERARDO')})
    assert r.status_code == 200, r.json; pasos.append(('guardar', _estado(c, wo)))
    base.update({k: r.json['wo_data'].get(k, '') for k in ev})
    # 2) Otra foto después de guardar y luego Enviar a Atendido sin cambiar textos
    _subir_item(c, wo, items[1]['key'], 'after')
    r = c.post('/api/cotizacion/sustento/guardar', json={'key': 'COT-SUST-TEST', 'wo': wo, 'evidencia': {}, 'base_evidencia': base,
               'manual': _manual(entry, items, work_responsible='GERARDO')})
    assert r.status_code == 200, r.json; pasos.append(('atendido', _estado(c, wo)))
    # 3) Reabrir en Atendido, editar texto y guardar
    g = _abrir(c); entry = next(x for x in g['wos'] if x['wo'] == wo); base = _vista(entry)
    r = c.post('/api/cotizacion/sustento/wo', json={'key': 'COT-SUST-TEST', 'wo': wo, 'evidencia': {'_BITACORA_INICIO': 'Editado'},
               'base_evidencia': base, 'manual': _manual(entry, items, work_responsible='GERARDO')})
    assert r.status_code == 200, r.json; pasos.append(('editar en atendido', _estado(c, wo)))
    for p in pasos: print(wos or '(sin WO)', p)
    for nombre, e in pasos:
        assert e['fotos_item'] == (4 if nombre == 'guardar' else 5), (nombre, e)
        assert e['ubicacion'] and e['inicio'] == '2026-11-02 07:15:00' and e['resp'] == 'GERARDO', (nombre, e)
