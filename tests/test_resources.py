from unittest.mock import Mock
from types import SimpleNamespace


def test_resources_page_loads_assets(auth_client):
    response = auth_client.get('/salud')
    assert response.status_code == 200
    assert b'css/resources.css' in response.data
    assert b'js/resources.js' in response.data
    assert b'Exportar reporte' in response.data
    assert b'render-cpu' in response.data
    assert b'CPU utilizada' in response.data
    assert b'flm-resource-menu' not in response.data
    assert b'APPLICATION / INVENTARIO' not in response.data
    assert b'Monitor externo' not in response.data
    assert b'FLM - INTEGRATEL' in response.data


def test_resources_requires_admin_role(auth_client):
    with auth_client.session_transaction() as session:
        session['rol'] = 'gestor'
    assert auth_client.get('/api/salud').status_code == 403
    assert auth_client.get('/salud').status_code == 302


def test_resources_sqlite_is_not_reported_as_neon(auth_client, app, monkeypatch):
    from services import resources
    app.extensions.pop('resources_monitor', None)
    monkeypatch.setattr(resources, '_render', lambda: {'status': 'unconfigured'})
    monkeypatch.setattr(resources, '_b2', lambda: {'status': 'unconfigured'})
    response = auth_client.get('/api/salud')
    assert response.status_code == 200
    assert response.json['neon']['status'] == 'unavailable'
    assert 'app' not in response.json
    assert response.headers['Cache-Control'] == 'no-store'
    assert auth_client.get('/api/salud').json['cached'] is True


def test_budget_is_explicit_and_percent_is_not_clamped(app):
    from services.resources import _capacity
    with app.app_context():
        app.config['RESOURCES_NEON_STORAGE_MB'] = None
        item = {'size_bytes': 2 * 1024**2}
        _capacity(item, 'RESOURCES_NEON_STORAGE_MB')
        assert item['pct_used'] is None
        app.config['RESOURCES_NEON_STORAGE_MB'] = 1
        _capacity(item, 'RESOURCES_NEON_STORAGE_MB')
        assert item['pct_used'] == 200
        app.config.pop('RESOURCES_NEON_STORAGE_MB')


def test_b2_counts_versions_and_bounds_partial_inventory(app, monkeypatch):
    import boto3
    from services.resources import _b2
    page = {'IsTruncated': True, 'Versions': [
        {'Key': 'evidencia/test.jpg', 'Size': 100, 'IsLatest': True},
        {'Key': 'evidencia/test.jpg', 'Size': 200, 'IsLatest': False}]}
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = iter([page] * 50)
    monkeypatch.setattr(boto3, 'client', lambda *a, **kw: client)
    with app.app_context():
        for key in ('B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY'):
            monkeypatch.setitem(app.config, key, 'test')
        result = _b2()
    assert result['status'] == 'partial'
    assert result['complete'] is False
    assert result['size_bytes'] == 3000
    assert result['versions'] == 20
    assert result['files'] == 10
    assert result['groups'][0]['size_bytes'] == 3000


def test_render_reads_service_detail_fields(app, monkeypatch):
    import io
    from services import resources
    monkeypatch.setattr(resources.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(
        b'{"name":"modus","suspended":"not_suspended","serviceDetails":{"plan":"starter","region":"oregon"}}'))
    with app.app_context():
        monkeypatch.setitem(app.config, 'RENDER_API_KEY', 'test')
        monkeypatch.setitem(app.config, 'RENDER_SERVICE_ID', 'srv-test')
        result = resources._render()
    assert result['status'] == 'ok'
    assert result['plan'] == 'starter'
    assert result['region'] == 'oregon'


def test_postgresql_reports_size_tables_and_connections(app, monkeypatch):
    from services import resources
    connection = Mock()
    size = Mock(); size.scalar.return_value = 1000
    tables = Mock(); tables.mappings.return_value.all.return_value = [
        {'name': 'public.data', 'size_bytes': 800, 'estimated_rows': 20}]
    activity = Mock(); activity.scalar.return_value = 3
    connection.execute.side_effect = [Mock(), size, tables, activity]
    context = Mock()
    context.__enter__ = Mock(return_value=connection)
    context.__exit__ = Mock(return_value=False)
    engine = Mock()
    engine.dialect.name = 'postgresql'
    engine.connect.return_value = context
    monkeypatch.setattr(resources, 'db', SimpleNamespace(engine=engine))
    with app.app_context():
        result = resources._neon()
    assert result['status'] == 'ok'
    assert result['size_bytes'] == 1000
    assert result['tables'][0]['estimated_rows'] == 20
    assert result['connections'] == 3
    assert 'statement_timeout' in str(connection.execute.call_args_list[0].args[0])


def test_provider_error_does_not_leak_exception_details(app, monkeypatch):
    from services import resources
    def failed_request(*args, **kwargs):
        raise ValueError('secret-value-in-url')
    monkeypatch.setattr(resources.urllib.request, 'urlopen', failed_request)
    with app.app_context():
        monkeypatch.setitem(app.config, 'RENDER_API_KEY', 'test')
        monkeypatch.setitem(app.config, 'RENDER_SERVICE_ID', 'srv-test')
        result = resources._render()
    assert result['status'] == 'error'
    assert result['error_type'] == 'ValueError'
    assert 'secret-value' not in str(result)


def test_cpu_uses_container_quota_and_elapsed_usage(app, monkeypatch):
    from services import resources
    monkeypatch.setattr(resources, '_read', lambda path: '50000 100000' if path.endswith('cpu.max') else None)
    monkeypatch.setattr(resources, '_cpu_counter', lambda: 10.1)
    monkeypatch.setattr(resources.time, 'monotonic', lambda: 101)
    with app.app_context():
        monkeypatch.setitem(app.extensions, 'resources_cpu_sample', (100, 10))
        result = resources._cpu()
    assert result['pct_used'] == 20
    assert result['limit_cores'] == 0.5
    assert result['sample_seconds'] == 1


def test_memory_limit_ignores_unlimited_values(monkeypatch):
    from services import resources
    monkeypatch.setattr(resources, '_read', lambda path: 'max' if path.endswith('memory.max') else str(2**63))
    assert resources._memory_limit() is None
    monkeypatch.setattr(resources, '_read', lambda path: str(512*1024**2))
    assert resources._memory_limit() == 512*1024**2
