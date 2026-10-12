# Resources

Panel administrativo en `/salud`; API de solo lectura en `/api/salud`.
Acceso restringido a `zeno` y `suport`. El menú muestra **Resources**.

## Configuración en Render → Environment

- `RENDER_API_KEY`: clave de la API Render. Nunca se envía al navegador.
- `RENDER_SERVICE_ID`: servicio a consultar.
- `RESOURCES_RENDER_MEMORY_MB`: presupuesto de RAM en MiB.
- `RESOURCES_NEON_STORAGE_MB`: presupuesto de almacenamiento de la base conectada en MiB.
- `RESOURCES_B2_STORAGE_MB`: presupuesto de almacenamiento del bucket en MiB.
- B2 reutiliza `B2_*`; PostgreSQL reutiliza `DATABASE_URL`.

Los presupuestos deben corresponder al alcance medido y al plan contratado.
No se asumen cuotas gratuitas. RAM detecta el límite finito de cgroup si no
hay presupuesto explícito. Neon y B2 requieren un presupuesto para calcular
porcentajes. Umbrales: aviso desde 70%, crítico desde 90%. Un presupuesto
superado no prueba que el proveedor haya aplicado un límite duro.

## Fuentes y alcance

Render: API de detalles del servicio (estado administrativo, plan, región y
fecha de actualización, que no es fecha de último deploy). RAM desde cgroup
en Linux; si no existe, RSS del proceso actual. No es memoria histórica ni
consumo completo de toda la cuenta. CPU se obtiene del contador del contenedor y su cuota: promedio entre
lecturas; primera muestra de 0,2 segundos. Sin cuota finita se muestran
núcleos utilizados, sin inventar un porcentaje. Disco muestra el sistema
de archivos visible y su espacio libre: puede ser compartido con el host
y no representa almacenamiento contratado. Tráfico y despliegues se
consultan desde el enlace a las métricas del proveedor.

Neon: `pg_database_size`, `pg_stat_user_tables`, `pg_total_relation_size` y
conexiones visibles de la base actual. No incluye otras bases, ramas ni
horas de compute. La latencia incluye apertura de conexión y consulta de
tamaño; puede incluir el despertar del compute. Las filas son estimaciones.

B2: `list_object_versions`, incluyendo versiones antiguas con tamaño.
Se agrupa por primer segmento del key, hasta 12 grupos de mayor consumo.
Los marcadores de borrado no tienen contenido y no se suman. Máximo 10
páginas de 1.000 entradas; se detiene tras una página si la lectura supera
6 segundos. Una lectura truncada es un mínimo observado, no un total.
No mide egreso, operaciones facturadas ni otros buckets.

Consultas del proveedor tienen timeout y no reintentos B2. PostgreSQL limita
cada sentencia a 4 segundos. El resultado se cachea por proceso durante 60
segundos para reducir el coste de monitorización. “Actualizar” puede devolver
la captura cacheada; siempre muestra su fecha y origen. No hay colector
externo ni historial persistente. Si la app cae, este panel tampoco estará
disponible; para disponibilidad externa hace falta un monitor independiente.

## Sustento

**Exportar reporte** descarga JSON con timestamp UTC, commit del despliegue
(cuando Render lo suministra), métricas, alcance, errores sin secretos y
hallazgos priorizados. Conserva reportes de diferentes momentos para comparar.
Si falla una actualización, la interfaz conserva la captura anterior y
advierte que está desactualizada. No borra datos ni cambia planes.

## Referencias

- [API de Render](https://render.com/docs/api)
- [Campos de servicio Render](https://api-docs.render.com/reference/service-fields)
- [Versiones de archivos B2](https://www.backblaze.com/docs/cloud-storage-file-versions)
- [API compatible con S3 de B2](https://www.backblaze.com/docs/en/cloud-storage-call-the-s3-compatible-api)

El panel conserva el menú de módulos, oculta el selector de recursos FLM
y tiene scroll vertical propio. Se retiraron el monitor externo y el
inventario de usuarios/proyectos/cotizaciones.

- [Contadores y cuotas cgroup v2](https://cdn.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
