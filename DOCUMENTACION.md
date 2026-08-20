# DOCUMENTACIÓN TÉCNICA — NUCLEUS

> Referencia completa del sistema para modificar/agregar criterios, reglas y funcionalidad.
> Última actualización: 20/08/2026.

---

## 1. ARQUITECTURA GENERAL

| Componente | Tecnología | Dónde |
|---|---|---|
| Backend | Flask + Flask-SQLAlchemy | `app.py` (3888 líneas) |
| Frontend | Jinja2 + Tabulator (JS) | `templates/index.html` (5198 líneas), `dashboard.html`, etc. |
| BD | PostgreSQL en producción (Render), SQLite local | env `DATABASE_URL` o `nucleus.db` |
| Despliegue | Render (`https://nucleus-j2cv.onrender.com/`) | Procfile: `web: gunicorn app:app`, `runtime.txt: python-3.11.8` |
| Fotos/evidencia | Local `static/evidencia/` o Backblaze B2 (opcional) | envs `B2_*` |
| Importación automática | Scripts Selenium (Chrome) en `scripts/` | Programador de tareas Windows |

**Stack datos:** `pandas`, `openpyxl`, `Pillow`, `reportlab`, `boto3`, `psycopg2-binary`.

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

### 7.4 Dataper / Material / Site Name
- Catálogos fuente. Dataper alimenta técnicos; Material alimenta materiales del modal WO; Site Name cruza DIRECCION/LAT/LONG a FLM por `Nombre de Site` (solo ESTADO=ACTIVO).

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
**WO:** `GET /api/wo/meta|historial` · `POST /api/wo/servicios`
**Evidencia:** `POST /api/evidencia/subir|eliminar` · `GET /api/evidencia/foto/<pid>/<key>/<nombre>`
**Cotizaciones:** `GET /api/cotizacion/estado|lista` · `POST /api/cotizacion/desbloquear|eliminar|generar`
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
- **Fault Level de PEXT** es inmutable (no aparece en columnas manuales): es dato de origen.