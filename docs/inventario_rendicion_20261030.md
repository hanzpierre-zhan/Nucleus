# Inventario de Rendición — producción — 30/10/2026

Consulta de solo lectura a las 10:06, America/Lima. Proyecto Nucleus, rama production, base neondb, módulo Rendicion (proyecto_id 16). Total: 1.853 solicitudes. No se modificaron columnas ni registros.

Se detectaron 121 campos lógicos: 119 presentes en registros y 2 solo configurados. Los recuentos significan «valor no vacío», no «dato válido»: por ejemplo #N/A o NA cuentan como contenido.

Los campos de negocio se guardan dentro de data_json (columna física TEXT). Por ello una fecha o un importe puede tener tipo lógico fecha/importe pero estar serializado como texto. Los nombres y las descripciones se mantienen según el esquema y el código; no se han unificado campos parecidos.

## 1. Solicitud, beneficiario y datos de origen

| Campo exacto | Tipo de dato que contiene | Almacenamiento real | Qué guarda | Solicitudes con datos |
|---|---|---|---|---:|
| CODIGO DEPOSITO (Form) | Texto de origen | Texto JSON | Campo homónimo del formulario externo; no sustituye el código interno. | 0 |
| Cruce de personal | Texto / resultado | Texto JSON | Resumen del cruce del beneficiario con Personal. | 1762 |
| DEPARTAMENTO | Texto | Texto JSON | Departamento obtenido del catálogo de Personal o corregido. | 1619 |
| Documento del beneficiario | Texto / documento | Texto JSON | Documento actual del beneficiario; conservar como texto para mantener ceros iniciales. | 1851 |
| Documento del beneficiario (Form) | Texto / documento | Texto JSON | Documento original recibido del formulario. | 1762 |
| ESTADO (Form) | Texto de origen | Texto JSON | Estado recibido del formulario externo; separado del estado interno. Puede contener #N/A. | 644 |
| Marca temporal | Fecha y hora | Texto JSON | Fecha de envío de la solicitud; clave del módulo. | 1853 |
| MONTO PAGO (Form) | Texto de origen | Texto JSON | Campo homónimo externo; no sustituye el pago interno. | 0 |
| Monto total del depósito | Importe en soles | Texto JSON | Importe solicitado; puede diferir del pago efectivo. | 1853 |
| Motivo de la solicitud | Texto libre | Texto JSON | Justificación de la solicitud. | 1853 |
| N° COTIZACION | Texto / identificador | Texto JSON | Número de la cotización de origen de solicitudes enviadas a Tránsito. | 2 |
| Nombre de site | Texto | Texto JSON | Sitio relacionado con el gasto. | 1853 |
| Nombre del proyecto | Texto / categoría | Texto JSON | Proyecto u operador al que pertenece la solicitud. | 1853 |
| Número CM / PM / PLM | Texto / identificador | Texto JSON | Número del ticket operativo. | 1851 |
| Número de cuenta o CCI | Texto / identificador | Texto JSON | Cuenta bancaria o CCI; debe conservar ceros iniciales. | 1851 |
| Numero de Yape/Plin | Texto / identificador | Texto JSON | Número informado para Yape/Plin; no convertir automáticamente a número. | 1844 |
| NUMERO WO | Texto / identificador | Texto JSON | WO vinculada a la solicitud originada desde Cotizaciones. | 2 |
| Observaciones (Form) | Texto libre | Texto JSON | Observaciones originales del formulario. | 1120 |
| Responsable de la validación | Texto / responsable | Texto JSON | Responsable asignado para revisar la solicitud. | 1851 |
| Supervisor encargado | Texto / responsable | Texto JSON | Supervisor indicado en la solicitud. | 1834 |
| Técnico beneficiario | Texto | Texto JSON | Beneficiario actual, normalizado o corregido mediante el cruce con Personal. | 1851 |
| Técnico beneficiario (Form) | Texto | Texto JSON | Nombre original recibido del formulario. | 1762 |
| Tipo de billetera digital | Texto / categoría | Texto JSON | Medio de billetera digital indicado. | 1851 |
| Tipo de gasto | Texto / categoría | Texto JSON | Concepto o categoría del gasto solicitado. | 1851 |
| Tipo de presupuesto | Texto / categoría | Texto JSON | Clasificación presupuestaria de la solicitud. | 1851 |
| TIPO DE PRESUPUESTO | Texto / categoría | Texto JSON | Variante usada en solicitudes originadas desde Tránsito/Cotizaciones; revisar dependencias antes de unificar. | 2 |
| Tipo de Ticket | Texto / categoría | Texto JSON | Clasificación del ticket operativo. | 1851 |
| Titular de la cuenta | Texto | Texto JSON | Titular del medio de pago. | 1851 |
| VERIFICACIÓN PERSONAL | Texto / estado | Texto JSON | Resultado de la verificación contra Personal. | 1771 |

