(function () {
    'use strict';
    const ids={
        'wo-servicio':'SERVICIO','wo-sistemas':'SISTEMAS','wo-solucion':'SOLUCIÓN',
        'wo-tecnico':'TECNICO ASIGNADO','wo-se-instalo-mufas':'SE INSTALÓ MUFAS',
        'wo-requiere-correctivo':'REQUIERE CORRECTIVO FINAL','wo-requiere-biaticos':'REQUIERE BIÁTICOS',
        'wo-requiere-material':'¿REQUIERE MATERIAL?','wo-requiere-acceso':'¿REQUIERE ACCESO AL SITE?',
        'wo-fue-torrera':'¿FUE TORRERA?','wo-fue-site-propio':'¿FUE SITE PROPIO?',
        'wo-cuadrilla':'¿CUADRILLA DE 3 O 2?','wo-team-leader':'TEAM LEADER ASIGNADO EN APLICATIVO',
        'wo-supervisor':'¿QUIÉN FUE EL SUPERVISOR A CARGO EN ESE TURNO?',
        'wo-status-atencion':'STATUS DE ATENCION','wo-quedo-pendiente':'¿QUEDO PENDIENTE ALGUN CORRECTIVO ADICIONAL?'
    };
    const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/gi,'').toLowerCase();
    const manageValue='__nucleus_manage_choices__';
    let fields=new Map();
    const records=new WeakMap();
    const all=new Set();
    let permitted=false;
    function apply(select,field){
        let state=records.get(select);
        if(!state){state={previous:select.value,labels:new Map()};records.set(select,state);all.add(select);}
        for(const o of select.options)if(o.value!==manageValue&&!o.dataset.historical)state.labels.set(o.value,o.textContent);
        if(field.configurada){
            const current=select.value===manageValue?state.previous:select.value;
            const wanted=field.opciones.map(String);
            const historical=current&&!wanted.includes(current)?[current]:[];
            const existing=[...select.options].filter(o=>o.value&&o.value!==manageValue).map(o=>o.value);
            if(JSON.stringify(existing)!==JSON.stringify([...wanted,...historical])){
                const blank=state.labels.get('')||'— Seleccionar —';select.replaceChildren(new Option(blank,''));
                wanted.forEach(v=>select.add(new Option(state.labels.get(v)||v,v)));
                historical.forEach(v=>{const o=new Option((state.labels.get(v)||v)+' (valor registrado)',v);o.disabled=true;o.dataset.historical='1';select.add(o);});
                select.value=current;
            }
        }
        if(!permitted)return;
        if(!select.querySelector('option[data-manage-choices]')){
            const option=new Option('＋ Agregar o quitar opciones…',manageValue);option.dataset.manageChoices='1';select.add(option);
        }
        if(state.button)return;
        const wrapper=document.createElement('div');wrapper.className='select-options-control';
        select.before(wrapper);wrapper.append(select);
        const button=document.createElement('button');button.type='button';button.className='action-pill pill-neutral select-options-button';
        button.innerHTML='<i class="fa-solid fa-sliders" aria-hidden="true"></i>';
        button.title='Agregar o quitar opciones: '+field.nombre;button.setAttribute('aria-label',button.title);
        wrapper.append(button);state.button=button;
        const open=async()=>{
            const values=[...select.options].filter(o=>o.value&&o.value!==manageValue&&!o.disabled).map(o=>o.value);
            const result=await window.nucleusOptionsDialog('Opciones · '+field.nombre,values);
            if(result===null)return;
            button.disabled=true;
            try{
                const response=await fetch('/api/master/manual_columns/options',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre:field.nombre,opciones:result.split('\n').map(v=>v.trim()).filter(Boolean)})});
                const body=await response.json();if(!response.ok)throw new Error(body.error||'No se guardaron las opciones.');
                field.opciones=body.opciones;field.configurada=true;
                if(typeof manualColsConfig!=='undefined'){
                    const col=manualColsConfig.find(c=>norm(c.nombre)===norm(field.nombre));
                    if(col)col.opciones=body.opciones;
                }
                if(typeof table!=='undefined'){
                    const column=table.getColumns().find(c=>c.getField()===field.nombre);
                    if(column){
                        const definition=column.getDefinition();
                        await column.updateDefinition({editorParams:{...definition.editorParams,values:body.opciones},
                            ...(typeof listaHeaderFilter==='function'?{headerFilter:listaHeaderFilter(body.opciones)}:{})});
                    }
                }
                for(const control of all)if(control.isConnected&&norm(control.dataset.field||ids[control.id]||control.name)===norm(field.nombre))apply(control,field);
            }catch(error){window.nucleusAlert(error.message);}finally{button.disabled=false;}
        };
        button.addEventListener('click',open);
        const remember=()=>{if(select.value!==manageValue)state.previous=select.value;};
        select.addEventListener('pointerdown',remember);select.addEventListener('focus',remember);
        select.addEventListener('change',event=>{
            if(select.value!==manageValue){remember();return;}
            event.stopImmediatePropagation();select.value=state.previous;open();
        },true);
    }
    function scan(root){
        if(root.nodeType!==1&&root!==document)return;
        if(root.closest?.('.tabulator'))return;
        for(const select of all)if(!select.isConnected)all.delete(select);
        const controls=root.matches?.('select')?[root]:root.querySelectorAll('select');
        for(const select of controls){
            if(select.closest('.tabulator, .di-filters, .sidebar'))continue;
            const key=select.dataset.field||ids[select.id]||select.name;
            const field=fields.get(norm(key));if(field)apply(select,field);
        }
    }
    document.addEventListener('DOMContentLoaded',async()=>{
        if(!document.body.dataset.optionsUser)return;
        permitted=['zeno','suport','supervisor'].includes(document.body.dataset.optionsRole);
        try{
            const response=await fetch('/api/master/manual_columns/options');if(!response.ok)return;
            const data=await response.json();fields=new Map(data.campos.map(f=>[norm(f.nombre),f]));scan(document);
            window.nucleusCanManageOptions=name=>fields.has(norm(name));
            window.addEventListener('nucleus:options-updated',event=>{
                const field=fields.get(norm(event.detail.nombre));if(!field)return;
                field.opciones=event.detail.opciones;field.configurada=true;scan(document);
            });
            new MutationObserver(mutations=>{
                const roots=new Set();
                for(const mutation of mutations){
                    const select=mutation.target.closest?.('select');if(select)roots.add(select);
                    for(const node of mutation.addedNodes)if(node.nodeType===1)roots.add(node);
                }
                roots.forEach(scan);
            }).observe(document.body,{subtree:true,childList:true});
        }catch(error){/* A configuration fetch must not block the form. */}
    });
})();
