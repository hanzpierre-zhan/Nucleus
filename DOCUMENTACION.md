# DOCUMENTACIÓN TÉCNICA — NUCLEUS

> Referencia completa del sistema para modificar/agregar criterios, reglas y funcionalidad.
> Última actualización: 03/10/2026.

---

## 1. ARQUITECTURA GENERAL

La app se refactorizó de **monolito (`app.py` de ~3900 líneas) a módulos**. `app.py` quedó
como *factory* (`create_app()`): configura BD, compresión, migraciones, cachés y registra
los blueprints. **Las rutas ya no están en `app.py`.**

| Componente | Tecnología | Dónde |
|---|---|---|
| Factory / arranque | Flask + Flask-SQLAlchemy | `app.py` (`create_app()`, ~9.4 KB) |
| Config / BD | `DATABASE_URL` o `nucleus.db` | `config.py`, `db.py`, `models.py` |
| Rutas de páginas | `pages.py` | `blueprints/pages.py` — `/`, `/dashboard`→`/analytics`, `/analytics`, `/proyectos`, `/usuarios`, `/admin`, `/configuraciones`, `/mapa-site` |
| Datos / filas | `rows.py` | `blueprints/rows.py` — update/add/delete/bulk_update/finalizar |
| WO / AUTIN / sitios | `wo.py` | `blueprints/wo.py` — meta, historial, servicios, detalle/opciones, sites, wos_flm, **`/api/autin/*`** |
| Evidencia | `evidencia.py` | `blueprints/evidencia.py` — subir/eliminar/foto/zip/reporte |
| Cotizaciones | `cotizacion.py` | `blueprints/cotizacion.py` — estado, lista, registro, generar, PDF |
| Rendición | `rendicion.py` | `blueprints/rendicion.py` — `/api/rendicion/accion|subir_foto|foto|avisos` |
| Import / master | `imports.py`, `master.py` | preview/process, filtros, tablas, reglas, columnas, layout |
| Admin / usuarios | `admin.py`, `auth.py` | proyectos, usuarios, permisos, sync, config |
| Lógica compartida | `services/` | `apoyo.py` (reportes PEXT, cálculos), `utilidades.py` (decoradores), `__init__.py` re-exporta |
| Frontend | Jinja2 + Tabulator/Chart/XLSX **locales** | `templates/index.html` (~13.7 k líneas), `analytics.html`, `base.html` |
| Despliegue | Render | `Procfile` `web: gunicorn app:app`, `runtime.txt` python-3.11.8 |
| Fotos/evidencia | Local `static/evidencia/` o Backblaze B2 (opcional) | envs `B2_*` |
| Fotos AUTIN | Disco `C:\Evidencias\FLM - ENTEL` + túnel Cloudflare | `AppConfig autin_fotos_dir` y `autin_base_url`; ver §7.5 |

**Stack datos:** `pandas`, `openpyxl`, `Pillow` (+`pillow-heif` para HEIC), `reportlab`,
`python-docx`, `boto3`, `psycopg2-binary`.

> ⚠️ Los números de línea de este documento son orientativos: tras el refactor casi todos
> cambiaron. Busca por **nombre de función/ruta**, no por línea.

### 1.1 Assets estáticos (sin CDN)

Todo el JS/CSS de terceros vive en `static/vendor/` y `static/js/` para eliminar ~1.9 s de
bloqueo por CDNs (ver `?v=1` en `base.html`/`login.html`): `luxon`, `xlsx.full.min`,
`chart.umd.min`, `tabulator.min` (+ CSS), `fontawesome.min.css` + `webfonts/`, `leaflet`
(+ `css/images/`). **Si actualizas una librería, sube el `?v=`** para romper la caché.


---

## 2. PROYECTOS (tabla `proyectos`)

| id | Nombre | Tipo | PK (columna llave) | Registros | Reglas |
|---|---|---|---|---|---|
| 1 | FLM | WOs | `Número de WO` | 757 | Import exige `CATEGORY=O&M CRM` |
| 2 | PEXT | WOs | `Número de WO` | 98 | Import exige `CATEGORY=O&M PEXT` + 4 reglas TablaMaestra |
| 3 | Dataper | Catálogo | `DOCUMENTO` | 79 | Fuente de técnicos |
| 4 | Material | Catálogo | `COD_MATERIAL` | 30 | Fuente de materiales |
| 5 | Site Name | Catálogo | `NOMBRE DE SITE` | 5485 | Fuente de sitios (FLM) |
| 6 | Generadores | Manual | (auto) | 52 | Grupos electrógenos FLM |
| 7 | Combustible | Manual | (auto) | 2 | Consumo de combustible FLM |

**Proyectos fijos** (creados en migración, protegidos de borrado): FLM, PEXT, Dataper, Material, Site Name, Generadores, Combustible.

**Visibilidad por rol** (reglas especiales en `switch_project`/`get_menu_proyectos`):
- Tener FLM o PEXT ⇒ acceso a Dataper y Material.
- Tener FLM ⇒ acceso a Site Name, Generadores y Combustible.

---

## 3. MODELO DE DATOS (tablas)

