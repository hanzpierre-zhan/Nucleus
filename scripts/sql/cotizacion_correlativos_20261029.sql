-- Conciliación reversible por fila: conserva claves, IDs y valores originales.
-- Ejecutar dentro de una transacción con respaldo previo de nucleus_data e historial.
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';

SELECT 1 FROM app_config WHERE proyecto_id=(SELECT id FROM proyectos WHERE nombre='Cotizaciones')
AND clave='cotizacion_next_seq' FOR UPDATE;
LOCK TABLE nucleus_data IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE numeracion_antes ON COMMIT DROP AS
SELECT id,proyecto_id,key_value,data_json FROM nucleus_data;
CREATE TEMP TABLE numeracion_cambios(id integer, clave text, campo text, anterior text, nuevo text) ON COMMIT DROP;

DO $conciliar$
DECLARE
 p integer; r record; d jsonb; numero text; orden text; sufijo integer; nuevo text;
BEGIN
 SELECT id INTO STRICT p FROM proyectos WHERE nombre='Cotizaciones';
 -- Solo los dos casos recuperados que coinciden con consecutivos ya usados.
 -- Se conserva su clave técnica: los enlaces anteriores siguen resolviendo.
 FOR r IN SELECT * FROM nucleus_data WHERE proyecto_id=p
   AND key_value IN ('CL-2026-10-000524','CL-2026-10-000526') ORDER BY id LOOP
   d:=r.data_json::jsonb;
   IF d->'_RECUPERACION'->>'lote'='recuperacion-cotizaciones-20261029'
      AND d->>'N° COTIZACION'=r.key_value THEN
     numero:=r.key_value||'.1';
     IF EXISTS(SELECT 1 FROM nucleus_data WHERE proyecto_id=p AND data_json::jsonb->>'N° COTIZACION'=numero) THEN
       RAISE EXCEPTION 'Etiqueta recuperada ocupada: %',numero;
     END IF;
     d:=jsonb_set(d,ARRAY['N° COTIZACION'],to_jsonb(numero));
     d:=d||jsonb_build_object('_NUMERACION_CONCILIADA',jsonb_build_object(
       'lote','correlativos-20261029','numero_original',r.key_value,'fecha_utc',CURRENT_TIMESTAMP));
     UPDATE nucleus_data SET data_json=d::text WHERE id=r.id;
     INSERT INTO numeracion_cambios VALUES(r.id,r.key_value,'N° COTIZACION',r.key_value,numero);
   END IF;
 END LOOP;

 -- No renumerar toda la tabla ni alterar su orden histórico: distinguir solo
 -- las ocurrencias posteriores de cada orden con .1, .2, etc.
 FOR r IN SELECT id,key_value,data_json FROM (
   SELECT n.*,row_number() OVER (PARTITION BY data_json::jsonb->>'N° ORDEN' ORDER BY id) AS repeticion
   FROM nucleus_data n WHERE proyecto_id=p AND COALESCE(data_json::jsonb->>'N° ORDEN','')<>''
 ) t WHERE repeticion>1 ORDER BY id LOOP
   d:=r.data_json::jsonb; orden:=d->>'N° ORDEN'; sufijo:=1;
   nuevo:=orden||'.'||sufijo;
   WHILE EXISTS(SELECT 1 FROM nucleus_data WHERE proyecto_id=p AND data_json::jsonb->>'N° ORDEN'=nuevo) LOOP
     sufijo:=sufijo+1; nuevo:=orden||'.'||sufijo;
   END LOOP;
   d:=jsonb_set(d,ARRAY['N° ORDEN'],to_jsonb(nuevo));
   d:=d||jsonb_build_object('_ORDEN_CONCILIADA',jsonb_build_object(
     'lote','correlativos-20261029','orden_original',orden,'fecha_utc',CURRENT_TIMESTAMP));
   UPDATE nucleus_data SET data_json=d::text WHERE id=r.id;
   INSERT INTO numeracion_cambios VALUES(r.id,r.key_value,'N° ORDEN',orden,nuevo);
 END LOOP;

 INSERT INTO historial_cambios(proyecto_id,usuario_id,username,key_value,campo_modificado,valor_anterior,valor_nuevo,fecha)
 SELECT p,NULL,'conciliacion',c.clave,c.campo,c.anterior,c.nuevo,CURRENT_TIMESTAMP AT TIME ZONE 'UTC' FROM numeracion_cambios c;

 -- No se toca ningún campo comercial, financiero, de workflow ni de vínculo.
 IF EXISTS(SELECT 1 FROM numeracion_antes b FULL JOIN nucleus_data n USING(id)
    WHERE b.id IS NULL OR n.id IS NULL OR n.proyecto_id IS DISTINCT FROM b.proyecto_id OR n.key_value IS DISTINCT FROM b.key_value
    OR (n.data_json::jsonb - ARRAY['N° COTIZACION','N° ORDEN','_NUMERACION_CONCILIADA','_ORDEN_CONCILIADA'])
       IS DISTINCT FROM (b.data_json::jsonb - ARRAY['N° COTIZACION','N° ORDEN','_NUMERACION_CONCILIADA','_ORDEN_CONCILIADA'])) THEN
   RAISE EXCEPTION 'La conciliacion alteraria campos protegidos';
 END IF;
END $conciliar$;

-- Protección para cualquier escritor: también importaciones o código anterior.
DO $indices$
DECLARE p integer;
BEGIN
 SELECT id INTO STRICT p FROM proyectos WHERE nombre='Cotizaciones';
 EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS uq_cotizacion_serie_mensual
   ON nucleus_data (proyecto_id,(regexp_replace(data_json::jsonb->>''N° COTIZACION'',
     ''^(HW|EN|CL|IN|PX)-([0-9]{4})-[0-9]{2}-0*([0-9]+([.][0-9]+)?)$'',''\2:\3'')))
   WHERE proyecto_id=%s AND data_json::jsonb->>''N° COTIZACION'' ~ ''^(HW|EN|CL|IN|PX)-[0-9]{4}-[0-9]{2}-[0-9]+([.][0-9]+)?$''',p);
 EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS uq_cotizacion_orden
   ON nucleus_data (proyecto_id,((data_json::jsonb)->>''N° ORDEN''))
   WHERE proyecto_id=%s AND COALESCE(data_json::jsonb->>''N° ORDEN'','''')<>''''',p);
END $indices$;

SELECT campo,count(*) AS cambios FROM numeracion_cambios GROUP BY campo ORDER BY campo;
