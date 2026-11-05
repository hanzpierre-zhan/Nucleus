"""Read-only infrastructure diagnostics; cache to bound monitoring overhead."""
import json
import math
import os
import time
import threading
import shutil
import urllib.request
from urllib.parse import urlencode
from collections import defaultdict
from datetime import datetime, timezone
from flask import current_app
from sqlalchemy import text
from db import db


def _budget(name):
    value = current_app.config.get(name, os.environ.get(name))
    try:
        value = float(value)
        return value if 0 < value < float('inf') else None
    except (TypeError, ValueError):
        return None


def _capacity(item, name):
    limit = _budget(name)
    item['limit_bytes'] = int(limit * 1024**2) if limit else None
    item['pct_used'] = round(item['size_bytes'] / item['limit_bytes'] * 100, 1) if limit else None


def _error(component, exc):
    current_app.logger.warning('Resources %s: %s', component, type(exc).__name__)
    return {'status': 'error', 'error': 'No se pudo consultar. Revisa permisos, conexión y logs del servidor.',
            'error_type': type(exc).__name__}


def _read(path):
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return None


def _memory_limit():
    for path in ('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'):
        try:
            value = int(_read(path))
            if 0 < value < 2**60:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _cpu_counter():
    raw = _read('/sys/fs/cgroup/cpu.stat')
    if raw:
        stats = dict(line.split() for line in raw.splitlines())
        if 'usage_usec' in stats:
            return int(stats['usage_usec']) / 1_000_000
    for path in ('/sys/fs/cgroup/cpuacct/cpuacct.usage', '/sys/fs/cgroup/cpu,cpuacct/cpuacct.usage'):
        raw = _read(path)
        if raw is not None:
            return int(raw) / 1_000_000_000
    return None


def _cpu():
    try:
        cores = None
        quota = _read('/sys/fs/cgroup/cpu.max')
        if quota:
            maximum, period = quota.split()
            if maximum != 'max' and int(maximum) > 0 and int(period) > 0:
                cores = int(maximum) / int(period)
        else:
            for prefix in ('/sys/fs/cgroup/cpu', '/sys/fs/cgroup/cpu,cpuacct'):
                maximum, period = _read(prefix + '/cpu.cfs_quota_us'), _read(prefix + '/cpu.cfs_period_us')
                if maximum and period and int(maximum) > 0 and int(period) > 0:
                    cores = int(maximum) / int(period)
                    break
        usage = _cpu_counter()
        if usage is None:
            return {'pct_used': None, 'note': 'El entorno no expone contadores CPU del contenedor.'}
        now = time.monotonic()
        previous = current_app.extensions.get('resources_cpu_sample')
        if previous is None:
            previous = (now, usage)
            time.sleep(0.2)
            usage, now = _cpu_counter(), time.monotonic()
        current_app.extensions['resources_cpu_sample'] = (now, usage)
        elapsed = now - previous[0]
        used_cores = max(0, usage - previous[1]) / elapsed if elapsed > 0 else 0
        return {'pct_used': round(used_cores / cores * 100, 1) if cores else None,
                'used_cores': round(used_cores, 3), 'limit_cores': cores,
                'sample_seconds': round(elapsed, 2), 'scope': 'Contenedor (cgroup)',
                'note': 'Promedio entre lecturas; porcentaje de la cuota CPU del contenedor.' if cores else
                        'Uso medido en núcleos; el contenedor no expone una cuota CPU finita.'}
    except (ValueError, TypeError, ZeroDivisionError):
        return {'pct_used': None, 'note': 'No se pudo interpretar la medición CPU.'}


def _render_credentials():
    return tuple(current_app.config.get(name) or os.environ.get(name)
                 for name in ('RENDER_API_KEY', 'RENDER_SERVICE_ID'))