## 2. Pagos y adjuntos

| Campo exacto | Tipo de dato que contiene | Almacenamiento real | Qué guarda | Solicitudes con datos |
|---|---|---|---|---:|
| ADJUNTO CORREO VALIDACION | Texto / enlace de archivo | Texto JSON | Referencia al correo .msg de validación; el archivo tiene almacenamiento separado. | 465 |
| CODIGO DEPOSITO | Texto / identificador | Texto JSON | Código interno del depósito; se usa para vincular sustentos. | 1372 |
| COMENTARIOS SUSTENTO | Texto libre | Texto JSON | Comentario asociado al sustento registrado dentro de Nucleus. | 359 |
| FOTO PAGO | Texto / enlace de archivo | Texto JSON | Referencia al comprobante de depósito. | 1372 |
| FOTOS SUSTENTO | Texto / lista de enlaces | Configurado; sin registros | Campo configurado para las fotografías de sustento; no aparece en registros actuales. | 0 |
| MONTO PAGO | Importe en soles | Texto JSON | Pago efectivamente registrado; importe usado para los reportes de pagos. | 1372 |
| NOMBRE CORREO VALIDACION | Texto / nombre de archivo | Texto JSON | Nombre original del correo adjunto. | 465 |

## 3. Flujo y auditoría

| Campo exacto | Tipo de dato que contiene | Almacenamiento real | Qué guarda | Solicitudes con datos |
|---|---|---|---|---:|
| ANULADO DESDE | Texto / etapa | Texto JSON | Etapa desde la que se anuló. | 160 |
| ANULADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de anulación. | 160 |
| ARCHIVADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de archivo. | 259 |
| DEPOSITADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de depósito. | 1372 |
| DESARCHIVADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de desarchivo. | 1 |
| DEVUELTO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de devolución. | 1 |
| EDITADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de edición. | 4 |
| ENVIADO A TRANSITO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de envío a Tránsito. | 2 |
| ESTADO | Texto / estado del flujo | Texto JSON | Etapa principal; la gestionan los botones del flujo, no una edición genérica. | 1776 |
| FECHA ANULACION | Fecha y hora | Texto JSON | Fecha registrada para anulacion. | 160 |
| FECHA ARCHIVO | Fecha y hora | Texto JSON | Fecha registrada para archivo. | 259 |
| FECHA ATENDIDO | Fecha y hora | Configurado; sin registros | Fecha registrada para atendido. | 0 |
| FECHA DESARCHIVO | Fecha y hora | Texto JSON | Fecha registrada para desarchivo. | 1 |
| FECHA DEVOLUCION | Fecha y hora | Texto JSON | Fecha registrada para devolucion. | 1 |
| FECHA ENVIO TRANSITO | Fecha y hora | Texto JSON | Fecha registrada para envio transito. | 2 |
| FECHA OBSERVACION | Fecha y hora | Texto JSON | Fecha registrada para observacion. | 114 |
| FECHA PAGO | Fecha y hora | Texto JSON | Fecha registrada para pago. | 1372 |
| FECHA RECHAZO | Fecha y hora | Texto JSON | Fecha registrada para rechazo. | 265 |
| FECHA SUSTENTO | Fecha y hora | Texto JSON | Fecha registrada para sustento. | 361 |
| FECHA VALIDACION | Fecha y hora | Texto JSON | Fecha registrada para validacion. | 1530 |
| INTERACCION | Texto / usuario | Texto JSON | Usuario que realizó la última acción del flujo. | 1532 |
| MOTIVO RECHAZO | Texto libre | Texto JSON | Motivo de rechazo o anulación conservado por el flujo. | 251 |
| OBSERVACIONES | Texto libre | Texto JSON | Observaciones del flujo gestionadas dentro de Nucleus. | 966 |
| OBSERVADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de observación. | 114 |
| RECHAZADO DESDE | Texto / estado | Texto JSON | Etapa desde la que se rechazó la solicitud. | 235 |
| RECHAZADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de rechazo. | 265 |
| SUBESTADO | Texto / estado complementario | Texto JSON | Observado o Archivado, conservando el estado principal cuando corresponde. | 308 |
| SUSTENTADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de sustento. | 361 |
| TIEMPO DE RESPUESTA | Texto / lista | Texto JSON | Menor a 4 horas, Mayor a 4 horas, No aplica o Atención Continua; se elige al validar. | 1475 |
| VALIDADO POR | Texto / usuario | Texto JSON | Usuario que realizó la acción de validación. | 1530 |
| VECES RECHAZADO | Contador | Texto JSON | Cantidad de rechazos registrados; actualmente serializada como texto. | 235 |

