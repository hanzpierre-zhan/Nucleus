(function(){
    'use strict';
    const data=JSON.parse(document.getElementById('di-data').textContent);
    const get=id=>document.getElementById('di-'+id);
    const rows=data.detalle; let page=0, visible=[];
    const number=value=>new Intl.NumberFormat('es-PE',{maximumFractionDigits:1}).format(value);
    const palette={CM:'#548cff',PM:'#25b8c7',PLM:'#a58aff',leave:'#e77969',complete:'#45bb83',arrive:'#e6b34c',dispatch:'#a58aff',depart:'#df955a',accept:'#548cff'};
    const count=(items,key)=>{const result=new Map();items.forEach(r=>result.set(r[key],(result.get(r[key])||0)+1));return [...result].sort((a,b)=>b[1]-a[1]);};
    for(const [id,key] of [['month','mes'],['department','departamento']]){
        [...new Set(rows.map(r=>r[key]).filter(Boolean))].sort().forEach(value=>get(id).add(new Option(value,value)));
    }
    function bars(id,values){
        const box=get(id);box.replaceChildren();
        if(!values.length){const empty=document.createElement('p');empty.className='di-empty';empty.textContent='No hay registros para estos filtros.';box.append(empty);return;}
        const max=Math.max(...values.map(v=>v[1]),1);
        values.forEach(([label,value])=>{
            const row=document.createElement('div');row.className='di-bar-row';
            const name=document.createElement('span');name.className='di-bar-name';name.textContent=label;name.title=label;
            const track=document.createElement('div');track.className='di-bar-track';
            const fill=document.createElement('div');fill.className='di-bar-fill';fill.style.width=100*value/max+'%';track.append(fill);
            if(palette[label]) fill.style.background=palette[label];
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
        get('quality').textContent=`${visible.filter(r=>!r.mes).length} sin fecha · ${open.filter(r=>r.grupo==='Fecha futura').length} con fecha futura`;
        bars('departments',count(closed,'departamento').slice(0,5));
        const siteCounts=new Map(count(closed.filter(r=>r.site!=='Sin site'),'site'));
        bars('sites',[...siteCounts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,10));
        const leastSites=[...new Set(visible.map(r=>r.site).filter(s=>s!=='Sin site'))]
            .map(site=>[site,siteCounts.get(site)||0])
            .sort((a,b)=>a[1]-b[1]||a[0].localeCompare(b[0]));
        bars('sites-low',leastSites.slice(0,10));
        const typeCounts=new Map(count(closed,'tipo'));
        bars('types',['CM','PM','PLM',...(typeCounts.has('Otros')?['Otros']:[])].map(t=>[t,typeCounts.get(t)||0]));bars('phases',count(open,'fase'));
        const months=count(closed.filter(r=>r.mes),'mes').sort((a,b)=>a[0].localeCompare(b[0])),max=Math.max(...months.map(v=>v[1]),1);get('months').replaceChildren();
        months.forEach(([month,value])=>{const bar=document.createElement('div');bar.className='di-month';bar.title=`${month}: ${value} WO cerrados por fecha de creación`;const number=document.createElement('b');number.textContent=value;const fill=document.createElement('i');fill.style.height=value/max*80+'px';const label=document.createElement('span');label.textContent=month;bar.append(number,fill,label);get('months').append(bar);});
        if(!months.length){get('months').textContent='No hay producción con fecha para estos filtros.';}
        const percentage=visible.length?closed.length/visible.length*100:0;
        get('story-title').textContent=visible.length?`El ${number(percentage)}% de los WO está cerrado`:'Sin órdenes para esta selección';
        const backlog=open.filter(r=>r.grupo==='Backlog');
        const focus=count(backlog,'departamento')[0];
        const messages=[];
        if(backlog.length) messages.push(`${number(backlog.length)} WO de meses anteriores pendientes${focus?`; ${focus[0]} concentra ${number(focus[1])}`:''}.`);
        else if(visible.length) messages.push('No hay backlog identificado en esta selección.');
        if(months.length>1){
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