| Tabla | Campos clave | Propósito |
|---|---|---|
| `usuarios` | username (único), password_hash, rol (`admin`/`supervisor`/`gestor`) | Usuarios |
| `proyectos` | nombre (único), descripcion, icono | Proyectos |
| `app_config` | proyecto_id, clave, valor (JSON/texto) | Configuración (ver §4) |
| `nucleus_data` | proyecto_id, key_value (único), data_json | Datos actuales de filas |
| `nucleus_history` | proyecto_id, key_value, data_json, fecha_consolidado | Historial de consolidación |
| `filtros_maestros` | columna, valor | Filtros de exclusión por fila (vacía) |
| `tablas_maestras` | columna_criterio, valor_criterio, nueva_columna, nuevo_valor | Reglas de asignación de valores |
| `reglas_estado_manual` | columna_criterio, valor_criterio, columna_manual, nuevo_valor | Reglas de estado manual (vacía) |
| `accesos_proyecto` | usuario_id, proyecto_id, restricciones (JSON) | Permisos por columna/valor |
| `kpi_configs` | nombre, col_inicio, restar_contra (HOY/COLUMNA), col_fin, tipo | KPIs (vacía) |
| `historial_cambios` | key_value, campo_modificado, valor_anterior, valor_nuevo, fecha | Bitácora de cambios |
| `tecnicos` | nombre, contrata, especialidad, telefono | Tabla auxiliar (vacía — se usa Dataper) |
| `cotizaciones` | key_value, numero, nota, gastos_json, mano_obra_json, bloqueada | Cotizaciones de tickets |

---

## 4. CONFIGURACIÓN GUARDADA (`app_config`)

| Clave | Formato | Para qué sirve |
|---|---|---|
| `primary_key` | texto | Columna llave del proyecto |
| `app_schema` | JSON array | Lista de columnas conocidas (esquema dinámico) |
| `manual_columns` | JSON array `[{"nombre","tipo","opciones"}]` | Columnas manuales (editables por gestores) |
| `column_layout` | JSON array `[{"field","visible"}]` | Orden/visibilidad de columnas |
| `saved_dashboard_charts` / `saved_dashboard_kpis` / `saved_dashboard_filters` | JSON | Config del dashboard |
| `consolidation_config` | JSON `{consolidate_on_filter_fail, auto_consolidate_missing}` | Comportamiento ante filas que fallan filtros o ausentes |
| `cotizacion_margen_pct` | número | % de margen de cotización (FLM=50, default 30) |
| `servicio_opciones` | JSON array | Opciones de SERVICIO del modal WO |
| `historial_backfill_done` | flag | Idempotencia de migración de historial |

**NOTA:** `fault_rules` NO es clave de `app_config`. Las horas de respuesta de PEXT son **filas de `tablas_maestras`** (ver §5.1).

---

## 5. CRITERIOS Y REGLAS — CÓMO MODIFICARLOS O AGREGARLOS

### 5.1 Tablas Maestras (`tablas_maestras`) — asignación automática de valores

**Regla actual (PEXT):** si `Fault Level` = X ⇒ asignar `Hrs Respuesta` = Y.

| id | columna_criterio | valor_criterio | nueva_columna | nuevo_valor |
|---|---|---|---|---|
| 1 | Fault Level | Critical | Hrs Respuesta | 8hrs |
| 2 | Fault Level | Alta | Hrs Respuesta | 10hrs |
| 3 | Fault Level | Media | Hrs Respuesta | 48hrs |
| 4 | Fault Level | Baja | Hrs Respuesta | 72hrs |

**Lógica de aplicación** (`app.py:2100-2108` importación; `2312-2321` y `2380-2390` reproceso):
- Condiciones múltiples en `columna_criterio` separadas por coma = **AND** (todas deben cumplirse).
- Comparación de valores **exacta, sensible a mayúsculas** (`str(current_data.get(c,'')) != v`).
- Si cumple ⇒ `data[nueva_columna] = nuevo_valor` (sobrescribe).

**CÓMO agregar/modificar una regla:**
1. En la web: Proyecto → **Configuraciones** (admin) → sección tablas maestras, o directamente en la BD:
   ```sql
   INSERT INTO tablas_maestras (proyecto_id, columna_criterio, valor_criterio, nueva_columna, nuevo_valor)
   VALUES (1, 'Fault Level', 'Muy Alta', 'Hrs Respuesta', '2hrs');
   ```
2. **Aplicar**: importar de nuevo O ir a **Configuraciones → Reprocesar** (`POST /api/master/reprocess`) para re-aplicar sobre registros existentes.
3. Si la columna destino (`nueva_columna`) es nueva, se agrega automáticamente al `app_schema`.

### 5.2 Filtros Maestros (`filtros_maestros`) — excluir filas que no cumplen

Lógica de **clusters** (`app.py:1923-1953`, evaluación `2110-2129`):
- Reglas que comparten columnas forman un cluster → dentro del cluster se evalúa **OR** (basta cumplir una).
- Entre clusters distintos se evalúa **AND** (debes cumplir todos).
- Comparación **case-insensitive** (uppercase), a diferencia de TablaMaestra.
- Si una fila no cumple: si `consolidate_on_fail` ⇒ se mueve a `nucleus_history`; si no ⇒ se ignora.

**Actual:** 0 reglas (vacía).

### 5.3 Reglas de Estado Manual (`reglas_estado_manual`) — escritura en columnas manuales

