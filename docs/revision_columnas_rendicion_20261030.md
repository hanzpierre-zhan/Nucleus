# Revisión de columnas de Rendición — 30/10/2026

Revisión de solo lectura. Se consultaron metadatos y recuentos de producción (Neon) y se reprodujo la configuración de columnas en un navegador local con una base temporal y un registro ficticio. No se modificó producción. Esto no confirma la versión actualmente desplegada en Render.

En esta reproducción: **45 opciones en el selector**, **59 columnas en Excel**, además del control obligatorio Flujo. La visibilidad inicial varía por pestaña y configuración guardada. El exportable incorpora campos históricos de los registros, aunque no estén visibles en la tabla.

Los recuentos indican registros con contenido, no validación del dato. Los formularios F1/F2 y sus exclusiones aprobadas se mantienen. No se propone borrar campos de la base.

## Inventario de tabla, selector y exportable

“Tabla” significa que el campo está definido y disponible; no que aparezca visible en todas las pestañas. Los campos solo históricos pueden salir únicamente en exportables.

| Campo / control | Tabla | Selector | Excel | Con datos | Recomendación |
|---|:---:|:---:|:---:|---:|---|
| Flujo | Sí | — | — | — | Conservar control visual; no es una columna de datos. |
| Responsable de la validación | Sí | Sí | Sí | 1851 | Conservar. |
| ESTADO | Sí | Sí | Sí | 1776 | Conservar. |
| SUBESTADO | Sí | Sí | Sí | 308 | Conservar. |
| Monto total del depósito | Sí | Sí | Sí | 1853 | Conservar. |
| ADJUNTO CORREO VALIDACION | Sí | Sí | Sí | 465 | Conservar. |
| MOTIVO RECHAZO | Sí | Sí | Sí | 251 | Conservar. |
| Marca temporal | Sí | Sí | Sí | 1853 | Conservar. |
| CODIGO DEPOSITO | Sí | Sí | Sí | 1372 | Conservar. |
| Nombre del proyecto | Sí | Sí | Sí | 1853 | Conservar. |
| Técnico beneficiario | Sí | Sí | Sí | 1851 | Conservar. |
| Técnico beneficiario (Form) | Sí | Sí | Sí | 1762 | Conservar. |
| Nombre de site | Sí | Sí | Sí | 1853 | Conservar. |
| Número CM / PM / PLM | Sí | Sí | Sí | 1851 | Conservar. |
| Tipo de presupuesto | Sí | Sí | Sí | 1851 | Conservar. |
| Tipo de gasto | Sí | Sí | Sí | 1851 | Conservar. |
| Motivo de la solicitud | Sí | Sí | Sí | 1853 | Conservar. |
| Observaciones (Form) | Sí | Sí | Sí | 1120 | Conservar. |
| OBSERVACIONES | Sí | Sí | Sí | 966 | Conservar. |
| Documento del beneficiario (Form) | Sí | Sí | Sí | 1762 | Conservar. |
| Tipo de billetera digital | Sí | Sí | Sí | 1851 | Conservar. |
| Numero de Yape/Plin | Sí | Sí | Sí | 1844 | Conservar. |
| Número de cuenta o CCI | Sí | Sí | Sí | 1851 | Conservar. |
| Titular de la cuenta | Sí | Sí | Sí | 1851 | Conservar. |
| Evidencia | Sí | Sí | — | — | Conservar control visual; no es una columna de datos. |
| FECHA ATENDIDO | Sí | Sí | Sí | — | Ocultar de tabla, selector y exportable: sin datos en la consulta. |
| Tipo de Ticket | Sí | Sí | Sí | 1851 | Conservar. |
| FECHA PAGO | Sí | Sí | Sí | 1372 | Conservar. |
| MONTO PAGO | Sí | Sí | Sí | 1372 | Conservar. |
| FOTO PAGO | Sí | Sí | Sí | 1372 | Conservar. |
| FOTOS SUSTENTO | Sí | Sí | Sí | — | Opcional: mostrar solo mediante Evidencia. Tiene uso en el código, no eliminar. |
| EDITADO POR | Sí | Sí | — | 4 | Ocultar de tabla y selector; ya excluido del exportable. Conservar interno. |
| Supervisor encargado | Sí | Sí | Sí | 1834 | Conservar. |
| ENVIADO A TRANSITO POR | Sí | Sí | Sí | 2 | Conservar. |
| COMENTARIOS SUSTENTO | Sí | Sí | Sí | 359 | Conservar. |
| FECHA ENVIO TRANSITO | Sí | Sí | Sí | 2 | Conservar. |
| DEPOSITADO POR | Sí | Sí | Sí | 1372 | Conservar. |
| FECHA RECHAZO | Sí | Sí | Sí | 265 | Conservar. |
| FECHA SUSTENTO | Sí | Sí | Sí | 361 | Conservar. |
| FECHA VALIDACION | Sí | Sí | Sí | 1530 | Conservar. |
| INTERACCION | Sí | Sí | — | 1532 | Ocultar de tabla y selector; ya excluido del exportable. Conservar interno. |
| N° COTIZACION | Sí | Sí | Sí | 2 | Conservar. |
| RECHAZADO POR | Sí | Sí | Sí | 265 | Conservar. |
| SUSTENTADO POR | Sí | Sí | Sí | 361 | Conservar. |
| TIEMPO DE RESPUESTA | Sí | Sí | Sí | 1475 | Conservar. |
| VALIDADO POR | Sí | Sí | Sí | 1530 | Conservar. |
| ANULADO DESDE | — | — | Sí | 160 | Conservar. |
| ANULADO POR | — | — | Sí | 160 | Conservar. |
| ARCHIVADO POR | — | — | Sí | 259 | Conservar. |
| DESARCHIVADO POR | — | — | Sí | 1 | Conservar. |
| DEVUELTO POR | — | — | Sí | 1 | Conservar. |
| FECHA ANULACION | — | — | Sí | 160 | Conservar. |
| FECHA ARCHIVO | — | — | Sí | 259 | Conservar. |
| FECHA DESARCHIVO | — | — | Sí | 1 | Conservar. |
| FECHA DEVOLUCION | — | — | Sí | 1 | Conservar. |
| FECHA OBSERVACION | — | — | Sí | 114 | Conservar. |
| NOMBRE CORREO VALIDACION | — | — | Sí | 465 | Excluir como columna independiente; conservar nombre junto al adjunto. |
| NUMERO WO | — | — | Sí | 2 | Conservar. |
| OBSERVADO POR | — | — | Sí | 114 | Conservar. |
| RECHAZADO DESDE | — | — | Sí | 235 | Conservar. |
| TIPO DE PRESUPUESTO | — | — | Sí | 2 | Revisar unificación con Tipo de presupuesto: tiene 2 valores de Tránsito; no borrar. |
| VECES RECHAZADO | — | — | Sí | 235 | Conservar. |
| VERIFICACIÓN PERSONAL | — | — | Sí | 1771 | Excluir del exportable; resultado técnico del cruce. Conservar interno. |

