# Propuesta inicial: proyectos separados, procesos conectados

Fecha: 17 de octubre de 2026. Estado: piloto local implementado; producción sin modificar.

## Experiencia del usuario

Arriba: proyecto activo (Claro, Entel, Entel - Pext, Integratel).
Al costado: Operación FLM, Personal / Dataper, Materiales, Combustible,
Sites, Cotizaciones, Rendición y Liquidaciones, según los permisos asignados.
Cambiar de módulo conserva el proyecto. Cada módulo tendrá su propia pantalla.
En móvil, el proyecto activo debe quedar visible y el menú ser plegable.

Un gestor ve su proyecto. El responsable central de cotizaciones puede ver
todos sus proyectos dentro de Cotizaciones. El certificador consolida las
liquidaciones autorizadas. Administración dispone de indicadores globales.
Toda vista consolidada muestra el proyecto de cada registro.

## Administración de accesos

Cada asignación combina usuario, proyecto, módulo y acciones permitidas.
Los perfiles (gestor, contrata, supervisor, certificador, finanzas, soporte,
zeno y futuros perfiles) son plantillas administrables, no permisos universales.
Consultar, crear, editar, exportar, validar, pagar y administrar son facultades
separadas. El acceso a un proyecto nuevo requiere asignación expresa.

Los controles se aplicarán a consultas, cambios, exportaciones y adjuntos,
también al acceder por enlace directo. Toda operación conserva su autor e historial.

## Identidad y relaciones

Separar proyecto de negocio (Claro, Entel, etc.) de módulo funcional.
Asignar explícitamente un proyecto a los registros que hoy viven en módulos
compartidos. Lo ambiguo queda pendiente de revisión; no se asigna por conjetura.
Conservar identificadores de origen y mapa de equivalencias para Anton y Modus.
Una persona puede tener una identidad común y múltiples asignaciones por
proyecto; no se fusionan fichas únicamente por nombre. Las existencias de
materiales, movimientos y responsabilidades se distinguen por proyecto.

## Pasos y criterios de avance

1. **Inventario y copia local verificada.** Leer la fuente sin modificarla,
   copiar tablas con identificadores y relaciones, comparar conteos y comprobar
   integridad. Excluir la descarga de archivos; conservar sus referencias.
2. **Entorno de pruebas aislado.** Crear una copia de trabajo del respaldo,
   bloquear envíos, sincronizaciones, tareas externas y acceso a almacenamiento
   real. No iniciar la aplicación con datos reales hasta revisar estas salidas.
   Desactivar credenciales de integración en la copia de trabajo; conservar el
   respaldo original protegido y fuera de Git. Evitar que adjuntos remotos se
   carguen automáticamente durante las pruebas.
3. **Mapa de datos y permisos.** Inventariar Anton y Modus por separado, definir
   equivalencias de proyectos, estados, usuarios y registros. Conciliar montos,
   duplicados, huérfanos y códigos repetidos antes de importar.
4. **Piloto de navegación y separación.** Implementar selector de proyecto y
   pantallas independientes en local. Probar usuarios de un proyecto y de varios,
   permisos por acción y accesos directos, incluida la vista móvil.
5. **Pruebas de procesos.** Solicitud → validación → depósito → sustento → cierre;
   cotización → aprobación → liquidación; personal y movimientos de materiales.
   Verificar vínculo entre registros y aislamiento de proyectos, sin duplicarlos.
6. **Ensayo de absorción.** Importar Anton y Modus en pruebas, conciliar cada
   tabla, sus montos y relaciones; revisar muestras con responsables de negocio.
7. **Puesta en producción planificada.** Respaldo nativo, ventana de transición,
   últimas diferencias, cambio de formularios e integraciones y plan de reversión.
   Mantener los sistemas anteriores para consulta durante la transición.

## Primer paso: hallazgos verificados

- La navegación actual mezcla proyectos FLM y módulos. Oculta accesos directos
  a Dataper, Material, SITE y Generadores cuando existen proyectos FLM asignados.
- Existe asignación de usuario a proyecto y restricciones, pero debe revisarse
  su aplicación uniforme antes de usarla como aislamiento integral.
- La réplica anterior solo copia `nucleus_data` y `app_config`; no es suficiente
  para reproducir usuarios, permisos, historiales y relaciones completas.
- El exportador ZIP administrativo enumera tablas manualmente y no incluye,
  entre otras del modelo actual, notificaciones, detalles refacturables,
  numeración de liquidaciones y conformidades de usuarios. No basta como única
  copia completa para este ensayo.