Misma mecánica que TablaMaestra pero escribe en `columna_manual` (columna editable por gestores). Actualmente 0 reglas.

### 5.4 Fault Level / SLA — CRITERIOS DE VISUALIZACIÓN (FRONTEND)

**Todo está en `templates/index.html`.** La fuente de verdad del SLA es el **frontend**, no la BD.

**Flags de proyecto** (`index.html:874-878`):
```js
IS_WO_PROJECT = ['pext','flm'];
MANUAL_PROJECT = ['dataper','material','site name','generadores','combustible'];
IS_FLM = (nombre == 'flm'); IS_PEXT = (nombre == 'pext');
```

**Colores de Fault Level** (`FAULT_COLORS`, `index.html:880-890`):

| Nivel | FLM (min) | PEXT/otros (min) |
|---|---|---|
| Critical | 240 (4hrs) | 480 (8hrs) |
| Alta | 300 (5hrs) | 600 (10hrs) |
| Media | 720 (12hrs) | 2880 (48hrs) |
| Baja | 2880 (48hrs) | 4320 (72hrs) |

**Threshold SLA** (`getSlaThreshold` `index.html:1200-1228`, `getSlaThresholdData` `1309-1330`):
1. Si la columna SLA tiene número entero ⇒ se toma como minutos.
2. Si es patrón `(\d+)\s*HRS` ⇒ horas × 60.
3. **Fallback por Fault Level**: los minutos de la tabla de arriba según `IS_FLM`.
4. **Default: 360 min (6 h)**.

**Semáforo** (`slaCumplimientoEstado` `index.html:1346-1362`):
- `CANCELADO O&M` = SÍ ⇒ NO APLICA (gris).
- Estado `canceled`/`rejected` ⇒ NO APLICA.
- `closed`: dentro del límite ⇒ SLA CUMPLIDO (verde); si no ⇒ VENCIDO (rojo oscuro).
- Activos: `<50%` verde · `<80%` amarillo · `<100%` rojo · `>=100%` rojo oscuro.

**CÓMO cambiar umbrales:** editar los números en `FAULT_COLORS` (`index.html:880-890`) y en los bloques `getSlaThreshold`/`getSlaThresholdData` (`1215-1224`). Cambiar **ambos** lugares (tabla y función).

**CÓMO agregar un nivel nuevo (ej. "Muy Alta"):** añadir entrada en `FAULT_COLORS` (condicional FLM/PEXT), en los dos mapas de fallback de threshold, y en `tablas_maestras` si también quieres asignar `Hrs Respuesta`.

### 5.5 Otras lógicas de color en frontend
- **WO State** (`WO_STATE_COLORS` `892-900`): unscheduled, accepted, dispatched, inprocess, rejected, closed, canceled.
- **PRIORIDAD DEL SITE** (`SITE_PRIORITY_COLORS` `902-927`): p0+/p0/p1/critical/vip/p2/alta/high/gold/p3/media/p4/baja/silver/bronze.
- **KPI alarmas** (`kpiAlarmFormatter` `1167-1184`): rangos de días.
- **Heatmap ACUMULADO** (`1758-1821`): rank 1-4.

---

## 6. PROCESO DE IMPORTACIÓN (`POST /api/import/process`, `app.py:1821`)

**Flujo paso a paso:**
1. Parámetros: `type` (`base`/`cruce`/`manual_cols`), `sum_duplicates`+`sum_type`, `consolidate_date`+`date_column`, `columns_to_keep`, `file_key`.
2. Carga de columnas manuales del proyecto.
3. **Validación CATEGORY** (`1862-1877`): FLM exige `O&M CRM`, PEXT exige `O&M PEXT` (error 400 si falta o trae otros valores).
4. Filtrado de columnas / consolidación de duplicados (por fecha `keep=last` o suma de numéricos / `last` para resto).
5. Construcción de clusters de filtros + reglas de tablas maestras.
6. **Delta SELECT** (`1984-2002`): consulta solo las claves del archivo (chunks de 400, límite SQLite) — optimizado para no traer toda la tabla.
7. **Columnas especiales:**
   - `Estado de la tarea (WO State)` = estado del WO.
   - `FECHA CAMBIO ESTADO` = timestamp de transición.
   - `_fecha_dispatched` / `_fecha_cancel_reject` = timestamps internos (prefijo `_` = ocultas en UI).
   - Estados: `dispatched`, terminales `canceled`/`rejected`.
8. **Campos protegidos** (`protected_fields` `2020-2030`): la importación NO pisa: todas las columnas manuales + SERVICIO, CIUDAD, TECNICO, CONTRATA, MOTIVO DE AVERÍA, SOLUCIÓN, LATITUD/LONGITUD, MUFAS, UBICACIÓN DE MUFAS, MATERIALES. Excepción: modo `manual_cols` (Dataper) sí pisa.
9. **Por fila:** merge (UPDATE) o insert (ADD) con historial de transiciones de estado, aplicación de reglas, evaluación de filtros, decisión de consolidar/ignorar.
10. **Consolidación por ausencia** (`2157-2173`): si `auto_consolidate_missing` ⇒ filas que ya no vienen se mueven a `nucleus_history` y se eliminan (hoy apagado).
11. Commit único + actualización de `app_schema`.

