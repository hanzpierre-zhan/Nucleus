# Carga de Anton en Nucleus — 18/10/2026

La transacción de producción terminó y se verificó desde una conexión independiente: 30 tablas contrastadas contra el ensayo, 14.060 registros operativos en Nucleus. Se preservaron los registros existentes; únicamente se ampliaron dos configuraciones de columnas.

- 601 registros operativos añadidos: 394 de PEXT, 69 de Personal PEXT, 6 de Material y 132 de Cotizaciones.
- Dos cotizaciones históricas adicionales conservan su formato Huawei y su fecha original. Sus PDF se probaron sin regenerar ni alterar los documentos.
- Las 132 cotizaciones del módulo y los dos documentos históricos usan números PX únicos; se conserva la numeración original como procedencia.
- 15 cuentas añadidas y una cuenta coincidente conservada. Ante un nombre de usuario igual con nombre de cuenta distinto, se preservaron ambas: `hvargas` de Anton quedó como `anton_2_hvargas`, sin sustituir la cuenta ni las credenciales actuales de Nucleus.
- 7.807 entradas de historial importadas, con proyectos, usuarios y claves remapeados. Las asignaciones de acceso también se remapean.
- Se conservaron los datos actuales de cinco rendiciones y un material, archivando sus seis versiones de Anton para revisión.
- Los dos técnicos que ya pertenecían a Entel mantienen además su asociación independiente con PEXT.
- 8.566 filas de procedencia permiten detectar una carga ya realizada y evitar duplicados.

## Archivos y referencias preexistentes

Se verificaron 3.613 objetos actuales de Anton por tamaño y MD5 remoto, con SHA-256 del respaldo local. Ocho colisiones de archivos se resolvieron con nombres diferenciados y enlaces remapeados, sin sustituir archivos existentes. Se recuperó además una fotografía desde una versión histórica borrada en el origen: total preservado, 3.614 objetos.

Quedan dos referencias a fotos inexistentes en el origen actual y sin versiones recuperables: `CM-20260721-00000121/pex_7.jpg` y `CM-20260913-00000111/pex_4.jpg`. No se inventaron archivos sustitutos.

En las cotizaciones de Anton se identificaron 37 referencias WO sin coincidencia inequívoca en los datos disponibles (una es un texto pendiente). Se conservan como referencias históricas; no se crean órdenes ficticias ni se enlazan por semejanza. El inventario detallado permanece en el respaldo privado.

## Verificación y recuperación

Respaldo nativo de Nucleus anterior al corte y copia consistente tomada dentro del bloqueo de escritura de la transacción. Restauración del respaldo y aplicación del plan ensayadas en PostgreSQL local. Ensayo SQLite con integridad y claves foráneas correctas, comprobación de numeración y repetición sin duplicados. Pruebas de la aplicación: 389 aprobadas, más tres pruebas del importador.

Las evidencias, respaldos, versiones conflictivas y manifiestos completos permanecen en `backups/migracion-anton-final-20261018/`, excluido de Git. No se modificó ni suspendió el servicio de Anton. El código necesario para PEXT se guardó en el commit `8ba8756` y el usuario lo publicó junto con `d0eaf31`. Se comprobó en producción `/healthz` (200) y la disponibilidad del nuevo endpoint protegido de descarga (401 sin sesión, frente al 404 anterior).
