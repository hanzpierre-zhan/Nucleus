# Preparación de Anton hacia Nucleus — 18/10/2026

Origen actual confirmado por el usuario y revisado en Render: servicio `anton`, `srv-danc3gjtqb8s73bdbjag`, URL `https://anton-ibm8.onrender.com`, repositorio `hanzpierre-zhan/Anton`, commit `44630619dbb1412cc51a84724e7ef59f9239461b`. El servicio antiguo `Py.Anton` de otra cuenta se descartó y no se respaldó como origen.

La base de la aplicación está en Supabase, PostgreSQL 17.6, esquema `public`. Se verificó la conexión configurada en Render y se leyó dentro de una transacción de solo lectura. No se cambió su puerto, credenciales, configuración ni aplicación.

## Respaldos y controles completados

- Copia lógica consistente de las 18 tablas de la aplicación: 636 registros operativos, integridad correcta, cero relaciones foráneas rotas y cero JSON inválidos.
- Respaldo nativo del esquema `public`, verificado con `pg_restore --list` y restaurado correctamente en PostgreSQL local: 18 tablas y 636 registros operativos. No incluye esquemas de administración de Supabase ajenos a la aplicación. El servidor de prueba quedó detenido.
- Copia lógica de Nucleus posterior a Modus: 28 tablas, 13.454 registros operativos al obtenerla. La carga final necesitará otro respaldo de corte actualizado.
- Inventario actual de B2 de Anton y Nucleus: solo objetos actuales, sin versiones históricas borradas. El respaldo de archivos se registra en la actualización final de este informe.

La primera copia local del 16/10 tenía 480 registros y seis referencias rotas de historial. Esos datos preliminares quedaron sustituidos por la revisión de Supabase: las seis referencias rotas no aparecen en el origen real. No se eliminó ni reparó información en Anton.

## Comparación del origen real

| Datos | Resultado contra Nucleus |
|---|---|
| PEXT → FLM - PEXT | 394 claves nuevas |
| Personal PEXT | 67 documentos nuevos y 2 documentos que ya figuran bajo FLM - ENTEL |
| Material | 29 coincidencias exactas, 6 claves nuevas y 1 clave conflictiva |
| Cotizaciones | 132 registros: 1 clave nueva y 131 claves coincidentes con datos distintos |
| Rendición | 5 claves coincidentes con datos distintos |
| Cuentas | 14 nombres de usuario nuevos, 1 homónimo con nombre distinto y 1 cuenta coincidente |

Las 131 cotizaciones coincidentes contienen diferencias de estado y datos operativos: no son duplicados exactos ni cambios meramente visuales. La mayoría corresponde al cliente ENTEL (128 colisiones), además de INTEGRATEL (1) y CLARO (2). No se deben reemplazar las cotizaciones vigentes de Nucleus por la copia de Anton sin conciliar los casos.

Los dos documentos de Personal coincidentes pertenecen a Entel en Nucleus y a PEXT en Anton. Su participación en PEXT debe conservarse como asociación separada; no cambiar el proyecto del registro existente ni omitirlos como si ya fueran parte de PEXT. El comparador distingue documento y proyecto; no deduplica únicamente por documento.

Además de las cotizaciones dinámicas, existe una tabla física `cotizaciones` con dos filas. El importador deberá contemplarla y remapear sus dependencias. Hay 7.807 entradas de historial, cuatro reglas en `tablas_maestras`, 45 asignaciones de acceso y ocho notificaciones que también deben evaluarse. No se reutilizarán tokens, contraseñas o permisos por coincidencia de nombre de usuario.

## Archivos B2

Anton contiene 3.613 objetos actuales, 475.726.754 bytes. La comparación con Nucleus encontró 1.979 claves idénticas por tamaño y ETag, 1.626 claves nuevas y ocho claves con contenido diferente.

Se reutilizan las 1.979 copias locales existentes después de verificar su SHA-256; así se evita descargarlas otra vez. Se respaldan desde Anton únicamente los otros 1.634 objetos, incluidos los ocho conflictivos, manteniendo su procedencia. No se subieron archivos a Nucleus ni se sobreescribió ningún objeto. Las ocho colisiones requieren otra clave de almacenamiento y remapeo de enlaces si se incorporan ambas versiones; nunca reemplazar a ciegas el archivo actual.

## Formato propio de PEXT

El catálogo se mapeará de `PEXT` a `FLM - PEXT`. Ambos usan la clave `Numero de WO`; el origen tiene 74 campos presentes en sus datos. El código local de Anton mantiene controladores propios en `pext_compat` para PEXT y Cotizaciones. El cambio del nombre del catálogo no demuestra por sí solo compatibilidad de sus formularios y flujos.

El inventario local de rutas detectó dos URLs sin equivalente literal en el árbol principal de Nucleus (`/analytics/integratel`, `/api/clean`); las otras rutas también necesitan comprobación de comportamiento. Ese inventario no certifica el código desplegado ni obliga a trasladar herramientas administrativas antiguas.

## Próxima etapa antes de importar

1. Resolver las colisiones de Cotizaciones, Rendición y Material comparando campos, fechas e historial. Preparar diferencias revisables y conservar Nucleus mientras se decide.
2. Diseñar la representación de las dos asociaciones adicionales de Personal a PEXT sin alterar Entel.
3. Resolver la cuenta homónima antes de vincular permisos o historial.
4. Adaptar un importador propio de Anton, con procedencia separada de `migracion_modus_origen`, remapeo de IDs, enlaces, marcadores de notificación y tratamiento explícito de los ocho archivos conflictivos.
5. Ensayar con los formatos PEXT, la repetición sin duplicados, validación de adjuntos y reversión selectiva. Después, preparar el corte con respaldos actuales y un plan revisable.

**Estado de producción:** ninguna fila ni archivo de Anton se importó todavía en Nucleus. Tampoco se modificó el origen. Estos son los preparativos y respaldos; no una migración terminada.

## Herramienta de comparación

`scripts/preparar_anton.py` compara dos respaldos SQLite en lectura y genera un JSON nuevo. No importa la aplicación ni incorpora secretos. Tres pruebas aprobaron: comparación por documento/proyecto sin modificar bases, rechazo de escrituras y archivos inexistentes, y distinción de una persona con el mismo documento en otro proyecto.

Los secretos, diferencias detalladas y respaldos están en `backups/preparacion-anton-20261018/`, excluido de Git. Los documentos y pruebas publicados no incluyen datos personales ni conexiones privadas.


## Cierre del respaldo de archivos

Respaldo completo: 3.613 objetos actuales de Anton, 475.726.754 bytes. Se reutilizaron 1.979 archivos y se descargaron 1.634. Todos los archivos se releyeron desde el respaldo local y coincidieron por tamaño y SHA-256 con su manifiesto. No se modificaron límites de B2 ni facturación. Preparativos y respaldos finalizados; conciliación e importación pendientes.
