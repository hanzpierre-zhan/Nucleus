# Verificación previa al commit — 17 de octubre de 2026

Objetivo: dejar constancia de **qué está comprobado hoy** para poder hacer el commit
con seguridad. Los números son reales, medidos en este equipo (Windows, Python 3.12
local; producción es 3.11).

---

## 1. Resultado de la validación

| Comprobación | Resultado | Cómo se reproduce |
|---|---|---|
| Suite completa | **368 casos en verde** (ejecutada 3 veces) | `.\scratch\verify-rendicion-env\Scripts\python.exe -m pytest tests -p no:cacheprovider` |
| Arranque en frío | **1.726 ms** | `.\scratch\verify-rendicion-env\Scripts\python.exe scratch\chequeo_arranque.py` |
| Librerías pesadas al arrancar | `pandas`, `numpy`, `openpyxl`, `boto3`, `reportlab`, `docx`: **ninguna** | igual que arriba |
| `pytest` sin argumentos | recoge **solo** `tests/` (0 de `scratch/`) | `python -m pytest --collect-only -q` |
| Equivalencia byte a byte de las salidas optimizadas | verificada en su momento con `scratch/equiv_*.py` | — |

### Qué cubre la suite
- Unitarios de funciones puras (normalización, fechas con corpus de 759 casos, montos, URLs, compresión, marcador).
- Barrido de rutas: ninguna ruta GET sin parámetros responde con error 5xx.
- Presupuesto de consultas SQL por endpoint (guarda contra los N+1).
- *Golden* de formato: plantilla Excel (bytes idénticos entre llamadas) y contrato de datos de `/`.
- Degradación: fallo de red y falta de configuración externa responden con aviso, no rompen.
- Humo con navegador real sobre `/`: carga sin errores de JavaScript y la tabla se construye.

---

## 2. Qué debe entrar en el commit

**Sí incluir** (código y documentación del trabajo):
- `app.py`, `config.py`, `db.py`, `perezoso.py`, `infrastructure/`, `services/`, `blueprints/` (optimizaciones).
- `tests/` (todos los `test_*.py` nuevos y existentes), `pytest.ini`, `requirements-dev.txt`.
- `.github/workflows/tests.yml`.
- `docs/` (`estrategia_testing.md`, `revision_codigo_profesional.md`, `migracion_anton_modus_render.md`, `verificacion/`).
- `.gitignore`.

**No incluir** (datos privados o artefactos):
- `backups/` (ya ignorado): contiene datos personales y credenciales.
- `*.db`, `nucleus.db`, `instance/`.
- **`scratch/verify-rendicion-env/`** (entorno virtual con el navegador). Se acaba de
  añadir a `.gitignore`; si ya estaba añadido por error, quítalo del índice con
  `git rm -r --cached scratch/verify-rendicion-env`.
- Cualquier archivo con `DATABASE_URL`, contraseñas, tokens o `B2_*`/`OD_*`.

### Mensaje de commit sugerido
```
Rendimiento, pruebas y plan de migración

- Optimizaciones medidas (arranque en frío, SQL, memoria) con salida idéntica
- Suite de pruebas de 309 a 368 casos (unitarios, rutas, SQL, golden, degradación, navegador)
- Estrategia de testing y revisión de código profesional
- Plan de migración de Anton y Modus a Nucleus en Render
```

---

## 3. Pendientes que NO bloquean el commit

| Pendiente | Por qué no bloquea |
|---|---|
| Parches P0 de seguridad (revisión §7) | Requieren re-verificar; se aplican por lotes y con la suite en verde |
| Hallazgos que cambian el comportamiento (CSRF general, rol en importación, validadores fail-open) | Necesitan decisión de negocio (cambia quién puede hacer qué) |
| Importador a Postgres (§2.1 del plan de migración) | Es un script nuevo, no un cambio de la app |
| Copias actuales de Anton y Modus | Depende de acceso externo |
| Fase 7 del CI (activar en cada push) | Hoy es de disparo manual a propósito |

---

## 4. Riesgos conocidos y documentados (NO corregidos)

Se dejan tal cual para no cambiar el resultado; están explicados en
`docs/estrategia_testing.md` §9 y `docs/revision_codigo_profesional.md`:

- `_normalizar_db_url` genera una URL malformada en un caso concreto de orden de parámetros.
- `/api/master/template/<tipo>` responde 500 (falta `xlsxwriter`).
- `/api/catalogos/autocompletar` recorre 5.583 filas y siempre devuelve `sites: []`.
- `fecha('2026/08/14') → None`; `primer_texto(0, 5) → '5'`; `_monto('1e5')` acepta notación científica.
- `/api/evidencia/reporte_config` responde 503 a propósito cuando falta configuración.

---

## 5. Conclusión

**Todo lo que se iba a validar está verde.** El commit es seguro en cuanto a que
ninguna prueba falla y ninguna salida observable cambió. El único cuidado es no
subir `backups/` ni el entorno virtual (ver §2).
