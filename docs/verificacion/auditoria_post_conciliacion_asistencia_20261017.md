# Auditoría local de tablas y flujos

Copia local; no certifica integraciones externas ni datos no exportados

Integridad: ok. Relaciones foráneas rotas: 0. JSON inválido: 0.

## Inventario de tablas

| Tabla | Registros | Columnas físicas | Relaciones declaradas |
|---|---:|---:|---:|
| accesos_proyecto | 105 | 4 | 2 |
| app_config | 89 | 4 | 1 |
| asistencia_cambios | 0 | 6 | 2 |
| asistencia_diaria | 0 | 11 | 3 |
| conciliacion_origen | 75 | 7 | 1 |
| conformidad_usuario | 2 | 3 | 1 |
| cotizaciones | 0 | 15 | 1 |
| espacio_accesos | 0 | 4 | 3 |
| espacio_auditoria | 1 | 5 | 1 |
| espacio_clasificaciones | 0 | 2 | 2 |
| espacio_cuentas | 0 | 1 | 1 |
| espacio_perfiles | 7 | 3 | 0 |
| espacio_proyectos | 0 | 2 | 1 |
| filtros_maestros | 0 | 4 | 1 |
| historial_cambios | 3202 | 9 | 2 |
| kpi_configs | 0 | 7 | 1 |
| liquidacion_numero | 319 | 2 | 0 |
| notificaciones | 0 | 8 | 0 |
| nucleus_data | 10978 | 4 | 1 |
| nucleus_history | 0 | 5 | 1 |
| proyectos | 13 | 4 | 0 |
| refacturable_detalle | 0 | 4 | 1 |
| reglas_estado_manual | 0 | 6 | 1 |
| tablas_maestras | 0 | 6 | 1 |
| tecnicos | 0 | 6 | 1 |
| token_store | 0 | 3 | 0 |
| usuarios | 18 | 5 | 0 |

## Catálogos y columnas dinámicas

| Proyecto / módulo | Registros | Campos | Campos sin valores |
|---|---:|---:|---:|
| Combustible | 227 | 19 | 0 |
| Cotizaciones | 351 | 53 | 3 |
| Dataper | 163 | 11 | 3 |
| FLM - CLARO | 1 | 7 | 0 |
| FLM - ENTEL | 2081 | 162 | 93 |
| FLM - INTEGRATEL | 72 | 154 | 36 |
| FLM - PEXT | 0 | 40 | 40 |
| Generadores | 38 | 10 | 0 |
| Liquidaciones | 0 | 0 | 0 |
| Material | 32 | 8 | 0 |
| Rendicion | 1055 | 115 | 7 |
| SITE | 5583 | 20 | 0 |
| Site Name | 1375 | 5 | 0 |

Una columna vacía no se considera sobrante: puede ser un formulario, campo calculado o contrato de importación. Los campos sin referencias verificables se conservan para revisión. No se fusionan alias ni se eliminan columnas físicas por ausencia de datos.

## Correlaciones sobre la copia disponible

- Rendicion_a_WO: sin_coincidencia_local=893, coincidencia_unica=162.
- Cotizaciones_a_WO: sin_referencia_wo=143, sin_coincidencia_local=127, coincidencia_unica=80, varias_coincidencias_revisar=1.
- Combustible_a_WO: coincidencia_unica=191, sin_coincidencia_local=10, sin_referencia_wo=26.
- personal_por_proyecto: FLM - ENTEL=58, FLM - INTEGRATEL=38, FLM - CLARO=67.
- Material_proyecto: total=32, sin_proyecto=0.
- SITE_proyecto: total=5583, sin_proyecto=5583.
- Generadores_proyecto: total=38, sin_proyecto=38.
- refacturable_detalle: referencias=0, sin_origen_actual=0, origen_otro_modulo=0.
- liquidacion_numero: referencias=319, sin_origen_actual=0, origen_otro_modulo=0.
- combustible_a_generador: encontrado=227.

Una coincidencia por WO es una comprobación de claves, no una aprobación del registro. Una referencia sin coincidencia puede corresponder a datos externos no exportados, una WO pendiente o una clave histórica: no se inventan enlaces ni se eliminan filas.

## Limpieza segura

Artefactos vacíos sin datos, declaraciones ni referencias detectados: 0.

Esta auditoría no modifica datos. No certifica adjuntos remotos, formularios Google/OneDrive, entregas de correo ni el aislamiento nuevo en todas las rutas nativas. Estos puntos necesitan comprobaciones específicas adicionales.
