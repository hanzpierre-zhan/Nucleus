# Migración de Modus a Nucleus — 18/10/2026

Carga confirmada en la base PostgreSQL de Nucleus. Una conexión independiente cotejó las tablas modificadas contra el plan final completo; todas coincidieron. No se ejecutó despliegue de código ni se eliminó el origen.

## Datos incorporados

| Datos de Modus | Tratamiento |
|---|---|
| 2.005 órdenes de FLM - INTEGRATEL | Agregadas |
| 437 materiales | Agregados con su proyecto original |
| 16 cotizaciones | Agregadas |
| 37 técnicos | Se conservaron los actuales de Nucleus, según indicación del usuario |
| 10.157 movimientos de historial | Agregados con usuario/proyecto remapeado y etiqueta de origen |
| 5 cuentas de origen | 4 vinculadas sin sustituir datos, contraseñas ni roles de Nucleus; 1 incorporada |
| Accesos de origen | 24 coincidencias conservadas y 25 asignaciones incorporadas |
| 2 detalles refacturables y 2 números de liquidación | Incorporados con sus referencias remapeadas |
| 11 notificaciones | Incorporadas; IDs de usuario de lectura remapeados |
| 34 adjuntos, 8.843.483 bytes | Transferidos a B2 de Nucleus manteniendo sus claves |

Se ampliaron los campos de un esquema visual para mostrar los datos importados. No se sustituyeron diseños, secuencias de negocio ni configuraciones de integración existentes. Las rutas internas de fotos y correos se adaptaron a los IDs de Nucleus.

## Resultado

Nucleus conserva 13.452 registros operativos y 18 cuentas al finalizar esta carga. Los datos de Modus tienen 12.770 entradas de procedencia, incluyendo coincidencias conservadas; esto no significa 12.770 filas operativas nuevas. Personal sigue con 163 filas. FLM - INTEGRATEL queda con 2.006 registros (1 existente + 2.005 nuevos), Material con 469 y Cotizaciones con 369.

Los cambios recibidos en producción durante la preparación se preservaron: el plan definitivo se generó a partir de un respaldo inmediato bajo una transacción con bloqueo de escrituras. Los dos intentos anteriores abortaron al detectar cambios del destino y no escribieron datos.

No se introdujeron referencias rotas. Ya existía una reserva de `liquidacion_numero` sin registro operativo actual antes de esta migración; se conservó sin inventar un enlace. Las dos reservas incorporadas de Modus apuntan a sus registros correctos. Las referencias textuales ambiguas que ya traía Modus se conservan; no se fabricaron coincidencias.

## Verificación y respaldo

- Cinco pruebas del importador y del plan de carga aprobaron: conservación de Personal, remapeo de adjuntos, repetición sin duplicados, reversión por conflicto y rechazo de cambios posteriores al respaldo.
- Ensayo con los datos reales en SQLite y restauración nativa PostgreSQL comprobados antes de la carga.
- Carga final cotejada por hashes de tablas en una conexión independiente.
- Respaldos nativos de Modus y Nucleus verificados con `pg_restore --list`; se restauró el de Nucleus para el ensayo.
- Respaldos de los objetos actuales: 34 de Modus y 3.563 de Nucleus. No se incluyeron versiones históricas borradas.
- Secretos, diferencias de Personal, planes con datos privados y respaldos están en `backups/migracion-modus-20261018/`, excluido de Git. Las herramientas temporales de PostgreSQL también se excluyeron de Git y su servidor de ensayo quedó detenido.

## Incidencia temporal de B2 — resuelta

Durante el respaldo y la verificación B2 respondió: `Cannot download file, download bandwidth or transaction (Class B) cap exceeded`. Los 34 objetos transferidos se cotejaron por tamaño y ETag MD5 remoto; los archivos de origen tienen SHA-256 local verificado y los nuevos envíos se firmaron con SHA-256 y Content-MD5. No se pudo completar una nueva descarga de todos los archivos destino por ese límite. La visualización de adjuntos puede seguir bloqueada hasta que se restablezca o ajuste el límite de B2. No se cambiaron límites de consumo ni ajustes de facturación.

## Recuperación

Conservar los respaldos nativos y el respaldo inmediato `nucleus_inmediato_pre_carga.db`, además de `plan_final_privado.json` y `carga_produccion_verificada.json`. El plan identifica todas las filas agregadas y el cambio de esquema. Si se solicita revertir, preparar una reversión selectiva que compruebe cambios posteriores y respete las dependencias; una restauración global del respaldo anterior puede perder trabajo nuevo. No ejecutar de nuevo los ayudantes de `scratch/` sin revisar sus archivos y su estado.

Anton queda pendiente y no se modificó.


## Verificación final de descargas

Tras restablecerse la cuota, se descargaron íntegramente los 34 adjuntos desde B2 de Nucleus (8.843.483 bytes). Todos coinciden por tamaño y SHA-256 con el respaldo de Modus. El bloqueo temporal de descargas quedó resuelto; no se ampliaron límites ni se modificó facturación. El detalle privado está en `verificacion_b2_descarga_completa.json`.
