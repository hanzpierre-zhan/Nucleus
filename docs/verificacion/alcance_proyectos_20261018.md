# Acceso a datos por proyectos asignados

El defecto estaba en las rutas nativas: entrar a un módulo compartido no implicaba filtrar sus datos por los proyectos FLM de la cuenta. Personal y Material tenían un filtro particular; Rendición, Cotizaciones y otros módulos podían cargar filas de todo el catálogo.

La política ahora se aplica en servidor, en una sola capa de acceso ORM, a `NucleusData`, cotizaciones guardadas, historial y seguimiento de Liquidaciones. Incluye consultas de columnas, conteos y operaciones por lote. Las descargas directas de fotos, ZIP y correos también comprueban el registro de origen. La asignación de módulos conserva sus controles previos; asignar un módulo no concede otros proyectos.

- Una cuenta nativa con Entel ve Entel; una con Claro e Integratel ve la unión de ambos.
- Las cuentas con los cuatro proyectos ven todo el catálogo compartido, incluidos históricos sin atribución. Los roles globales Zeno y Soporte conservan su alcance global.
- Los permisos se consultan nuevamente por solicitud. Una revocación no depende de cerrar sesión ni de la cookie anterior.
- Los selectores de proyecto/cliente muestran únicamente opciones autorizadas.
- Las cachés de opciones y del cruce de sites se separan por alcance para evitar mezclas entre cuentas.
- El piloto `/espacios` conserva su política propia y su aislamiento previo; no se le sustituyen sus perfiles por los accesos nativos.

## Históricos y relaciones

La atribución explícita de proyecto tiene prioridad. Para históricos sin ese campo se admiten relaciones verificables: una WO del proyecto, un site por nombre/código exactos o el QR de un generador vinculado a movimientos con WO. Una coincidencia contradictoria con un proyecto no asignado no concede acceso. No se reescriben datos históricos ni se asignan proyectos por proximidad textual. Los registros sin atribución inequívoca quedan para revisión desde una cuenta global o con todos los proyectos.

## Validación

Pruebas con uno, dos, cuatro y cero proyectos; revocación entre solicitudes; conteos; páginas; plantillas; historial; Liquidaciones con join; edición y borrado de registros ajenos; URLs de fotos/correos; reasignación de proyecto; caché entre cuentas; y atribución histórica por WO, site y QR, incluida una WO duplicada entre proyectos. La suite completa y el resultado final están en los respaldos privados.

También se comprobó la política contra una restauración PostgreSQL de los datos migrados. Una cuenta de prueba con solo Entel recibió 356 cotizaciones, 286 rendiciones, 58 personas y los sites/generadores atribuibles a ese proyecto. Son conteos de la copia al corte, no cifras permanentes de producción. No se modificaron usuarios ni permisos reales para ejecutar esta prueba.