- Se añadió `scripts/copia_datos_local.py`: copia lógica de todas las tablas
  del esquema predeterminado a un SQLite nuevo, lectura consistente, sin cambios
  en origen ni descargas de adjuntos; conserva claves y verifica conteos,
  integridad, referencias y huella del archivo. No sustituye `pg_dump` para
  recuperación nativa de PostgreSQL (secuencias, funciones y otros objetos).
- No hay conexión de producción configurada en este entorno. El respaldo real
  está **pendiente de acceso**, no se ha realizado. Las pruebas sintéticas no
  acreditan compatibilidad con todas las tablas reales de Neon.

## Ejecutar la copia cuando esté disponible el acceso

Configurar `DATABASE_URL` de forma privada en el entorno, nunca en el código
ni en el chat. Ejecutar desde la raíz del repositorio:

```powershell
python scripts/copia_datos_local.py --destino backups/nucleus_datos_pruebas_20261017.db
```

El destino debe ser nuevo. El manifiesto adjunto contiene los conteos y la
huella; solo aparece tras completar las comprobaciones. Un fallo conserva
un archivo parcial que no debe usarse como copia verificada. La carpeta de
backups está excluida de Git. La copia puede incluir datos personales,
credenciales y configuración almacenada: acceso local restringido y uso
exclusivo para estas pruebas. No publicar ni conectar esta copia a servicios reales.

Próximo entregable: respaldo real verificado y copia de trabajo aislada; después,
piloto de la nueva navegación con un gestor de Claro y otro de Integratel.

## Avance implementado durante esta sesión

- Pantalla independiente `/espacios`, con selector de proyecto persistente en la
  URL y módulos separados: Operación, Personal, Materiales, Combustible, Sites,
  Generadores, Cotizaciones, Rendición y Liquidaciones.
- Consulta, búsqueda, detalle y exportación por proyectos autorizados; edición
  de campos existentes conservando las reglas anteriores y control de versión.
  Los estados y campos de auditoría no se editan como texto libre.
- Rendición reutiliza las acciones del flujo existente después de comprobar
  permiso y pertenencia del registro; no elude la asignación de validadores.
- Perfiles reutilizables con permisos por módulo y asignación por usuario y
  proyecto. Alta de nuevos proyectos desde administración, sin accesos automáticos.
- Registro auditable de perfiles, asignaciones, revocaciones y clasificación.
- Las cuentas inscritas usan exclusivamente las rutas del piloto cuando está
  habilitado. Revocar su último proyecto no reactiva las rutas anteriores.
- Entel y Entel - Pext se distinguen en este piloto. Los registros sin una
  atribución inequívoca requieren clasificación administrativa; no se duplican.
- Marca temporal ordenada de la más reciente a la más antigua, con comparación
  cronológica tanto en el piloto como en la tabla anterior de Rendición.
- Los dos enlaces de respuestas están añadidos al panel de formularios, plegable
  en móvil. Revisión del piloto en 320 px y escritorio; corregido desbordamiento móvil.

### Qué sigue siendo piloto

No habilitar todavía a usuarios de producción. El piloto cubre consulta,
exportación, edición de campos y flujo de Rendición. Las pantallas especializadas
de altas, generación de documentos/cotizaciones, adjuntos, certificación y edición
de Liquidaciones y dashboards completos todavía requieren adaptar sus rutas a
los nuevos permisos. Liquidaciones ofrece de momento consulta y exportación.
Los usuarios inscritos no pueden usar esos flujos por las rutas anteriores.
No se han reemplazado los módulos originales ni fusionado datos de negocio.

### Copias locales realmente obtenidas

| Fuente local | Tablas | Filas de todas las tablas | Resultado |
|---|---:|---:|---|
| Anton | 18 | 574 | Respaldo preservado; 6 referencias de historial a usuarios inexistentes |
| Modus | 18 | 9.725 | Copia lógica verificada, integridad y relaciones correctas |
| Staging conjunto | — | 10.299 | Procedencia y claves originales preservadas, sin fusionar IDs |

Se usaron las bases locales existentes: su última modificación corresponde al
15 de octubre (Anton) y 14 de octubre (Modus), respectivamente. Estas fechas no
acreditan hasta cuándo estaban sincronizadas. No son respaldos actuales de Neon.
La copia de trabajo de Modus se ha iniciado con la aplicación de Nucleus en
un proceso local separado; las migraciones solo afectan esa copia de ensayo.
Las seis referencias de Anton requieren revisión con la fuente autorizada;
no se eliminaron historiales ni se inventaron usuarios para ocultarlas.