## Encabezados exactos del Excel comprobado

1. F1. Marca temporal
2. F1. Nombre del proyecto
3. ESTADO
4. F1. Tipo de presupuesto
5. F1. Tipo de gasto
6. F1. Tipo de Ticket
7. F1. Nombre de site
8. F1. Técnico beneficiario
9. F1. Número CM / PM / PLM
10. F1. Motivo de la solicitud
11. F1. Monto total del depósito
12. F1. Tipo de billetera digital
13. F1. Numero de Yape/Plin
14. F1. Número de cuenta o CCI
15. F1. Titular de la cuenta
16. F1. Supervisor encargado
17. F1. Responsable de la validación
18. F1. Observaciones (Form)
19. Tiempo de respuesta
20. FECHA VALIDACION
21. VALIDADO POR
22. Código depósito
23. FECHA PAGO
24. MONTO PAGO
25. FOTO PAGO
26. DEPOSITADO POR
27. FOTOS SUSTENTO
28. COMENTARIOS SUSTENTO
29. FECHA SUSTENTO
30. SUSTENTADO POR
31. Motivo (flujo)
32. FECHA RECHAZO
33. RECHAZADO POR
34. RECHAZADO DESDE
35. VECES RECHAZADO
36. DEVUELTO POR
37. FECHA DEVOLUCION
38. FECHA ATENDIDO
39. ADJUNTO CORREO VALIDACION
40. F1. Documento del beneficiario (Form)
41. ENVIADO A TRANSITO POR
42. FECHA ENVIO TRANSITO
43. MOTIVO RECHAZO
44. N° COTIZACION
45. SUBESTADO
46. F1. Técnico beneficiario (Form)
47. ANULADO DESDE
48. ANULADO POR
49. ARCHIVADO POR
50. DESARCHIVADO POR
51. FECHA ANULACION
52. FECHA ARCHIVO
53. FECHA DESARCHIVO
54. FECHA OBSERVACION
55. NOMBRE CORREO VALIDACION
56. NUMERO WO
57. OBSERVADO POR
58. TIPO DE PRESUPUESTO
59. VERIFICACIÓN PERSONAL