def _render():
    key, service = _render_credentials()
    result = {'status': 'unconfigured', 'note': 'Configura RENDER_API_KEY y RENDER_SERVICE_ID.',
              'metrics_url': f'https://dashboard.render.com/web/{service}/metrics' if service else None}
    if key and service:
        try:
            req = urllib.request.Request(f'https://api.render.com/v1/services/{service}',
                headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                r = json.load(response)
            detail = r.get('serviceDetails', {})
            result.update(status='warn' if r.get('suspended') == 'suspended' else 'ok',
                          service=r.get('name'), plan=detail.get('plan'), region=detail.get('region'),
                          url=detail.get('url'), updatedAt=r.get('updatedAt'),
                          note='Estado administrativo del servicio; no prueba disponibilidad externa.')
        except Exception as exc:
            result.update(_error('render', exc))
    result.update(_local_runtime())
    try:
        disk = shutil.disk_usage(current_app.root_path)
        result['disk'] = {'size_bytes': disk.used, 'free_bytes': disk.free, 'total_bytes': disk.total,
                          'scope': 'Sistema de archivos visible; puede ser compartido con el host'}
    except OSError:
        result['disk'] = {'size_bytes': None}
    return result


def _local_runtime():
    # cgroup usage includes the instance; RSS includes only this worker.
    memory = None
    scope = 'No disponible en este entorno'
    for path in ('/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory/memory.usage_in_bytes'):
        try:
            with open(path) as handle:
                memory = int(handle.read().strip())
            scope = 'Contenedor (cgroup)'
            break
        except (OSError, ValueError):
            pass
    if memory is None:
        try:
            with open('/proc/self/statm') as handle:
                memory = int(handle.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
            scope = 'Solo este proceso; no todos los workers'
        except (OSError, ValueError, AttributeError):
            pass
    medicion = {'size_bytes': memory, 'scope': scope}
    if memory is not None:
        _capacity(medicion, 'RESOURCES_RENDER_MEMORY_MB')
        detected_limit = _memory_limit() if scope == 'Contenedor (cgroup)' else None
        if not medicion['limit_bytes'] and detected_limit:
            medicion.update(limit_bytes=detected_limit,
                pct_used=round(memory / detected_limit * 100, 1), limit_source='Límite del contenedor')
        elif medicion['limit_bytes']:
            medicion['limit_source'] = 'Presupuesto configurado'
    return {'memory': medicion, 'cpu': _cpu()}


def _render_metric(path, key, service, units):
    query = urlencode({'resource': service, 'aggregationMethod': 'AVG', 'resolutionSeconds': 60})
    req = urllib.request.Request(f'https://api.render.com/v1/metrics/{path}?{query}',
                                 headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            series = json.load(response)
        samples = []
        for item in series:
            scale = units.get(str(item.get('unit', '')).strip().lower())
            if scale is not None:
                samples.extend((point['timestamp'], point['value'] * scale)
                               for point in item['values']
                               if isinstance(point.get('value'), (int, float))
                               and math.isfinite(point['value']) and point['value'] >= 0)
        return max(samples, key=lambda point: point[0])[1] if samples else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        current_app.logger.warning('Resources Render %s: %s', path, type(exc).__name__)
        return None


def render_runtime():
    local = _local_runtime() if os.environ.get('RENDER') == 'true' else None
    if local and local['memory']['size_bytes'] is not None and local['cpu'].get('used_cores') is not None:
        return local
    key, service = _render_credentials()
    if not key or not service:
        if local:
            return local
        return {'memory': {}, 'cpu': {}, 'note': 'Para ver la instancia desde local, configura RENDER_API_KEY y RENDER_SERVICE_ID.'}

    cached = current_app.extensions.get('resources_render_runtime')
    now = time.monotonic()
    if cached and cached[0] == service and now - cached[1] < 60:
        return cached[2]
    byte_units = {'b': 1, 'bytes': 1, 'kb': 10**3, 'mb': 10**6, 'gb': 10**9,
                  'kib': 1024, 'mib': 1024**2, 'gib': 1024**3}
    core_units = {'cpu': 1, 'cpus': 1, 'core': 1, 'cores': 1, 'vcpu': 1, 'vcpus': 1,
                  'millicores': 0.001, 'millicpu': 0.001}
    memory = _render_metric('memory', key, service, byte_units)
    memory_limit = _render_metric('memory-limit', key, service, byte_units) if memory is not None else None
    cpu = _render_metric('cpu', key, service, core_units)
    cpu_limit = _render_metric('cpu-limit', key, service, core_units) if cpu is not None else None
    result = {
        'memory': {'size_bytes': memory, 'limit_bytes': memory_limit, 'scope': 'API de Render',
                   'pct_used': round(memory / memory_limit * 100, 1) if memory_limit else None},
        'cpu': {'used_cores': cpu, 'limit_cores': cpu_limit,
                'pct_used': round(cpu / cpu_limit * 100, 1) if cpu_limit else None},
        'note': 'API de Render · última muestra disponible' if memory is not None or cpu is not None else
                'Render no devolvió métricas recientes. Revisa el servicio y el acceso de la clave.',
    }
    if local:
        if memory is None:
            result['memory'] = local['memory']
        if cpu is None:
            result['cpu'] = local['cpu']
    current_app.extensions['resources_render_runtime'] = (service, time.monotonic(), result)
    return result


def _neon():
    if db.engine.dialect.name != 'postgresql':
        return {'status': 'unavailable', 'note': 'La conexión actual no es PostgreSQL; métricas Neon no disponibles.'}
    started = time.monotonic()
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '4000ms'"))
            size = int(connection.execute(text('SELECT pg_database_size(current_database())')).scalar())
            latency = round((time.monotonic() - started) * 1000, 1)
            tables = connection.execute(text('''SELECT schemaname || '.' || relname AS name,
                pg_total_relation_size(relid) AS size_bytes, n_live_tup AS estimated_rows
                FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 12''')).mappings().all()
            connections = connection.execute(text('''SELECT count(*) FROM pg_stat_activity
                WHERE datname = current_database()''')).scalar()
            result = {'status': 'ok', 'size_bytes': size, 'latency_ms': latency,
                      'connections': connections, 'tables': [dict(row) for row in tables],
                      'note': 'Base conectada: tablas + índices. No incluye otras bases o ramas de Neon. Filas estimadas.'}
            _capacity(result, 'RESOURCES_NEON_STORAGE_MB')
            return result
    except Exception as exc:
        return _error('neon', exc)


def _b2():
    bucket = current_app.config.get('B2_BUCKET')
    key = current_app.config.get('B2_KEY_ID')
    secret = current_app.config.get('B2_APP_KEY')
    if not all((bucket, key, secret)):
        return {'status': 'unconfigured', 'note': 'Configura B2_BUCKET, B2_KEY_ID y B2_APP_KEY.'}
    try:
        import boto3
        from botocore.config import Config
        region = current_app.config.get('B2_REGION', 'us-west-004')
        client = boto3.client('s3', endpoint_url=current_app.config.get('B2_ENDPOINT_URL') or
            f'https://s3.{region}.backblazeb2.com', aws_access_key_id=key,
            aws_secret_access_key=secret, region_name=region,
            config=Config(connect_timeout=3, read_timeout=4, retries={'total_max_attempts': 1}))
        groups = defaultdict(lambda: {'size_bytes': 0, 'files': 0})
        total = versions = current = 0
        complete = False
        started = time.monotonic()
        # Include old versions: these also consume storage. Never enumerate unbounded.
        pages = client.get_paginator('list_object_versions').paginate(Bucket=bucket, PaginationConfig={'PageSize': 1000})
        for index, page in enumerate(pages):
            for obj in page.get('Versions', []):
                total += obj['Size']
                versions += 1
                current += int(obj.get('IsLatest', False))
                prefix = obj['Key'].split('/')[0] if '/' in obj['Key'] else '(raíz)'
                groups[prefix]['size_bytes'] += obj['Size']
                groups[prefix]['files'] += 1
            if not page.get('IsTruncated'):
                complete = True
                break
            if index >= 9 or time.monotonic() - started > 6:
                break
        result = {'status': 'ok' if complete else 'partial', 'bucket': bucket, 'size_bytes': total,
                  'files': current, 'versions': versions, 'complete': complete,
                  'latency_ms': round((time.monotonic() - started) * 1000, 1),
                  'groups': sorted([dict(name=name, **values) for name, values in groups.items()],
                                   key=lambda row: row['size_bytes'], reverse=True)[:12],
                  'note': 'Incluye versiones anteriores; excluye marcadores de borrado.' if complete else
                          'Inventario parcial: consumo mínimo observado. Consulta B2 para el total; máximo 10 páginas por lectura.'}
        _capacity(result, 'RESOURCES_B2_STORAGE_MB')
        return result
    except Exception as exc:
        return _error('b2', exc)


def snapshot():
    app = current_app._get_current_object()
    state = app.extensions.setdefault('resources_monitor', {'lock': threading.Lock(), 'data': None, 'at': 0})
    with state['lock']:
        if state['data'] and time.monotonic() - state['at'] < 60:
            return dict(state['data'], cached=True)
        started = time.monotonic()
        data = {'timestamp': datetime.now(timezone.utc).isoformat(), 'cached': False,
                'render': _render(), 'neon': _neon(), 'b2': _b2(),
                'commit': (os.environ.get('RENDER_GIT_COMMIT') or 'No disponible')[:40]}
        data['duration_ms'] = round((time.monotonic() - started) * 1000, 1)
        state.update(data=data, at=time.monotonic())
        return data
