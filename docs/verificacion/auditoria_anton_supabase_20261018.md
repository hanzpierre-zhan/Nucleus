# Auditoría local de tablas y flujos

Copia local; no certifica integraciones externas ni datos no exportados

Integridad: ok. Relaciones foráneas rotas: 0. JSON inválido: 0.

## Inventario de tablas

| Tabla | Registros | Columnas físicas | Relaciones declaradas |
|---|---:|---:|---:|
| accesos_proyecto | 45 | 4 | 2 |
| app_config | 35 | 4 | 1 |
| conformidad_usuario | 7 | 3 | 1 |
| cotizaciones | 2 | 15 | 1 |
| filtros_maestros | 0 | 4 | 1 |
| historial_cambios | 7807 | 9 | 2 |
| kpi_configs | 0 | 7 | 1 |
| liquidacion_numero | 0 | 2 | 0 |
| notificaciones | 8 | 8 | 0 |
| nucleus_data | 636 | 4 | 1 |
| nucleus_history | 0 | 5 | 1 |
| proyectos | 6 | 4 | 0 |
| refacturable_detalle | 0 | 4 | 1 |
| reglas_estado_manual | 0 | 6 | 1 |
| tablas_maestras | 4 | 6 | 1 |
| tecnicos | 0 | 6 | 1 |
| token_store | 0 | 3 | 0 |
| usuarios | 16 | 5 | 0 |

## Catálogos y columnas dinámicas

| Proyecto / módulo | Registros | Campos | Campos sin valores |
|---|---:|---:|---:|
| Cotizaciones | 132 | 22 | 5 |
| Dataper | 69 | 9 | 1 |
| Liquidaciones | 0 | 0 | 0 |
| Material | 36 | 8 | 0 |
| PEXT | 394 | 74 | 0 |
| Rendicion | 5 | 74 | 37 |

Una columna vacía no se considera sobrante: puede ser un formulario, campo calculado o contrato de importación. Los campos sin referencias verificables se conservan para revisión. No se fusionan alias ni se eliminan columnas físicas por ausencia de datos.

## Correlaciones sobre la copia disponible

- Rendicion_a_WO: sin_coincidencia_local=5.
- Cotizaciones_a_WO: sin_referencia_wo=69, sin_coincidencia_local=63.
- Combustible_a_WO: .
- personal_por_proyecto: PEXT=69.
- Material_proyecto: total=36, sin_proyecto=0.
- SITE_proyecto: total=0, sin_proyecto=0.
- Generadores_proyecto: total=0, sin_proyecto=0.
- refacturable_detalle: referencias=0, sin_origen_actual=0, origen_otro_modulo=0.
- liquidacion_numero: referencias=0, sin_origen_actual=0, origen_otro_modulo=0.
- combustible_a_generador: .

Una coincidencia por WO es una comprobación de claves, no una aprobación del registro. Una referencia sin coincidencia puede corresponder a datos externos no exportados, una WO pendiente o una clave histórica: no se inventan enlaces ni se eliminan filas.

## Limpieza segura

Artefactos vacíos sin datos, declaraciones ni referencias detectados: 0.

Esta auditoría no modifica datos. No certifica adjuntos remotos, formularios Google/OneDrive, entregas de correo ni el aislamiento nuevo en todas las rutas nativas. Estos puntos necesitan comprobaciones específicas adicionales.
