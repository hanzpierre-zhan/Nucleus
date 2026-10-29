from copy import deepcopy
import pytest
from services.rendicion_gastos import CAMPO, META, OPCIONES, clasificar, valido, validar_manual


@pytest.mark.parametrize('valor', ['PEAJE','OTROS','PEAJE, VIATICOS','COMPRAS, ALQUILER','PASAJE, HOSPEDAJE, COCHERA'])
def test_validos_no_se_tocan(valor):
    d={CAMPO:valor,'Motivo de la solicitud':'alquiler y comida','MONTO PAGO':'50','ESTADO':'DEPOSITADO'}
    assert clasificar(d)==d
    assert META not in clasificar(d)


@pytest.mark.parametrize('valor,esperado', [
    ('alquiler de cochera','COCHERA'),('Desayuno - almuerzo ,','VIATICOS'),
    ('COMPRAS, ALQUILER, Alquiler de pertiga y compra de fusible de 10A','COMPRAS, ALQUILER'),
    ('PASAJE, VIATICOS, cochera','PASAJE, VIATICOS, COCHERA'),
    ('VIATICOS, Hospedaje X2 tambo del Ene','VIATICOS, HOSPEDAJE'),
    ('Pago a personal de apoyo','OTROS'),('Acarreo de combustible','OTROS'),
    ('PASAJE, ENCOMIENDA DE REPUESTOS RRU','PASAJE, OTROS'),
    ('Compra de combustible','COMPRAS'),('Alquiler de grupo electrógeno','ALQUILER'),
    ('VIATICOS, Servicio de custodio','VIATICOS, OTROS'),('ALQUILER,','ALQUILER')])
def test_descripciones_y_combinaciones(valor,esperado):
    d={CAMPO:valor,'MONTO PAGO':'125.01','ESTADO':'DEPOSITADO','FOTO PAGO':'/pago.jpg'}
    previo=deepcopy(d); r=clasificar(d)
    assert r[CAMPO]==esperado and valido(r[CAMPO])
    assert r[META]['original']==valor
    assert {k:v for k,v in r.items() if k not in (CAMPO,META)}=={k:v for k,v in previo.items() if k!=CAMPO}
    assert d==previo
    assert clasificar(r)==r


def test_contexto_ambiguos_y_registros_de_cotizacion():
    assert clasificar({CAMPO:'Cable 6 metros x2','Motivo de la solicitud':'Compra de cable'})[CAMPO]=='COMPRAS'
    r=clasificar({CAMPO:'Atención urgente','Motivo de la solicitud':'Sin detalle'})
    assert r[CAMPO]=='OTROS' and r[META]['requiere_revision']
    legacy={'TIPO DE GASTO':'Refacturable','ESTADO COTIZACION':'En Aprobación'}
    assert clasificar(legacy)==legacy
    with pytest.raises(ValueError): validar_manual('cualquier cosa')


def test_revisa_contexto_y_no_confunde_reparacion_con_compra():
    assert clasificar({CAMPO:'ALMACENAJE DE GEP -FEN','Motivo de la solicitud':'Alquiler de almacenaje de GEP'})[CAMPO]=='ALQUILER'
    r=clasificar({CAMPO:'CUSTODIO','Motivo de la solicitud':'Alquiler de GEP'})
    assert r[CAMPO]=='OTROS' and r[META]['requiere_revision']
    assert clasificar({CAMPO:'OTROS - SUMINSTRO DE TARJETA','Motivo de la solicitud':'Pago por reparación de GEP'})[CAMPO]=='OTROS'
    assert clasificar({CAMPO:'Consumibles para mantenimiento','Motivo de la solicitud':'Se requiere comprar en zona'})[CAMPO]=='COMPRAS'
