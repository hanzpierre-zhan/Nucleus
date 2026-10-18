# Estrategia de testing — Nucleus

> **Principio rector:** los tests no cambian el comportamiento. El contrato es
> que **la salida observable sea idéntica** (byte a byte donde aplique). Ninguna
> prueba de este documento modifica código de la aplicación.
>
> Documento de diseño **+ estado de implementación**:
>
> - **Fase 1 — implementada:** `pytest.ini` (fija `testpaths = tests` y
>   `--strict-markers`) y `requirements-dev.txt`.
> - **Fase 2 — implementada:** `tests/test_unit_normalizacion.py`,
>   `test_unit_config_url.py`, `test_unit_monto.py`, `test_unit_fecha_corpus.py`,
>   `test_unit_http_compresion.py`, `test_unit_marcador_index.py`.
> - **Fase 3 — implementada:** `tests/test_golden_formato.py` (congela el formato
>   de la plantilla Excel de columnas manuales y el contrato de datos `rawData`
>   que `/` incrusta para la tabla).
> - **Fase 4 — implementada:** `tests/test_barrido_rutas.py` (ninguna ruta GET
>   sin parámetros devuelve 5xx) y `tests/test_presupuesto_sql.py` (tope de
>   consultas por endpoint; guarda contra los N+1). Los picos de memoria siguen
>   midiéndose con el arnés aparte `scratch/bench_perf.py`, no dentro de la
>   suite (tracemalloc es ruidoso y haría la suite inestable).
> - **Fase 5 — implementada:** `tests/test_degradacion_red.py` (fallo de red y
>   falta de configuración externa, provocados con `monkeypatch` del propio
>   Python: no hace falta instalar `responses` ni `moto`).
> - **Fase 6 — implementada:** `.github/workflows/tests.yml`, con disparo
>   **manual** hasta confirmar una vez que pasa en Linux.
> - **Fase 7 — implementada:** `tests/test_e2e_navegador.py`, prueba de humo con
>   un navegador real sobre `/`: la página carga sin errores de JavaScript y la
>   tabla (que construye Tabulator dentro del navegador) aparece con los datos.
>   Si falta Playwright o su navegador, la prueba se **salta** en lugar de
>   fallar, así la suite sigue verde en cualquier máquina. Para ejecutarla:
>   `pip install playwright && python -m playwright install chromium`.
> - **Sin tocar:** código de la aplicación, plantillas/HTML y tests existentes.
>   La suite pasó de **309 a 368 casos**, todos en verde.

---

## 1. Estado actual (medido, no estimado)

| Dato | Valor | Comentario |
|---|---|---|
| Casos de test | **309** | `pytest tests -q` → 309 passed |
| Archivos de test | **51** | `tests/test_*.py` (+ `conftest.py`) |
| Configuración de pytest | **no existe** | sin `pytest.ini` / `pyproject` / `setup.cfg` |
| Herramienta de cobertura | **no instalada** | `pytest-cov` y `coverage` ausentes |
| Integración continua (CI) | **no existe** | no hay `.github/workflows` |
| `pytest` en dependencias | **no declarado** | `requirements.txt` no lo incluye |
| Base de tests | **SQLite temporal** | producción es **Postgres remoto (Neon)** |
| Runner | venv `scratch/verify-rendicion-env` | no reproducible desde `requirements.txt` |

**Consecuencia inmediata:** hoy los tests solo se ejecutan a mano, en un entorno
que no está declarado, contra un motor de base distinto al de producción. La
suite es buena (buen volumen y buena cobertura funcional de Rendición y
Cotizaciones), pero **no hay red de seguridad automática**.

### Módulos sin ningún test directo (gap real)

Verificado buscando referencias a cada módulo en `tests/*.py`:

| Módulo | Riesgo |
|---|---|
| `services/normalizacion.py` | **Alto** — lo usa todo el dashboard; función pura, trivial de probar |
| `services/utilidades.py` | **Alto** — permisos (`puede_*`), sesión, `safe_json_dumps`, `inject_kpis` |
| `services/apoyo.py` | **Alto** — evidencia en Backblaze B2 + OneDrive; solo se *mockea*, no se prueba |
| `services/cotizacion_pdf.py` | Medio — PDF con `reportlab`, sin verificación de contenido |
| `services/flm_sync.py` | Medio — sincronización entre proyectos |
| `services/pext_reporte.py` | Medio — reporte PEXT |
| `services/identidades.py` | Medio — resolución de identidades |
| `services/form_options.py` | Bajo/Medio — opciones de formulario |
| `services/asistencia_exportacion.py` | Bajo |
| `services/asistencia_permisos.py` | Medio — permisos |
| `services/proyectos_catalogo.py` | Bajo — solo se usa `presentar` en un test |
| `services/combustible.py` | Bajo — solo funciones privadas en `test_bug_hunt` |

---

## 2. Capas y pirámide propuesta

```
        (4) E2E navegador real (Playwright)   ~5 %   → JS de table-controller.html
      (3) Contrato de integraciones externas  ~10 %  → B2, OneDrive, SharePoint, Google Sheets
    (2) Integración con test_client (Flask)   ~35 %  → rutas, permisos, JSON de respuesta
  (1) Unitarios de función pura               ~50 %  → parsing, normalización, montos, fechas
```

- **Capa 1 (rápida, sin app):** `normalizar`, `fecha`, `_monto`, `_normalizar_db_url`,
  proxy `perezoso`, helpers de `utilidades`. Son el **mejor retorno**: cubren la
  lógica donde un `None` silencioso se convierte en pérdida de datos.
- **Capa 2 (la que ya domina el repo):** `test_client` + sesión. Mantener el estilo
  actual, pero aislar la base **por test** (hoy es `scope='session'`).
- **Capa 3 (contratos de red):** nunca salir a Internet en un test. Dobles que
  reproduzcan respuestas grabadas y, sobre todo, **casos de fallo**.
- **Capa 4 (navegador):** ya hay scripts Playwright en `scratch/shot_*.py`; formalizar
  unos pocos como *smoke tests* reales.

---

## 3. Tests unitarios por función (casos normal / límite / inválido)

Los valores "esperado" de las tablas son **medidos** con `scratch/valores_esperados.py`
(ejecutado contra el código actual), no supuestos.

### 3.1 `services/normalizacion.py` → `normalizar(valor)` *(sin test — prioritario)*

| Tipo | Entrada | Esperado |
|---|---|---|
| normal | `'WO-123 / A'` | `'wo123a'` |
| normal | `'Ñandú'` | `'nandu'` (NFKD + sin diacríticos) |
| normal | `'ÁÉÍÓÚ'` | `'aeiou'` |
| límite | `'  x  '` | `'x'` |
| límite | `123` (no str) | `'123'` |
| límite | `''` | `''` |
| límite | `None` | `''` |
| **límite** | `'١٢٣'` (dígitos árabes) | `''` — **se descartan**: documentar |
| inválido | `'ABC_1'` | `'abc1'` (símbolos fuera) |

### 3.2 `normalizacion.primer_texto(*vals)`

| Tipo | Entrada | Esperado |
|---|---|---|
| normal | `(None, '', '  x  ')` | `'x'` (recorta) |
| **límite** | `(0, 5)` | `'5'` — **el `0` se pierde**; fijar la semántica |

### 3.3 `blueprints/refacturable.py` → `_monto(valor)` *(money parsing)*

| Tipo | Entrada | Esperado |
|---|---|---|
| normal | `'1234.56'` | `Decimal('1234.56')` |
| normal | `'S/ 1,234.56'` | `Decimal('1234.56')` |
| normal | `'1.234,56'` (formato europeo) | `Decimal('1234.56')` |
| normal | `'1,5'` | `Decimal('1.50')` (cuantiza a 2) |
| normal | `'-5,00'` | `Decimal('-5.00')` |
| **límite** | `'999999999999'` | `Decimal('999999999999.00')` (aceptado) |
| **límite** | `'1000000000000'` | `None` (tope `> 999999999999`) |
| **límite** | `'1e5'` | `Decimal('100000.00')` — notación científica **aceptada** |
| inválido | `'abc'` | `None` |
| inválido | `'NaN'` | `None` (no finito) |
| inválido | `'Infinity'` | `None` (no finito) |
| inválido | `'S/'`, `'PEN'`, `''`, `None` | `None` |

