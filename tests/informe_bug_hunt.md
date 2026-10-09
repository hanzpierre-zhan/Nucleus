# Informe de Auditoría (Bug-Hunt) — Nucleus

Fecha: 2026-10-08 · Método: tests unitarios aislados (`tests/`) · No se modificó
el código fuente ni la base real `nucleus.db`.

## Resumen ejecutivo

- **20 pruebas** ejecutadas en **4.21 s** → **17 pasan, 3 fallan**.
- Los 3 fallos son **bugs reales confirmados** por ejecución (no especulativos).
- 10 hallazgos adicionales detectados por inspección estática de código.

Ejecución (intérprete del proyecto):

```
C:\Users\Hanz\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests
```

Aislamiento: `tests/conftest.py` redirige `DATABASE_URL` a un SQLite temporal
antes de importar `app`, de modo que la instancia a nivel de módulo de `app.py`
nunca toca `nucleus.db` (57.7 MB intacta).

---

## Bugs confirmados por test

### 1. [ALTA] Fuga de detalle interno en errores 500 (info-leak)
- **Archivo:** `app.py:36-40` (handler global `@app.errorhandler(Exception)`).
- **Test:** `test_bug_500_no_filtra_detalle_interno` → **FALLA**.
- **Prueba real:** una excepción `RuntimeError('DETALLE-INTERNO-SECRETO-12345')`
  devuelve al cliente: `{"error":"DETALLE-INTERNO-SECRETO-12345"}` con HTTP 500.
- **Impacto:** cualquier error no capturado expone el `str(e)` original: nombres
  de tablas/columnas, rutas de archivos del servidor, fragmentos de SQL o valores
  internos. Con el handler global, un solo `ValueError` en cualquier ruta filtra
  información del entorno al atacante autenticado o no.
- **Solución sugerida:**
  ```python
  @app.errorhandler(Exception)
  def handle_exception(e):
      if isinstance(e, HTTPException):
          return jsonify(error=e.description), e.code
      current_app.logger.exception("Error no capturado")   # causa completa al log
      return jsonify(error="Error interno del servidor"), 500   # mensaje genérico
  ```
  (Devolver `str(e)` solo cuando `app.debug is True`.)

### 2. [ALTA] Open redirect vía URL protocol-relative (`//dominio`)
- **Archivo:** `blueprints/auth.py:192-197` (`switch_project`).
- **Test:** `test_bug_open_redirect_protocol_relative` → **FALLA**.
- **Prueba real:** `GET /switch_project/1?next=//evil.com` responde `Location: //evil.com`.
- **Causa:** la validación solo rechaza cuando `urlparse(target)` trae `scheme` en
  `('http','https')`. `//evil.com` tiene `scheme=''`, `netloc='evil.com'`, y el
  navegador lo interpreta como una URL absoluta externa.
- **Impacto:** `switch_project` está tras `@login_required`, así que es una
  redirección autenticada → phishing/robo de sesión en un enlace tipo
  `nucleus…/switch_project/1?next=//phishing.com`.
