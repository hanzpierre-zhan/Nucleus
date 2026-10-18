(() => {
const init=()=>{const form=document.getElementById('mar-fields');if(!form)return;
const decorar=()=>{const estado=form.querySelector('[data-field="ESTADO"]');if(estado){estado.dataset.status=estado.value;for(const o of estado.options){if(o.value==='ACTIVO')o.textContent='● Activo';if(o.value==='CESADO')o.textContent='● Cesado';}estado.onchange=()=>{estado.dataset.status=estado.value;};}
const supervisor=form.querySelector('[data-field="SUPERVISOR"]');const defaults=JSON.parse(document.getElementById('personal-registro-default').textContent);if(supervisor&&['gestor','supervisor'].includes(defaults.rol)&&(typeof manualEditMode==='undefined'||!manualEditMode)){if(!supervisor.value)supervisor.value=defaults.supervisor;supervisor.readOnly=true;}
const proyecto=form.querySelector('select[data-field="PROYECTO"]');if(proyecto){const opciones=[...proyecto.options].filter(o=>o.value);if(!proyecto.value&&opciones.length===1){proyecto.value=opciones[0].value;proyecto.dispatchEvent(new Event('change',{bubbles:true}));}}};
new MutationObserver(decorar).observe(form,{childList:true});form.addEventListener('change',e=>{if(e.target.dataset.field==='ESTADO')e.target.dataset.status=e.target.value;});decorar();};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