> `_importe(None) → ''`, `_importe(Decimal('1.5')) → '1.50'`.

### 3.4 `services/dashboard_integratel.py` → `fecha(valor)` *(parsing de fechas)*

| Tipo | Entrada | Esperado |
|---|---|---|
| normal | `'2026-08-14 12:46:17'` | `datetime.date(2026, 8, 14)` |
| normal | `'14/08/2026'` | `date(2026, 8, 14)` (día primero) |
| normal | `'14-08-2026'` | `date(2026, 8, 14)` |
| normal | `'2/1/2026 8:5'` | `date(2026, 1, 2)` (hora sin ceros) |
| normal | `'2026-08-14'` | `date(2026, 8, 14)` |
| **límite/bug** | `'2026/08/14'` | `None` — **se pierde** si la fuente cambia el separador |
| inválido | `'no-es-fecha'`, `''`, `None` | `None` |

> Existe ya un corpus de equivalencia de 759 casos en `scratch/equiv_fecha.py`:
> **promoverlo a test permanente** dentro de `tests/`.

### 3.5 `config.py` → `_normalizar_db_url(url)` *(arranque / conexión)*

| Tipo | Entrada | Esperado |
|---|---|---|
| normal | `'sqlite:///x.db'` | sin cambios |
| normal | `'postgres://u:p@h/db'` | `'postgresql+psycopg2://u:p@h/db?sslmode=require'` |
| normal | `'postgresql://h/db?channel_binding=require'` | `'postgresql+psycopg2://h/db?sslmode=require'` |
| normal | `'postgresql://h/db?sslmode=require&channel_binding=require'` | `'postgresql+psycopg2://h/db?sslmode=require'` |
| **límite → BUG** | `'postgresql://h/db?channel_binding=require&sslmode=require'` | devuelve `'postgresql+psycopg2://h/db&sslmode=require'` → **URL malformada** (se elimina el `?`) |
| inválido | `None` | `None` |

> **Este es el ejemplo que justifica la capa 1.** Un test de una línea detecta que,
> si el `channel_binding` va primero, la cadena de conexión queda rota. *(No se
> corrige aquí: cambiaría el resultado.)*

### 3.6 `perezoso.py` → proxy de importación diferida

- `pd` no está en `sys.modules` tras `create_app()`.
- Primer acceso (`pd.DataFrame`) importa el módulo real y **cachea**.
- `hasattr` de un atributo inexistente no revienta de forma distinta a un módulo real.
- Ya cubierto por `tests/test_perezoso.py` (2 casos): añadir el caso "atributo inexistente".

### 3.7 `infrastructure/http.py` → `_compress_response`

| Tipo | Caso | Esperado |
|---|---|---|
| normal | JSON de 2 KB sin `Accept-Encoding: gzip` | sin comprimir |
| normal | JSON de 2 KB con gzip | `Content-Encoding: gzip`, `Vary` incluye `Accept-Encoding` |
| límite | cuerpo **< 1024 bytes** | sin comprimir (umbral) |
| límite | cuerpo **≥ 1 MB** | se usa nivel 3 (adaptativo) |
| límite | tipo no textual (`image/png`) | sin comprimir |
| inválido | ya tiene `Content-Encoding` | no recomprime |
| inválido | `response.direct_passthrough` | se devuelve tal cual |

> El bloque envuelve todo en `except Exception: pass`: conviene un test que
> garantice que un fallo de compresión **no rompe la respuesta** (contrato actual).

### 3.8 `blueprints/pages.py` → técnica del marcador (`/`)

El endpoint serializa el JSON y lo inserta con
`html.replace(_MARCADOR_DATOS_TABLA, datos_json)` (línea 552).

- **Normal:** el marcador **desaparece** del HTML y el JSON aparece **una sola vez**.
- **Límite:** si se cambia la plantilla y `{{ data }}` aparece dos veces → el JSON
  se insertaría dos veces (la respuesta se duplicaría). Test de invariante:
  `html.count(marcador) == 0` y el JSON **una** vez.
