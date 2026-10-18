# Plan por pasos: migrar Anton + Modus → Nucleus (Render)

Fecha: 17 de octubre de 2026 · Estado: **plan, nada ejecutado**

---

## 0. Mapa de las tres instalaciones

| | Anton | Modus | **Nucleus (destino)** |
|---|---|---|---|
| Hosting | Render | Render | Render |
| Base de datos | **Supabase** (Postgres) | **Neon** (Postgres) | **Neon** (Postgres) |
| Adjuntos | **B2** (bucket propio) | **B2** (bucket propio) | **B2** (bucket propio) |
| Rol | Origen | Origen | Destino |

Los tres son Postgres: **no hay que exportar a Excel ni pasar por SQLite** para
leerlos. Se lee directo, con una conexión **de solo lectura**.

---

## 1. Reglas que no se rompen

1. **Nunca escribir en Anton ni en Modus.** Solo lectura (rol de solo lectura).
2. Todo se **ensaya antes** sobre una copia de producción. Si un paso no se ensayó, no se ejecuta.
3. Las credenciales **no van** al chat, al código ni a Git.
4. Los adjuntos (B2) son parte de la migración: una fila sin su foto está a medias.
5. La reversión siempre es **completa** (volver al respaldo), nunca "arreglar a mano".

---

## 2. Antes de empezar: accesos y decisiones

**Accesos a conseguir (privados):**
- [ ] Alta de un **rol de solo lectura** en Supabase (Anton) y su cadena de conexión.
- [ ] Cadena de conexión de Neon (Modus), preferiblemente **de una rama** (copia), no de la principal.
- [ ] Cadena de conexión de **Neon de producción** (Nucleus) y acceso al panel de Neon (para ramas).
- [ ] Credenciales de **B2 de solo lectura** de Anton y de Modus, y de **escritura** de Nucleus.
- [ ] Confirmar que **`SECRET_KEY`** está definida en Render (Nucleus).

**Decisiones (D1–D5):**
| # | Decisión | Recomendación |
|---|---|---|
| D1 | ¿Anton y Modus se apagan al migrar? | Dejarlos en **solo lectura** una temporada |
| D2 | ¿Los registros se fusionan o se conserva su procedencia? | **Conservar procedencia** (ya está implementado) |
| D3 | ¿Los usuarios de Anton/Modus entran a Nucleus? | **Solo datos**; las cuentas se piden aparte |
| D4 | Ventana de corte | Fuera de horario, con aviso a los usuarios |
| D5 | ¿Los adjuntos de B2 se copian o se dejan en sus buckets? | **Copiar** al bucket de Nucleus (ver Etapa 5) |

---

## 3. Pasos

### Etapa 1 — Respaldo de producción (Nucleus)
1. En **Neon**, crear una **rama** de producción = fotografía del momento. Anotar su nombre.
2. Copia local adicional con la herramienta existente (lee cualquier `DATABASE_URL`):
   ```powershell
   $env:DATABASE_URL = '<neon-produccion>'
   python scripts/copia_datos_local.py --destino backups/nucleus_produccion_previa.db
   ```
3. Auditar la copia:
   ```powershell
   python scripts/auditar_integridad.py --db backups/nucleus_produccion_previa.db --salida backups/auditoria_previa.json --reporte docs/verificacion/auditoria_previa.md
   ```
✅ **Control:** integridad OK, 0 claves foráneas rotas, conteos cuadran. Si no, parar.

### Etapa 2 — Leer Anton y Modus (solo lectura, sin tocarlos)
4. **Anton (Supabase):** usar una conexión que **no** sea el *pooler de transacciones*
   (puerto **6543**). Hace falta una sesión real: **puerto 5432** (directo o session pooler).
   ```powershell
   $env:DATABASE_URL = '<supabase-anton>'   # debe terminar en ?sslmode=require
   python scripts/copia_datos_local.py --destino backups/anton_del_corte.db
   ```
   > ⚠️ Si la cadena trae `channel_binding=require` **junto con** `sslmode`, quítalo: hay un
   > fallo conocido del normalizador de URLs (documentado) que la rompe. Deja solo `sslmode=require`.
5. **Modus (Neon):** leer **de una rama**, no de la principal (riesgo cero sobre producción):
   ```powershell
   $env:DATABASE_URL = '<neon-modus-rama>'
   python scripts/copia_datos_local.py --destino backups/modus_del_corte.db
   ```
6. Auditar las dos copias (integridad, claves foráneas, conteos por tabla).
✅ **Control:** ambas copias auditadas y con manifiesto. Ninguna escritura en origen.

### Etapa 3 — Staging con procedencia
7. Reunir las dos fuentes sin fusionar identificadores:
   ```powershell
   python scripts/preparar_absorcion.py --anton backups/anton_del_corte.db --modus backups/modus_del_corte.db --destino backups/staging_del_corte.db
   ```
✅ **Control:** el manifiesto del staging cuadra y las referencias están bien.

### Etapa 4 — Ensayo general en una rama de Neon (nunca en producción)
8. En **Neon**, crear una rama que sea copia de producción.
9. **Falta construir el importador** (ver §4). Ensayo sin escribir:
   ```powershell
   python scripts/importar_a_destino.py --origen backups/staging_del_corte.db --destino-url '<rama-neon>'
   ```
