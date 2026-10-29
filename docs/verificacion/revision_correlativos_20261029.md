# Revisión de correlativos — 29/10/2026

Consulta de solo lectura en Neon, proyecto little-waterfall-75236198, rama production br-spring-tree-axi7369a. No se renumeraron registros ni se cambió código o configuración.

## Hallazgos confirmados

- No hay claves completas repetidas en Cotizaciones, ni números visibles completos repetidos. Todos los números visibles coinciden con key_value.
- La serie de octubre sí repite dos consecutivos entre clientes: CL-2026-10-000524 / EN-2026-10-000524 y CL-2026-10-000526 / PX-2026-10-000526. Los registros CL fueron los recuperados por autorización del usuario, conservando su numeración histórica; la recuperación resolvió la colisión completa 528 con .1, pero no eliminó las coincidencias de la parte numérica entre prefijos. La implementación local y su test de prefijos establecen una secuencia global compartida.
- CL-2026-10-000528 y CL-2026-10-000528.1 son solicitudes diferentes. La primera figura ahora Cancelado; la recuperada, de Villa Virgen, sigue En Aprobación.
- La columna N° ORDEN es un identificador diferente del N° COTIZACION: en la captura 451 corresponde a la orden de CL-2026-10-000527; la orden 452 corresponde a CL-2026-10-000528.
- Existen además 132 grupos de N° ORDEN repetidos dentro del mismo cliente, con 264 filas implicadas. Esta auditoría no atribuye su causa; incluye registros anteriores a las cuatro recuperaciones. Las cuatro altas recuperadas usan órdenes 453–456.
- cotizacion_next_seq vale 530. Esto acredita la configuración actual, no una prueba en vivo de creación desde Render.

## Lectura del código local

blueprints/rows.py serializa altas con cotizacion_next_seq y escanea las numeraciones existentes. La lista de equivalencias de números manuales omite PX en algunos formatos, acepta un número manual libre aunque sea inferior al siguiente configurado, y no contempla sufijos de recuperación en el escaneo. Son límites identificados en el código local; no se confirmó el commit desplegado en Render ni se atribuyen automáticamente a estos límites las repeticiones existentes.

## Criterio de corrección

No cambiar cotizaciones ya emitidas sin conciliar documentos y referencias. Si se exige unicidad de la parte numérica global también en los registros recuperados, hace falta una asignación excepcional para los consecutivos 524 y 526 recuperados, manteniendo número original y procedencia. El sufijo .1 de 528 fue autorizado expresamente. La renumeración masiva de órdenes históricas requiere revisar su uso y preservar trazabilidad; no se ejecutó durante una solicitud de revisión.
