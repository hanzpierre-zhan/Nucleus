# Conciliación y asistencia en el ensayo local

Fecha: 17 de octubre de 2026. Entorno: http://127.0.0.1:5001. Sin commit, publicación ni cambios en producción.

## Resultado de la conciliación

Se recuperaron 75 WO referenciadas que faltaban en la base activa: 4 de Entel y 71 de Integratel. Se resolvieron 135 referencias mediante coincidencias exactas de clave y proyecto con las copias locales de origen. Los 10.903 registros originales conservaron su contenido; ahora hay 10.978 registros en nucleus_data. Cada incorporación tiene procedencia y copia del contenido de origen en conciliacion_origen. No se sobrescribieron estados ni importes existentes.

Respaldos anteriores a la intervención: backups/previo_conciliacion_asistencia_20261017.db y backups/conciliacion_aplicada_20261017.previo.db. Detalle privado: backups/conciliacion_aplicada_20261017.json. Estos archivos se mantienen fuera del código versionado.

Corrección del diagnóstico previo: combustible se relaciona con Generadores mediante QR ASIGNADO, no por la clave interna del registro. Los 227 movimientos encuentran su generador usando ese campo. El anterior resultado de 21 referencias sin generador era una falsa alarma del auditor; no fue necesario duplicar generadores.

La auditoría posterior verifica 27 tablas, integridad SQLite correcta, cero relaciones foráneas rotas y cero JSON inválidos. Ver auditoria_post_conciliacion_asistencia_20261017.md.

## Pendientes que impiden certificar todo el histórico

El plan conserva 1.073 entradas de referencias sin recuperación inequívoca. No equivalen necesariamente a 1.073 registros rotos: incluyen claves provisionales, referencias no disponibles y desacuerdos de proyecto. No se inventaron coincidencias. La auditoría posterior aún identifica 893 rendiciones, 127 cotizaciones y 10 movimientos de combustible sin WO coincidente; una cotización tiene varias coincidencias posibles. Estos conteos tienen criterios distintos al plan de recuperación.

Los 5.583 sites y 38 generadores no tienen una asignación histórica explícita de proyecto. Para repartirlos hace falta una fuente de pertenencia comprobable; un recurso podría compartirse. No se asignaron por suposición. Tampoco se eliminaron columnas vacías sin demostrar que carecen de función.

Se impide que una misma clave WO presente en varios proyectos mezcle rendiciones de negocios distintos. La resolución de sustento exige una coincidencia única. Esto evita enlazar por accidente y deja visibles los casos que necesitan clasificación.

La copia administrativa disponible no es un volcado completo de Neon. Las integraciones externas permanecen bloqueadas durante el ensayo; estas pruebas no certifican envíos reales ni datos excluidos de la exportación. La adaptación de todas las rutas nativas al esquema nuevo de permisos todavía requiere una revisión específica antes de desplegarlo.

## Asistencia: primera versión operativa

Acceso: Personal → Control de asistencia. Conserva la pantalla original de Personal.

1. Elegir fecha y proyecto, o todos los proyectos autorizados; pulsar Consultar.
2. La gestora o supervisor selecciona personas verificadas y pulsa Marcar presentes los seleccionados, o marca cada caso individualmente.
3. Estados: Presente, Falta, Permiso, Descanso, Vacaciones, Licencia y Sin marcar. Se admite observación.
4. Guardar cambios confirma únicamente las modificaciones. Sin marcar no genera una falta automática.
5. Resumen mensual permite consultar los días registrados y exportar CSV.

El servidor vuelve a consultar los permisos de la cuenta. Se requiere Personal y los proyectos correspondientes; gestores y supervisores pueden registrar. Zeno y soporte tienen el alcance administrativo. Las consultas permiten consolidar solo los proyectos autorizados. Una cuenta de consulta no puede modificar marcas.

Una persona tiene una marca por proyecto y día. Las modificaciones guardan autor, fecha y valores anteriores/nuevos. Si dos personas editan la misma marca, el segundo guardado desactualizado se rechaza y requiere consultar otra vez. Se mantienen nombre y documento históricos aunque cambie el catálogo. No se permiten eliminaciones de Personal con asistencia vinculada; las consolidaciones de importación conservan esos registros y los cuentan como omitidos. Para una baja se utiliza Cesado.

No calcula remuneraciones ni genera decisiones de planilla. No se registró asistencia ficticia sobre el personal copiado. La interfaz real se verificó con 163 personas sin marcar y el mes sin marcaciones. Los guardados y cambios se probaron con personas ficticias en bases de prueba.

Validación: suite completa de 291 pruebas aprobada; después se agregaron tres casos de regresión (histórico con cambio de proyecto y CSV seguro en dos modos de permisos, y WO compartida entre proyectos). Los 17 casos de asistencia/rendición, incluidos los nuevos, aprobaron. git diff --check sin errores de espacios.

## EPP: propuesta posterior

Agregar otra herramienta dentro de Personal: entregas por trabajador con equipo, talla, cantidad, fecha, vencimiento, devolución y constancia de recepción. Reutilizar la persona y su proyecto, con historial de reposiciones. Se pospone su implementación para priorizar asistencia.
