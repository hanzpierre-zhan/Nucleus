# Verificación de carga local

Se incorporó el respaldo histórico `nucleus_pre_coti_estados.db` al ensayo
que ya contenía las copias locales de Anton y Modus. No se descargó Neon.
Se preservó la base anterior y cada fila importada tiene procedencia.

Base ampliada: `backups/nucleus_ensayo_completo_historico_20261017.db`.
Contiene 10.805 registros de nucleus_data y siete cuentas (antes de agregar
la cuenta técnica temporal que crea el servidor de ensayo).
Integridad SQLite: OK. Referencias sin destino en el ensayo: cero.
Las referencias históricas originales a usuarios inexistentes están archivadas
y documentadas en los manifiestos, sin modificar las fuentes.

## Comprobación del navegador en el puerto 5001

| Pantalla | Conteo visible | Filas comprobadas |
|---|---|---|
| FLM - ENTEL | 1122 / 1122 | Sí |
| Combustible | 152 / 152 | Sí |
| Cotizaciones | 1 / 6 en Registro | Sí; las demás están en otras pestañas |

Se verificó el acceso con la cuenta existente. El servicio fue reiniciado
para usar la nueva copia de trabajo: hay que recargar y volver a iniciar
sesión si el navegador conserva una sesión anterior.

Las pantallas ya no están vacías en los módulos verificados. Esto acredita
la carga de los respaldos usados para el ensayo; no acredita igualdad con
la información actual de producción. No se hizo commit ni despliegue.