**CÓMO agregar una columna nueva al import:** basta que venga en el archivo Excel/CSV → se agrega sola al `app_schema`. Si es columna manual, hay que declararla en Configuraciones → Columnas Manuales (así el gestor puede editarla y queda protegida del import).

---

## 7. MÓDULOS ESPECIALES

### 7.1 Combustible (solo FLM, proyecto 7)
- **Columnas:** FECHA, QR ASIGNADO, TIPO (PROPIO/ALQUILADO/ENTEL), TECNICO ASIGNADO, ZONA, NOMBRE DE SITE, MOVIMIENTO (INGRESO/GASTO), NUMERO FACTURA, GALONES, FOTO, WO NUMBER, GESTOR, COMENTARIOS.
- **Llave interna auto-generada** (numérica, sin PK visible).
- **Saldo disponible** = INGRESOS − GASTOS por generador, ordenado por FECHA (backend `app.py:1213-1232`, `_combustible_saldo`).
- **Catálogos dinámicos:** QR ASIGNADO → Generadores; TIPO/TECNICO/ZONA autocompletados desde el mapa de Generadores; WO NUMBER → WOs de FLM (`_flm_wo_list`); TECNICO ASIGNADO → técnicos Dataper con PROYECTO=FLM.
- **Validaciones:** gestor solo completa campos vacíos; GESTOR inmutable; WO NUMBER debe pertenecer a FLM (vacío = "CM PENDIENTE"); validación de saldo en GASTO; eliminación solo admin.
- **Frontend:** tarjetas de saldo por zona (`buildCombustibleStats` `980`), modal detalle `#modal-comb-detalle` (`3485`), alta `aniadirRegistroCombustible` (`2763`).

### 7.2 Generadores (solo FLM, proyecto 6)
- **Columnas:** QR ASIGNADO, SERIE DE EQUIPO, TIPO, TECNICO ASIGNADO, ZONA. Seed de 26 series idempotente.
- Llave interna auto-generada (QR editable, puede ser vacío).
- TECNICO ASIGNADO = técnicos Dataper activos con PROYECTO=FLM.

### 7.3 Cotizaciones (tickets FLM/PEXT)
- Tabla `cotizaciones` (varias por ticket). PDF generado con ReportLab: cliente fijo HUAWEI DEL PERU (RUC 20507646728), subtotales A (materiales) + B (mano de obra), margen `cotizacion_margen_pct` (FLM=50%).
- Número de cotización: prefijo `HW-` + año. Guarda en `nucleus_data` columnas `COTIZACION_*`.
- Desbloquear/eliminar solo admin; gestor no toca bloqueadas.

#### Flujo de 4 pestañas (columna `ESTADO COTIZACION`)
| # | Pestaña | Estados que la alimentan | Acción de la columna *Flujo* |
|---|---------|--------------------------|------------------------------|
| 1 | Registro | `Pdt. Cotización` + estados sin mapear (`En proceso`, `Observado`, `Rechazado`, `Cancelado`, vacío) | **Generar cotización** → abre el desglose; al generar se pasa a `Cotizado` |
| 2 | Cotización | `Cotizado` | **Enviar a cliente** → `En Aprobación` |
| 3 | Cliente | `En Aprobación` | **Conformar aprobación** (modal: fecha/hora auto, correo del cliente, comentario) → `Atendido` |
| 4 | Atendido | `Atendido` / `Validado` | Historial / auditoría |

- **Alta en la pestaña 1:** el botón *Añadir nuevo registro* abre el formulario de **solicitud** (Código Interno autogenerado `COB-{AÑO}-{MES}-{SECUENCIAL}`, N° de WO, Proyecto, Departamento, Site, Región, Tipo de Cotización, Motivo de Cotización y Supervisor). `GESTOR` **no se muestra**: lo asigna el servidor en `POST /api/rows/add`. El botón **Solicitar Cotización** guarda con estado `Pdt. Cotización` y la fila permanece en la pestaña 1. El desglose de partidas/PDF no se llena aquí: lo hace la pestaña 2.
- **Varios WO por cotización:** `NUMERO WO` admite **0, 1 o varios** valores mediante chips (Enter para añadir, × para quitar; Backspace vacío quita el último). También se aceptan varios pegados de golpe separados por `,` `;` `|` o salto de línea. Se guardan en una sola cadena separados por coma.
  La cotización es **una sola** y `GET /api/cotizacion/registro?key=<WO>` la devuelve para **cada** WO declarado (helper `_split_wos`), de modo que se refleja en la pestaña Cotización de todos los WO que cubre; esa tabla incluye la columna **WOs DECLARADOS**. En la tabla principal, cada WO es un enlace independiente al detalle FLM/PEXT.
- Las columnas que soportan la pestaña 1 (`DEPARTAMENTO`, `REGION`, `TIPO DE COTIZACION`) y las 9 opciones de estado se crean/fusionan en `migrations.run_migrations()`; esa migración **solo añade** lo que falte y nunca sobrescribe columnas u opciones propias del proyecto.
- `POST /api/cotizacion/accion` es **idempotente**: `generar` sobre una cotización ya `Cotizado` devuelve éxito sin error.

