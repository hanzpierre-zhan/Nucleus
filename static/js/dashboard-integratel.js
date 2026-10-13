(function(){
    'use strict';
    const data=JSON.parse(document.getElementById('di-data').textContent);
    const get=id=>document.getElementById('di-'+id);
    const rows=data.detalle; let page=0, visible=[];
    const number=value=>new Intl.NumberFormat('es-PE',{maximumFractionDigits:1}).format(value);
    const palette={CM:'#548cff',PM:'#25b8c7',PLM:'#668fc9',leave:'#e77969',complete:'#45bb83',arrive:'#e6b34c',dispatch:'#668fc9',depart:'#df955a',accept:'#548cff'};
    function daily(closed){
        const month=get('month').value||data.mes_actual;
        const [year,monthNumber]=month.split('-').map(Number);
        const days=new Date(year,monthNumber,0).getDate();
        const counts=Array(days).fill(0);
        closed.filter(r=>r.fecha&&r.mes===month).forEach(r=>counts[Number(r.fecha.slice(-2))-1]++);
        const total=counts.reduce((a,b)=>a+b,0), maximum=Math.max(...counts,1);
        get('daily-month').textContent=month;
        get('daily-caption').textContent=`${total} WO close · por fecha de creación${total?'':' · ningún WO close creado en este mes; elige otro mes para consultar el histórico'}`;
        const ns='http://www.w3.org/2000/svg';
        const el=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text!==undefined)e.textContent=text;return e;};
        const width=Math.max(320,get('daily').clientWidth),height=Math.max(96,get('daily').clientHeight);
        const left=24,right=width-6,bottom=height-18;
        const svg=el('svg',{viewBox:`0 0 ${width} ${height}`,preserveAspectRatio:'none',role:'img','aria-label':`${total} WO close por día de creación en ${month}`});
        const step=(right-left)/days;
        const x=i=>left+(i+0.5)*step,y=v=>bottom-v/maximum*(bottom-18);
        [0,maximum].forEach(v=>{svg.append(el('line',{x1:left,y1:y(v),x2:right,y2:y(v),class:'di-daily-grid'}));svg.append(el('text',{x:left-5,y:y(v)+3,'text-anchor':'end',class:'di-daily-label'},v));});

        counts.forEach((v,i)=>{
            const bar=el('rect',{x:x(i)-step*0.32,y:y(v),width:step*0.64,height:Math.max(1,bottom-y(v)),rx:2,class:'di-daily-dot'});
            bar.append(el('title',{},`${month}-${String(i+1).padStart(2,'0')}: ${v} WO close`));svg.append(bar);
            svg.append(el('text',{x:x(i),y:y(v)-5,'text-anchor':'middle',class:'di-daily-value'},v));
            svg.append(el('text',{x:x(i),y:height-3,'text-anchor':'middle',class:'di-daily-label'},i+1));
        });
        get('daily').replaceChildren(svg);
    }
    const count=(items,key)=>{const result=new Map();items.forEach(r=>result.set(r[key],(result.get(r[key])||0)+1));return [...result].sort((a,b)=>b[1]-a[1]);};
    for(const [id,key] of [['month','mes'],['department','departamento']]){
        [...new Set(rows.map(r=>r[key]).filter(Boolean))].sort().forEach(value=>get(id).add(new Option(value,value)));
    }
    function bars(id,values){
        const box=get(id);box.classList.add('di-ranking');box.replaceChildren();
        if(!values.length){const empty=document.createElement('p');empty.className='di-empty';empty.textContent='No hay registros para estos filtros.';box.append(empty);return;}
        const max=Math.max(...values.map(v=>v[1]),1);
        values.forEach(([label,value])=>{
            const row=document.createElement('div');row.className='di-bar-row';
            const name=document.createElement('span');name.className='di-bar-name';name.textContent=label;name.title=label;
            const track=document.createElement('div');track.className='di-bar-track';
            const fill=document.createElement('div');fill.className='di-bar-fill';fill.style.width=100*value/max+'%';track.append(fill);
            if(palette[label]) fill.style.background=palette[label];
            if(id==='priority'||id==='fault'){
                const severity=String(label).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
                const colors={p1:'#e77969',p2:'#df955a',p3:'#548cff',p4:'#25b8c7',alta:'#e77969',alto:'#e77969',critical:'#e77969',critico:'#e77969',media:'#e6b34c',medio:'#e6b34c',baja:'#45bb83',bajo:'#45bb83',high:'#e77969',medium:'#e6b34c',low:'#45bb83'};
                if(colors[severity])fill.style.background=colors[severity];
            }
            const number=document.createElement('b');number.textContent=value;row.append(name,track,number);box.append(row);
        });
    }
    function table(){
        const group=get('group').value, subset=visible.filter(r=>r.grupo!=='Producción'&&(!group||r.grupo===group));
        const pages=Math.max(1,Math.ceil(subset.length/50));page=Math.min(page,pages-1);get('orders').replaceChildren();
        subset.slice(page*50,page*50+50).forEach(r=>{
            const tr=document.createElement('tr');['wo','tipo','mes','departamento','site','fase','grupo'].forEach(k=>{const td=document.createElement('td');td.textContent=r[k]||'—';tr.append(td);});get('orders').append(tr);
        });
        get('page-count').textContent=`${subset.length} órdenes · página ${page+1} de ${pages}`;get('prev').disabled=page===0;get('next').disabled=page>=pages-1;
    }
    function render(){
        visible=rows.filter(r=>(!get('month').value||r.mes===get('month').value)&&(!get('department').value||r.departamento===get('department').value)&&(!get('type').value||r.tipo===get('type').value));
        const closed=visible.filter(r=>r.grupo==='Producción'),open=visible.filter(r=>r.grupo!=='Producción');
        get('production').textContent=closed.length;get('backlog').textContent=open.filter(r=>r.grupo==='Backlog').length;get('current').textContent=open.filter(r=>r.grupo==='En atención').length;get('total').textContent=visible.length;
        const missingDate=visible.filter(r=>!r.mes).length, futureDate=open.filter(r=>r.grupo==='Fecha futura').length;
        get('quality').textContent=missingDate||futureDate?`${missingDate} sin fecha · ${futureDate} futuros`:'WO registrados';
        bars('departments',count(closed,'departamento').slice(0,5));
        const siteCounts=new Map(count(closed.filter(r=>r.site!=='Sin site'),'site'));
        bars('sites',[...siteCounts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,10));
        const leastSites=[...new Set(visible.map(r=>r.site).filter(s=>s!=='Sin site'))]
            .map(site=>[site,siteCounts.get(site)||0])
            .sort((a,b)=>a[1]-b[1]||a[0].localeCompare(b[0]));
        bars('sites-low',leastSites.slice(0,10));
        const typeCounts=new Map(count(closed,'tipo'));
        ['CM','PM','PLM'].forEach(type=>get('type-'+type.toLowerCase()).textContent=typeCounts.get(type)||0);
        bars('phases',count(open,'fase'));
        bars('tasks',count(visible,'tarea').slice(0,5));
        bars('people',count(closed.filter(r=>r.personal!=='Sin personal asignado'),'personal').slice(0,5));
        bars('priority',count(visible,'prioridad'));
        bars('fault',count(visible,'fault'));
        daily(closed);
        const monthlyClosed=rows.filter(r=>r.grupo==='Producción'&&r.mes&&(!get('department').value||r.departamento===get('department').value)&&(!get('type').value||r.tipo===get('type').value));
        const months=count(monthlyClosed,'mes').sort((a,b)=>a[0].localeCompare(b[0])),max=Math.max(...months.map(v=>v[1]),1);get('months').replaceChildren();
        months.forEach(([month,value])=>{const bar=document.createElement('div');bar.className='di-month'+(month===(get('month').value||data.mes_actual)?' di-month-selected':'');bar.title=`${month}: ${value} WO cerrados por fecha de creación`;const number=document.createElement('b');number.textContent=value;const fill=document.createElement('i');fill.style.height=value/max*Math.max(54,get('months').clientHeight-32)+'px';const label=document.createElement('span');label.textContent=month;bar.append(number,fill,label);get('months').append(bar);});
        if(!months.length){get('months').textContent='No hay producción con fecha para estos filtros.';}
        const percentage=visible.length?closed.length/visible.length*100:0;
        get('story-title').textContent=visible.length?`El ${number(percentage)}% de los WO está cerrado`:'Sin órdenes para esta selección';
        const backlog=open.filter(r=>r.grupo==='Backlog');
        const focus=count(backlog,'departamento')[0];
        const messages=[];
        if(backlog.length) messages.push(`${number(backlog.length)} WO de meses anteriores pendientes${focus?`; ${focus[0]} concentra ${number(focus[1])}`:''}.`);
        else if(visible.length) messages.push('No hay backlog identificado en esta selección.');
        if(months.length>1&&!get('month').value){
            const [latest,value]=months[months.length-1], [previous,previousValue]=months[months.length-2];
            const change=previousValue?(value-previousValue)/previousValue*100:0;
            messages.push(`${latest}: ${number(value)} cerrados, ${number(Math.abs(change))}% ${change<0?'menos':'más'} que ${previous} (por creación del WO).`);
        }
        const withoutDate=visible.filter(r=>!r.mes).length;
        if(withoutDate) messages.push(`${withoutDate} WO sin fecha: no se asignan a un mes.`);
        get('story-detail').textContent=messages.join(' ');
        get('progress-fill').style.width=percentage+'%';
        get('progress-fill').parentElement.title=`${closed.length} cerrados de ${visible.length} WO`;
        get('detail-count').textContent=`(${open.length})`;
        page=0;table();
    }
    ['month','department','type'].forEach(id=>get(id).addEventListener('change',render));get('group').addEventListener('change',()=>{page=0;table();});
    get('clear').addEventListener('click',()=>{['month','department','type','group'].forEach(id=>get(id).value='');render();});
    get('prev').addEventListener('click',()=>{page--;table();});get('next').addEventListener('click',()=>{page++;table();});render();
})();
