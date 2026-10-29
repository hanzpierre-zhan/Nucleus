# Auditoría de cotizaciones — 29/10/2026

Consultas de solo lectura mediante el conector Neon al proyecto Nucleus (`little-waterfall-75236198`). No se modificaron datos, configuración ni despliegues remotos.

## Resultado

| Cotización | Rama anterior | Producción actual |
|---|---|---|
| CL-2026-10-000524 | LP3206_VILLA_RICA; alquiler; En Aprobación; 441.00 | Ausente |
| CL-2026-10-000526 | LJ8879 REPETIDOR_SAN_LORENZO_AUTIKI; alquiler; En Aprobación; 378.00 | Ausente |
| CL-2026-10-000528 | AC4471_VILLA VIRGEN; servicio de custodio; En Aprobación; 100.80 | Número ocupado por otro registro: LP3206_VILLA_RICA; acarreo; Pdt. Cotización; fecha 29/10/2026 08:25 |
| CL-2026-10-000529 | LJ1101 Nat Puerto anapati; servicio; Pdt. Cotización | Ausente |

Las búsquedas se realizaron tanto por key_value como por el contenido JSON, en todos los proyectos de ambas ramas. Los cuatro originales están en nucleus_data del proyecto 8, Cotizaciones. No se encontraron filas relacionadas en cotizaciones ni nucleus_history con esas claves. La rama anterior conserva además cuatro entradas de historial_cambios por cada una de las claves 524, 526 y 528; producción no conserva esas entradas.

## Restauración observada

La rama actual `production` (`br-spring-tree-axi7369a`) se creó el 28/10/2026 a las 18:16:55, hora de Perú (23:16:55 UTC). Neon registra `restore_status=finalized`, `restored_from=snap-old-morning-ax60miww`, `parent_timestamp=2026-10-28T18:59:45Z` (13:59:45 Perú) y `restored_as=br-divine-surf-ax353lz7`.

La rama anterior `br-divine-surf-ax353lz7`, hoy llamada `auditoria-rendicion-antes-borrado-20261028 (1)`, conserva los cuatro originales. El endpoint histórico de producción `ep-old-queen-ax41x5bx` está asociado ahora a la nueva rama production. La rama anterior dispone del endpoint `ep-shiny-flower-axdw1ryt`.

Estos hechos son consistentes con un retroceso de producción a un estado anterior a las solicitudes reclamadas. El código de altas calcula el siguiente correlativo con AppConfig y los registros presentes en la misma base (blueprints/rows.py), de modo que una restauración también puede permitir reutilizar numeración. No hay evidencia suficiente para atribuir quién ejecutó la restauración.

## Relación con el aviso

El texto literal `Record not found` aparece en `/api/rows/update`, que busca por proyecto de sesión y clave. La ausencia de tres claves es compatible con ese aviso; la captura no contiene la solicitud HTTP, por lo que no acredita por sí sola qué clave/proyecto produjo el error. La colisión de la 528 requiere conciliación explícita.

## Render y límites

La documentación local identifica el servicio Nucleus como `srv-d9t0eiqjobas7388nffg`. No se verificaron en vivo su DATABASE_URL, despliegues ni logs: el acceso al Chrome abierto fue rechazado por la herramienta con `Computer Use was not approved to use Google Chrome`. No se debe presentar la conexión actual de Render como comprobada.

## Evidencia y recuperación pendiente

Respuestas completas de las consultas de los cuatro registros guardadas en `backups/auditoria-cotizaciones-20261029/anterior.json` y `produccion.json` (carpeta local ignorada por Git). Las habilidades neon y neon-postgres ya estaban instaladas y accesibles; no fue necesaria una instalación adicional para consultar el proyecto.

Una recuperación debe conservar ambos registros que comparten el número 528 y conciliar su numeración y referencias antes de escribir. También debe revisar los códigos internos: COB-2026-10-00177 identifica tanto la 524 anterior como la 528 actual. Restaurar toda la base descartaría cambios posteriores; esta auditoría no ejecutó una restauración ni reinserciones.

## Recuperación ejecutada y verificada — 29/10/2026

Con autorización explícita del usuario, se recuperaron las cuatro solicitudes en la rama production dentro de una transacción. Una consulta posterior confirmó la persistencia de las cuatro altas y la presencia de la 528 actual por separado.

| Número recuperado | ID nuevo | Orden nueva | Código interno recuperado |
|---|---|---|---|
| CL-2026-10-000524 | 73491 | 453 | COB-2026-10-00177.1 |
| CL-2026-10-000526 | 73492 | 454 | COB-2026-10-00178.1 |
| CL-2026-10-000528.1 | 73493 | 455 | COB-2026-10-00180.1 |
| CL-2026-10-000529 | 73494 | 456 | COB-2026-10-00181.1 |

Se conservaron importes, conceptos, ítems, responsables, fechas y estados originales. La comprobación comparó cada campo con la fuente, exceptuando los tres identificadores remapeados. El objeto interno `_RECUPERACION` conserva rama e ID de origen, número, orden y código originales, fecha y motivo.

Se recuperaron 12 entradas de historial originales con sus fechas completas y claves remapeadas, y se añadieron cuatro trazas de recuperación. Las dos referencias de liquidacion_numero se remapearon a los IDs nuevos: 598 anterior → 600 actual (524); 600 anterior → 601 actual (526). El 598 actual ya pertenecía a otra cotización y no se alteró. No había detalles refacturables, clasificaciones, correos ni cotizaciones físicas asociados que trasladar; tampoco otros registros dinámicos con referencias a las claves originales.

El correlativo de nuevas cotizaciones quedó como mínimo en 530. Las nuevas órdenes siguen el máximo vigente, sin duplicarlo. La transacción comprobó que las cuatro altas fueran el único cambio en nucleus_data, comparando todas las filas previamente existentes antes de confirmar. No se efectuó ningún despliegue ni cambio de configuración en Render.

Fuente, respaldo anterior, SQL ejecutado y resultado verificado están en `backups/recuperacion-cotizaciones-20261029/`. La numeración con punto se usa como texto en los lectores de cotizaciones; no se modificó el formato normal del generador de nuevas solicitudes.