### 7.4 Dataper / Material / Site Name
- Catálogos fuente. Dataper alimenta técnicos; Material alimenta materiales del modal WO; Site Name cruza DIRECCION/LAT/LONG a FLM por `Nombre de Site` (solo ESTADO=ACTIVO).

### 7.5 Pestaña AUTIN (fotos de campo por WO)

Dentro del modal WO hay una pestaña **AUTIN** que agrupa las fotos del WO por estado
(Llegada / Completado / Salida / Suspendido / Otros).

- **Clave:** el **número de WO** (`NucleusData.key_value`, p. ej. `CM-20260814-00000160`).
- **Origen de las fotos:** `AppConfig autin_fotos_dir` (por defecto `C:\Evidencias\FLM - ENTEL`)
  más la carpeta `<raíz>/<WO>`. La raíz local solo se muestra (y se edita con
  `POST /api/autin/config`) si la carpeta existe de verdad en el servidor; en un contenedor
  (Render) esa ruta no está montada, así que la pestaña solo muestra la URL del servidor
  de fotos.
- **Modo de entrega:** si `autin_base_url` (túnel Cloudflare) está configurado, el frontend
  arma las URLs directamente (`fotos_base`) y las pide al túnel; si no, usa
  `/api/autin/foto?wo=..&f=..` como proxy local. `zip_url` descarga todo el WO en ZIP.
- **Endpoints:** `GET /api/autin/fotos` (config + grupos), `GET /api/autin/foto`,
  `GET /api/autin/zip`, `GET|POST /api/autin/config`.
- **Anti-traversal:** los nombres de archivo se validan contra la carpeta del WO (los intentos
  de `..\..\` devuelven 404).
- ⚠️ El túnel de Cloudflare cambia de URL en cada reinicio: hay que re-pegarla en el campo
  "URL del servidor de fotos" (solo zeno). Si no hay túnel, las fotos se sirven por el backend
  (más lento, ~1 img/seg vs ~1.6 s del túnel por imagen, pero sin depender de la URL).

### 7.6 Analytics: dashboards

`/analytics` (y `/dashboard`, que redirige a `/analytics`) tiene **8 vistas** en el selector
superior, en dos grupos: **Métricas clave** (4 vistas nuevas, una por programa) y
**Dashboards** (las 4 vistas originales, disponibles aparte). La vista elegida se recuerda
**por proyecto** (`sessionStorage an-dash:<proyecto>`); sin elección previa cada programa
abre su vista de métricas y el resto de proyectos, **Producción**.

| Grupo | Vista | Cuándo se usa | Qué grafica |
|---|---|---|---|
| Métricas clave | **FLM KPIs** | Solo proyectos WO (`isPext`); por defecto en FLM - ENTEL | KPIs (WO totales, % cerradas, abiertas, suspendidas, críticas, antigüedad prom., VIP) + estado, departamentos, fault level, tipo de tarea, prioridad, evolución mensual y resumen por estado |
| Métricas clave | **Combustible KPIs** | Solo proyecto Combustible; por defecto ahí | KPIs de galones (totales/ingresos/gastos/saldo, % con factura y foto) + galones por zona (suma), evolución, movimientos, top técnicos y resumen con galones |
| Métricas clave | **Cotizaciones KPIs** | Solo proyecto Cotizaciones; por defecto ahí | KPIs (total, monto `SUB TOTAL + FEE`, ticket medio, validadas/rechazadas, con N° WO, peticiones) + estado, cliente, monto por supervisor, evolución y resumen con montos |
| Métricas clave | **Rendición KPIs** | Solo proyecto Rendición; por defecto ahí | KPIs (solicitudes, monto solicitado/pagado, gestionadas, pendientes, rechazadas, con foto) + estado, monto por estado, presupuesto, proyecto, responsable, evolución diaria y resumen |
| Dashboards | **Seguimiento** | Solo proyectos WO con `Operate Phase` (FLM/PEXT) | operación, backlog, prioridad, falla, departamento, tipo avería, sites |
| Dashboards | **Producción** | WO — vista por defecto en proyectos sin dashboards propios | solo filas `Operate Phase = close`, evolución mensual, detalle |
| Dashboards | **Rendición** | Proyecto 11 (también disponible en cualquier proyecto con columna `ESTADO`) | estado, responsable de validación, proyecto, criticidad, evolución mensual y tabla resumen con montos (`Monto total del depósito`) |
| Dashboards | **Cotización** | Proyecto 8 (y cualquiera con `ESTADO COTIZACION`) | estado, cliente, supervisor, gestor, evolución mensual y tabla con `SUB TOTAL + FEE` |

- Cada opción de **Métricas clave** solo se ofrece en su programa (`MK_OK` en
  `templates/analytics.html`); el separador del grupo desaparece si el proyecto no tiene ninguna.
- Las tarjetas KPI (`.an-kpis` / `.an-kpi`) se pintan con `renderKpiRow(...)` y los cálculos
  son defensivos: columnas ausentes → 0 o tarjetas de gráfico ocultas, nunca errores.
- `anSumBar` grafica **sumas** (galones por zona, S/ por estado) con los mismos clics/filtros
  que las barras de conteo; `anLine` acepta `gran: 'day'` (evolución diaria de Rendición).

- Los nombres de columna se resuelven con `keyNamed(...)`, así que si cambias el formulario
  las tarjetas se reacomodan solas; si no hay columnas compatibles aparece un aviso en vez
  de una pantalla vacía.
- **Tarjetas automáticas** (`#an-gen-cards`, solo proyectos no-WO como Dataper, SITE,
  Material, Combustible): se eligen hasta 6 columnas categóricas con datos reales y se
  grafican solas (`gen:<columna>`). Si ninguna califica aparece `an-aviso-sin-tarjetas`.