## Visibilidad por pestaña comprobada

### transito

Flujo, ESTADO, Evidencia, F1. Nombre del proyecto, N° COTIZACION, F1. Nombre de site, F1. Motivo de la solicitud, F1. Marca temporal, F1. Monto total del depósito, ENVIADO A TRANSITO POR, FECHA ENVIO TRANSITO

### validacion

Flujo, F1. Responsable de la validación, ESTADO, F1. Monto total del depósito, CORREO DE VALIDACIÓN, MOTIVO RECHAZO, F1. Marca temporal, F1. Nombre del proyecto, F1. Técnico beneficiario (Formulario), F1. Nombre de site, F1. Número CM / PM / PLM, F1. Tipo de presupuesto, F1. Tipo de gasto, F1. Motivo de la solicitud, F1. Observaciones (Form), OBSERVACIONES, F1. Documento del beneficiario (Form), F1. Tipo de billetera digital, F1. Numero de Yape/Plin, F1. Número de cuenta o CCI, F1. Titular de la cuenta, F1. Supervisor encargado

### depositos

Flujo, F1. Responsable de la validación, F1. Monto total del depósito, ESTADO, F1. Nombre del proyecto, F1. Tipo de presupuesto, F1. Marca temporal, F1. Tipo de gasto, F1. Técnico beneficiario (Formulario), F1. Motivo de la solicitud, F1. Tipo de billetera digital, F1. Numero de Yape/Plin, F1. Número de cuenta o CCI, F1. Titular de la cuenta, F1. Nombre de site, F1. Número CM / PM / PLM, F1. Supervisor encargado, OBSERVACIONES, F1. Observaciones (Form), F1. Documento del beneficiario (Form)

### evidencia

Flujo, ESTADO, F1. Nombre del proyecto, FOTO PAGO, Evidencia, FECHA RECHAZO, MOTIVO RECHAZO, F1. Responsable de la validación, FECHA PAGO, CODIGO DEPOSITO, MONTO PAGO, F1. Técnico beneficiario (Formulario), F1. Motivo de la solicitud, F1. Tipo de presupuesto, F1. Tipo de gasto, DEPOSITADO POR, F1. Tipo de billetera digital, F1. Numero de Yape/Plin, F1. Número de cuenta o CCI, F1. Titular de la cuenta, F1. Nombre de site, F1. Número CM / PM / PLM, OBSERVACIONES, F1. Supervisor encargado, F1. Observaciones (Form)

### rendicion

