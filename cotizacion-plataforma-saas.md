# COTIZACIÓN DE SERVICIOS — PLATAFORMA WEB SAAS TIPO NUCLEUS

**N° de cotización:** COT-2026-001  
**Fecha de emisión:** 28 de octubre de 2026  
**Validez:** 30 días calendario  
**Moneda:** Soles peruanos (PEN) — IGV 18% incluido donde se indica  

---

## 1. Datos del proveedor

| Campo | Detalle |
|---|---|
| Proveedor | Nucleus Solutions SAC |
| RUC | 20601234567 |
| Domicilio | Av. Javier Prado Este 4200, San Isidro, Lima, Perú |
| Contacto comercial | ventas@nucleussolutions.pe |
| Teléfono | +51 987 654 321 |
| Responsable técnico | Equipo de 2 personas (1 Líder Full-Stack / PM + 1 Desarrollador Full-Stack y QA) |

## 2. Datos del cliente

| Campo | Detalle |
|---|---|
| Cliente | [Nombre de la empresa solicitante] |
| RUC | [RUC del cliente] |
| Contacto | [Nombre del contacto] |
| Correo | [correo@cliente.pe] |
| Teléfono | [teléfono] |

> Nota: los datos del cliente se completarán en la versión final una vez confirmado el contacto y el alcance definitivo.

---

## 3. Resumen ejecutivo

Se propone el diseño, desarrollo e implementación de una **plataforma web SaaS** inspirada en Nucleus, orientada a la gestión integral de cotizaciones, sustento de obra, liquidaciones y expedientes documentales para operaciones en el mercado peruano.

La solución permitirá:
- Importar datos desde Excel/CSV y APIs externas.
- Gestionar cotizaciones con estados, aprobaciones y bloqueo por aprobación.
- Registrar sustento fotográfico y documental por WO/ítem.
- Generar expedientes ZIP con documentos organizados.
- Controlar liquidaciones, avance documental y seguimiento operativo.
- Operar en modalidad SaaS con usuarios, roles y auditoría.

Dado que el cliente aún no ha detallado todos los requerimientos, esta cotización se presenta en **alcance base + módulos opcionales**, de forma que pueda ajustarse sin recalcular todo el proyecto.

---

## 4. Alcance funcional

### 4.1 Módulo base (incluido)

1. **Autenticación y seguridad**
   - Login por usuario/contraseña.
   - Roles: administrador, gestor, consulta.
   - Auditoría de cambios relevantes.
   - Sesiones seguras y control de permisos.

2. **Importación de datos**
   - Carga masiva desde Excel/CSV.
   - Validación de columnas y datos obligatorios.
   - Vista previa antes de confirmar importación.
   - Registro de errores de carga.
   - Exportación de datos filtrados a Excel.

3. **Cotizaciones**
   - Registro y edición de cotizaciones.
   - Estados: Pendiente, En aprobación, Aprobado, Atendido, Observado, Rechazado, Cancelado.
   - Generación de PDF de cotización.
   - Bloqueo de edición después de la aprobación (solo administrador).
   - Adjuntos de correo, cotización de proveedor y factura de proveedor.
   - Eliminación controlada de adjuntos.

4. **Sustento de obra**
   - Ficha por WO con datos del sitio, responsable y fechas.
   - Evidencia fotográfica por ítem y por fase (antes, durante, después).
   - Fotos de ubicación del sitio.
   - Reemplazo y eliminación de fotos.
   - Validación de tamaño y formato de imágenes.

5. **Liquidaciones**
   - Listado de casos aprobados.
   - Seguimiento documental: sustento, factura, correo, cotización.
   - Avance porcentual por caso.
   - Campos manuales: código AJB/EJB, expense, estado de liquidación, observación, mes de cierre, número de PO.
   - Descarga individual de expediente ZIP.
   - Descarga masiva de varios expedientes en un solo ZIP.

6. **Expedientes documentales**
   - Estructura plana: 4 documentos principales por caso.
   - Sustento consolidado en ZIP interno.
   - Factura del proveedor.
   - Correo del cliente con nombre de asunto.
   - Cotización generada en PDF.
   - Límite de tamaño y validación de archivos.

7. **Dashboard y reportes**
   - Resumen por estado.
   - Filtros por gestor, estado, fechas y proyecto.
   - Tarjetas de totales y montos.
   - Exportación a Excel.

8. **Administración**
   - Gestión de usuarios y permisos.
   - Configuración de columnas y opciones.
   - Respaldos y recuperación básica.

### 4.2 Módulos opcionales (cotizados por separado)

| Módulo opcional | Descripción | Precio estimado |
|---|---|---|
| Integración con correo corporativo | Lectura/adjunto automático desde buzones | S/ 6,500 |
| Firma digital de documentos | Firma electrónica de cotizaciones y expedientes | S/ 8,000 |
| App móvil para carga de evidencias | Captura de fotos desde celular | S/ 12,000 |
| Integración con ERP/contabilidad | Envío de datos a sistema contable | S/ 9,000 |
| Multiempresa / multi-tenant avanzado | Aislamiento por empresa y facturación | S/ 10,000 |
| BI avanzado | Dashboards ejecutivos y KPIs | S/ 7,500 |

