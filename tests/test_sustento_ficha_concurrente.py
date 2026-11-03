"""Una pestaña abierta antes no debe borrar lo que otra ya guardó en la ficha."""
from test_sustento_por_wo import caso  # noqa: F401
from test_sustento_flujo_completo import _prep, _abrir, _manual


def _guardar(c, manual, base):
    r = c.post('/api/cotizacion/sustento/wo', json={'key': 'COT-SUST-TEST', 'wo': 'WO-SUST-1', 'evidencia': {},
               'manual': manual, 'base_manual': base})
    assert r.status_code == 200, r.json


def _ficha(c):
    return _abrir(c)['wos'][0]['wo_data']['_SUSTENTO_MANUAL']


def test_pestana_desactualizada_no_borra_campos_ni_items(app, auth_client, caso):
    _prep(app, caso, 'WO-SUST-1'); c = auth_client; c.get('/switch_project/%s' % caso['cot'])
    g = _abrir(c); entry = g['wos'][0]; items = g['items']; item = items[0]['key']
    vista_b = _manual(entry, items)  # lo que ve la pestaña B al abrir
    a = _manual(entry, items, work_responsible='GERARDO', expense='EXP-1')
    a['item_details'][item]['remarks'] = 'Detalle de A'
    _guardar(c, a, _manual(entry, items))
    # B guarda sin tocar esos campos, solo cambia el distrito
    b = _manual(entry, items, district='SANTA ROSA')
    _guardar(c, b, vista_b)
    m = _ficha(c)
    assert m['work_responsible'] == 'GERARDO' and m['expense'] == 'EXP-1'
    assert m['item_details'][item]['remarks'] == 'Detalle de A'
    assert m['district'] == 'SANTA ROSA'


def test_borrar_un_campo_a_proposito_si_se_aplica(app, auth_client, caso):
    _prep(app, caso, 'WO-SUST-1'); c = auth_client; c.get('/switch_project/%s' % caso['cot'])
    g = _abrir(c); entry = g['wos'][0]; items = g['items']
    lleno = _manual(entry, items, expense='EXP-1')
    _guardar(c, lleno, _manual(entry, items))
    _guardar(c, _manual(entry, items, expense=''), lleno)
    assert _ficha(c)['expense'] == ''
