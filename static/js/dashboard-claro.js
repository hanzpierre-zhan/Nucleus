(function(){
 'use strict';const data=JSON.parse(document.getElementById('cl-data').textContent),get=id=>document.getElementById('cl-'+id),charts=new Map();let page=0,current;
 const num=v=>new Intl.NumberFormat('es-PE',{maximumFractionDigits:1}).format(v);
 const palette=window.NucleusDashVisual.operationalColors;
 const colors=[palette.teal,palette.amber,palette.red], speedLabels=['≤ 24 h','24–48 h','> 48 h'];
 for(const field of ['zona','fme','tipo'])[...new Set(data.rows.map(r=>r[field]))].sort().forEach(v=>get(field).add(new Option(v,v)));
 function chart(id,type,labels,datasets,extra={}){charts.get(id)?.destroy();const dark=document.body.classList.contains('dark-mode');const config={type,data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,color:dark?'#cbd5e1':'#4b5563',plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:10}}}},...(type==='bar'?{scales:{x:{stacked:true,ticks:{maxRotation:60,autoSkip:true,maxTicksLimit:18,color:dark?'#9ca3af':'#64748b'},grid:{display:false}},y:{stacked:true,beginAtZero:true,ticks:{precision:0,color:dark?'#9ca3af':'#64748b'},grid:{color:dark?'#ffffff0d':'#0000000d'}}}}:{}),...extra}};charts.set(id,new Chart(get(id),window.NucleusDashVisual.prepare(config)));}
 function table(){const rows=current.selected,pages=Math.max(1,Math.ceil(rows.length/50));page=Math.min(page,pages-1);get('tickets').replaceChildren();for(const r of rows.slice(page*50,page*50+50)){const tr=document.createElement('tr');for(const v of [r.id,r.estado,r.creacion,r.cierre,r.zona,r.fme,r.sla===null?'Sin dato':r.sla?'Cumple':'Fuera de SLA']){const td=document.createElement('td');td.textContent=v||'—';tr.append(td);}get('tickets').append(tr);}get('count').textContent='· '+num(rows.length);get('pagina').textContent=`${page+1} / ${pages}`;get('anterior').disabled=page===0;get('siguiente').disabled=page>=pages-1;}
 function renderSummary(){
  const value=get('sla-value'), needle=get('sla-needle');
  value.textContent=current.sla===null?'Sin dato':num(current.sla)+'%';
  value.dataset.level=current.sla===null?'empty':current.sla>=95?'high':current.sla>=80?'mid':'low';
  needle.setAttribute('visibility',current.sla===null?'hidden':'visible');
  needle.setAttribute('transform',`rotate(${(current.sla??0)*1.8} 120 108)`);
  get('sla-nota').textContent=`${num(current.slaBase)} cierres con SLA medido · ${num(current.slaSinDato)} sin SLA`;

  const total=current.velocidad.reduce((sum,count)=>sum+count,0);
  get('velocidad-total').textContent=num(total);
  get('velocidad-leyenda').replaceChildren(...speedLabels.map((label,index)=>{
   const row=document.createElement('li'), name=document.createElement('span'), count=document.createElement('strong');
   const quantity=current.velocidad[index];
   row.dataset.band=String(index);
   name.textContent=label;
   count.textContent=`${num(quantity)} (${num(total?quantity/total*100:0)}%)`;
   row.append(name,count);
   return row;
  }));
  chart('velocidad','doughnut',speedLabels,[{data:total?current.velocidad:[1],backgroundColor:total?colors:[palette.muted],borderWidth:0}],
   {cutout:'68%',plugins:{legend:{display:false},tooltip:{enabled:total>0}}});
 }
 function render(){
 const from=get('desde').value,to=get('hasta').value;
 if(from&&to&&from>to){get('nota').textContent='La fecha inicial debe ser anterior o igual a la final.';return;}
 current=ClaroModel.snapshot(data.rows,{desde:from,hasta:to,zona:get('zona').value,fme:get('fme').value,
  tipo:get('tipo').value,excluir:get('excluir-cancelados').checked,escala:document.querySelector('[data-cl-scale][aria-pressed="true"]').dataset.clScale});
 for(const k of ['creados','completados','cancelados','despachados','abiertos'])get(k).textContent=num(current[k]);get('promedio').textContent=current.promedio===null?'Sin dato':num(current.promedio)+' h';
 get('creados-nota').textContent='Por Create Time';get('completados-nota').textContent='Por Complete Time';get('cancelados-nota').textContent=get('excluir-cancelados').checked?'Excluidos de la selección':'Por Cancel Time';get('despachados-nota').textContent='Por Dispatch Time';get('abiertos-nota').textContent='Acumulado hasta la fecha final';get('promedio-nota').textContent=current.sinDuracion+' cierres sin duración válida';
 get('nota').textContent=`${num(data.total)} tickets importados · ${data.sin_identificador} registros sin Ticket Id excluidos · ${current.sinFecha} tickets sin fecha de creación. Los filtros se aplican a todos los gráficos.`;
 renderSummary();
 const series=current.series,labels=series.map(g=>g.key);chart('evolucion','bar',labels,[{type:'line',label:'Backlog',data:series.map(g=>g.backlog),borderColor:palette.red,backgroundColor:palette.red,pointRadius:2,borderWidth:2,tension:.2,stack:'backlog'},{label:'Creados',data:series.map(g=>g.creados),backgroundColor:palette.blue,stack:'creados'},{label:'Completados',data:series.map(g=>g.completados),backgroundColor:palette.teal,stack:'cerrados'},{label:'Cancelados',data:series.map(g=>g.cancelados),backgroundColor:palette.muted,stack:'cancelados'}]);
 chart('cierres','bar',labels,speedLabels.map((label,i)=>({label,data:series.map(g=>g.velocidad[i]),backgroundColor:colors[i],stack:'tiempo'})));table();}
 for(const id of ['desde','hasta','zona','fme','tipo','excluir-cancelados'])get(id).addEventListener('change',()=>{page=0;render();});
 const scales=document.querySelectorAll('[data-cl-scale]');
 scales.forEach(button=>button.addEventListener('click',()=>{
  scales.forEach(option=>option.setAttribute('aria-pressed',String(option===button)));
  render();
 }));
 get('anterior').onclick=()=>{page--;table();};get('siguiente').onclick=()=>{page++;table();};
 new MutationObserver(render).observe(document.body,{attributes:true,attributeFilter:['class']});render();
})();