---

## 5. Entregables

1. Código fuente de la plataforma web.
2. Base de datos inicial y scripts de migración.
3. Manual de usuario y manual técnico.
4. Capacitación de 4 horas para usuarios clave.
5. Despliegue en entorno productivo.
6. Soporte post-implementación por 3 meses.
7. Documento de alcance y acta de conformidad por hito.

---

## 6. Cronograma conservador

Se propone un plazo total de **20 semanas** (5 meses), considerando validaciones, ajustes y pruebas. Este plazo es deliberadamente conservador para evitar compromisos imposibles de cumplir.

| Fase | Semanas | Actividades principales |
|---|---:|---|
| 1. Levantamiento y diseño | 1-3 | Reuniones, definición de requerimientos, prototipo y diseño de base de datos |
| 2. Base técnica y seguridad | 4-6 | Autenticación, roles, estructura SaaS, importación de datos |
| 3. Cotizaciones y aprobaciones | 7-9 | Flujo de cotización, PDF, adjuntos, bloqueo por aprobación |
| 4. Sustento y evidencias | 10-12 | Ficha por WO, fotos, carga, reemplazo y eliminación |
| 5. Liquidaciones y expedientes | 13-15 | Listado, avance documental, ZIP individual y masivo |
| 6. Dashboard y reportes | 16-17 | Filtros, tarjetas, exportaciones |
| 7. Pruebas y ajustes | 18-19 | QA, corrección de errores, pruebas con datos reales |
| 8. Despliegue y capacitación | 20 | Pase a producción, capacitación y entrega |

> El cronograma puede ampliarse si el cliente solicita cambios de alcance o integraciones adicionales.

---

## 7. Equipo y dedicación

| Rol | Personas | Dedicación estimada |
|---|---:|---|
| Líder Full-Stack / PM | 1 | 60% del proyecto |
| Desarrollador Full-Stack y QA | 1 | 80% del proyecto |

Total estimado: **2 personas**, sin ampliación de equipo en esta propuesta.

---

## 8. Propuesta económica

### 8.1 Desarrollo del proyecto

| Concepto | Monto (PEN) |
|---|---:|
| Levantamiento, diseño y arquitectura | 8,000 |
| Desarrollo backend (API, seguridad, datos) | 18,000 |
| Desarrollo frontend (interfaz, tablas, modales) | 14,000 |
| Módulo de cotizaciones y aprobaciones | 6,000 |
| Módulo de sustento y evidencias | 6,000 |
| Módulo de liquidaciones y expedientes ZIP | 7,000 |
| Dashboard, reportes y exportaciones | 4,000 |
| Pruebas, QA y correcciones | 5,000 |
| Despliegue, documentación y capacitación | 4,000 |
| **Subtotal desarrollo** | **72,000** |

### 8.2 Infraestructura y servicios (primer año)

Stack tecnológico propuesto:
- Hosting: Render
- Base de datos: Neon (PostgreSQL)
- Almacenamiento de archivos: Backblaze B2

| Concepto | Monto anual (PEN) |
|---|---:|
| Render (aplicación web y workers) | 4,200 |
| Neon (base de datos PostgreSQL) | 2,400 |
| Backblaze B2 (archivos, fotos y ZIPs) | 1,200 |
| Dominio, SSL y monitoreo | 600 |
| **Subtotal infraestructura** | **8,400** |

### 8.3 Operación SaaS

| Concepto | Monto mensual (PEN) |
|---|---:|
| Licencia SaaS por empresa (hasta 15 usuarios) | 1,200 |
| Soporte y mantenimiento evolutivo | 1,800 |
| **Subtotal mensual** | **3,000** |

### 8.6 Escenario para 50 usuarios iniciales

Para una operación con 50 usuarios iniciales, se recomienda el siguiente esquema:

| Concepto | Monto (PEN) |
|---|---:|
| Implementación inicial (escenario acelerado con IA) | 18,000 |
| Infraestructura primer año (Render + Neon + B2) | 9,000 |
| **Total inicial sin IGV** | **27,000** |
| IGV 18% | 4,860 |
| **Total inicial con IGV** | **31,860** |

Operación mensual estimada para 50 usuarios:

| Concepto | Monto mensual (PEN) |
|---|---:|
| Plataforma base SaaS | 1,500 |
| 50 usuarios x S/ 45 | 2,250 |
| Soporte y mantenimiento | 1,200 |
| **Subtotal mensual sin IGV** | **4,950** |
| IGV 18% | 891 |
| **Total mensual con IGV** | **5,841** |

