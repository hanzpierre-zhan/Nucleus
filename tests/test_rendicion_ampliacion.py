from services.rendicion_personal import IndicePersonal, presentar_beneficiario_dataper
from services.rendicion_gastos import ampliar_otros, validar_manual


def test_supervisor_por_dni_sin_adivinar_ni_modificar_original():
    indice = IndicePersonal()
    indice['00123456'] = [('Nombre oficial', 'LIMA')]
    indice.supervisores['00123456'] = ['Supervisora oficial']
    original = {'Documento del beneficiario': '00-123-456', 'Supervisor encargado': 'texto libre'}
    result = presentar_beneficiario_dataper(original, indice)
    assert result['Supervisor encargado'] == 'Supervisora oficial'
    assert result['Supervisor encargado (Form)'] == 'texto libre'
    assert original['Supervisor encargado'] == 'texto libre'
    indice.supervisores['00123456'] = ['']
    assert presentar_beneficiario_dataper(original, indice)['Supervisor encargado'] == 'SUPERVISOR NO REGISTRADO EN DATAPER'
    indice.supervisores['00123456'] = ['Uno', 'Dos']
    assert presentar_beneficiario_dataper(original, indice)['Supervisor encargado'] == 'SUPERVISOR AMBIGUO EN DATAPER'
    assert presentar_beneficiario_dataper(original, {})['Supervisor encargado'] == 'NO REGISTRADO EN DATAPER'


def test_otros_ampliacion_conserva_datos_y_selecciones():
    original = {'Tipo de gasto': 'PEAJE, OTROS', 'Motivo de la solicitud': 'Acarreo de GEP y custodio del equipo',
                'MONTO PAGO': '100', 'ESTADO': 'DEPOSITADO', 'FOTO PAGO': '/foto.jpg'}
    result = ampliar_otros(original)
    assert result['Tipo de gasto'] == 'PEAJE, ACARREO, OTROS'
    assert all(result[k] == v for k, v in original.items() if k != 'Tipo de gasto')
    assert ampliar_otros(result) == result
    assert validar_manual('MATERIAL, ACARREO')


def test_solo_otros_con_evidencia_no_envio_material_ni_registros_correctos():
    for categoria, motivo, esperado in [
        ('OTROS', 'Compra de materiales para mantenimiento', 'MATERIAL'),
        ('OTROS', 'Envío de repuesto a Huancayo', 'OTROS'),
        ('OTROS', 'Custodio por corte de energía', 'OTROS'),
        ('OTROS', 'Servicio de acarreo y alquiler de cilindro', 'ALQUILER, ACARREO'),
        ('COMPRAS', 'Compra de materiales', 'COMPRAS'),
    ]:
        row = {'Tipo de gasto': categoria, 'Motivo de la solicitud': motivo}
        assert ampliar_otros(row)['Tipo de gasto'] == esperado
