(function(){
    window.nucleusOptionsDialog = function(title, options){
        return new Promise(resolve=>{
            const dialog=document.createElement('dialog');dialog.className='manual-options-dialog';
            const form=document.createElement('form');form.method='dialog';
            const heading=document.createElement('h2');heading.textContent=title;
            const help=document.createElement('p');help.textContent='Una opción por línea. Puedes agregar o quitar opciones. Los valores ya registrados se conservan.';
            const input=document.createElement('textarea');input.rows=10;input.value=options.join('\n');input.setAttribute('aria-label','Opciones del campo');
            const actions=document.createElement('div');actions.className='manual-options-actions';
            const cancel=document.createElement('button');cancel.type='button';cancel.className='action-pill pill-neutral';cancel.textContent='Cancelar';
            const save=document.createElement('button');save.type='submit';save.className='action-pill pill-blue';save.textContent='Guardar opciones';
            let result=null;cancel.addEventListener('click',()=>dialog.close());form.addEventListener('submit',()=>{result=input.value;});
            dialog.addEventListener('close',()=>{resolve(result);dialog.remove();},{once:true});
            actions.append(cancel,save);form.append(heading,help,input,actions);dialog.append(form);document.body.append(dialog);dialog.showModal();input.focus();
        });
    };
})();