## 4. Segundo formulario: sustentos

| Campo exacto | Tipo de dato que contiene | Almacenamiento real | Qué guarda | Solicitudes con datos |
|---|---|---|---|---:|
| SUSTENTO_ADJUNTAR COMPROBANTE | Texto / enlaces | Texto JSON | Campo de comprobante del segundo formulario; sin valores actualmente. | 0 |
| SUSTENTO_CARGAR EVIDENCIAS | Texto / enlaces | Texto JSON | Referencias a evidencias recibidas desde el segundo formulario. | 859 |
| SUSTENTO_DOCUMENTO | Texto de formulario | Texto JSON | Respuesta de la pregunta Documento del segundo formulario; validar el significado exacto de la pregunta antes de renombrar. | 859 |
| SUSTENTO_FOTO ALQUILER | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para alquiler. | 37 |
| SUSTENTO_FOTO COCHERA | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para cochera. | 0 |
| SUSTENTO_FOTO COMPRAS | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para compras. | 101 |
| SUSTENTO_FOTO HOSPEDAJE | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para hospedaje. | 73 |
| SUSTENTO_FOTO OTROS | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para otros. | 130 |
| SUSTENTO_FOTO PASAJE | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para pasaje. | 11 |
| SUSTENTO_FOTO PEAJE | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para peaje. | 126 |
| SUSTENTO_FOTO VIATICOS | Texto / enlaces de archivos | Texto JSON | Foto o comprobante declarado para viaticos. | 413 |
| SUSTENTO_INGRESE RUC DE PROVEDOR | Texto / identificador | Texto JSON | Campo general de RUC del segundo formulario; sin valores actualmente. | 0 |
| SUSTENTO_MARCA TEMPORAL | Fecha y hora | Texto JSON | Marca temporal importada del formulario de sustento. | 42 |
| SUSTENTO_MOTO TOTAL DE LO GASTADO | Importe en soles | Texto JSON | Total gastado declarado en el segundo formulario. Nombre conservado tal como llega del origen. | 859 |
| SUSTENTO_NOMBRE TECNICO | Texto | Texto JSON | Nombre del técnico en el segundo formulario; sin valores actualmente. | 0 |
| SUSTENTO_PRECIO ALQUILER | Importe en soles | Texto JSON | Importe declarado para  alquiler. | 33 |
| SUSTENTO_PRECIO COCHERA | Importe en soles | Texto JSON | Importe declarado para  cochera. | 0 |
| SUSTENTO_PRECIO COMPRAS | Importe en soles | Texto JSON | Importe declarado para  compras. | 81 |
| SUSTENTO_PRECIO HOSPEDAJE | Importe en soles | Texto JSON | Importe declarado para  hospedaje. | 72 |
| SUSTENTO_PRECIO OTROS | Importe en soles | Texto JSON | Importe declarado para  otros. | 127 |
| SUSTENTO_PRECIO PASAJE | Importe en soles | Texto JSON | Importe declarado para  pasaje. | 4 |
| SUSTENTO_PRECIO PEAJE | Importe en soles | Texto JSON | Importe declarado para  peaje. | 117 |
| SUSTENTO_PRECIO VIATICOS | Importe en soles | Texto JSON | Importe declarado para  viaticos. | 372 |
| SUSTENTO_RUC ALQUILER | Texto / identificador | Texto JSON | RUC declarado para alquiler; conservar como texto. | 36 |
| SUSTENTO_RUC COCHERA | Texto / identificador | Texto JSON | RUC declarado para cochera; conservar como texto. | 0 |
| SUSTENTO_RUC COMPRAS | Texto / identificador | Texto JSON | RUC declarado para compras; conservar como texto. | 81 |
| SUSTENTO_RUC HOSPEDAJE | Texto / identificador | Texto JSON | RUC declarado para hospedaje; conservar como texto. | 72 |
| SUSTENTO_RUC OTROS | Texto / identificador | Texto JSON | RUC declarado para otros; conservar como texto. | 113 |
| SUSTENTO_RUC PASAJE | Texto / identificador | Texto JSON | RUC declarado para pasaje; conservar como texto. | 6 |
| SUSTENTO_RUC PEAJE | Texto / identificador | Texto JSON | RUC declarado para peaje; conservar como texto. | 116 |
| SUSTENTO_RUC VIATICOS | Texto / identificador | Texto JSON | RUC declarado para viaticos; conservar como texto. | 369 |
| SUSTENTO_TIPO DE PROYECTO | Texto / categoría | Texto JSON | Proyecto indicado en el segundo formulario. | 859 |
| SUSTENTO_TIPO DOCUMENTO ALQUILER | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  alquiler. | 34 |
| SUSTENTO_TIPO DOCUMENTO COCHERA | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  cochera. | 0 |
| SUSTENTO_TIPO DOCUMENTO COMPRAS | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  compras. | 98 |
| SUSTENTO_TIPO DOCUMENTO HOSPEDAJE | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  hospedaje. | 82 |
| SUSTENTO_TIPO DOCUMENTO OTROS | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  otros. | 94 |
| SUSTENTO_TIPO DOCUMENTO PASAJE | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  pasaje. | 3 |
| SUSTENTO_TIPO DOCUMENTO PEAJE | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  peaje. | 128 |
| SUSTENTO_TIPO DOCUMENTO VIATICOS | Texto / categoría | Texto JSON | Tipo de comprobante declarado para  viaticos. | 410 |

