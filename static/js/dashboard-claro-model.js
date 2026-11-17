(function(root){
 'use strict';
 // Mismo modelo para Claro, Integratel y Entel (el servidor ya normaliza las columnas).
 const day=s=>s?s.slice(0,10):'';
 const duration=r=>r.creacion&&r.cierre?(Date.parse(r.cierre)-Date.parse(r.creacion))/3600000:null;
 function bucket(s,scale){
  const date=day(s);
  if(scale==='anio')return date.slice(0,4);
  if(scale==='mes')return date.slice(0,7);
  if(scale==='trimestre')return date.slice(0,4)+' T'+Math.ceil(Number(date.slice(5,7))/3);
  if(scale==='semana'){
   const d=new Date(date+'T12:00:00Z');
   d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);
   return d.toISOString().slice(0,10);
  }
  return date;
 }
 const dias=(from,to)=>from&&to&&from<=to?Math.round((Date.parse(to)-Date.parse(from))/864e5)+1:null;
 // Cumplimiento de SLA por grupo (oficina o técnico), de menor a mayor.
 function ranking(closed,campo){
  const m=new Map();
  closed.forEach(r=>{if(r.sla===null)return;const k=r[campo]||'—';const g=m.get(k)||{nombre:k,total:0,ok:0};g.total++;if(r.sla)g.ok++;m.set(k,g);});
  return [...m.values()].map(g=>({...g,pct:g.ok/g.total*100})).sort((a,b)=>a.pct-b.pct||b.total-a.total);
 }
 function snapshot(rows,f){
  const from=f.desde||'0000-01-01',to=f.hasta||'9999-12-31',inside=s=>!!s&&day(s)>=from&&day(s)<=to;
  const all=rows.filter(r=>(!f.zona||r.zona===f.zona)&&(!f.region||r.region===f.region)&&(!f.proveedor||r.proveedor===f.proveedor)
   &&(!f.rm||r.rm===f.rm)&&(!f.fme||r.fme===f.fme)&&(!f.tipo||r.tipo===f.tipo)&&(!f.excluir||!r.cancelado)
   &&(!f.hijos||!r.hijo)&&(!f.despachados||r.despacho));
  const selected=all.filter(r=>inside(r.creacion)),closed=all.filter(r=>r.completado&&inside(r.cierre));
  const measured=closed.filter(r=>r.sla!==null),durations=closed.map(duration).filter(h=>h!==null&&h>=0);
  const bins=[0,0,0];durations.forEach(h=>bins[h<=24?0:h<=48?1:2]++);
  // Cancelados: Claro y Entel no traen Cancel Time, así que se cuentan por su fecha de creación.
  const cancelados=selected.filter(r=>r.cancelado);
  const groups=new Map();const ensure=s=>{const k=bucket(s,f.escala);if(!groups.has(k))groups.set(k,{key:k,creados:0,completados:0,cancelados:0,velocidad:[0,0,0],end:day(s)});const g=groups.get(k);if(day(s)>g.end)g.end=day(s);return g;};
  if(from!=='0000-01-01'&&to!=='9999-12-31'&&from<=to){const d=new Date(from+'T12:00:00Z');for(let i=0;i<36600&&d.toISOString().slice(0,10)<=to;i++,d.setUTCDate(d.getUTCDate()+1))ensure(d.toISOString());}
  all.forEach(r=>{if(inside(r.creacion)){const g=ensure(r.creacion);g.creados++;if(r.cancelado)g.cancelados++;}if(r.completado&&inside(r.cierre)){const g=ensure(r.cierre);g.completados++;const h=duration(r);if(h!==null&&h>=0)g.velocidad[h<=24?0:h<=48?1:2]++;}});
  const backlog=end=>all.filter(r=>r.creacion&&day(r.creacion)<=end&&!(r.completado&&r.cierre&&day(r.cierre)<=end)&&!r.cancelado).length;
  const series=[...groups.values()].sort((a,b)=>a.key.localeCompare(b.key));series.forEach(g=>g.backlog=backlog(g.end));
  const n=dias(f.desde,f.hasta);
  return {selected,series,creados:selected.length,completados:closed.length,cancelados:cancelados.length,
   despachados:selected.filter(r=>r.despacho).length,abiertos:backlog(to),dias:n,
   creadosDia:n?selected.length/n:null,completadosDia:n?closed.length/n:null,
   promedio:durations.length?durations.reduce((a,b)=>a+b,0)/durations.length:null,
   sla:measured.length?measured.filter(r=>r.sla).length/measured.length*100:null,slaOk:measured.filter(r=>r.sla).length,slaBase:measured.length,slaSinDato:closed.length-measured.length,
   velocidad:bins,sinDuracion:closed.length-durations.length,sinFecha:all.filter(r=>!r.creacion).length,
   porZona:ranking(closed,'zona'),porFme:ranking(closed,'fme')};
 }
 const api={snapshot,duration,bucket,ranking};root.ClaroModel=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