- **Límite:** una fila cuyo valor **contenga** el texto del marcador. `str.replace`
  no re-escanea el reemplazo, así que hoy es seguro; **fijar ese comportamiento**
  con un test (documenta por qué el marcador es seguro).
- Ya existe `tests/test_index_datos.py` (1 caso): ampliarlo con los tres.

---

## 4. Escenarios obligatorios **antes de ir a producción**

Ordenados por riesgo. Los P0 deberían ser bloqueantes de despliegue.

### P0 — bloqueantes

1. **Autenticación y sesión** (`blueprints/auth.py`): login válido/ inválido,
   consentimiento legal (versión nueva vs ya aceptada), cambio de contraseña,
   cierre de sesión, `@login_required` en **cada** ruta `/api/*` (barrido
   automático: toda ruta nueva debe devolver 401/302 sin sesión).
2. **Aislamiento entre proyectos:** un usuario con acceso al proyecto A **no**
   puede leer ni editar filas de B (existe parcialmente en
   `test_correlacion_integral`, ampliar a todas las rutas con `proyecto_id`).
3. **Migraciones** (`migrations/__init__.py`) sobre (a) base vacía y (b) **copia
   de producción**: la base real es el mayor activo; una migración mal aplicada
   es el peor escenario.
4. **Ida y vuelta de exportación/restauración** (`/api/admin/export_zip` +
   `test_restaurar_exportacion`): exportar → restaurar → comparar contenido.
5. **Parsing de importación** (`blueprints/imports.py`, con `pandas`): CSV con
   **BOM**, separador `;`, columnas duplicadas (`col`, `col.1`), cabecera vacía,
   archivo > `nrows`, `dtype=str` y celdas vacías. Es la puerta de entrada de
   datos: un fallo aquí corrompe la base.
6. **Fechas y montos** (§3.3, §3.4): un `None` silencioso es pérdida de datos.

### P1 — muy recomendables

7. **Presupuesto de consultas y memoria** (regresión de las optimizaciones de
   esta sesión): formalizar `scratch/scan_sql.py` y `scratch/bench_perf.py` como
   tests con **umbral**, no con tiempo absoluto:
   - `SQL por endpoint ≤ N` (los N+1 vuelven a aparecer con facilidad y, contra
     Postgres remoto, **cada consulta es una ida y vuelta**).
   - pico de memoria de `/`, `export_zip`, `manual_template` bajo un tope.
   - `pandas`/`openpyxl` **ausentes** de `sys.modules` tras `create_app()` (cold start).
8. **Respuestas "doradas" (golden files):** congelar la salida byte a byte de
   `/`, `/api/sites`, `/api/sites/nombres`, `export_zip`, `manual_template` y
   `validadores` — exactamente lo que se validó con `scratch/capturar_ruta.py`.
   Un cambio no intencional en cualquiera de esas respuestas se detecta solo.
9. **Evidencia (B2 / OneDrive / SharePoint)** — degradación: si B2 falla,
   ¿la foto se guarda local? `services/apoyo.py` **traga excepciones** en varios
   puntos (`except Exception: pass`): probar que el fallo **no** pierde datos en silencio.
10. **Sincronización externa** (`/api/rendicion/sync`, `services/flm_sync.py`):
    idempotencia (correr dos veces no duplica), CSV vacío/malformado, cambio de
    columnas en el origen, y **timeout** (los `urlopen` ya tienen timeout: fijarlo con test).
11. **Concurrencia:** el `Procfile` corre `gthread --threads 4` con **1 worker**:
    dos peticiones simultáneas sobre la misma fila (última escritura gana vs
    error). Hoy no se prueba.

### P2 — higiene

12. **Barrido de rutas:** test paramétrico que recorra `app.url_map` y exija que
    **ninguna ruta GET devuelva 5xx**. Habría detectado
    `/api/master/template/<tipo>` (devuelve **500** porque usa
    `engine='xlsxwriter'`, paquete **no instalado**).
13. **Códigos de error:** 400/403/404 consistentes y **sin filtrar** `str(e)`
    (el manejador de 500 ya lo hace bien; fijarlo con test).

---

## 5. Zonas de mayor riesgo