Archivos guardados en la carpeta privada `backups/` (excluida de Git):

- `anton_local_20261017_original.db` y su manifiesto: copia preservada con incidencias.
- `modus_local_20261017.db` y su manifiesto: copia lógica verificada.
- `absorcion_anton_modus_staging_20261017.db` y su manifiesto: staging trazable.
- `inventario_migracion_20261017.json`: tablas, columnas, relaciones y conteos.

El intento de copia lógica de Anton produjo también un archivo parcial
`anton_local_20261017.db` SIN manifiesto; no debe utilizarse como copia validada.
Se conserva para diagnóstico. El respaldo original identificado arriba sí
preserva los datos y documenta los problemas existentes en origen.

### Probar en local

```powershell
python scripts/servidor_pruebas.py --demo --port 5058
# O usar una copia de datos verificada (crea otra base de trabajo):
python scripts/servidor_pruebas.py --backup backups/modus_local_20261017.db --port 5059
```

El servidor solo escucha en localhost; bloquea las conexiones externas del
proceso y los recursos remotos del navegador. Elimina tokens de integración
en la copia de trabajo, nunca en el respaldo ni en las fuentes. Genera una
cuenta local y guarda su acceso en `acceso-local.json` dentro del directorio
de ensayo, sin publicar contraseñas de producción. Las cookies de cada puerto
de ensayo son independientes.

Para preparar otro staging sin fusionar datos:

```powershell
python scripts/preparar_absorcion.py --anton backups/anton_local_20261017_original.db --modus backups/modus_local_20261017.db --destino backups/otro_staging.db
```

El despliegue normal mantiene `ESPACIOS_HABILITADOS` desactivado. El arranque
crea las tablas adicionales mediante el mecanismo idempotente existente; no
asigna usuarios, no mueve registros ni activa permisos automáticamente.

Pendiente externo: acceso privado a la base actual de Nucleus en Neon/Render,
copias actuales de los otros sistemas, conciliación con esas fuentes y decisión
de transición una vez completadas las pantallas especializadas y sus pruebas.

## Carga local unificada disponible en el puerto 5001

Se creó `backups/nucleus_unificado_ensayo_20261017.db` a partir de la base local
de Nucleus y los respaldos locales de Modus y Anton. No se descargó Neon.
El archivo conserva 2.540 registros operativos y seis cuentas, junto con
configuración, permisos, historiales y un mapa de procedencia de cada fila
importada (`ensayo_procedencia`). Las claves en conflicto no se sobrescriben.
PEXT de Anton se mapea al proyecto operativo FLM - PEXT.

Los seis historiales de Anton que apuntaban a usuarios inexistentes conservan
su fila original en la procedencia. En la copia de ensayo su usuario_id queda
en NULL para permitir comprobar las demás relaciones sin inventar usuarios.
El manifiesto documenta estas incidencias; los archivos fuente no se modificaron.

Se respaldó el Nucleus local anterior y se cargó el ensayo en `nucleus.db`.
El servicio en `http://127.0.0.1:5001` utiliza otra copia de trabajo aislada
de ese respaldo unificado, con bloqueo de conexiones externas y sin descargas
de adjuntos. El acceso de hvargas fue comprobado sin cambiar su contraseña.
Por el cambio de cookie de sesión puede ser necesario volver a iniciar sesión.

Conteos de los módulos en la base local:

| Módulo | Registros |
|---|---:|
| FLM - INTEGRATEL | 2.005 |
| FLM - PEXT | 378 |
| Dataper | 69 |
| Material | 30 |
| Cotizaciones | 5 |
| Rendicion | 53 |

Las vistas separadas por negocio mantienen pendientes los casos ambiguos.
El respaldo actual de producción y la conciliación con Neon siguen pendientes
de acceso. No se hizo commit ni despliegue.

## Actualización final: fuente de producción obtenida

Se consiguió autenticar la cuenta existente en Nucleus publicado y descargar
su exportación administrativa actual. El puerto 5001 utiliza ahora esta copia
de producción, sin mezclar respaldos históricos. Los números anteriores de
6 cotizaciones y 53 rendiciones ya NO describen la instancia activa.
Los conteos actuales comprobados en pantalla son 351 cotizaciones y 1.055
rendiciones. Se conservaron los 17 usuarios, 105 permisos y 3.202 historiales
que incluye el exportador. Detalles y limitaciones en
`docs/verificacion/copia_produccion_2026-10-17.md`.
