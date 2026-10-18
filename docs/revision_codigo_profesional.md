# Revisión de código profesional — Nucleus

Fecha: 17 de octubre de 2026
Alcance revisado: `app.py`, `config.py`, `db.py`, `perezoso.py`, `infrastructure/`,
`services/` y `blueprints/` (con foco en los módulos que se tocaron en esta etapa).
Método: lectura del código **con comprobación directa de cada hallazgo** (se cita
archivo:línea) y la suite de pruebas como respaldo (**368 casos en verde**).
Criterio: los hallazgos se clasifican además por si corregirlos **cambia el
comportamiento observable** (regla del proyecto: no cambiar salidas).

---

## Veredicto

El código es **una base sólida y sorprendentemente disciplinada** para un proyecto
que ha crecido tanto: no hay inyección SQL, no hay secretos en el repositorio, las
contraseñas se guardan con hash y el manejo de errores es centralizado. Las
optimizaciones hechas en esta etapa están medidas y respaldadas por pruebas.

Los riesgos que quedan **no son de rendimiento ni de estilo: son de control de
acceso**. Tres son relevantes antes de que la aplicación maneje más datos y más
usuarios: (1) no hay protección CSRF en la mayoría de endpoints, (2) la importación
masiva no comprueba rol, y (3) la validación de Rendición **permite por defecto**
(fail-open). Ninguno bloquea el commit; los tres deberían abordarse **después** de
la migración, en lotes pequeños y con la suite en verde.

---

## 1. Fortalezas verificadas (lo que está bien y hay que conservar)

| Aspecto | Evidencia |
|---|---|
| **Sin inyección SQL** | Todo el acceso a datos usa el ORM (`filter`, `in_`, `yield_per`). No se encontró SQL construido por concatenación en los módulos revisados. |
| **Contraseñas con hash** | `generate_password_hash` / `check_password_hash` de Werkzeug en `blueprints/admin.py` y `auth.py`; nunca texto plano. |
| **Sin secretos en el código** | Todo se lee de variables de entorno (`config.py:43-71`). La única excepción es la clave de pruebas (`config.py:104`), que está acotada al entorno de test. |
| **Manejo de errores centralizado** | `infrastructure/http.py` responde un mensaje genérico en los 500 y no filtra el detalle interno (a diferencia de otros puntos, ver S5). |
| **CSRF sí resuelto donde se hizo nuevo** | `blueprints/espacios.py:71-72,115` y `blueprints/asistencia.py:36-50` implementan token por sesión y cabecera. El patrón correcto ya existe en el proyecto: el problema es que no se replicó en el resto. |
| **Rendimiento medido, no supuesto** | Cada optimización tiene su equivalencia byte a byte (`scratch/equiv_*.py`) y su prueba. |
| **Carga diferida bien encapsulada** | `perezoso.py`: un único proxy, con la misma interfaz que `pandas`, sin obligar a cambiar el código que lo usa (bajo acoplamiento). |
| **Aislamiento de datos en los scripts** | Los scripts de copia/auditoría abren origen en solo lectura (`mode=ro`, `query_only=ON`) y validan integridad y claves foráneas antes de dar por buena una copia. |

---

## 2. Seguridad — hallazgos (ordenados por gravedad)

> "Cambia comportamiento" indica si corregirlo altera lo que hoy ve el usuario.
> Si cambia, **se documenta y se decide**, no se aplica por sorpresa.

