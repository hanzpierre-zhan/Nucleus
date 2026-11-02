from copy import deepcopy
import pytest
from services.rendicion_gastos import ampliar_custodio_combustible, CAMPO, META_CUSTODIO_COMBUSTIBLE, validar_manual


@pytest.mark.parametrize('tipo,motivo,observaciones,esperado',[
 ('OTROS','Custodio para abastecimiento y encendido de GEP','','CUSTODIO'),
 ('VIATICOS, OTROS','Servicio de custodio y dos almuerzos','','VIATICOS, CUSTODIO'),
 ('COMPRAS','Compra de combustible para unidad','','COMBUSTIBLE'),
 ('VIATICOS','PARA COMPRA DE COMBUSTIBLE','YA SE PAGO','COMBUSTIBLE'),
 ('PEAJE, VIATICOS, OTROS','Pago de Viáticos, Combustible, Peajes','','PEAJE, VIATICOS, COMBUSTIBLE'),
 ('PEAJE','Peaje por abastecimiento de combustible','','PEAJE'),
 ('VIATICOS','Abastecimiento de combustible para GEP','Viatico de desayuno','VIATICOS'),
 ('ACARREO','Acarreo de combustible','','ACARREO'),
 ('COMPRAS','Compra de filtros de combustible','','COMPRAS'),
 ('COMPRAS','Compra de 3 galoneras para combustible','','COMPRAS'),
 ('COMPRAS','Mantenimiento: bujias y filtros','Se deja al custodio','COMPRAS'),
])
def test_clasifica_concepto_no_contexto(tipo,motivo,observaciones,esperado):
    datos={CAMPO:tipo,'Motivo de la solicitud':motivo,'Observaciones (Form)':observaciones,
           'ESTADO':'DEPOSITADO','MONTO PAGO':'100','FOTO PAGO':'/foto.jpg',
           '_EVIDENCIA_INICIO':'["/otra.jpg"]'}
    previo=deepcopy(datos);resultado=ampliar_custodio_combustible(datos)
    assert resultado[CAMPO]==esperado
    assert datos==previo
    assert {k:v for k,v in resultado.items() if k not in (CAMPO,META_CUSTODIO_COMBUSTIBLE)}=={k:v for k,v in datos.items() if k!=CAMPO}
    assert ampliar_custodio_combustible(resultado)==resultado
    assert validar_manual(esperado)==esperado
