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