10. Revisar el informe. Si está bien, aplicar:
    ```powershell
    python scripts/importar_a_destino.py --origen backups/staging_del_corte.db --destino-url '<rama-neon>' --aplicar
    ```
11. Auditar la rama y **abrir la app contra la rama** para revisar a mano:
    ```powershell
    python scripts/servidor_pruebas.py --backup backups/<resultado_del_ensayo>.db --port 5059
    ```
12. Repetir la Etapa 4 **hasta que salga perfecta dos veces seguidas**.
    La segunda vez el importador debe informar **0 filas nuevas** (prueba de que repetir es inofensivo).
✅ **Control:** conteos por tabla cuadran, 0 claves foráneas rotas, muestras de negocio OK.

### Etapa 5 — Adjuntos (B2) ← no olvidar
13. Averiguar **cómo guarda cada sistema la referencia** del adjunto: ¿clave relativa o URL completa?
    (Esto decide si basta copiar objetos o hay que reescribir rutas.)
14. Contar y pesar los objetos de B2 de Anton y de Modus (cuántos, cuántos GB).
15. Ensayar la copia de objetos de un bucket de origen a un bucket **de prueba**, conservando la clave.
16. Copiar los objetos al **bucket de Nucleus**.
17. Verificar que las filas importadas **encuentran** sus adjuntos (abrir una muestra de registros con foto).
✅ **Control:** ninguna fila queda con la foto rota.

### Etapa 6 — Conciliación de negocio
18. Plan de recuperación de WO/QR faltantes (no escribe nada):
    ```powershell
    python scripts/conciliar_referencias.py --db <resultado> --fuente backups/anton_del_corte.db --fuente backups/modus_del_corte.db --salida backups/plan_conciliacion.json
    ```
19. Revisar el informe con los responsables. Aplicar solo lo aprobado:
    ```powershell
    python scripts/conciliar_referencias.py --db <resultado> --fuente ... --salida backups/plan_conciliacion.json --aplicar
    ```
20. Dejar por escrito quién revisa cada pendiente (sin WO, sin proyecto, sin clasificar).
✅ **Control:** cada pendiente tiene responsable y decisión.

### Etapa 7 — Corte en producción
21. Avisar y **bloquear la escritura** (usuarios fuera o aviso en pantalla).
22. Respaldo **fresco** justo antes (rama de Neon; anotar nombre).
23. Volver a leer Anton y Modus del día del corte (pasos 4–5) y rehacer el staging (pasos 7).
24. Importar a **producción** con `--aplicar`, revisando el informe.
25. Verificar conteos, claves foráneas y una muestra por módulo. Reabrir el acceso.
✅ **Control:** los números coinciden con lo ensayado en la Etapa 4.

### Etapa 8 — Después del corte
26. Vigilar logs y errores las primeras horas; comprobar el arranque en frío.
27. Poner **Anton y Modus en solo lectura** (no borrarlos todavía).
28. Guardar el manifiesto de la migración en `docs/verificacion/`.
29. Mantener disponible la reversión unos días.

### Etapa 9 — Reversión (si algo falla)
30. Restaurar la rama de Neon del paso 22 (reversión **completa**), o volver la rama elegida.
31. Reabrir el acceso y avisar. Repetir el ensayo antes de reintentar.

---

## 4. Lo que falta construir (único software pendiente)

**El importador a Postgres.** Las herramientas actuales leen cualquier base, pero
**ninguna escribe** en Postgres. Debe:

1. **Ensayar por defecto:** sin `--aplicar` no escribe nada, solo informa.
2. Insertar **en orden de dependencias** (claves foráneas).
3. Ser **idempotente:** si la fila ya existe, omitirla (repetir no daña) → y avisar al final.
4. **Reajustar las secuencias de Postgres** (`setval`) en cada tabla. Sin esto, las altas nuevas
   fallarán con "duplicate key" *(riesgo típico y grave)*.
5. **Política de colisiones**: `omitir` (por defecto) o `abortar`; nunca sobrescribir en silencio.
6. Dejar **manifiesto + verificación** (conteos por tabla, claves foráneas, huella).

---

## 5. Checklist final

```
PREVIO
[ ] Rol de solo lectura en Supabase (Anton)
[ ] Conexión de rama en Neon (Modus)
[ ] Acceso a ramas en Neon (Nucleus) y a B2 de los tres
[ ] SECRET_KEY en Render
[ ] Decisiones D1–D5 tomadas y usuarios avisados

ENSAYO (repetido hasta salir perfecto 2 veces)
[ ] Respaldo de producción + auditoría OK
[ ] Copias de Anton y Modus auditadas (0 escrituras en origen)
[ ] Staging con procedencia OK
[ ] Importador ensayado en una rama de Neon
[ ] Conteos por tabla y claves foráneas OK
[ ] Segunda ejecución: 0 filas nuevas
[ ] Adjuntos B2 copiados y comprobados
[ ] App revisada a mano contra la rama

CORTE
[ ] Escritura bloqueada
[ ] Respaldo fresco (rama de Neon) anotado
[ ] Delta final importado y verificado
[ ] Acceso reabierto

DESPUÉS
[ ] Anton y Modus en solo lectura
[ ] Manifiesto guardado
[ ] Reversión disponible unos días
```