| # | Zona | Por qué es riesgosa |
|---|---|---|
| 1 | **Esquema JSON-por-fila** (`NucleusData.data_json`) | No hay esquema: cada lectura hace `json.loads`; un `None`/clave cambiada falla en silencio. Sin test de contrato de columnas, un cambio de nombre en el origen rompe todo |
| 2 | **Permisos** (`puede_cotizaciones`, `puede_rendicion`, `_autorizar`, `get_menu_proyectos`) | Un fallo = **fuga de datos entre proyectos o roles**. Muy ramificado |
| 3 | **Migraciones sobre la base real** | Irreversible si sale mal; no se prueba contra una copia real |
| 4 | **Parsing de importación** (`pandas`) | Entrada no confiable; corrompe datos si falla |
| 5 | **Servicios externos** (B2, OneDrive, SharePoint, Google Sheets) | Sin dobles, los tests dependen de la red; con `except: pass`, los fallos son mudos |
| 6 | **Dialecto SQLite (tests) vs Postgres (producción)** | `LIKE` sensible a mayúsculas, tipos JSON, secuencias, transacciones anidadas/`IntegrityError` — **divergen** y los tests no lo ven |
| 7 | **Renderizado de 9 MB en `/`** | Memoria/CPU al límite del plan free; cualquier regresión puede tumbar la instancia |
| 8 | **JS de `templates/table-controller.html`** (19 793 líneas) | Cero cobertura; ver §6 |

---

## 6. Lo difícil (o imposible) de probar, y cómo mitigarlo

| Zona | Por qué es difícil | Mitigación |
|---|---|---|
| **`table-controller.html`** (19 793 líneas, script de nivel superior, `rawData` en decenas de sitios) | No hay runner JS ni tests; refactorizarlo es inverificable | (a) **Contrato de datos**: los tests de Python fijan el JSON embebido; (b) **Playwright** (ya usado en `scratch/shot_*.py`) para 3–5 *smoke tests* reales: cargar `/`, filtrar, editar una celda, guardar; (c) no tocarlo sin (b) |
| **Arranque en frío y memoria** (0.1 CPU / 512 MB) | El tiempo depende de la máquina; `tracemalloc` distorsiona la medición | Medir en el arranque real (`gunicorn`) con umbral amplio; aserciones sobre **hechos** (módulos no importados) en vez de milisegundos |
| **Red externa** | No determinista, lenta, puede fallar | Dobles de `urllib.request.urlopen` con respuestas grabadas **y** casos de error/timeout/HTTP 500 |
| **B2 con `boto3`** | Requiere credenciales reales | `moto` o `botocore.stub.Stubber`; probar siempre el camino "sin credenciales" (`evidencia_usa_b2() → False`) |
| **PDFs (`reportlab`)** | Comparar bytes es frágil | Comparar **texto extraído** y estructura (nº de páginas), no bytes |
| **Zona horaria / `utcnow`** | Fecha local vs UTC | `freezegun` y congelar TZ |
| **Concurrencia (4 hilos)** | Carreras difíciles de reproducir | Tests con `ThreadPoolExecutor` sobre el mismo registro + `pool_pre_ping`; aceptar cobertura parcial |
| **Postgres real** | El entorno de tests es SQLite | Servicio Postgres en CI (§7) y un marcador `@pytest.mark.postgres` |

---

## 7. Infraestructura de testing recomendada

### 7.1 Configuración (hoy inexistente) — `pytest.ini`

```ini
[pytest]
testpaths = tests
norecursedirs = scratch .git __pycache__ instance
addopts = -q --strict-markers
markers =
    integracion: usa test_client de Flask
    postgres: solo se ejecuta contra Postgres
    lento: > 2 s
```

> **Importante:** hoy `pytest` sin argumentos **arrastra `scratch/`**, que
> contiene paquetes vendorizados (`scratch/rendicion-test-deps/sqlalchemy/testing/suite/test_*.py`).
> Por eso hay que ejecutar siempre `pytest tests`. `testpaths = tests` lo hace
> seguro por defecto.

### 7.2 Dependencias de desarrollo — `requirements-dev.txt`

```
pytest
pytest-cov
pytest-mock
freezegun
responses
moto
playwright
```

### 7.3 Cobertura

