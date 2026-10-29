from copy import deepcopy
from services.rendicion_homologacion import dni, nombre_completo, aplicar
from services.dashboard_rendicion import indicadores


def test_documentos_con_ceros_y_nombre_completo_sin_similitud_aproximada():
    assert dni('00.123.456') == '00123456'
    assert not dni('00000000')
    assert nombre_completo(['Jorge Carbajal', 'Carbajal Alvarado, Jorge']) == 'Carbajal Alvarado, Jorge'
    assert nombre_completo(['Juan Perez', 'Pedro Perez']) is None
    assert nombre_completo(['cochera ayacucho']) is None
    assert nombre_completo(['CM-20261029-00000001']) is None


def test_conserva_campos_sensibles_y_correcciones_manuales():
    original={'Técnico beneficiario':'j car', 'Documento del beneficiario':'00123456',
              'MONTO PAGO':'100.50','ESTADO':'DEPOSITADO','FOTO PAGO':'/pago.jpg',
              'Supervisor encargado':'Supervisor histórico','Técnico beneficiario (Form)':'j car'}
    datos=deepcopy(original)
    aplicar(datos,{'00123456':{'nombre':'Carbajal Alvarado, Jorge','fuente':'Personal'}})
    assert datos['Técnico beneficiario']=='Carbajal Alvarado, Jorge'
    assert datos['_BENEFICIARIO_HOMOLOGACION']['original']=='j car'
    assert {k:v for k,v in datos.items() if k not in ('Técnico beneficiario','_BENEFICIARIO_HOMOLOGACION')}=={k:v for k,v in original.items() if k!='Técnico beneficiario'}
    datos=deepcopy(original); datos['_PERSONAL_CORRECCION_MANUAL']=True
    assert aplicar(deepcopy(datos),{'00123456':{'nombre':'Otro','fuente':'Personal'}})==datos


def test_dashboard_prefiere_homologado_sin_alterar_formulario_ni_totales():
    datos={'Documento del beneficiario':'00123456','Técnico beneficiario':'Carbajal Alvarado, Jorge',
           'Técnico beneficiario (Form)':'JORGE','MONTO PAGO':'100.50','ESTADO':'DEPOSITADO'}
    previo=deepcopy(datos)
    result=indicadores([datos])
    assert result['detalle'][0]['beneficiario']=='Carbajal Alvarado, Jorge'
    assert result['monto_total']==100.50
    assert datos==previo
