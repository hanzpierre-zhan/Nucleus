(() => {
const iniciar=()=>{const form=document.getElementById('mar-fields');if(!form)return;
const completar=()=>{const campo=form.querySelector('select[data-field="PROYECTO"]');if(!campo||campo.value)return;const opciones=[...campo.options].filter(o=>o.value);if(opciones.length===1){campo.value=opciones[0].value;campo.dispatchEvent(new Event('change',{bubbles:true}));}};
new MutationObserver(completar).observe(form,{childList:true});completar();};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',iniciar);else iniciar();
})();