| # | Gravedad | Ubicación | Problema | Recomendación | ¿Cambia comportamiento? |
|---|---|---|---|---|---|
| **S1** | Alta | `app.py` (no hay `CSRFProtect`), `blueprints/imports.py:186`, `wo.py:327`, `rendicion.py:382`, `refacturable.py:253`, `pages.py:433` | Los endpoints que **crean, modifican o borran datos** confían solo en la cookie de sesión. Un sitio externo puede provocar esas acciones con la sesión abierta del usuario. | 1) Ya: `SESSION_COOKIE_SAMESITE='Lax'` (una línea, corta el vector principal). 2) Después: replicar el patrón token+cabecera que ya usan `espacios` y `asistencia`. | Sí (el 2.º paso; el 1.º no) |
| **S2** | Alta | `blueprints/imports.py:186-192` | `/api/import/process` solo bloquea el rol `demo`. **Cualquier usuario autenticado** puede importar, consolidar o borrar filas. | Exigir rol explícito (`zeno`/`suport`/`supervisor`) y comprobar el acceso al proyecto actual. | Sí (algunos usuarios recibirán 403) |
| **S3** | Alta (matiz) | `services/rendicion_validadores.py:18-22,37-38` | Si el administrador no configuró la regla, `puede_validar` devuelve `True`: **cualquiera valida cualquier proyecto**. El comentario indica que es compatibilidad deliberada, pero es un "permitir por defecto". | Denegar por defecto cuando falte configuración, con aviso visible al administrador. | Sí (cambia quién puede validar) |
| **S4** | Media | `blueprints/rendicion.py:999-1021` | `/api/rendicion/sync` no usa `@login_required` y compara la clave con `==` (no es comparación en tiempo constante). | Usar `secrets.compare_digest` y exigir sesión para la vía web. | No (mismo resultado) |
| **S5** | Media | `blueprints/wo.py:191`, `imports.py:183,722-724`, `rendicion.py:673-674` | Devuelven `str(e)` al cliente: expone rutas, SQL y estado interno. | Registrar la excepción (`logger.exception`) y responder un mensaje genérico, como ya hace `infrastructure/http.py`. | Sí (cambia el texto de error) |
| **S6** | Media | `config.py:43-49` | Si falta `SECRET_KEY`, se genera una aleatoria por proceso: con varios workers o reinicios las sesiones se invalidan sin explicación. | En producción, **fallar el arranque** si `SECRET_KEY` no está definida (hoy Genera una y sigue). | Sí (puede impedir un arranque mal configurado) |
| **S7** | Media | `config.py` (no define flags de cookie) | Se usan los valores por defecto de Flask: `HttpOnly=True` (bien), pero `Secure=False` y `SameSite` sin definir. | En `ProductionConfig`: `SESSION_COOKIE_SECURE=True` y `SESSION_COOKIE_SAMESITE='Lax'`. | Sí para http local; correcto en Render (https) |
| **S8** | Baja | `config.py:50` | `MAX_CONTENT_LENGTH = 100 MB` sin límite por endpoint: una subida grande consume memoria en un plan pequeño. | Bajar el límite global y subirlo solo en las rutas de importación. | Sí (subidas más grandes fallarían) |

---

## 3. Principios SOLID — dónde se cumple y dónde se rompe

| Principio | Se cumple en… | Se rompe en… | Propuesta concreta |
|---|---|---|---|
| **S** — Responsabilidad única | `perezoso.py`, `normalizacion.py`, `rendicion_validadores.py (accesos_rendicion)`, `infrastructure/http.py` | `pages.index` (**~470 líneas**, `pages.py:82-552`) hace permisos + carga + cruces + KPIs + layout + serialización. `imports.api_import_process` (**~535 líneas**, `imports.py:186-724`) mezcla parseo, reglas, consolidación, historial y esquema. | Extraer servicios: `permisos_proyecto.py`, `datos_indice.py`, `layout_columnas.py`; y en importación un pipeline `leer → aplicar_reglas → persistir → actualizar_esquema`. |
| **O** — Abierto/cerrado | El registro de blueprints (`app.py`) es fácil de extender | Añadir un módulo obliga a copiar bloques en varias listas y en `pages.py` (el mismo bucle de permisos se repite **5 veces**: `pages.py:121-182`) | Una tabla declarativa de módulos (`MODULOS = {clave: {...}}`) y un único helper `acceso_por_familia(pid, familia, usuario_id)`. |
| **L** — Sustitución de Liskov | `perezoso.pd` sustituye a `pandas` sin que el código que lo usa lo note | — (no se detectaron violaciones relevantes) | — |
| **I** — Segregación de interfaces | Las funciones puras de `normalizacion.py` tienen firmas mínimas | `get_session_info()` devuelve una **tupla posicional** `(uid, rol, pid)` (`utilidades.py:50-55`): un `Unpack` desordenado no avisa | Devolver un `NamedTuple` `SesionInfo(usuario_id, rol, proyecto_id)`. |
| **D** — Inversión de dependencias | `services/` no depende de `blueprints/` | `app.py:79-95`: el hook `_on_commit` importa `blueprints.wo`/`blueprints.pages` "en caliente" para invalidar cachés → el núcleo depende de las pantallas | Un pequeño bus de eventos (`services/eventos.py`) o invalidación por versión/contador. |

---

## 4. Nombres — propuestas (renombrado mecánico, sin cambiar comportamiento)