- **Solución sugerida:** solo aceptar destinos que empiecen por `/` y **no** por
  `//`, sin `\` y sin esquema:
  ```python
  target = request.args.get('next') or url_for('pages.index')
  target = target.lstrip() or '/'
  if (not target.startswith('/')) or target.startswith('//') or '\\' in target:
      target = url_for('pages.index')
  ```

### 3. [MEDIA] Rutas inexistentes responden JSON en vez de página HTML 404
- **Archivo:** `app.py:36-40` (mismo handler global).
- **Test:** `test_bug_404_devuelve_pagina_no_json` → **FALLA**.
- **Prueba real:** `GET /esta-ruta-no-existe-jamas-123` → HTTP 404 con
  `Content-Type: application/json`.
- **Impacto:** UX mala (el usuario que teclea mal una dirección ve un JSON crudo)
  y las spiders/indexadores no reciben HTML de error.
- **Solución sugerida:** distinguir por prefijo `/api/` o por `Accept`; para rutas
  web renderizar una plantilla `404.html`; para `/api/*` mantener JSON.

---

## Hallazgos por inspección (sin test dedicado)

### 4. [MEDIA] Código muerto: el "hermano FLM" nunca existe
- **Archivo:** `services/utilidades.py:416-420` — `_flm_hermano_id()` devuelve
  `None` siempre (docstring lo admite).
- **Consecuencia:** todas las ramas condicionales quedan inertes:
  - `evidencia.py:114-129` (replicar la foto en la carpeta del hermano);
  - `_flm_registro_hermano`, `_flm_sync_campos` (`utilidades.py:448-483`);
  - comprobaciones de `_flm_hermano_id(cur) == pid` en permisos (`evidencia.py:48`).
- **Verificado por test:** `test_flm_hermano_id_siempre_none` y
  `test_flm_pair_ids_segundo_siempre_none` pasan (caracterización).
- **Solución sugerida:** eliminar las funciones y ramas muertas, o reintroducir la
  sincronización por esquema si el flujo FLM↔FLM-ENTEL debe seguir funcionando.

### 5. [MEDIA] `MAX_CONTENT_LENGTH` contradice el mensaje del handler 413
- `config.py:46` define **100 MB**; el handler 413 de cotizaciones anuncia **50 MB**.
- Un usuario que suba 60–100 MB no sabrá el límite real al ver el aviso.
- **Solución sugerida:** constante única (p. ej. `app.config['MAX_CONTENT_LENGTH']`)
  interpolada en el mensaje.

### 6. [BAJA] Línea duplicada
- `blueprints/auth.py:184-185`: `proj = db.session.get(Proyecto, pid)` aparece dos
  veces seguidas. Inofensivo, pero indicio de merge descuidado.

### 7. [BAJA] Flag global de "aviso mostrado" que nunca se resetea
- `blueprints/rendicion.py:33` `_TABLA_AVISOS_OK = [False]`; se pone `True` en
  `188-190`, `648-650`, `683-685` y nunca vuelve a `False`.
- Con `--workers 1` (Procfile) el aviso de "tabla no existe" solo se muestra la
  primera vez de todo el proceso, aunque la condición vuelva a darse.
- **Solución sugerida:** chequear el estado real cada vez (sin flag persistente)
  o resetear el flag tras mostrarlo.

### 8. [BAJA] `inject_kpis` usa UTC para "hoy" en lugar de hora de Perú
- `services/utilidades.py:147` `hoy = datetime.now()` (UTC del servidor), mientras
  el resto del sistema documenta el uso de `ahora_peru()` (UTC−5) para todo lo
  visible al usuario.
- Posible desfase de **1 día** en `KPI_*` de tipo DILACIÓN en cálculos cercanos a
  las 19:00 hora Perú.
- **Solución sugerida:** usar `ahora_peru()`.

### 9. [INFO] `_flm_wo_list` hace dos full-scan de TODAS las filas FLM
- `services/utilidades.py:363-402`: recorre `NucleusData.query.filter_by(proyecto_id=…)`
  dos veces, con `json.loads` por fila, en cada request del buscador de Combustible.
- En FLM grande es O(2·n·json) por request. Aceptable para pruebas, costoso en prod.
- **Solución sugerida:** índice + cache con TTL, o columna dedicada de WO.

### 10. [INFO] Caché de opciones por proceso
- `wo.py`: `_opciones_cache` en memoria (TTL 120 s) invalidada por `after_commit`
  (`app.py:119-129`, se dispara en **cada** commit incluyendo lecturas de login/404).
- `login/404` innecesarios: `404` no registra commit, pero el inválido después de
  cada `commit()` fuerza recálculo en *todos* los workers. Con `workers=1` es
  coherente; si se escala a más workers, cada worker tendrá su copia y la
  invalidación cruzada no ocurre (consistencia eventual).
- **Solución sugerida:** invalidar por versión/estampa en vez de por evento, o
  guardar la cache fuera del proceso (Redis) al escalar.

---

## Qué NO se modificó

- Código fuente de la aplicación: **intacto** (solo se creó `tests/`).
- `nucleus.db`: **intacta** (los tests usan SQLite temporal en `%TEMP%`).
- Servidor dev `localhost:5001` ni producción en Render: **no tocados**.

## Próximos pasos sugeridos

1. Aplicar correcciones 1–3 (seguridad) y re-ejecutar `pytest` → verde.
2. Limpiar código muerto (4) y constantes de tamaño (5).
3. Revisar 7–8 con el equipo antes de decidir el cambio de comportamiento.