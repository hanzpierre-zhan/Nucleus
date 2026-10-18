# Navegación por proyecto y módulo (local)

El menú principal separa Proyectos, Módulos y Configuración. El selector ofrece los proyectos autorizados para el módulo activo. Con uno se muestra ese proyecto; con varios se permite el consolidado. El módulo se mantiene al cambiar de proyecto. Personal, Materiales, Sites, Mapa de Sites y Generadores tienen accesos directos.

Configuración agrupa Usuarios, Perfiles y accesos y Resources. La pantalla de Usuarios edita datos de cuenta y enlaza a la asignación de perfiles/proyectos; la antigua lista mezclada se oculta en la nueva navegación. La cuenta operativa solo adopta la nueva política cuando se le asignan accesos. Los administradores globales siguen siendo globales. No se reasignaron usuarios reales automáticamente.

Se prepararon siete perfiles sugeridos en la copia local, sin otorgar acceso a cuentas operativas. El mapa utiliza Leaflet local y únicamente puntos autorizados; en el sandbox no descarga cartografía externa.

Verificado en navegador: Rendición consolidada 1055 registros; Claro 489. Suite general: 260 tests; prueba adicional de cuatro proyectos y pruebas específicas: 18 tests del archivo test_espacios.py. Los conteos corresponden a la copia exportada, no a una consulta en vivo.

Alcance: navegación y permisos en el piloto local. Las vistas del espacio consultan/exportan datos, permiten edición de campos y acciones de Rendición mediante puentes con las validaciones existentes. La creación especializada de WO, documentos, adjuntos, importaciones y el flujo completo de cotizaciones/liquidaciones todavía requieren adaptación antes de reemplazar la interfaz operativa en producción. La bandera permanece deshabilitada por defecto. Los registros sin atribución de proyecto solo aparecen en el consolidado administrativo y requieren clasificación antes de exponerse a un gestor. No hay commit ni despliegue.

## Ajuste final: administración única en Usuarios

Se retiró la pantalla separada de perfiles y permisos y sus pestañas. Usuarios contiene datos de cuenta, rol, casillas Proyectos y casillas Módulos, con una sola operación de guardado atómica. La tabla separa proyectos y módulos. El enlace antiguo de administración redirige a Usuarios. Los perfiles de almacenamiento existentes quedan como detalle interno para conservar el aislamiento y la compatibilidad; no se eligen ni crean desde otra pantalla. Los módulos seleccionados se aplican al conjunto de proyectos marcado; las acciones dependen del rol. Zeno y soporte mantienen acceso global. Las pruebas se realizaron con usuarios de fixtures, sin guardar cambios de permisos en cuentas reales de la copia local.

## Recuperación de las pantallas originales

Por indicación del usuario, se recuperó la navegación original por FLM Entel, Claro, Integratel y Pext, y los módulos originales de Combustible, Cotizaciones, Rendición y Liquidaciones. El menú operativo deja de enlazar la tabla genérica. Las URL de /espacios de administración/globales redirigen al módulo nativo correspondiente. Usuarios conserva los grupos Proyectos y Módulos. Analytics continúa como grupo separado arriba de Módulos. No se modificaron ni sustituyeron los datos al recuperar las pantallas.

Verificado en navegador: los cuatro FLM muestran #data-grid nativo; Entel 2077 registros, Combustible 227, Cotizaciones 351 con pestañas y acciones, Rendición 1055 con pestañas y formularios. Suite específica: 21 tests aprobados.

Limitación explícita: la integración del aislamiento por proyecto en todos los flujos nativos NO está completa. La copia local no tenía ninguna CuentaEspacio ni AccesoEspacio real asignado al momento de recuperar las pantallas (ambas tablas con 0 filas). Se preserva el aislamiento del piloto para impedir que asignar una cuenta exponga datos de otros proyectos; las cuentas inscritas del piloto aún usan las rutas aisladas. No presentar esto como una migración terminada de permisos a los módulos nativos. Antes de activar usuarios reales con las nuevas asignaciones, adaptar y probar las consultas, acciones, adjuntos y exportaciones de cada módulo original. No se amplió acceso de ninguna cuenta ni se realizó despliegue.

## Catálogos comunes en el menú nativo

Los cuatro FLM están agrupados bajo Proyectos. Personal, Material, Sites, Mapa de Sites, Generadores, Combustible, Cotizaciones, Rendición y Liquidaciones aparecen bajo Módulos, conservando sus rutas y vistas originales. Se retiró el desplegable Recursos. Los enlaces directos a los catálogos limpian el contexto de un FLM previo para consolidar los proyectos autorizados. La autorización del cambio de módulo utiliza el mismo menú de permisos, permitiendo al gestor abrir los catálogos que ya tiene autorizados. Entel y Pext tienen identificadores de familia distintos.

Prueba nativa con cuenta de fixture (AccesoProyecto) asignada a Claro e Integratel: Personal contiene ambos y excluye Entel, incluso después de abrir un enlace de contexto de un solo FLM. Navegador con administrador local: Personal 163 registros, tabla nativa; FLM Entel 2077, tabla nativa, cero desplegables flm-resource-menu. Las restricciones nuevas de CuentaEspacio conservan el aislamiento del piloto descrito arriba; esta prueba nativa corresponde al sistema de accesos original y no implica haber terminado aquella adaptación.

## Personal: proyecto, supervisor y estado

Conteos cotejados entre trabajo.db y el respaldo de producción: Entel 58, Integratel 38, Claro 67, total 163. No se volvió a importar ni duplicar personal. Se verificaron por filtro en navegador Integratel (38/163) y Claro (67/163); se dejó Integratel visible en la pestaña de revisión. La tabla inicialmente presentaba las filas de Entel primero y los indicadores antiguos solo distinguían FLM/PEXT. Se añadieron indicadores de los cuatro proyectos.

El formulario y la presentación usan nombres completos FLM - ENTEL, FLM - INTEGRATEL, FLM - CLARO, FLM - PEXT. Un usuario con un solo proyecto lo obtiene automáticamente; con varios debe elegir uno autorizado. El servidor valida la pertenencia. Se añadió SUPERVISOR al formulario y tabla; los nuevos registros de gestor/supervisor capturan el nombre de quien registra, sin inventar el responsable de históricos. ACTIVO/CESADO se presentan con etiquetas verdes/rojas y texto e icono; los registros históricos no se reescriben por esta presentación.
