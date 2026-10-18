(() => {
const selector=document.getElementById('proyecto');
if(!selector || location.pathname==='/espacios')return;
selector.addEventListener('change',()=>{const active=document.querySelector('[data-modulo].active') || document.querySelector('[data-modulo]');if(active)location.assign(`/espacios?modulo=${encodeURIComponent(active.dataset.modulo)}&proyecto=${encodeURIComponent(selector.value)}`);});
})();