## 5. Campos internos

| Campo exacto | Tipo de dato que contiene | Almacenamiento real | Qué guarda | Solicitudes con datos |
|---|---|---|---|---:|
| _CORRECCION_REV | Número entero | Número JSON | Versión de las correcciones manuales. | 53 |
| _CORREGIDO_POR | Texto / usuario | Texto JSON | Usuario que corrigió la solicitud. | 53 |
| _COTIZACION_ORIGEN | Objeto JSON | Objeto JSON | Referencia y metadatos de la cotización que originó la solicitud. | 2 |
| _FECHA_CORRECCION | Fecha y hora | Texto JSON | Fecha de la corrección manual. | 53 |
| _fecha_ultima_act_manual | Fecha y hora | Texto JSON | Última actualización manual registrada. | 4 |
| _HISTORIAL_FLUJO | Lista JSON | Lista JSON | Eventos de las acciones del flujo y sus estados anteriores. | 1648 |
| _PERSONAL_CORRECCION_MANUAL | Booleano | Booleano JSON | Indica que el cruce de Personal fue corregido manualmente. | 3 |
| _PERSONAL_CRUCE | Objeto JSON | Objeto JSON | Resultado y metadatos del cruce con Personal. | 1771 |
| _PERSONAL_ORIGINAL | Objeto JSON | Objeto JSON | Datos originales conservados para el cruce con Personal. | 1771 |
| _RECHAZO_ETAPA | Texto / etapa | Texto JSON | Destino de retorno del rechazo; interviene en la pestaña donde aparece. | 158 |
| _RECUPERACION_ANULADO | Objeto JSON | Objeto JSON | Trazabilidad de la recuperación del incidente de borrado y reimportación. | 247 |
| _SUSTENTO_FOTOS_FORM | Texto / metadatos serializados | Texto JSON | Control de las fotos importadas del formulario. | 159 |
| _SUSTENTO_MARCAS | Texto / lista de marcas | Texto JSON | Marcas temporales procesadas para no reaplicar un mismo sustento. | 830 |
| _ultimo_usuario_manual | Texto / usuario | Texto JSON | Usuario de la última actualización manual. | 4 |

## Columnas físicas y controles de pantalla

| Elemento | Tipo | Función |
|---|---|---|
| id | Entero | Identificador físico, referenciado por adjuntos y otras tablas. |
| proyecto_id | Entero / clave foránea | Identifica el módulo propietario; Rendicion usa 16. |
| key_value | Texto | Clave única de la solicitud dentro del módulo; se deriva de Marca temporal. |
| data_json | Texto que contiene JSON | Contenedor de los campos lógicos anteriores. |
| _key | Identificador derivado | Alias que usa la tabla para identificar la fila; no es otra columna física. |
| Flujo (_accion) | Control visual | Botones de acción según etapa y permisos; no almacena datos. |
| Evidencia (_evidencia_btn) | Control visual | Acceso a evidencias; no almacena datos. |

## Campos sin valores actuales

- CODIGO DEPOSITO (Form).
- MONTO PAGO (Form).
- FOTOS SUSTENTO (solo configurado).
- FECHA ATENDIDO (solo configurado).
- SUSTENTO_ADJUNTAR COMPROBANTE.
- SUSTENTO_FOTO COCHERA.
- SUSTENTO_INGRESE RUC DE PROVEDOR.
- SUSTENTO_NOMBRE TECNICO.
- SUSTENTO_PRECIO COCHERA.
- SUSTENTO_RUC COCHERA.
- SUSTENTO_TIPO DOCUMENTO COCHERA.

Que un campo esté vacío no demuestra que sea seguro borrarlo: FOTOS SUSTENTO, por ejemplo, participa en el flujo. Los campos (Form) preservan el origen; los campos internos protegen trazabilidad y sincronización. La primera fase de limpieza puede ocultar columnas sin borrar datos. Borrar, renombrar o fusionar requiere comprobar importación, formularios, reportes y referencias.