- Límite de filas: `_ANALYTICS_MAX = 20000` en `blueprints/pages.py`. Si el proyecto tiene
  más, se muestra el aviso ámbar `an-aviso-limite` con el total real.
- Clic en una barra → filtro de gráfico (`anState.chart`); el chip superior lo quita.

**¿Por qué el dashboard puede verse distinto entre entornos/proyectos?** No es un bug:
cada proyecto muestra las vistas que sus columnas permiten y sus propias tarjetas.

- La opción **Seguimiento** solo aparece si `isPext && K_PHASE`
  (`templates/analytics.html`), es decir: nombre de proyecto en `FLM - ENTEL / FLM /
  PEXT / CLARO / FLM-INTEGRATEL` **y** que exista la columna `Operate Phase` en ese
  proyecto. Si falta cualquiera de las dos, se oculta y se abre **FLM KPIs** (o
  **Producción** si el proyecto no es WO).
- Las tarjetas fijas (`Operate Phase`, `Backlog`, `Sites`, `Prioridad`, `Nivel de Falla`,
  `Departamento`, `Tipo de Avería`) y los filtros WO (Tipo WO / Mes / Departamento /
  Causa raíz) viven en `#an-view-seg` y solo se ven en esa vista.
- Proyectos **no-WO** (Dataper, Material, SITE, Combustible…) usan las **tarjetas
  automáticas** `#an-gen-cards` (tipo «112 registros · N valores · clic para filtrar»),
  que se generan a partir de sus propias columnas: es normal que no se parezcan a las de
  FLM.
- La vista elegida se recuerda por proyecto (`sessionStorage an-dash:<proyecto>`) y los
  contadores reflejan los filtros activos (p. ej. `MES 2026-09`), por lo que los totales
  cambian aunque la BD sea la misma.

### 7.7 Avisos legales y cookies

- **3 rutas públicas** (sin login) en `blueprints/pages.py`: `/privacidad`, `/terminos`
  y `/cookies`. Las tres renderizan la misma plantilla `templates/legal.html` con el
  parámetro `seccion`; cada página tiene pestañas para ir a las otras dos.
- **Banner de consentimiento**: `templates/cookie_banner.html`, incluido con
  `{% include %}` en `login.html` y `base.html` (todas las páginas de la app). Se muestra
  solo si no existe `localStorage['nucleus-consent']`; el botón *Entendido* lo guarda y
  lo oculta. El contenido se documenta en `/cookies`.
- **Enlaces legales**: pie del login (`.vl-footer`) y fila `.sidebar-legal` en
  `base.html` (Privacidad · Términos · Cookies).
- **Cookies en uso**: solo la cookie de sesión de Flask (técnica, no requiere
  consentimiento) + `localStorage` (`nucleus-theme`, `nucleus-consent`, orden y
  visibilidad de columnas). **No hay analítica ni píxeles de terceros**: si se añade uno,
  debe pedirse consentimiento previo instalando el mismo aviso.
- Prueba: `Temp\opencode\legal_test.py` (rutas 200 sin sesión, banner visible → acepta →
  no vuelve a aparecer, enlaces en login y sidebar).

---

## 8. PERMISOS POR ROL

Roles: **admin** · **supervisor** (antes editor) · **gestor** · **demo** (solo lectura).

| Acción | admin | supervisor | gestor | demo |
|---|---|---|---|---|
| Ver todos los proyectos | ✔ | solo accesos | solo accesos | ✔ |
| Crear/borrar proyectos, usuarios, permisos | ✔ | ✘ | ✘ | solo GET |
| Configurar columnas/layout | ✔ | ✘ | ✘ | ✘ |
| Dashboard (charts/kpis/filtros) | ✔ | ✔ | ✘ | ✘ |
| Filtros/tablas/reglas/reproceso | ✔ | ✔ | ✘ | solo GET |
| Importar | ✔ | ✔ | ✘ | ✘ |
| Editar/agregar filas | ✔ | ✔ | limitado | ✘ |
| Eliminar filas | ✔ | ✔ | solo proyectos manuales | ✘ |
| Evidencia fotográfica | ✔ | ✔ | ✔ | ✘ |
| Cotizaciones | ✔ | ✔ | ✔ (no bloqueadas) | ✘ |
| Editar campos ya registrados (Combustible) | ✔ | ✘ | ✘ (solo vacíos) | ✘ |

**Restricciones por fila** (`AccesoProyecto.restricciones`): JSON `{COLUMNA: [valores]}`, comparación case-insensitive, aplicada en `apply_data_restrictions` (`app.py:300-335`).

---

## 9. SCRIPTS DE AUTOMATIZACIÓN (`scripts/`)

> ⚠️ La carpeta `scripts/` **ya no existe en este repo** (no forma parte del deploy).
> Estos scripts viven en la máquina que hace la descarga programada:

| Archivo | Función |
|---|---|
| `WOs_descargar_FLM_PEXT.bat` | Orquestador: corre FLM y luego PEXT (cada uno con su sesión Chrome), log en `WOs_run.log` |
| `WOs Report Console FLM.py` | Selenium: descarga WOs FLM (últimos 3 días, CATEGORY O&M CRM) y los importa a Nucleus proyecto FLM (`/switch_project/1`) |
| `WOs Report Console PEXT.py` | Ídem para PEXT (CATEGORY O&M PEXT, `/switch_project/2`) |
| `WOs List FLM.xlsx` / `WOs List PEXT.xlsx` | Artefactos de descarga |

**Programación:** Task Scheduler cada 30 min (para SLA). Con 30 min, el gasto de Neon baja de ~$19 a ~$6-8/mes.

**Credenciales hardcodeadas en los scripts (RIESGO):** teleows `mhuayanab.ofg` / `MAE123_LK34*r`; Nucleus `hvargas` / `123456`. Cambiar si se comparte el repo.

---

## 10. MAPA RÁPIDO DE ENDPOINTS (backend)

**Datos:** `POST /api/rows/update|add|delete|bulk_update` · `GET /api/combustible/por_wo`
**Import:** `POST /api/import/preview|process` · `GET /api/import/manual_template` · `POST /api/master/bulk_import/<tipo>`
**Reglas:** `GET|POST|DELETE /api/master/filtros|tablas|reglas_manuales|manual_columns` · `POST /api/master/reprocess` · `GET /api/master/all_columns` · `GET /api/master/template/<tipo>`
**Config:** `POST /api/columns/layout` · `/api/master/dashboard_charts|kpis|filters` · `/api/config/consolidation` · `/api/config/cotizacion_margen` · `/api/config/init_manual`
**WO:** `GET /api/wo/meta|historial|resolver` · `POST /api/wo/servicios|enviar_aprobacion`
**Sitios/WO:** `GET /api/sites|site/detalle|wos_flm|detalle/opciones`
**AUTIN:** `GET /api/autin/fotos|foto|zip|config` · `POST /api/autin/config`
**Evidencia:** `POST /api/evidencia/subir|eliminar` · `GET /api/evidencia/foto/<pid>/<key>/<nombre>|zip|reporte_config|reporte_xlsx/<pid>/<key>`
**Rendición:** `POST /api/rendicion/accion` · `POST /api/rendicion/subir_foto` · `GET /api/rendicion/foto/<pid>/<key>/<nombre>|avisos` · `POST /api/rendicion/avisos/leer`
**Sincronizaciones:** `GET|POST /api/rendicion/sync` · `POST /api/rendicion/sync_sustentos`
**Cotizaciones:** `GET /api/cotizacion/estado|lista` · `POST /api/cotizacion/desbloquear|eliminar|generar|previsualizar|registro_generar|descargar_registro|descargar_lote`
**Cotizaciones (flujo 4 pestañas):** `POST /api/cotizacion/accion` (`generar`·`enviar`·`conformar_aprobacion`·`revertir`) · `POST /api/cotizacion/subir_correo` · `GET /api/cotizacion/correo/<pid>/<key>/<nombre>`
**Admin:** `/api/admin/proyecto|usuario|permisos|columnas|column_values` · `/api/tecnicos` · `/api/clean`
**Auth:** `/login` `/logout` `/switch_project/<pid>`
**Health:** `/healthz`

---

## 11. GUÍA RÁPIDA "CÓMO..."

| Quiero... | Hago... |
|---|---|
| Cambiar horas SLA de FLM | Editar `FAULT_COLORS` (`index.html:880-890`) y los mapas de fallback en `getSlaThreshold`/`getSlaThresholdData` (`1215-1224`) |
| Agregar un nivel de Fault Level nuevo | 1) `FAULT_COLORS` + los 2 mapas de threshold · 2) fila en `tablas_maestras` si quiero asignar Hrs Respuesta · 3) Reprocesar |
| Agregar columna manual | Configuraciones → Columnas Manuales → añadir con nombre/tipo/opciones |
| Nueva regla de asignación (ej. por Departamento) | Insert en `tablas_maestras` o UI de tablas maestras → Reprocesar |
| Filtrar qué filas se muestran/importan | Insert en `filtros_maestros` (AND entre grupos, OR dentro) |
| Nueva columna en Combustible | 1) agregar en `manual_columns` de proyecto 7 · 2) si es especial, agregar lógica en modal (`aniadirRegistroCombustible`, `abrirCombDetalle`, `guardarCombDetalle`) y validaciones en backend (`/api/rows/update` y `/api/rows/add`) |
| Cambiar margen de cotización | `GET/POST /api/config/cotizacion_margen` (UI: modal WO → margen %) |
| Ver consumo de Neon | Dashboard Neon → Usage → View billing |

---

## 12. NOTAS DE SEGURIDAD Y MANTENIMIENTO

