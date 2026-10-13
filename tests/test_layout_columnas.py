def test_orden_incluye_identidad_evidencia_flujo_y_kpi(auth_client):
    fields=['_evidencia_btn','KPI_PRUEBA','_key','_accion_cot','_accion']
    columns=[{'field':field,'visible':True} for field in fields]
    response=auth_client.post('/api/columns/layout',json={'columns':columns})
    assert response.status_code==200
    assert auth_client.get('/api/columns/layout').json==columns
    auth_client.post('/api/columns/layout',json={'columns':[]})
