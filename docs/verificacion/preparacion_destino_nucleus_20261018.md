# Preparación de Modus hacia Nucleus — 18/10/2026

Destino confirmado: servicio Nucleus `srv-d9t0eiqjobas7388nffg`, commit desplegado `3a3d1983a2930078fa06d3b3298293a3f31b41ca`.

La lectura consistente de Neon produjo una copia lógica de 27 tablas: integridad correcta, cero relaciones foráneas rotas y cero JSON inválidos. Se conservaron 10.992 registros operativos y 17 cuentas. Esta copia no sustituye un respaldo nativo completo de PostgreSQL.

## Comparación

| Módulo | Filas de Modus | Claves nuevas | Revisión |
|---|---:|---:|---|
| FLM - INTEGRATEL | 2.005 | 2.005 | Pendiente ensayo de importación |
| Material | 437 | 437 | Pendiente ensayo de importación |
| Cotizaciones | 16 | 16 | Pendiente referencias y adjuntos |
| Personal | 37 | 0 | Existen por documento, con diferencias |

Los 37 documentos tienen una coincidencia única en Personal de Nucleus, todos asociados a FLM - INTEGRATEL. No se debe usar únicamente la clave de registro para sobreescribir personas. Hay diferencias en nombre y celular de los 37 casos, además de cargo (23), departamento (3), documento (1; valor textual distinto), estado (1) y contrata (1). Las diferencias completas se guardan en el respaldo privado, sin publicar datos personales en este informe. Se pidió al usuario definir qué fuente prevalece.

B2: Modus tiene 34 objetos actuales (8.843.483 bytes); Nucleus tiene 3.563 (497.072.394 bytes). No coinciden claves entre ambos inventarios. El respaldo de Modus está descargado y verificado; el del destino se ejecuta antes de la importación. El inventario y respaldo no abarcan versiones históricas borradas.

## Estado

No se escribió en las bases remotas ni se subieron archivos a B2. No se modificaron permisos ni despliegues. Falta resolver las diferencias de Personal, probar importación y remapeo de relaciones en copia, preparar recuperación y ejecutar/validar la carga final. El unificador de ensayo existente no es un importador listo para producción.


## Actualización final

El usuario eligió conservar los datos actuales de Nucleus para los 37 técnicos. Las diferencias de Modus quedan en el respaldo privado. La migración se completó usando un plan generado dentro de una transacción que conservó también los cambios recientes de producción. Ver el informe final `migracion_modus_completada_20261018.md`.