| Actual | Propuesto | Dónde | Motivo |
|---|---|---|---|
| `_tec_map` | `tecnicos_por_contrata` | `wo.py:108-157` | Dice **qué contiene** el diccionario y con qué clave |
| `_add_tec` | `registrar_tecnico` | `wo.py:110` | Verbo + objeto, en lugar de abreviatura |
| `_cg`, `_rm`, `_p`, `_r`, `_d`, `_g`, `_s`, `_v` | `costo_galon`, `rendimiento`, `precio`, `registro`, `datos`, `galones`, `sustento`, `valor` | `wo.py:464-471`, `imports.py:456-648` | Hoy hay que leer el bloque entero para saber qué es cada variable |
| `get_session_info()` → `(uid, rol, pid)` | `sesion_actual()` → `SesionInfo(usuario_id, rol, proyecto_id)` | `utilidades.py:50-55` | Elimina el error clásico de intercambiar el orden al desempaquetar |
| `_bajar_foto_form` | `descargar_foto_formulario` | `rendicion.py:277` | "bajar" es ambiguo (¿bajar o descargar?); el nombre completo se lee igual de rápido |
| `_folder` | `carpeta_evidencia` | `rendicion.py:272` | Igual |
| `flag`, `data`, `info` (genéricos) | nombre del contenido real | varios | Un nombre genérico obliga a leer el contexto |

**Criterio aplicado:** nombre completo cuando aporta; se conservan los nombres ya
correctos (`puede_rendicion`, `accesos_rendicion`, `inject_kpis`, `normalizar`).

---

## 5. Plan de mejora priorizado (por lotes, cada uno con la suite en verde)

| Prioridad | Lote | Contenido | Riesgo | Cómo se verifica |
|---|---|---|---|---|
| **P0** | Blindaje mínimo | S7 (SameSite/Secure), S4 (`compare_digest`), S6 (exigir `SECRET_KEY`) | Bajo | `pytest tests` |
| **P1** | Control de acceso | S2 (rol en importación), S3 (denegar por defecto en validadores) | Medio: cambia quién puede hacer qué | `pytest tests` + revisión con negocio |
| **P2** | Errores y CSRF | S5 (mensajes genéricos), S1 paso 2 (token por módulo) | Medio: cambia textos y requiere tocar el JS de cada módulo | `pytest tests` + prueba de navegador |
| **P3** | Refactor por SRP | Extraer servicios de `pages.index` e `imports.api_import_process` | Medio-alto en volumen, bajo si es mecánico | Equivalencia byte a byte (`scratch/equiv_*.py`) |
| **P4** | Nombres | Tabla §4 | Bajo | `pytest tests` (los nombres no se prueban, pero el comportamiento sí) |

**Orden recomendado: P0 ahora (3 cambios diminutos) → commit → migración → P1, P2, P3, P4.**

---

## 6. Por qué NO refactorizo ahora (decisión profesional)

El proyecto está en un momento delicado: se va a **hacer commit y a migrar datos de
producción**. Mezclar un refactor estructural con la migración significa que, si algo
sale mal, no se sabrá si fue el refactor o la carga de datos.

**Recomendación:** congelar el código, hacer el commit, ejecutar la migración y
**después** aplicar los lotes P0→P4 con la suite como red. Es la práctica estándar
(separar "cambio de código" de "cambio de datos") y protege lo ya verificado.

Este documento deja los parches de P0 listos para aplicar cuando lo decidas (§7).

---

## 7. Parches P0 listos para aplicar

### S7 — Cookies de sesión (no cambia Funcionamiento normal en https)
`config.py`, en `class Config`:
```python
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
```
`config.py`, en `class ProductionConfig`:
```python
SESSION_COOKIE_SECURE = True   # Render sirve por https
```

### S4 — Comparación en tiempo constante (`blueprints/rendicion.py:1011`)
```python
import secrets  # arriba del módulo
...
    key_valida = bool(cfg and cfg.valor and secrets.compare_digest(str(key), str(cfg.valor)))
```
(mismo resultado que hoy, sin `TypeError` si `key` llegara como número).

### S6 — No arrancar mal configurado (`config.py:43-49`)
```python
    _sk = os.environ.get('SECRET_KEY')
    if not _sk:
        if os.environ.get('FLASK_ENV', '').lower() == 'production' or os.environ.get('RENDER'):
            raise RuntimeError('Falta SECRET_KEY: defínela en el entorno antes de arrancar.')
        _sk = secrets.token_urlsafe(64)   # solo desarrollo/pruebas
    SECRET_KEY = _sk
```

**Verificación de cualquier parche P0:** `.\scratch\verify-rendicion-env\Scripts\python.exe -m pytest tests -p no:cacheprovider` → debe seguir en **368 passed**.
