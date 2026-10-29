# Corrección delicada de correlativos

Estado: implementación terminada y probada; publicación a cargo del usuario. El commit local e432e44 contiene el primer paquete. Deben incluirse también los cambios posteriores en app.py, blueprints/pages.py, migrations/cotizacion_correlativos.py, services/cotizacion_numeracion.py, scripts/verificar_correlativos_pg.py y tests/test_cotizacion_numeracion.py. No se completó el push: GitHub solicitó autenticación y el usuario indicó que haría el commit/publicación.

## Activación

Al arrancar la versión nueva en Render sobre PostgreSQL, se aplica una transacción de conciliación una sola vez, con un marcador persistente y bloqueo compartido con las altas. Se pospuso la conciliación de producción hasta ese arranque para que las etiquetas recuperadas se guarden y muestren con el editor compatible. No se aplicó esta conciliación en producción durante la preparación.

El ensayo en la copia aislada identificó 2 etiquetas recuperadas (524 y 526) que pasan a .1 y 192 ocurrencias posteriores de órdenes repetidas que reciben sufijos .1, .2, etc. Se conservan la primera ocurrencia de cada orden y todas las órdenes no repetidas. Se conservan IDs, claves técnicas, enlaces, importes, estados, ítems, fechas, archivos y relaciones. Las etiquetas y órdenes originales quedan en metadatos e historial. No se eliminan filas ni se restauran tablas enteras.

El plan de producción a las 09:00 de Perú verificó 631 cotizaciones: 194 filas con cambios únicamente de numeración y trazabilidad, 437 filas íntegramente intactas. Si hay nuevas altas antes del despliegue, se calcula el plan sobre los datos vigentes dentro del bloqueo. La comprobación SQL aborta si cambia algún otro campo.

## Prevención

- Reserva y alta en una misma transacción con bloqueo de configuración, incluida la inicialización concurrente del contador.
- Secuencia global compartida por ENTEL, CLARO, INTEGRATEL y PEXT; contempla históricos y sufijos recuperados.
- Sugerencias antiguas no reutilizan números. El administrador no puede reducir el siguiente consecutivo.
- Contadores de número y orden persistentes: borrar el último caso no hace retroceder los contadores.
- Clave técnica permanente y orden no editable por las rutas normales de Cotizaciones.
- Índices únicos en PostgreSQL para la serie mensual normalizada entre clientes y para las órdenes; rechazan escrituras duplicadas incluso si omiten el asignador.

## Verificación

Pruebas SQLite de numeración y prefijos: 12 aprobadas. El grupo de flujo y dashboard tuvo 21 aprobadas antes de añadir la prueba de eliminación del último caso. Se comprobó JavaScript renderizado: 41 bloques en cinco módulos. La prueba PostgreSQL realizó dos tandas de 12 altas concurrentes, con números y órdenes únicos, rechazo de duplicados entre clientes/meses y rollback correcto. El instalador de arranque se probó en la rama aislada; una segunda ejecución no vuelve a conciliar. Las pruebas de eliminación vinculada pasaron por separado (4); el grupo combinado anterior mostró interferencia de fixtures con otras suites, sin modificar pruebas ajenas.

Respaldo previo de producción, plan y ensayos privados: backups/correlativos-20261029/. Rama aislada usada: br-withered-darkness-axlnww9l. Ninguna prueba de altas se ejecutó en producción.

Tras publicar, GET /healthz debe responder OK y la cabecera X-Nucleus-Cotizacion-Sequence: v2. En Neon debe existir app_config.cotizacion_guardas_v2=aplicado-20261029. Estas dos señales distinguen código preparado de activación completada; no se ha confirmado todavía esa activación en Render.
