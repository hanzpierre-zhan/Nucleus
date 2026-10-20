# Dashboards de Nucleus · revisión del 19 de octubre de 2026

## Resultado visual vigente

Cotizaciones y Rendición tienen un resumen compacto, diseñado para la pantalla de referencia con menú lateral. La vista inicial no necesita desplazamiento horizontal ni vertical en los tamaños de escritorio comprobados. No se fuerza ese objetivo en el teléfono: allí las tarjetas se apilan con textos e importes legibles.

- Cotizaciones: cantidades e importes por estado, pendientes del cliente por usuario e importes por pestaña. El resto de gráficos permanece disponible en “Más gráficos e indicadores”.
- Rendición: importes solicitados y depositados, pendiente de sustento, pendiente de validar y cierre, junto con distribución de etapas y responsables de casos por depositar. Los indicadores y gráficos secundarios quedan en el bloque adicional.
- Los gráficos principales muestran los grupos con más casos o importe. Se pueden comparar Cantidad/Monto y abrir todos los grupos. En pantallas de menor altura se muestran inicialmente dos grupos; en las demás, tres. Los totales no se calculan a partir de ese límite visual.
- Los importes conservan céntimos, no se parten y tienen mayor tamaño que las notas secundarias. Las etiquetas conservan su texto completo.
- “Ver concentración por proyecto, usuario y etapa” se trasladó completamente a la parte inferior, junto al detalle por caso y la tabla de responsables. Todos esos desplegables están cerrados inicialmente, incluido el detalle interior de casos. Pulsar una celda de concentración abre sus casos para actuar.
- Los estilos nuevos solo se cargan y se aplican a Cotizaciones y Rendición (clase di-executive).

## Módulos restaurados

Producción y seguimiento recuperó exactamente su script original y su plantilla anterior, con una sola adición: la hoja dashboard-operativo-width.css para ancho disponible. Se conservaron sus tarjetas, colores y dimensiones previas. Cobranza recuperó íntegramente su script y su plantilla originales; no carga el renderer ni la nueva distribución visual.

## Reglas de datos preservadas

Los indicadores, gráficos y detalle comparten filtros por fechas, proyecto, departamento, estado y personas. Cambiar la fecha de referencia no borra la fecha original de solicitud. La autorización por proyecto se aplica en el servidor.

Rendición distingue responsable asignado de validación, quien validó y quien depositó. DEPOSITADO, CON SUSTENTO y SUSTENTADO se presentan como situaciones diferentes. Un pago registrado de cero se conserva y no se sustituye por lo solicitado. La cifra de referencia por etapa usa el pago registrado y, si falta, lo solicitado: su etiqueta aclara que no es un total depositado.

Cotizaciones distingue gasto de solicitud (Gasto Cobra/Refacturable) de gasto de aprobación (Caja Chica/Proveedor). Proveedor es una vista paralela y no se cuenta dos veces. No existe un campo que pruebe ingreso efectivamente cobrado en Cotizaciones: cotizado, aprobado y facturado por proveedor permanecen separados.

La espera en etapa usa su transición o fecha específica registrada. Sin fecha válida se indica esa ausencia; no se usa la creación para inventar una antigüedad de etapa. Los casos cerrados no siguen acumulando espera. INTERACCION en Rendición es el último actor y no se usa para inventar solicitante o registrador. Los importes y responsables ausentes se identifican como tales.

## Validación y evidencias

Pruebas Chromium en claro y oscuro para Cotizaciones y Rendición, en 1352×674, 1352×600, 1920×900 y 390×844. Las dos primeras representan área útil del navegador, con el menú lateral incluido. Se comprueban scrollWidth/clientWidth y scrollHeight/clientHeight del resumen, dimensiones del documento, desplegables cerrados inicialmente, ubicación inferior de concentración, apertura de secundarios y de listas completas, comparación de medidas, filtros combinados y apertura del caso exacto. Producción y Cobranza tienen una comprobación adicional de aislamiento de estilos, renderer y grilla original.

Los datos de capturas son ficticios, con etiquetas largas e importes de nueve cifras. Los archivos vigentes en outputs son los que incluyen “compacto” (Cotizaciones/Rendición) o “restaurado” (Producción/Cobranza). Las capturas de escritorio contienen la vista útil completa ; en móvil se permite desplazamiento y se comprueba la legibilidad de la distribución.

Carpeta de capturas: C:/Users/Hanz/Documents/Codex/2026-10-19/realtime-voice-chat/outputs/
Resultados: backups/dashboard-mejoras-20261019/compacto.xml y compacto-completo.xml.

No se desplegó ni se publicó código, y no se modificaron datos de producción.


Resultado final: suite completa **473 correctas**, sin fallos ni omisiones (compacto-completo.xml). Tras ajustar las etiquetas de los filtros y permitir desplegar todos los grupos sin el límite previo de ocho, se repitieron las **6 pruebas de navegador**, todas correctas (compacto-final.xml). JavaScript y git diff --check sin errores.

Las dimensiones de cada combinación de tema y viewport están registradas en cotizaciones-dimensiones.json y rendicion-dimensiones.json dentro de outputs. Las pruebas con los 20 registros ficticios verifican asimismo que la expansión de responsables muestra los diez grupos del conjunto, no una lista truncada a ocho. Las advertencias de la suite son deprecaciones del proyecto y sus dependencias.
