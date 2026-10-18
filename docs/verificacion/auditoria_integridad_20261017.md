# Auditoría local de tablas y flujos

Copia local; no certifica integraciones externas ni datos no exportados

Integridad: ok. Relaciones foráneas rotas: 0. JSON inválido: 0.

## Inventario de tablas

| Tabla | Registros | Columnas físicas | Relaciones declaradas |
|---|---:|---:|---:|
| accesos_proyecto | 105 | 4 | 2 |
| app_config | 89 | 4 | 1 |
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
| nucleus_data | 10903 | 4 | 1 |
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
| FLM - ENTEL | 2077 | 162 | 93 |
| FLM - INTEGRATEL | 1 | 123 | 114 |
| FLM - PEXT | 0 | 40 | 40 |
| Generadores | 38 | 10 | 0 |
| Liquidaciones | 0 | 0 | 0 |
| Material | 32 | 8 | 0 |
| Rendicion | 1055 | 115 | 7 |
| SITE | 5583 | 20 | 0 |
| Site Name | 1375 | 5 | 0 |

Una columna vacía no se considera sobrante: puede ser un formulario, campo calculado o contrato de importación. Los campos sin referencias verificables se conservan para revisión. No se fusionan alias ni se eliminan columnas físicas por ausencia de datos.

## Correlaciones sobre la copia disponible

- Rendicion_a_WO: sin_coincidencia_local=1019, coincidencia_unica=36.
- Cotizaciones_a_WO: sin_referencia_wo=143, sin_coincidencia_local=134, coincidencia_unica=74.
- Combustible_a_WO: coincidencia_unica=189, sin_coincidencia_local=12, sin_referencia_wo=26.
- personal_por_proyecto: FLM - ENTEL=58, FLM - INTEGRATEL=38, FLM - CLARO=67.
- Material_proyecto: total=32, sin_proyecto=0.
- SITE_proyecto: total=5583, sin_proyecto=5583.
- Generadores_proyecto: total=38, sin_proyecto=38.
- refacturable_detalle: referencias=0, sin_origen_actual=0, origen_otro_modulo=0.
- liquidacion_numero: referencias=319, sin_origen_actual=0, origen_otro_modulo=0.
- combustible_a_generador: encontrado=206, sin_coincidencia_local=21.

Una coincidencia por WO es una comprobación de claves, no una aprobación del registro. Una referencia sin coincidencia puede corresponder a datos externos no exportados, una WO pendiente o una clave histórica: no se inventan enlaces ni se eliminan filas.

## Limpieza segura

Artefactos vacíos sin datos, declaraciones ni referencias detectados: 0.

Esta auditoría no modifica datos. No certifica adjuntos remotos, formularios Google/OneDrive, entregas de correo ni el aislamiento nuevo en todas las rutas nativas. Estos puntos necesitan comprobaciones específicas adicionales.

## Fuentes locales anteriores, sin fusionar

- anton_local_20261017_original.db: integridad ok; WO por módulo {"PEXT": 378}.
- modus_local_20261017.db: integridad ok; WO por módulo {"FLM - INTEGRATEL": 2005}.

164 referencias de Rendición sin coincidencia en la base activa sí aparecen por clave en estas copias anteriores. Esto es evidencia de cobertura parcial de fuentes, no una autorización para fusionar o sobrescribir registros. No se importó ninguna fuente durante esta auditoría.

## Correcciones de flujo y validación

- Combustible por WO: requiere el módulo autorizado y una WO identificable en un proyecto permitido; rechaza una WO ajena o ambigua. Una sesión sin usuario vigente no obtiene datos.
- Duplicación de usuarios: conserva las asignaciones de proyectos/módulos y el aislamiento CuentaEspacio; crea permisos independientes para que editar al original no cambie al duplicado. Soporte no puede duplicar una cuenta Zeno.
- Pruebas parametrizadas en Entel, Integratel, Claro y Pext: Personal y Material → opciones de WO; WO → sustento de Cotizaciones; edición en WO → lectura actualizada desde Cotizaciones; WO → Rendición; Cotizaciones → Liquidaciones y margen derivado sin modificar el monto de origen.
- Suite completa: 280 pruebas, 0 fallos/errores. Se ejecutó sobre una base temporal con datos ficticios; no modifica los registros operativos de la copia local. No es una garantía de ausencia de defectos en todas las combinaciones.

## Decisión de limpieza

Se evaluaron 573 campos dinámicos. No se eliminó ninguna columna ni tabla: no hay artefactos de importación vacíos con ausencia demostrable de uso. Una parte de los campos sin valores corresponde a contratos de importación y pantallas dinámicas; borrarlos por estar vacíos rompería funcionalidades o impediría recibir datos futuros. El inventario JSON conserva el estado de cada campo y sus referencias de código. No se fusionaron alias ni se reescribieron registros históricos.

## Pendientes antes de dar conformidad total

1. Atribuir con evidencia los proyectos de 5583 sites y 38 generadores históricos. No asignarlos por suposición.
2. Conciliar las referencias de WO sin coincidencia y los 21 QR de combustible sin generador coincidente en la copia. Pueden depender de históricos, formatos o fuentes no unificadas; no deben borrarse como si fueran basura.
3. Completar la adaptación de CuentaEspacio a todos los flujos nativos: la separación nueva todavía conserva su piloto aislado. No confundir las pruebas de correlación de datos con una certificación de todas las rutas de autorización.
4. Validar sincronizaciones externas y adjuntos en un entorno controlado con sus fuentes; esta revisión local no hace envíos ni pruebas de escritura en Neon/Render/Google/OneDrive.

## Respaldo previo

Copia consistente: `backups/auditoria_integridad_20261017.previo.db`.
SHA-256: `bfcc5d402098a4182cb6312611998f87162b4d54e1634879188d8f46828edd24`.
Inventario detallado: `backups/auditoria_integridad_20261017.json`.
Pruebas: `backups/auditoria-pruebas-20261017-final.xml`.

No se ejecutó commit, push ni despliegue. Esta revisión encontró pendientes: no declarar la migración ni todos los flujos como completamente conformes para producción.

Verificación final: huella de los 10903 registros operativos idéntica al respaldo previo; no se alteraron sus valores. Servidor local reiniciado con las correcciones; consulta de combustible autenticada respondió 200.
