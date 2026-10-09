# Revisión previa al despliegue · 9 de octubre de 2026

## Cambios completados

FLM - CLARO y FLM - INTEGRATEL permiten registrar solicitudes sin Número de WO. Cada alta obtiene un CODIGO INTERNO permanente con formato CI-CL/IN-año-id. El número de WO permanece vacío y la tabla indica WO pendiente. El código sirve para abrir la solicitud y ordenar por creación. Al asignar el WO, se conservan el código interno y las relaciones con historial y cotizaciones; la clave principal cambia al WO asignado para mantener compatibilidad con las importaciones y la navegación existentes.

## Verificación ejecutada

- Suite completa de pruebas sobre base SQLite aislada, sin modificar la base real.
- Recorrido Cotizaciones: registro → cliente → aprobado/sustento → atendido, con permanencia del flujo paralelo de proveedor y acceso desde Refacturable.
- Recorrido Rendición: pendiente → validado → depositado → sustentado. Se verificó por separado la exigencia del correo .msg para validar solicitudes refacturables.
- Alta de WO pendiente y asignación posterior en Claro e Integratel, conservando el código interno.
- Login y conformidad persistente, permisos básicos, importación de ítems Excel, documentos del proveedor, montos y margen de Refacturable.
- Renderizado y sintaxis JavaScript de 10 módulos; sintaxis Python de app, modelos, configuración, blueprints y servicios.
- Arranque declarado en Procfile: gunicorn app:app --timeout 300 --workers 1.

## Límites y verificaciones pendientes en el servidor

No se ejecutó un despliegue ni una prueba visual interactiva de cada botón. Las pruebas de flujo usan registros aislados y simulan algunos efectos externos; no prueban Google Forms/Sheets, Backblaze, OneDrive o WhatsApp con las credenciales de producción. Las migraciones crean automáticamente la nueva tabla refacturable_detalle al arrancar; este recorrido se probó en SQLite, no en la base PostgreSQL de producción.

Los correos de validación de Rendición se guardan en EVIDENCIA_DIR/rendicion_correos. Debe existir almacenamiento persistente para esa ruta y para los demás adjuntos locales; en un servidor con disco efímero se pueden perder al reiniciar o desplegar. Confirmar SECRET_KEY estable, DATABASE_URL del entorno y credenciales de las integraciones habilitadas sin publicarlas en logs.

Refacturable contiene los campos ya definidos y el cálculo Cobra menos HW. Quedan pendientes del usuario los nombres poco legibles del esquema original y la definición de documentación/porcentaje. No se declara completo ese alcance funcional.

Esta revisión confirma los recorridos automatizados descritos, no garantiza todos los escenarios ni reemplaza la comprobación del entorno productivo.
