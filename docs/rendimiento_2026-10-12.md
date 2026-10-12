# Rendimiento y retirada de columnas antiguas · 12/10/2026

Cambios aplicados en Nucleus, Modus y Opus:

- Eliminados los cálculos, formatos y temporizador de SLA/SLA Cumplimiento, así como su creación automática. Se limpian sus definiciones antiguas; nuevas escrituras e importaciones no las reintroducen. Se conservan fechas, estados y evidencia.
- Virtualización horizontal de Tabulator: dibuja las columnas cercanas al área visible.
- Los cambios de vista agrupan los repintados. Cotizaciones reformatea las filas activas; Rendición mueve solamente las columnas que cambian de posición.
- El autocompletado evita recorrer cada celda que Tabulator añade durante el desplazamiento. Los editores se enlazan al recibir foco.
- Se reutilizan las consultas de menú/permisos dentro de una petición. Se invalidan al guardar y no se comparten entre solicitudes o usuarios.
- Comando de producción: `gunicorn app:app --worker-class gthread --workers 1 --threads 4 --timeout 300`. Un proceso limita la duplicación de memoria; cuatro hilos permiten atender peticiones mientras otras esperan a servicios externos.

## Comparación local orientativa

Copias aisladas de la base local, misma secuencia de pestañas y navegador. Se midió el recorrido de clic y consulta de estado mediante la herramienta de navegador; incluye su sobrecarga y no representa tiempos garantizados en producción.

| Cambio de pestaña en Rendición | Antes | Con optimizaciones |
|---|---:|---:|
| Depósitos | 1781 ms | 528 ms |
| Evidencia | 439 ms | 307 ms |
| Rendición | 996 ms | 291 ms |
| Validación | 372 ms | 321 ms |

## Verificación

- Nucleus: 145 pruebas aprobadas.
- Modus: 148 pruebas aprobadas.
- Opus: 138 pruebas aprobadas.
- Pruebas de agrupación de repintados, recuperación tras errores y orden mínimo de columnas aprobadas en Node.
- JavaScript renderizado: 5 módulos y 41 bloques verificados por proyecto.
- Revisión visual de desplazamiento horizontal, cambio de pestañas y ausencia de las dos columnas retiradas en FLM.

El plan Free de Render puede introducir demoras de arranque tras inactividad. El tamaño de los datos, la conexión del usuario y las respuestas de Neon/B2 también influyen; las optimizaciones evitan trabajo repetido de la aplicación, sin prometer latencia constante.
