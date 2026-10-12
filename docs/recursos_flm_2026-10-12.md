# Recursos de los tres FLM

Los accesos se encuentran en el botón Recursos de FLM - ENTEL, FLM - INTEGRATEL y FLM - CLARO. Personal utiliza Dataper; Material utiliza el catálogo Material. Ambos se filtran por PROYECTO. Sites y Mapa de Sites utilizan el maestro SITE común.

## Separación futura

Las rutas `/flm/<flm_id>/recursos/<recurso>` identifican el proyecto de origen. Las peticiones de esas páginas incluyen X-FLM-Origin y X-Nucleus-Project. El servidor verifica ambos identificadores contra los proyectos del usuario. Así, abrir otro FLM en otra pestaña no cambia el destino de un formulario abierto. Los componentes y servicios compartidos se pueden reutilizar cuando cada FLM tenga su propia página de entrada.

No se duplicaron los catálogos ni se migraron registros existentes. Se reconocen las etiquetas históricas FLM/PEXT/Entel, Claro e Integratel. Los registros sin PROYECTO no se asignan automáticamente a un operador; siguen guardados en la base. Los registros nuevos creados desde Recursos se asignan al FLM de origen.

## Guardado y lectura

La consulta del personal para los WO y la selección de materiales utilizan el mismo criterio de proyecto que los catálogos. En contexto de Recursos, editar, cambiar una clave, importar o eliminar registros de otro FLM está bloqueado. El maestro SITE mantiene sus permisos de edición originales.

El autocompletado utiliza departamentos de Perú (incluido Callao) y todos los nombres de SITE, aunque no tengan coordenadas. Permite escribir un site nuevo sin crear automáticamente otra fila en el maestro. Los valores se guardan mediante los formularios y endpoints existentes.

## Validación

120 pruebas pasaron en la suite completa. Incluyen acceso por proyecto/rol, alta con asignación automática, bloqueo de modificaciones cruzadas, importaciones de otro FLM, catálogo de sites sin coordenadas y conservación del origen con pestañas simultáneas. Se revisaron en navegador el menú Recursos, personal de Claro, su selector de técnico y las sugerencias en los formularios de Personal y Cotizaciones. JavaScript renderizado verificado en cinco módulos.
