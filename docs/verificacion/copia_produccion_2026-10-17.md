# Copia actual de Nucleus publicado: verificación local

Este informe sustituye la conformidad limitada de los respaldos históricos.
La aplicación publicada fue autenticada mediante la cuenta existente autorizada.
Se descargó su exportación administrativa, sin adjuntos, el 17 de octubre de 2026
a las 13:38 (Lima). No se modificaron registros de producción.

## Fuentes y restauración

- Respaldo original: `backups/nucleus_produccion_20261017.zip`.
- SQLite restaurado: `backups/nucleus_produccion_actual_20261017.db`.
- La restauración conserva los IDs de producción; verifica cada conteo del
  manifiesto, integridad SQLite y ausencia de referencias sin destino.
- Se respaldó la base histórica anterior y se sustituyó la base local. El
  servicio del puerto 5001 corre otra copia de trabajo con red externa bloqueada.
- No se mezclaron los datos históricos de Anton, Modus y Nucleus con esta copia.
  Sus respaldos y staging permanecen guardados para ensayos posteriores.

## Conteos de la exportación actual

| Tabla / módulo | Filas |
|---|---:|
| Usuarios | 17 |
| Permisos de proyecto | 105 |
| Configuración | 89 |
| Historial de cambios | 3.202 |
| Registros operativos totales | 10.903 |
| Cotizaciones | 351 |
| Rendición | 1.055 |
| FLM - Entel | 2.077 |
| Combustible | 227 |
| Dataper | 163 |
| Material | 32 |
| Generadores | 38 |
| SITE | 5.583 |
| Site Name | 1.375 |

El servidor agrega una cuenta técnica local adicional para verificar las
pantallas; los 17 usuarios originales se conservan con sus IDs y contraseñas.
La exportación no incluye conformidades de usuario; puede solicitar su revisión
al iniciar sesión por primera vez en esta copia. No se aceptaron términos en
nombre del usuario al verificar el acceso original.

## Verificación visual en localhost:5001

- Cotizaciones: 351 en total, 11 en Registro, 205 en Cliente, 95 en Sustentar,
  9 en Atendido, 31 en Anulado; vista paralela de Proveedor: 66. Se observaron filas.
- Rendición: 1.055 en total, 66 Validación, 6 Depósitos, 333 Evidencia,
  269 Sustento, 61 Observado, 117 Atendido, 28 Archivar y 175 Anulado. Se observaron filas.
- Dos pruebas del restaurador pasaron: conservación de IDs/conteos y rechazo
  de exportaciones truncadas sin emitir un manifiesto de éxito.

## Límite de la exportación

Es una copia de las 13 tablas que exporta la aplicación, no un pg_dump completo
de Neon. El exportador omite token_store (intencionalmente), conformidades,
notificaciones y tablas derivadas de Liquidaciones. La copia actual sirve para
los registros y estados comprobados; no acredita recuperación completa de
PostgreSQL ni de datos no expuestos por ese exportador. Estos últimos requieren
una exportación ampliada o acceso de solo lectura a la base.

No se hizo commit ni despliegue.

SHA-256 del ZIP original: a0b3e9015ed425b1268b74766504c110df0698eab493dc68e6dbce0374834aae
