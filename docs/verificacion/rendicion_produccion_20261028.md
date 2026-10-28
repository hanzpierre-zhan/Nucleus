# Incidente y recuperación de Rendición — 28/10/2026

La conclusión inicial de las 17:57 fue insuficiente: la ausencia de duplicados e historial en la tabla actual NO descartaba una eliminación seguida de reimportación. Esa interpretación queda corregida por la evidencia temporal descrita abajo.

## Causa confirmada

/api/rows/delete eliminaba físicamente filas de Rendición. La sincronización del CSV original volvía a crearlas como pendientes, perdiendo el estado y el historial interno del registro eliminado.

## Verificación temporal

Se creó una instantánea de production a las 14:00 America/Lima (19:00 UTC) y se abrió en una rama independiente de auditoría. Producción no se restauró globalmente ni se cambió de rama.

- Proyecto: little-waterfall-75236198; producción: br-divine-surf-ax353lz7; base: neondb; Rendicion proyecto_id 16.
- Instantánea: snap-old-morning-ax60miww.
- Rama de auditoría: br-spring-tree-axi7369a.
- En la instantánea había 249 casos de la pestaña Anulado, incluidos rechazos definitivos.
- 247 coincidían por clave en producción y tenían IDs nuevos, demostrando eliminación y reinserción.
- 242 estaban pendientes, 3 validados y 2 depositados tras reimportarse.
- 2 casos de la instantánea no estaban reimportados (claves 29/9/2026 15:41:45 y 1); no se inventaron ni reinsertaron registros ausentes.

## Recuperación aplicada y verificada

Se devolvieron los 247 casos identificados a ESTADO ANULADO, conservando el JSON vigente, los importes, códigos de depósito y el historial posterior, y recuperando motivos/metadatos del respaldo original. Se agregó la marca _RECUPERACION_ANULADO y un evento de recuperación.

Antes de cada actualización se guardó, en la misma transacción, un respaldo con el JSON previo y el parche en app_config:
- recuperacion_anulados_20261028_incidente_1: 242 filas.
- recuperacion_anulados_20261028_incidente_2: 5 filas.

Cada actualización exigió coincidencia de ID, clave y estado esperado, bloqueó las filas y comprobó la cantidad prevista antes de escribir.

Comprobación posterior: 247 marcados recuperados; los 247 en ANULADO; 2 pagos conservados; 77 pendientes genuinos restantes al momento de la consulta (sin incluir rechazos devueltos a Validación).

Los pagos posteriores al incidente requieren revisión operativa; cambiar el estado no revierte transferencias:
- COB-01383: S/ 19,40.
- COB-01384: S/ 14,00.

## Prevención en código

Rendición rechaza ahora /api/rows/delete con HTTP 409 y explica que debe usarse Anular. Se mantiene el comportamiento de eliminación de los demás módulos. La prueba test_rendicion_no_borrado verifica bloqueo de eliminación, sincronización sin duplicación y conservación de estado y motivo. La protección solo se aplica a producción cuando se despliega el commit correspondiente.

