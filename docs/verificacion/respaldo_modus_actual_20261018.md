# Respaldo actual de Modus — 18/10/2026

Se leyó la configuración del servicio Modus desde la sesión autorizada de Render. Se guardó una copia lógica consistente de Neon mediante una transacción REPEATABLE READ / READ ONLY. No se importó la aplicación ni se ejecutaron migraciones sobre la fuente.

- 18 tablas; 12.770 filas totales, incluyendo historial y configuración.
- nucleus_data: 2.495 registros (2.005 WO FLM - INTEGRATEL, 37 Personal, 437 Material y 16 Cotizaciones).
- 5 usuarios; 10.157 entradas de historial.
- Integridad SQLite correcta, cero referencias foráneas rotas y cero JSON inválidos.
- B2: 34 objetos actuales, 8.843.483 bytes, descargados con verificación de ETag/tamaño y huella SHA-256 local. No incluye versiones antiguas del bucket.
- Staging exclusivo de Modus con procedencia por tabla e identificador original: 12.770 filas preservadas.

Archivos privados bajo backups/migracion-modus-20261018/, excluidos de Git. Las credenciales no se incorporan al código.

La copia lógica no sustituye un respaldo nativo PostgreSQL de esquema, roles, funciones y demás objetos. Se debe preparar el mecanismo de recuperación del destino antes de la importación definitiva.

No se modificó Neon ni B2 de Modus. No se importaron registros en Nucleus. Pendiente obtener acceso a la configuración de Nucleus para respaldar su base actual, inventariar el almacenamiento de destino, resolver colisiones y ensayar la unión.