Notas:
- El costo por usuario puede bajar si se superan los 100 usuarios.
- El almacenamiento B2 se factura según consumo real de evidencias y expedientes.
- Si el cliente requiere migración masiva de datos históricos, se cotiza por separado.

Si el equipo utiliza herramientas de IA para acelerar el desarrollo, el costo puede reducirse, pero no de forma proporcional en todas las áreas. La IA ayuda mucho en boilerplate, CRUD, pruebas unitarias y refactorización, pero no elimina el trabajo de diseño de negocio, validaciones, seguridad, migraciones, integración con datos reales y validación con el cliente.

| Concepto | Escenario tradicional (PEN) | Escenario acelerado con IA (PEN) |
|---|---:|---:|
| Desarrollo del proyecto | 72,000 | 36,000 |
| Infraestructura primer año | 8,400 | 8,400 |
| Total inicial sin IGV | 80,400 | 44,400 |
| IGV 18% | 14,472 | 7,992 |
| **Total inicial con IGV** | **94,872** | **52,392** |
| Operación mensual SaaS | 3,540 | 3,540 |

**Cuándo usar el escenario acelerado:**
- El cliente acepta un MVP más estándar.
- Se reutilizan plantillas y componentes existentes.
- El alcance se mantiene estable.
- El cliente valida rápido y no pide cambios constantes.

**Riesgos del escenario acelerado:**
- Mayor dependencia de revisión humana en seguridad y datos.
- Posible retrabajo si el cliente cambia requerimientos.
- Menor tiempo para pruebas con datos reales.
- Riesgo de código generado que no cubre casos límite.

**Recomendación comercial:** presentar el escenario tradicional como propuesta principal y ofrecer el escenario acelerado como opción con menor costo, dejando claro que reduce tiempo de desarrollo pero no reemplaza validación, seguridad ni acompañamiento.

| Concepto | Monto (PEN) |
|---|---:|
| Desarrollo del proyecto | 72,000 |
| Infraestructura primer año | 8,400 |
| **Total inicial (sin IGV)** | **80,400** |
| IGV 18% | 14,472 |
| **Total inicial con IGV** | **94,872** |

Operación mensual estimada: **S/ 3,000 + IGV = S/ 3,540 por mes**.

---

## 9. Forma de pago sugerida

| Hito | Porcentaje | Monto (PEN) | Condición |
|---|---:|---:|---|
| Firma del contrato / inicio | 30% | 24,120 | Anticipo |
| Aprobación de diseño y base de datos | 20% | 16,080 | Hito 1 |
| Entrega de cotizaciones, sustento y liquidaciones | 30% | 24,120 | Hito 2 |
| Puesta en producción y capacitación | 20% | 16,080 | Cierre |
| **Total** | **100%** | **80,400** | Sin IGV |

> Los montos anteriores corresponden al subtotal sin IGV. El IGV se factura según la normativa vigente.

---

## 10. Supuestos

1. El cliente proporcionará usuarios de prueba y datos de ejemplo.
2. El cliente designará un responsable para validaciones semanales.
3. Las integraciones externas (ERP, correo corporativo, firma digital) no están incluidas salvo que se contraten como opcionales.
4. El alcance final se confirmará mediante acta de requerimientos.
5. Los cambios fuera del alcance se cotizarán por separado.
6. El hosting y servicios cloud se facturan según consumo real si superan los valores estimados.

---

## 11. Exclusiones

- Compra de licencias de terceros no especificadas.
- Integración con sistemas legacy no documentados.
- Migración masiva de datos históricos fuera del alcance base.
- Soporte 24/7 (se puede cotizar por separado).
- Desarrollo de app móvil nativa (solo web responsive incluida).

---

## 12. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Requerimientos cambiantes | Trabajo por hitos y actas de cambio |
| Datos inconsistentes en importación | Validaciones y vista previa |
| Retrasos por validación del cliente | Cronograma conservador y reuniones semanales |
| Sobre costo de infraestructura | Monitoreo mensual y alertas de consumo |
| Dependencia de 2 personas | Documentación técnica y respaldos |

---

## 13. Condiciones comerciales

- Los precios son referenciales y pueden ajustarse tras el levantamiento detallado.
- La propuesta no obliga a la contratación hasta la firma del contrato.
- El soporte incluido es de 3 meses posteriores al despliegue.
- La propiedad intelectual se transfiere al cliente tras el pago total.
- Se aplican las leyes peruanas y la facturación electrónica correspondiente.

---

## 14. Aceptación

| Proveedor | Cliente |
|---|---|
| Nombre: ____________________ | Nombre: ____________________ |
| Cargo: ____________________ | Cargo: ____________________ |
| Firma: ____________________ | Firma: ____________________ |
| Fecha: ____________________ | Fecha: ____________________ |

---

**Observación final:** Esta es una cotización inicial para negociación. Dado que el cliente aún no ha detallado sus necesidades reales, se recomienda realizar una reunión de levantamiento antes de cerrar el alcance y el precio final.
