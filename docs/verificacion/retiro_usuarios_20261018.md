# Eliminación de cuentas con historial

El borrado físico de `usuarios` fallaba porque solo retiraba `accesos_proyecto` y anulaba el autor de `historial_cambios`. Dejaba referencias desde `conformidad_usuario`, asistencia y auditoría, entre otras tablas. PostgreSQL rechazaba el DELETE y la interfaz mostraba el error SQL completo.

La acción Eliminar ahora retira la cuenta mediante `services/usuarios.py`, dentro de la transacción existente. Revoca los permisos de proyectos y espacios, elimina la inscripción al piloto, invalida la contraseña y marca el usuario como eliminado. La cuenta desaparece de las listas de administración y validadores, pero conserva su ID, nombre y username para los registros históricos. El identificador original queda reservado y no se reutiliza para otra persona.

Las pantallas y API protegidas comprueban que la cuenta siga vigente: una sesión anterior deja de funcionar en la siguiente solicitud. Tampoco se admite iniciar sesión por nombre, cambiar la contraseña desde el acceso público o completar una aceptación de términos pendiente de una cuenta eliminada. Los errores inesperados se registran en el servidor y devuelven un mensaje sin SQL ni parámetros internos.

Pruebas de regresión con claves foráneas activadas y un usuario con conformidad, permisos, perfil de espacio, auditoría, historial y asistencia. Se comprueba retiro repetible, conservación de todas las referencias, ocultación de la cuenta, bloqueo de sesiones y verificación pendiente, protección contra eliminarse a uno mismo y validación del ID. No se ejecutaron eliminaciones de cuentas reales para probar el cambio. No requiere cambios de esquema.
