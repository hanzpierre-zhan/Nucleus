# Optimización de carga de Liquidaciones — 2026-11-02

## Cambios

- El listado consulta las cotizaciones junto con su seguimiento y correlativo;
  consulta sus WO junto con el proyecto. Pasa de cinco a dos consultas principales
  cuando existen WO, sin consultas por cada caso ya numerado.
- Cada JSON de origen se interpreta una sola vez por ejecución. No hay caché
  compartida entre usuarios o solicitudes que pueda servir datos desactualizados.
- La vista solicita `?resumen=1`: conserva campos, documentos, montos y avance,
  y sustituye fotos/comentarios por `tiene_sustento`.
- `GET /liquidaciones/api/registros/<id>/sustento` lee el sustento vigente del
  caso al abrir el diálogo. Aplica los mismos permisos y alcance de proyectos.
  Cerrar el diálogo cancela la solicitud; los errores se muestran y se puede
  volver a abrirlo para reintentar.
- El navegador inicia la consulta mientras prepara la tabla y evita reconstruir
  columnas cuyos formateadores ya estaban definidos.
- Guardar un caso y preparar un ZIP consultan únicamente los casos solicitados.
  Si faltaban correlativos, se confirma la transacción después de construir la
  respuesta para evitar expirar los objetos y volver a consultar cada fila.
- Se mantiene la API completa por defecto, la numeración persistente y la
  paginación local con filtros, totales y exportación sobre todo el listado.
- La versión del JavaScript cambia a `v=22` para renovar el recurso del navegador.

## Medición aislada

Se abrió `nucleus.db` en modo solo lectura y se obtuvo una copia consistente con
`sqlite3.Connection.backup`. La aplicación y sus migraciones se ejecutaron
exclusivamente sobre esa copia temporal. No se conectó ni modificó producción.

La copia contiene 350 cotizaciones, de las cuales aparecen 318 en Liquidaciones.
Se guardó la respuesta completa anterior y se comparó con la optimizada:
**las 318 filas y todos sus valores coinciden**.

| Medida local | Antes | Después |
| --- | ---: | ---: |
| Consultas principales del listado con WO y números existentes | 5 | 2 |
| Mediana de preparación del listado, sin transferencia ni renderizado | 168 ms (5 muestras) | 82 ms (7 muestras) |
| Tamaño JSON del listado, misma serialización de medición | 268.194 bytes | 227.075 bytes con resumen |
| Mediana de preparación de un caso concreto | Se recorría todo el listado | 2,15 ms (7 muestras) |

Estas cifras describen esta copia y máquina; no son una promesa de latencia de
producción. La navegación con Chromium, usando la versión anterior y la nueva
sobre la misma copia, no produjo errores JavaScript. Los tiempos de apertura
completa fluctuaron y no demostraron una mejora consistente; por ello no se
atribuye a esta medición una reducción del tiempo total percibido.

La vista todavía prepara y recibe el listado resumido completo. No se implementó
paginación remota: requeriría adaptar conjuntamente filtros, totales, selección
y exportación. Tampoco se diagnosticaron aquí la latencia real a Postgres ni el
arranque en frío del alojamiento de producción.

## Verificación

73 pruebas aprobadas:

```powershell
python -m pytest tests/test_liquidaciones.py tests/test_refacturable.py tests/test_liquidacion_numero.py tests/test_sustento_por_wo.py tests/test_alcance_proyectos.py::test_liquidaciones_con_join_respeta_el_origen_sin_confundir_aliases tests/test_alcance_proyectos.py::test_liquidaciones_resumen_y_sustento_respetan_revocacion tests/test_e2e_navegador.py::test_liquidaciones_tarjetas_siguen_el_filtro_y_filtran_al_clic tests/test_lpu.py tests/test_cotizacion_proveedor.py -q --disable-warnings
node --check static/js/refacturable.js
git diff --check
```

Se cubren la equivalencia del resumen, lectura reciente de evidencias, consultas
acotadas, reutilización del JSON, guardado aislado, revocación de permisos y el
recorrido real en navegador (carga ligera, error de sustento, reintento y edición).

Un barrido adicional de `tests/test_alcance_proyectos.py` detectó un fallo en
`test_supervisor_descarga_importa_y_elimina_solo_su_proyecto`: el importador de
SITE responde 500 al recibir un rechazo de alcance 403. Se reprodujo cargando
las versiones anteriores de los dos módulos Python modificados desde `HEAD`,
sin alterar archivos. El fallo es previo a esta optimización y no se modificó.

Los cambios están en el código local. No se realizó despliegue.
