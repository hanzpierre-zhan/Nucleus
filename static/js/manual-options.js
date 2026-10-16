(function(){
    window.nucleusOptionsDialog = function(title, options){
        return new Promise(resolve=>{
            const dialog=document.createElement('dialog');dialog.className='manual-options-dialog';
            const form=document.createElement('form');form.method='dialog';
            const heading=document.createElement('h2');heading.textContent=title;
            const help=document.createElement('p');help.textContent='Agrega opciones o elimina las que ya no se usarán. Los datos ya registrados se conservan.';
            const list=document.createElement('div');list.className='manual-options-list';
            function addRow(value=''){
                const row=document.createElement('div');row.className='manual-option-row';
                const input=document.createElement('input');input.type='text';input.value=value;input.maxLength=200;input.setAttribute('aria-label','Opción');
                const remove=document.createElement('button');remove.type='button';remove.className='action-pill pill-red';remove.textContent='Quitar';remove.setAttribute('aria-label','Quitar opción');remove.onclick=()=>row.remove();
                row.append(input,remove);list.append(row);return input;
            }
            options.forEach(addRow);
            const add=document.createElement('button');add.type='button';add.className='action-pill pill-blue';add.textContent='+ Agregar opción';add.onclick=()=>addRow().focus();
            const actions=document.createElement('div');actions.className='manual-options-actions';
            const cancel=document.createElement('button');cancel.type='button';cancel.className='action-pill pill-neutral';cancel.textContent='Cancelar';
            const save=document.createElement('button');save.type='submit';save.className='action-pill pill-blue';save.textContent='Guardar opciones';
            let result=null;cancel.onclick=()=>dialog.close();form.onsubmit=()=>{result=[...list.querySelectorAll('input')].map(i=>i.value.trim()).filter(Boolean).join('\n');};
            dialog.addEventListener('close',()=>{resolve(result);dialog.remove();},{once:true});
            actions.append(cancel,save);form.append(heading,help,list,add,actions);dialog.append(form);document.body.append(dialog);dialog.showModal();
            (list.querySelector('input')||add).focus();
        });
    };
})();

// Editor de listas manuales: el identificador especial nunca se guarda en la fila.
window.nucleusManualListEditor = function(cell, onRendered, success, cancel) {
    const field=cell.getField();
    const column=manualColsConfig.find(c=>c.nombre===field);
    const select=document.createElement('select');select.style.cssText='width:100%;height:100%;color:var(--ios-label);background:var(--ios-card-bg)';
    const current=String(cell.getValue()??'');
    select.add(new Option('— Seleccionar —',''));
    const values=Array.from(new Set(column?.opciones||[]));
    for(const value of values)select.add(new Option(value,value));
    if(current && !values.includes(current))select.add(new Option(current+' (registrado)',current));
    const canManage=['zeno','suport','supervisor'].includes(document.body.dataset.optionsRole)
        && window.nucleusCanManageOptions?.(field);
    const manage='__nucleus_manage_manual__';
    if(canManage)select.add(new Option('＋ Agregar o quitar opciones…',manage));
    select.value=current;
    select.addEventListener('change',async()=>{
        if(select.value!==manage){success(select.value);return;}
        cancel();
        const result=await nucleusOptionsDialog('Opciones · '+field,values);
        if(result===null)return;
        try{
            const response=await fetch('/api/master/manual_columns/options',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre:field,opciones:result.split('\n').map(x=>x.trim()).filter(Boolean)})});
            const data=await response.json();if(!response.ok)throw new Error(data.error||'No se guardaron las opciones.');
            column.opciones=data.opciones;
            window.dispatchEvent(new CustomEvent('nucleus:options-updated',{detail:{nombre:field,opciones:data.opciones}}));
            cell.getTable().redraw();
        }catch(error){window.nucleusAlert(error.message);}
    });
    select.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();cancel();}});
    onRendered(()=>select.focus());
    return select;
};
