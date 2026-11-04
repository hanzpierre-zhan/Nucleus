(function(root){
 'use strict';
 const day=s=>s?s.slice(0,10):'';
 const duration=r=>r.creacion&&r.cierre?(Date.parse(r.cierre)-Date.parse(r.creacion))/3600000:null;
 const bucket=(s,scale)=>{if(scale==='mes')return day(s).slice(0,7);if(scale==='semana'){const d=new Date(day(s)+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return d.toISOString().slice(0,10);}return day(s);};
 function snapshot(rows,f){
  const from=f.desde||'0000-01-01',to=f.hasta||'9999-12-31',inside=s=>!!s&&day(s)>=from&&day(s)<=to;
  const all=rows.filter(r=>(!f.zona||r.zona===f.zona)&&(!f.fme||r.fme===f.fme)&&(!f.tipo||r.tipo===f.tipo)&&(!f.excluir||!r.cancelado)&&(!f.despachados||r.despacho));
  const selected=all.filter(r=>inside(r.creacion)),closed=all.filter(r=>r.completado&&inside(r.cierre));
  const measured=closed.filter(r=>r.sla!==null),durations=closed.map(duration).filter(h=>h!==null&&h>=0);
  const bins=[0,0,0];durations.forEach(h=>bins[h<=24?0:h<=48?1:2]++);
  const groups=new Map();const ensure=s=>{const k=bucket(s,f.escala);if(!groups.has(k))groups.set(k,{key:k,creados:0,completados:0,cancelados:0,velocidad:[0,0,0],end:day(s)});const g=groups.get(k);if(day(s)>g.end)g.end=day(s);return g;};
  if(from!=='0000-01-01'&&to!=='9999-12-31'&&from<=to){const d=new Date(from+'T12:00:00Z');for(let i=0;i<36600&&d.toISOString().slice(0,10)<=to;i++,d.setUTCDate(d.getUTCDate()+1))ensure(d.toISOString());}
  all.forEach(r=>{if(inside(r.creacion))ensure(r.creacion).creados++;if(r.completado&&inside(r.cierre)){const g=ensure(r.cierre);g.completados++;const h=duration(r);if(h!==null&&h>=0)g.velocidad[h<=24?0:h<=48?1:2]++;}if(inside(r.cancelacion))ensure(r.cancelacion).cancelados++;});
  const backlog=end=>all.filter(r=>r.creacion&&day(r.creacion)<=end&&!(r.completado&&r.cierre&&day(r.cierre)<=end)&&!(r.cancelado&&(!r.cancelacion||day(r.cancelacion)<=end))).length;
  const series=[...groups.values()].sort((a,b)=>a.key.localeCompare(b.key));series.forEach(g=>g.backlog=backlog(g.end));
  return {selected,series,creados:selected.length,completados:closed.length,cancelados:all.filter(r=>inside(r.cancelacion)).length,despachados:all.filter(r=>inside(r.despacho)).length,abiertos:backlog(to),promedio:durations.length?durations.reduce((a,b)=>a+b,0)/durations.length:null,sla:measured.length?measured.filter(r=>r.sla).length/measured.length*100:null,slaBase:measured.length,slaSinDato:closed.length-measured.length,velocidad:bins,sinDuracion:closed.length-durations.length,sinFecha:all.filter(r=>!r.creacion).length};
 }
 const api={snapshot,duration};root.ClaroModel=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
