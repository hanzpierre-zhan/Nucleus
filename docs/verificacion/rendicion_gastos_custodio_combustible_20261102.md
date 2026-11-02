# Homologación CUSTODIO y COMBUSTIBLE — 02/11/2026

Autorización: el usuario pidió agregar ambas opciones a F1. Tipo de gasto y homologar revisando los datos, especialmente Motivo de la solicitud.

Se revisaron 2.101 registros de Rendición en la rama de producción vigente `br-spring-tree-axi7369a` del proyecto Neon `little-waterfall-75236198`. Se contrastaron Tipo de gasto, Motivo de la solicitud, Observaciones (Form) y las marcas de homologación anteriores. Las referencias de pago/sustento se conservaron sin utilizarlas como fuente principal para redefinir el motivo original.

La rama histórica `br-divine-surf-ax353lz7` ya no es producción; no se modificó. Se probó primero en `br-soft-field-axjnsq59` (homologacion-custodio-combustible-20261102).

## Resultado aplicado

| Categoría resultante | Registros |
|---|---:|
| CUSTODIO | 50 |
| VIATICOS, CUSTODIO | 2 |
| ALQUILER, CUSTODIO | 3 |
| ACARREO, CUSTODIO | 1 |
| VIATICOS, ACARREO, CUSTODIO | 2 |
| COMBUSTIBLE | 8 |
| PEAJE, VIATICOS, COMBUSTIBLE | 2 |
| Total | 68 |

Se mantuvieron 2.033 registros sin cambio. No se infirió adquisición de combustible de la mera mención de abastecimiento, peaje, viático, acarreo, filtros o galoneras. Los casos sin evidencia explícita se conservaron para revisión humana, sin asignaciones nuevas especulativas.

## Integridad y reversión

- Respaldo de las 68 filas completas y de manual_columns anterior en app_config, proyecto 16, clave `backup_gastos_custodio_combustible_20261102`.
- Una entrada de historial_cambios por registro, usuario técnico `homologacion-gastos`.
- Campo de seguimiento `_TIPO_GASTO_CUSTODIO_COMBUSTIBLE` con valor anterior, nuevo, criterio y lote.
- Transacción con control de concurrencia sobre tipo, motivo y observaciones antes de modificar.
- Comparación de todos los demás campos JSON contra el estado previo dentro de la misma transacción. Cualquier diferencia provocaba rollback.
- Verificación de filas ajenas intactas y del recuento total sin variación.
- Las opciones se agregaron a manual_columns de producción, conservando las demás configuraciones.

Para revertir, restaurar únicamente Tipo de gasto y la marca de este lote a partir del respaldo; no sobrescribir la fila completa si hubo cambios posteriores. Revisar primero cualquier clasificación editada después del lote. La configuración anterior de opciones también está en el respaldo.

30 pruebas de clasificación pasaron. El soporte de validación de las nuevas categorías y sus opciones predeterminadas está preparado en el código local; su despliegue se gestiona por separado.