- ⚠️ Credenciales hardcodeadas en `scripts/*.py` y admin default `admin/admin123`.
- ⚠️ `seed_ejemplos.py` está **obsoleto** (importa modelos que ya no existen).
- ⚠️ `.gitignore` NO excluye `nucleus.db` actualmente (la BD se sube al repo).
- La BD de producción es PostgreSQL v18 (Neon Launch, AWS us-east-2). Local es SQLite.
- Migraciones automáticas al arranque: multi-proyecto, cotizaciones sin unique, backfill de historial, admin default.
- **Las migraciones solo añaden, nunca sobrescriben** la configuración del proyecto (`app_config`). Antes, el bloque de Cotizaciones reescribía `manual_columns` con la lista por defecto en cada arranque y borraba las columnas u opciones que el admin hubiera añadido; ahora fusiona lo que falte y conserva lo existente.
- **Fault Level de PEXT** es inmutable (no aparece en columnas manuales): es dato de origen.

---

## 13. LISTA DE VERIFICACIÓN ANTES DEL DEPLOY

1. `requirements.txt` completo — incluye `pillow-heif` (fotos HEIC de iPhone) y `psycopg2-binary`.
2. **Plantilla PEXT:** `REPORTE FOTOGRAFICO _ CORRECTIVOS.xlsx` en la raíz del proyecto.
   Sin ella, `GET /api/evidencia/reporte_config` responde **503** con mensaje limpio y
   `reporte_xlsx` **500** (la UI usa los slots por defecto y sigue funcionando).
3. `DATABASE_URL` apuntando a PostgreSQL; si no existe usa `nucleus.db`.
4. **AUTIN:** `AppConfig autin_fotos_dir` (ruta real de fotos) y `autin_base_url` (túnel) se
   configuran desde la pestaña AUTIN, no en código.
5. Assets locales en `static/vendor/` y `static/js/` — el deploy debe subirlos **tal cual**
   (si faltan, la app queda sin Tabulator/Chart/FontAwesome).
6. Después de un deploy con cachés en cliente: pedir **Ctrl+F5** (los assets llevan `?v=`).

---

## 14. RENDIMIENTO (medido 03/10/2026)

| Métrica | Valor |
|---|---|
| `GET /` FLM - ENTEL (servidor) | ~305 ms · 3.87 MB (≈550 KB con gzip) |
| `GET /` Rendición (servidor) | ~19 ms · 679 KB |
| `GET /analytics` FLM (servidor) | ~155 ms · 3.03 MB |
| Tabla FLM visible (cliente) | ~1.1 s — 1866 filas × 61 columnas |
| Redibujado completo de la tabla | ~378 ms |
| Modal WO | ~38 ms |
| `/api/detalle/opciones` | ~84 ms (caché 120 s; era 471 ms) |
| `/api/sites` | ~230 ms · 2.3 MB (**on demand**, no bloquea la carga) |
| Assets estáticos locales | 0–15 ms (antes 400–500 ms por CDN) |

**Cuellos de botella conocidos:**
- El HTML de FLM pesa 3.9 MB porque `rawData` va **inline** (3.1 MB de JSON: 1866 × 59
  columnas). Es el coste principal del parseo en cliente.
- Las fotos de AUTIN/Evidencia pasan por el túnel de Cloudflare (~1.6 s por imagen).
- Cachés con TTL 120 s (`_opciones_cache` en `wo.py`, `_site_map_cache` en `pages.py`):
  la primera petición de cada 2 minutos es más lenta. Se invalidan en cada commit
  (`app.py:_register_opciones_cache_invalidation`).

---

## 15. PRUEBAS

No hay framework de tests: son scripts sueltos fuera del repo (temp) que usan
`Flask.test_client()` o Selenium headless contra `python app.py` (puerto **5001**):

| Script | Qué cubre | Estado |
|---|---|---|
| `smoke2.py` | 13 endpoints crudos | 13/13 |
| `test_render.py` | render `/` por rol/proyecto | 5/5 |
| `test_coti_rend.py` | flujo Cotizaciones + Rendición | 19/19 |
| `test_analytics.py` / `test_an_cdn.py` | filtros Analytics y modo sin Chart.js | OK |
| `test_dashes.py` | 4 vistas Métricas clave + selector + columna Evidencia | 31/31 |
| `mob_check.py` | maquetación móvil (390 px) | 11/11 |
| `shot_autin.py` | pestaña AUTIN + lightbox | 0 fallos |
| `test_sync_cols.py` | sync de sustentos | **17/19** — ver §16 |

---

## 16. FALLOS CONOCIDOS / DECISIONES PENDIENTES

1. **`test_sync_cols.py` → 2 fallos** sobre columnas `SUSTENTO_*`: el test espera que *no*
   aparezcan en el schema/columnas y que se eliminen solas tras un sync; hoy sí se añaden.
   Hay que decidir el comportamiento (¿visibles en la tabla o solo internas?) y alinear test.
2. **Plantilla PEXT ausente** (ver §13.2): `reporte_config`/`reporte_xlsx` responden 503/500
   con mensaje limpio. Falta colocar el `.xlsx` del cliente.
3. **`/dashboard` redirige a `/analytics`** (decisión intencional: módulo sustituido).
4. `fotos_autin/` en la raíz es una **fixture de pruebas** que ya no usa el código de
   producción (la ruta real es `C:\Evidencias\FLM - ENTEL`); candidata a borrarse.
5. `nucleus.db.bak_biaticos_20260922_121659` (19.5 MB) y `backups/` son copias locales
   que no deben subir al deploy.