```bash
pytest tests --cov=. --cov-report=term-missing --cov-report=html
```

Objetivos realistas por capa (no un 100 % global engañoso):

| Capa | Objetivo |
|---|---|
| Funciones puras (servicios de cálculo) | **≥ 95 %** |
| Rutas (`blueprints/`) | ≥ 80 % |
| Integraciones externas | por **contrato**, no por línea |

### 7.4 CI (GitHub Actions) — dos trabajos

1. **rápido (SQLite):** cada push/PR → suite completa + cobertura.
2. **Postgres:** servicio `postgres:16` + `DATABASE_URL` → los tests marcados
   `@pytest.mark.postgres`, para cazar las divergencias de dialecto.

### 7.5 Fixtures y estilo (mejoras al `conftest.py` actual)

- **Base por test, no por sesión:** hoy la `app` es `scope='session'` y comparte
  estado; una fuga entre tests produce falsos verdes/rojos.
- **Fábricas** (`usuario_factory`, `proyecto_factory`, `fila_factory`) en vez de
  crear objetos sueltos por test.
- **No acoplarse a credenciales**: el `conftest` hace login con `'zeno'/'zeno123'`
  (sembrado por migraciones). Preferible: crear el usuario en el fixture.
- **Nunca tocar `nucleus.db`**: el `conftest` ya redirige a un temporal (bien);
  mantenerlo y añadir un *guard* que falle si `DATABASE_URL` apunta a la real.
- **Marcar** los tests que tocan red o son lentos.

---

## 8. Plan de adopción (incremental, sin cambiar comportamiento)

| Fase | Contenido | Valor | Estado |
|---|---|---|---|
| **1** | `pytest.ini` + `requirements-dev.txt` + cobertura en local | Hace reproducible y medible lo que ya existe | ✅ hecha |
| **2** | Unitarios de funciones puras (§3.1–3.5) + promover el corpus de `fecha` | Barato, alto retorno; detecta el bug de `_normalizar_db_url` | ✅ hecha |
| **3** | Golden files de las respuestas byte-equivalentes (§4.8) | Blinda todo lo logrado en rendimiento | ✅ hecha (plantilla Excel + contrato de datos de `/`) |
| **4** | Barrido de rutas + presupuestos de SQL/memoria (§4.7, §4.12) | Detecta N+1 y regresiones de recursos | ✅ hecha (rutas + SQL; la memoria se mide con `scratch/bench_perf.py`) |
| **5** | Dobles de red + casos de degradación (§4.9, §4.10) | Sacar la red de la suite | ✅ hecha (fallo de red y falta de configuración) |
| **6** | CI (SQLite + Postgres) | Red de seguridad automática | 🟡 hecha la parte SQLite, con disparo manual |
| **7** | Playwright *smoke* sobre `/` | Cubre el mayor punto ciego (JS) | ✅ hecha (la prueba se salta si no hay navegador) |

---

## 9. Hallazgos que la estrategia habría detectado

Documentados como evidencia del valor de cada capa. **No se han corregido**
(corregirlos cambiaría el resultado observable).

| Hallazgo | Capa que lo detecta | Efecto |
|---|---|---|
| `_normalizar_db_url` genera URL malformada si `channel_binding` va antes de `sslmode` | Unitarios (§3.5) | Conexión rota en arranque |
| `/api/master/template/<tipo>` → **500** (`xlsxwriter` no instalado) | Barrido de rutas (§4.12) | Función caída |
| `/api/catalogos/autocompletar` escanea 5 583 filas y **siempre** devuelve `sites: []` (la clave del catálogo es `Nombre`, ausente de la lista aceptada) | Tests de intención (§4) | Función inútil + coste |
| `fecha('2026/08/14') → None` | Unitarios (§3.4) | Pérdida silenciosa de fecha |
| `primer_texto(0, 5) → '5'` (el `0` se trata como vacío) | Unitarios (§3.2) | Semántica no documentada |
| `pytest` sin argumentos arrastra `scratch/` vendorizado | Infraestructura (§7.1) | Suite no reproducible |

---

*Documento de diseño. No modifica código de la aplicación ni de los tests
existentes: la suite sigue en 309 casos en verde.*
