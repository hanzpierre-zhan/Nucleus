import io
import openpyxl


def test_plantilla_columnas_y_carga_masiva(auth_client):
    respuesta = auth_client.get('/api/cotizacion/items_template')
    assert respuesta.status_code == 200
    libro = openpyxl.load_workbook(io.BytesIO(respuesta.data))
    hoja = libro['Items']
    assert [c.value for c in hoja[1]] == [
        'CORRELATIVO', 'TIPO', 'TEXTO EXPLICATIVO', 'UND', 'CANTIDAD',
        'VALOR UNITARIO', 'FEE %', 'VALOR TOTAL', 'COMENTARIOS',
    ]
    hoja.delete_rows(2, hoja.max_row)
    hoja.append([1, 'LPU', 'Servicio A', 'Und', 2, 100, 0, 200, 'Primero'])
    hoja.append([2, 'REEMBOLSABLE', 'Servicio B', 'Glb', 3, 50, 5, 157.5, 'Segundo'])
    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    carga = auth_client.post('/api/cotizacion/items_import', data={'file': (archivo, 'items.xlsx')})
    assert carga.status_code == 200
    assert carga.json['total'] == 2
    assert carga.json['items'][0]['texto'] == 'Servicio A'
    assert carga.json['items'][1]['comentarios'] == 'Segundo'
    assert float(carga.json['items'][1]['valor_total']) == 157.5
