(() => {
    'use strict';
    const el=id=>document.getElementById(id);
    const bytes=value=>{if(value==null||!Number.isFinite(Number(value)))return '—';let n=Number(value),i=0;const u=['B','KiB','MiB','GiB','TiB'];while(n>=1024&&i<4){n/=1024;i++;}return `${n.toLocaleString('es-PE',{maximumFractionDigits:1})} ${u[i]}`;};
    const labels={ok:'Conectado',warn:'Atención',error:'Error de consulta',partial:'Lectura parcial',unconfigured:'Sin configurar',unavailable:'No disponible'};
    function badge(id,status,label){el(id).dataset.state=status;el(id).textContent=label||labels[status]||'Sin datos';}
    function details(id,rows){el(id).replaceChildren();rows.forEach(([name,value])=>{const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value??'—';row.append(dt,dd);el(id).append(row);});}
    function table(id,rows,empty){el(id).replaceChildren();if(!rows?.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent=empty;tr.append(td);el(id).append(tr);return;}rows.forEach(row=>{const tr=document.createElement('tr');[row.name,bytes(row.size_bytes),(row.estimated_rows??row.files??0).toLocaleString('es-PE')].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});el(id).append(tr);});}
    function runtime(item){
        const cpu=item.cpu||{},disk=item.disk||{};
        el('render-cpu').textContent=cpu.pct_used!=null?`${cpu.pct_used}%`:cpu.used_cores!=null?`${cpu.used_cores} núcleos`:'No disponible';
        el('render-cpu-bar').style.width=cpu.pct_used==null?'0%':`${Math.min(100,cpu.pct_used)}%`;
        el('render-cpu-bar').dataset.state=cpu.pct_used>=90?'error':cpu.pct_used>=70?'warn':'ok';
        el('render-cpu-note').textContent=(cpu.limit_cores!=null?`Cuota: ${cpu.limit_cores} vCPU · muestra ${cpu.sample_seconds} s. `:'')+(cpu.note||'CPU pendiente de lectura.');
        el('render-disk').textContent=disk.free_bytes!=null?`${bytes(disk.free_bytes)} libres`:'No disponible';
        el('render-disk-note').textContent=disk.total_bytes!=null?`${bytes(disk.size_bytes)} utilizados / ${bytes(disk.total_bytes)} visibles. Disco temporal, puede ser compartido; no es cuota del plan.`:'Disco no disponible en este entorno.';
    }
    let report,busy=false;
    function display(d){
        const findings=[];
        ['render','neon','b2'].forEach(key=>{
            const item=d[key]||{},m=key==='render'?(item.memory||{}):item,partial=item.status==='partial';
            const pressure=Math.max(m.pct_used||0,item.cpu?.pct_used||0);
            const status=item.status==='ok'?(pressure>=90?'error':pressure>=70?'warn':'ok'):(item.status||'unavailable');
            badge(`${key}-badge`,status,item.status==='ok'&&status==='error'?'Capacidad crítica':item.status==='ok'&&status==='warn'?'Capacidad alta':undefined);
            el(`card-${key}`).dataset.state=status;el(`${key}-value`).textContent=(partial?'≥ ':'')+bytes(m.size_bytes);
            el(`${key}-bar`).style.width=m.pct_used==null?'0%':`${Math.min(100,Math.max(0,m.pct_used))}%`;el(`${key}-bar`).dataset.state=m.pct_used>=90?'error':m.pct_used>=70?'warn':status;
            el(`${key}-capacity`).textContent=m.size_bytes==null?'Consumo no disponible':m.limit_bytes?`${partial?'≥ ':''}${m.pct_used}% de ${bytes(m.limit_bytes)} · ${partial?'margen máximo':'disponible'} ${bytes(Math.max(0,m.limit_bytes-m.size_bytes))}`:'Consumo medido · capacidad de referencia sin definir';
            el(`${key}-note`).textContent=item.error||item.note||'Sin información adicional';
            if(key==='render'){runtime(item);details('render-details',[['Servicio',item.service],['Plan / región',[item.plan,item.region].filter(Boolean).join(' / ')||'—'],['Fuente RAM',m.scope],['Servicio actualizado',item.updatedAt?new Date(item.updatedAt).toLocaleString('es-PE'):'—']]);if(item.metrics_url)el('render-link').href=item.metrics_url;}
            else if(key==='neon')details('neon-details',[['Consulta + conexión',item.latency_ms==null?'—':`${item.latency_ms} ms`],['Conexiones de esta base',item.connections],['Fuente',item.status==='unavailable'?'Sin PostgreSQL':'PostgreSQL conectado']]);
            else details('b2-details',[['Bucket',item.bucket],['Archivos vigentes observados',item.files],['Versiones observadas',item.versions],['Cobertura',item.complete?'Inventario completo del bucket':partial?'Parcial (mínimo observado)':'No disponible']]);
            if(key==='neon')details('neon-quick',[['Latencia',item.latency_ms==null?'—':`${item.latency_ms} ms`],['Conexiones',item.connections]]);
            if(key==='b2')details('b2-quick',[['Archivos vigentes',item.files],['Versiones',item.versions]]);
            const source={render:'Render',neon:'Neon',b2:'B2'}[key];
            if(item.status==='error')findings.push({priority:0,source,title:'Falló la consulta',action:`${item.error} Tipo: ${item.error_type||'desconocido'}. Un fallo de consulta no confirma una caída del proveedor.`});
            else if(['unconfigured','unavailable'].includes(item.status))findings.push({priority:2,source,title:'Falta visibilidad',action:item.note});
            else if(item.status==='warn')findings.push({priority:0,source,title:'Servicio suspendido',action:'Revisa eventos, despliegues y configuración en Render.'});
            if(m.pct_used>=70)findings.push({priority:m.pct_used>=90?0:1,source,title:`${partial?'Al menos ':''}${m.pct_used}% del presupuesto utilizado`,action:key==='render'?'Revisa memoria por worker, logs de OOM, procesos y CPU antes de ajustar workers o el plan.':key==='neon'?'Revisa tablas e índices más grandes; valida retención y consultas antes de limpiar o ampliar el plan.':'Revisa carpetas y versiones antiguas; valida la retención antes de limpiar o ampliar el presupuesto.'});
            if(key==='neon'&&item.latency_ms>1000)findings.push({priority:1,source,title:'Consulta superior a 1 segundo',action:'Puede incluir conexión o despertar del compute. Contrasta varias lecturas con consultas lentas y métricas de Neon.'});
            if(key==='render'&&item.cpu?.pct_used>=70)findings.push({priority:item.cpu.pct_used>=90?0:1,source,title:`CPU al ${item.cpu.pct_used}% de su cuota`,action:'Revisa operaciones costosas, peticiones y procesos. Compara varias muestras antes de ajustar el plan.'});
            if(partial)findings.push({priority:1,source,title:'Inventario incompleto',action:item.note});
            if(m.size_bytes!=null&&!m.limit_bytes)findings.push({priority:2,source,title:'Define un presupuesto',action:'El consumo está medido. Configura el umbral en Environment para calcular porcentaje y margen.'});
        });
        findings.sort((a,b)=>a.priority-b.priority);el('findings').replaceChildren();
        (findings.length?findings:[{priority:3,source:'General',title:'Sin alertas en las mediciones disponibles',action:'Consulta las consolas para tráfico, cómputo y facturación. Esta captura no confirma disponibilidad externa.'}]).forEach(f=>{const row=document.createElement('div'),tag=document.createElement('span'),body=document.createElement('div'),title=document.createElement('strong'),action=document.createElement('p');row.className='finding';tag.className='badge';tag.dataset.state=f.priority===0?'error':f.priority===1?'warn':f.priority===3?'ok':'unavailable';tag.textContent=f.source;title.textContent=f.title;action.textContent=f.action;body.append(title,action);row.append(tag,body);el('findings').append(row);});
        el('summary').textContent=findings.some(f=>f.priority===0)?'Revisión prioritaria requerida':findings.length?`${findings.length} puntos para revisar`:'Sin alertas detectadas';
        el('updated').textContent=`Medido: ${new Date(d.timestamp).toLocaleString('es-PE')} · Consulta ${(d.duration_ms/1000).toFixed(1)} s${d.cached?' · lectura en caché':''}`;
        table('tables',d.neon?.tables,'Desglose no disponible: revisa el estado de Neon.');table('folders',d.b2?.groups,d.b2?.complete?'Bucket sin versiones almacenadas.':'Desglose no disponible: revisa el estado de B2.');
        report={...d,findings};el('export').disabled=false;
    }
    async function load(){if(busy)return;busy=true;el('refresh').disabled=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),45000);try{const response=await fetch('/api/salud',{credentials:'same-origin',headers:{Accept:'application/json'},signal:controller.signal});if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))throw new Error('Sesión vencida, acceso denegado o error del servidor.');display(await response.json());}catch(error){el('summary').textContent='No se pudo actualizar el panel';el('updated').textContent=(error.name==='AbortError'?'La consulta agotó el tiempo de espera.':error.message)+(report?' Se conserva la última captura; consulta su fecha.':' Reintenta la lectura o revisa tu sesión.');if(!report)['render','neon','b2'].forEach(key=>badge(`${key}-badge`,'error'));}finally{clearTimeout(timeout);busy=false;el('refresh').disabled=false;}}
    el('refresh').addEventListener('click',load);el('export').addEventListener('click',()=>{if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=`nucleus-resources-${report.timestamp.slice(0,19).replace(/:/g,'-')}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});load();setInterval(()=>{if(!document.hidden)load();},60000);
})();