Flujo, ESTADO, CORREO DE VALIDACIÓN, F1. Marca temporal, Evidencia, FECHA PAGO, FOTO PAGO, F1. Nombre del proyecto, F1. Responsable de la validación, CODIGO DEPOSITO, F1. Técnico beneficiario (Formulario), MONTO PAGO, F1. Tipo de billetera digital, F1. Numero de Yape/Plin, F1. Número de cuenta o CCI, F1. Titular de la cuenta, F1. Tipo de presupuesto, F1. Tipo de gasto, F1. Motivo de la solicitud, F1. Nombre de site, F1. Número CM / PM / PLM, F1. Supervisor encargado

### observado

Flujo, ESTADO, SUBESTADO, CODIGO DEPOSITO, CORREO DE VALIDACIÓN, Evidencia, F1. Nombre del proyecto, F1. Responsable de la validación, F1. Marca temporal, F1. Técnico beneficiario (Formulario), F1. Nombre de site, F1. Número CM / PM / PLM, MONTO PAGO, F1. Tipo de presupuesto, F1. Tipo de gasto, F1. Motivo de la solicitud, OBSERVACIONES

### archivado

Flujo, ESTADO, SUBESTADO, F1. Nombre del proyecto, FOTO PAGO, CORREO DE VALIDACIÓN, Evidencia, F1. Responsable de la validación, CODIGO DEPOSITO, F1. Marca temporal, F1. Técnico beneficiario (Formulario), MONTO PAGO, F1. Tipo de presupuesto, F1. Tipo de gasto, F1. Motivo de la solicitud, F1. Nombre de site, F1. Número CM / PM / PLM, F1. Supervisor encargado, OBSERVACIONES

### cerrado

Flujo, ESTADO, MONTO PAGO, FOTO PAGO, CODIGO DEPOSITO, F1. Técnico beneficiario (Formulario), F1. Nombre del proyecto, Evidencia, F1. Marca temporal, F1. Nombre de site, FECHA PAGO, F1. Número CM / PM / PLM, COMENTARIOS SUSTENTO, F1. Motivo de la solicitud, F1. Tipo de presupuesto, CORREO DE VALIDACIÓN

### rechazados

Flujo, ESTADO, F1. Marca temporal, CODIGO DEPOSITO, F1. Nombre del proyecto, F1. Técnico beneficiario (Dataper), F1. Técnico beneficiario (Formulario), F1. Nombre de site, F1. Número CM / PM / PLM, F1. Monto total del depósito, MONTO PAGO, OBSERVACIONES, MOTIVO RECHAZO

## Limpieza propuesta, sin pérdida de información

1. Ocultar INTERACCION y EDITADO POR de tabla y selector. El exportador ya los omite.
2. Quitar del exportable VERIFICACIÓN PERSONAL y NOMBRE CORREO VALIDACION, conservando el cruce y el adjunto con su nombre.
3. Ocultar FECHA ATENDIDO: está configurada pero no tiene valores. No sustituirla por FECHA SUSTENTO automáticamente.
4. Revisar el alias TIPO DE PRESUPUESTO de Tránsito antes de unificarlo con Tipo de presupuesto: sus dos registros tienen información real.
5. FOTOS SUSTENTO puede quedar solo en Evidencia si se busca una tabla más limpia; no es un campo muerto y no debe eliminarse del almacenamiento.

Conservar importes solicitado y pagado, estado/subestado, códigos, cotización, datos bancarios y la trazabilidad de quién/cuándo validó, pagó, sustentó, rechazó, observó, archivó o anuló. Que un campo tenga pocos registros no implica que sobre: NUMERO WO, N° COTIZACION y los datos de Tránsito están activos.

MOTIVO RECHAZO, OBSERVACIONES del flujo y Observaciones (Form) no son equivalentes; no deben fusionarse por su parecido. PRESUPUESTO es un campo nuevo del control contra cotización: conservar su funcionalidad aunque todavía no tenga datos de producción en esta consulta.

La configuración reproducida contiene las opciones de beneficiario Dataper y Formulario. Se documentan tal como están; no se modifican en esta revisión.
