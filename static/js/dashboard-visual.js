(function(){
 'use strict';
 const ns='http://www.w3.org/2000/svg';
 const el=(tag,attrs)=>{const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n;};
 const fade=(color,opacity)=>'color-mix(in srgb,'+color+' '+Math.round(opacity*100)+'%,transparent)';
 function months(box){
  box.querySelector('.dv-month-area')?.remove();
  const bars=[...box.querySelectorAll('.di-month')];
  if(bars.length<2)return;
  const heights=bars.map(b=>parseFloat(b.querySelector('i').style.height)||0),max=Math.max(...heights,1);
  const points=heights.map((v,i)=>[(i+.5)*1000/bars.length,145-v/max*105]);
  const svg=el('svg',{viewBox:'0 0 1000 180',preserveAspectRatio:'none',class:'dv-month-area','aria-hidden':'true'});
  const path='M '+points.map(p=>p.join(',')).join(' L ');
  svg.append(el('path',{d:path+' L '+points.at(-1)[0]+',160 L '+points[0][0]+',160 Z',fill:'var(--di-blue)',opacity:'.065'}));
  svg.append(el('path',{d:path,fill:'none',stroke:'var(--di-blue)','stroke-width':'2','stroke-dasharray':'5 7',opacity:'.3'}));
  box.prepend(svg);
 }
 function daily(svg,counts,x,y,bottom){
  if(!counts.some(Boolean))return;
  const d='M '+counts.map((v,i)=>x(i)+','+y(v)).join(' L ');
  svg.prepend(el('path',{d:d+' L '+x(counts.length-1)+','+bottom+' L '+x(0)+','+bottom+' Z',class:'dv-daily-area'}));
  svg.prepend(el('path',{d,class:'dv-daily-line'}));
 }
 function prepare(config){
  const type=config.type;
  if(type==='doughnut'){
   config.data.datasets.forEach(d=>{d.borderRadius=7;d.spacing=3;d.hoverOffset=7;});
  }else if(type==='bar'){
   const horizontal=config.options.indexAxis==='y';
   config.data.datasets.forEach(d=>{
    const base=d.backgroundColor;
    if(typeof base==='function')return;
    d.borderRadius=horizontal?8:9;d.borderSkipped=false;
    d.backgroundColor=context=>{
     const c=Array.isArray(base)?base[context.dataIndex]:base;
     const area=context.chart.chartArea;
     if(!area||typeof c!=='string')return c;
     const ctx=context.chart.ctx;
     const gradient=horizontal?ctx.createLinearGradient(area.left,0,area.right,0):ctx.createLinearGradient(0,area.bottom,0,area.top);
     gradient.addColorStop(0,c);gradient.addColorStop(1,fade(c,.65));return gradient;
    };
   });
  }else if(type==='line'){
   config.data.datasets.forEach(d=>{
    const base=d.borderColor;d.borderWidth=2.5;d.tension=.35;d.pointHoverRadius=6;
    d.pointBackgroundColor=base;d.pointBorderWidth=2;d.pointBorderColor=getComputedStyle(document.querySelector('.di-page')).getPropertyValue('--ios-card-bg').trim();
    d.fill=true;d.backgroundColor=context=>{
     const area=context.chart.chartArea;if(!area)return 'transparent';
     const gradient=context.chart.ctx.createLinearGradient(0,area.top,0,area.bottom);
     gradient.addColorStop(0,fade(base,.2));gradient.addColorStop(1,fade(base,.01));return gradient;
    };
   });
  }
  const tooltip=config.options.plugins?.tooltip;
  if(tooltip){tooltip.cornerRadius=10;tooltip.padding=13;tooltip.displayColors=true;tooltip.boxPadding=5;}
  return config;
 }
 const distributions=new Map();
 function distribution(box,values){
  distributions.get(box.id)?.destroy();distributions.delete(box.id);
  if(!window.Chart||!values.some(v=>v[1]>0))return;
  const legend=document.createElement('div');legend.className='dv-distribution-legend';
  const colors=[...box.querySelectorAll('.di-bar-fill')].map(n=>getComputedStyle(n).backgroundColor);
  while(box.firstChild)legend.append(box.firstChild);
  legend.querySelectorAll('.di-bar-row').forEach((row,i)=>row.style.setProperty('--dv-dot',colors[i]));
  const layout=document.createElement('div');layout.className='dv-distribution';
  const ring=document.createElement('div');ring.className='dv-distribution-ring';
  const canvas=document.createElement('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label',values.map(v=>v[0]+': '+v[1]).join(', '));
  ring.append(canvas);layout.append(ring,legend);box.append(layout);
  const css=getComputedStyle(box),text=css.getPropertyValue('--ios-label').trim(),surface=css.getPropertyValue('--ios-card-bg').trim();
  const total=values.reduce((a,v)=>a+v[1],0);
  const center={id:'distributionTotal',afterDraw(chart){const {ctx,chartArea:a}=chart;if(!a)return;ctx.save();ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=text;ctx.font='700 20px system-ui';ctx.fillText(new Intl.NumberFormat('es-PE').format(total),(a.left+a.right)/2,(a.top+a.bottom)/2-6);ctx.font='10px system-ui';ctx.fillText('registros',(a.left+a.right)/2,(a.top+a.bottom)/2+14);ctx.restore();}};
  distributions.set(box.id,new Chart(canvas,{type:'doughnut',plugins:[center],data:{labels:values.map(v=>v[0]),datasets:[{data:values.map(v=>v[1]),backgroundColor:colors,borderColor:surface,borderWidth:3,borderRadius:5,spacing:2,hoverOffset:4}]},options:{responsive:true,maintainAspectRatio:false,animation:false,cutout:'74%',plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.label+': '+c.parsed+' ('+(c.parsed/total*100).toFixed(1)+'%)'}}}}}));
 }
 window.NucleusDashVisual={months,daily,prepare,distribution};
}());
