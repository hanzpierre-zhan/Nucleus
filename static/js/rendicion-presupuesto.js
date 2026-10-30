(function(){
    'use strict';
    let timer,abort;
    const byId=id=>document.getElementById(id);
    const money=value=>'S/ '+new Intl.NumberFormat('es-PE',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value));
    window.rendLeerPresupuesto=()=>({presupuesto:byId('rend-val-presupuesto').value.trim(),cotizacion:byId('rend-val-cotizacion').value.trim()});
    window.rendConsultarPresupuesto=async function(){
        clearTimeout(timer);if(abort)abort.abort();
        if(typeof _rendModal==='undefined'||_rendModal?.accion!=='validar')return;
        const key=_rendModal.key,q=byId('rend-val-cotizacion').value.trim(),status=byId('rend-cotizacion-status'),panel=byId('rend-cotizacion-control');
        panel.hidden=true;status.dataset.estado='';
        if(!q){status.textContent='Ingresa una cotización para consultar el monto acumulado.';byId('rend-val-cotizaciones').replaceChildren();return;}
        status.textContent='Buscando cotización…';
        const params=new URLSearchParams({key,q});
        const monto=document.querySelector('#rend-resumen-grid [data-rend-campo="Monto total del depósito"]');
        if(monto)params.set('monto',monto.value);
        abort=new AbortController();
        try{
            const response=await fetch('/api/rendicion/cotizacion?'+params,{signal:abort.signal});
            const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo consultar la cotización.');
            if(_rendModal?.key!==key||byId('rend-val-cotizacion').value.trim()!==q)return;
            byId('rend-val-cotizaciones').replaceChildren(...result.opciones.map(c=>new Option(c.numero,c.numero)));
            if(!result.encontrada){status.textContent=result.mensaje||'Selecciona una cotización existente de este proyecto.';return;}
            const control=result.control;panel.hidden=false;
            panel.querySelectorAll('[data-rend-control]').forEach(el=>el.textContent=money(control[el.dataset.rendControl]));
            if(control.importes_sin_interpretar){status.dataset.estado='revisar';status.textContent='Acumulado incompleto: hay '+control.importes_sin_interpretar+' solicitudes con un monto inválido. Revisa esos registros antes de usar el saldo.';}
            else{status.dataset.estado=control.excede?'excede':'dentro';status.textContent=control.excede?'Excede el monto cotizado en '+money(-Number(control.saldo))+'.':'Dentro del monto cotizado. Saldo disponible: '+money(control.saldo)+'.';}
        }catch(error){if(error.name!=='AbortError')status.textContent=error.message;}
    };
    window.rendIniciarPresupuesto=row=>{
        byId('rend-val-presupuesto').value=row.PRESUPUESTO??'';
        byId('rend-val-cotizacion').value=row['N° COTIZACION']??'';
        rendConsultarPresupuesto();
    };
    document.addEventListener('input',event=>{
        if(event.target.id==='rend-val-cotizacion'||event.target.dataset.rendCampo==='Monto total del depósito'){
            clearTimeout(timer);timer=setTimeout(rendConsultarPresupuesto,250);
        }
    });
})();
