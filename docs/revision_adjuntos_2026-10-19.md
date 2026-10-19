# Revisión de adjuntos — 19 de octubre de 2026

## Alcance y evidencia

Revisión del guardado y lectura de fotos de Rendición, evidencia de WO,
correos de validación y adjuntos de cotizaciones. Inventario de la copia local
de SQLite abierto en modo de solo lectura: 10.903 registros y 2.595 referencias.

| Tipo | Referencias |
| --- | ---: |
| Fotos de WO | 1.108 |
| Adjuntos de cotizaciones | 198 |
| Fotos de Rendición | 1.071 |
| Correos de validación | 218 |

No se detectaron claves distintas del mismo proyecto que generasen la misma
carpeta saneada. Las 1.071 referencias de fotos de Rendición usan claves
transformadas; necesitan compatibilidad con el almacenamiento histórico.
Este dato no prueba que esos archivos estén perdidos.

## Correcciones

- Lectura de fotos históricas de B2 bajo la clave original del registro,
  aunque la URL use una clave saneada. Aplicada a Rendición, WO y lectura
  de evidencia para reportes. Se conserva la comprobación del alcance del usuario.
- Nuevas fotos del formulario: clave consistente con su URL y nombres únicos,
  para evitar sustituir otra imagen al cambiar el orden de los campos.
- Descargas del formulario: comprobar que el contenido sea una imagen válida;
  no guardar una página de inicio de sesión de Drive como JPG.
- Correos de validación: persistencia y descarga desde B2 cuando está configurado;
  la validación funciona sin la copia local. Una subida fallida no guarda una URL rota.
- Reemplazo de fotos: subir primero y limpiar después, sin borrar la evidencia
  anterior si falla la nueva subida. Copia local temporal en el disco de destino
  y sustitución al terminar, incluso cuando el directorio persistente esté en otro disco.
- Fotos locales de Rendición: respetar `EVIDENCIA_DIR` y conservar lectura
  de la carpeta histórica `static/evidencia`.
- Adjuntos de cotizaciones: buscar el registro con la clave original antes
  de sanearla para el nombre del archivo.
- Visor: distinguir un fallo de adjunto de Nucleus de un fallo de Drive.

## Validación

Suite general: 448 pruebas aprobadas y una omitida (Playwright no instalado).
Se añadieron pruebas de recuperación de claves antiguas, guardado y descarga,
persistencia sin disco local, fallo de subida sin pérdida del archivo anterior,
imagen válida frente a una página HTML y claves de cotización con espacios.
Las pruebas de permisos antiguas se ajustaron para usar el rol real de la cuenta,
que el servidor actualiza desde la base en cada solicitud.

Inventario reproducible:

```powershell
python scripts/auditar_adjuntos.py nucleus.db
```

## Trabajo ejecutado en producción

Se localizó el acceso conservado por la migración y se respaldaron 24.234 registros
antes de la reparación. No se imprimieron ni se incorporaron credenciales al repositorio.

- 1.268 referencias de Rendición revisadas: 899 imágenes válidas, 342 imágenes
  recuperadas o con su ruta corregida y 27 PDF recuperados conservando todas sus páginas.
- 3.607 rutas de fotos de WO revisadas: 3.604 válidas y tres eliminadas con versión
  histórica disponible. El usuario autorizó restaurarlas: se respaldaron y validaron
  las versiones históricas y se subieron nuevamente. Su lectura final está pendiente
  por la cuota del proveedor.
- Los PDF se guardaron con extensión `.pdf`; se actualizaron únicamente sus enlaces
  en las filas correspondientes, con respaldo previo y comparación del valor original.
- Se conservaron copias locales, hashes y diarios de las reparaciones bajo
  `backups/auditoria-adjuntos-20261019/`, fuera de Git.

Durante la verificación final de las tres fotos restauradas B2 comenzó a rechazar
las descargas con `AccessDenied`: límite de descarga o transacciones Class B
excedido. Se detuvieron las lecturas. Este bloqueo puede afectar a las descargas
habituales de la aplicación. No se modificaron los límites de gasto; se solicitó
al usuario revisar Backblaze → B2 Cloud Storage → Caps & Alerts. No debe repetirse
una auditoría masiva de descargas sin comprobar primero el presupuesto disponible.

La conexión Render sigue pendiente para desplegar las correcciones preventivas
y respaldar los correos que todavía solo residan en el disco de la instancia.

## Orden de tablas

El ordenador de fechas se aplicaba únicamente a columnas manuales; `Marca temporal`
es una columna importada. Ahora se configura en las definiciones finales, para
ambos tipos de columnas. También se comparan importes numéricos con separadores y
moneda, manteniendo vacíos al final en los dos sentidos.

Prueba de navegador aprobada: orden inicial de más reciente a más antiguo, clics
ascendente/descendente, cambio de mes, horas e importes. La corrección de tablas
está local y requiere despliegue.

## Cierre previo al commit

Suite completa final: 457 pruebas aprobadas, incluidas las pruebas de navegador;
no hubo pruebas omitidas. Continuación puntual programada para el 19 de octubre
de 2026 a las 19:05, hora de Perú, tras el reinicio del cupo diario de B2.
No se autorizaron cambios en los límites de gasto.
