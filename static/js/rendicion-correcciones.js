(function(){
    'use strict';
    let base = null, saving = false;
    const norm = field => String(field).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
    const campos = new Set(['DEPARTAMENTO','Documento del beneficiario','Motivo de la solicitud','Número CM / PM / PLM','Nombre de site','Monto total del depósito','Tipo de gasto','Tipo de presupuesto','Titular de la cuenta','Número de cuenta o CCI','Número de celular o CCI','Numero de Yape/Plin','Tipo de billetera digital','Tipo de depósito a realizar','Supervisor encargado','Observaciones (Form)','Criticidad - Prioridad'].map(norm));
    window.rendCampoCorregible = field => campos.has(norm(field));
    window.rendIniciarCorrecciones = data => { base = {...data}; };
    function cambios() {
        const result = {};
        if (!base) return result;
        document.querySelectorAll('#rend-resumen-grid [data-rend-campo]').forEach(input=>{
            const field=input.dataset.rendCampo;
            if(input.value.trim()!==String(base[field]??'').trim()) result[field]=input.value.trim();
        });
        return result;
    }
    window.rendHayCorrecciones = () => Object.keys(cambios()).length>0;
    window.rendGuardarCorrecciones = async function(){
        const editados=cambios();
        if(saving || !_rendModal || _rendModal.accion!=='validar') return;
        const status=document.getElementById('rend-correccion-status');
        if(!Object.keys(editados).length){status.textContent='No hay cambios para guardar.';return;}
        const key=_rendModal.key;
        const presupuesto=rendLeerPresupuesto();
        const obs=document.getElementById('rend-val-obs').value;
        const op=document.querySelector('#rend-val-ops input:checked')?.value;
        const button=document.getElementById('rend-correccion-save');
        const confirmar=document.getElementById('rend-modal-ok');
        saving=true;button.disabled=true;confirmar.disabled=true;status.textContent='Guardando correcciones…';
        try {
            const response=await fetch('/api/rendicion/solicitud',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,cambios:editados,revision:base._CORRECCION_REV||0})});
            const data=await response.json();if(!response.ok)throw new Error(data.error||'No se pudieron guardar las correcciones.');
            rendTrasAccion(data,key);rendValidar(key);
            document.getElementById('rend-val-presupuesto').value=presupuesto.presupuesto;
            document.getElementById('rend-val-cotizacion').value=presupuesto.cotizacion;
            rendConsultarPresupuesto();
            document.getElementById('rend-val-obs').value=obs;
            if(op)document.querySelectorAll('#rend-val-ops input').forEach(input=>input.checked=input.value===op);
            document.getElementById('rend-correccion-status').textContent='Correcciones guardadas. La solicitud sigue en Validación.';
        }catch(error){status.textContent=error.message;}
        finally{saving=false;button.disabled=false;confirmar.disabled=false;}
    };
})();
