(() => {
  'use strict';
  const base = '/form-pruebas', $ = id => document.getElementById(id);
  let state = null, files = [], previewUrls = [];
  const keys = {};
  const token = () => $('csrf').value;
  const freshKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2,'0')).join('');
  const money = value => new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(Number(value));
  const el = (tag,text,className) => {const node=document.createElement(tag); if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
  async function api(path, options={}) {
    const response=await fetch(base+path,{credentials:'same-origin',...options,headers:{'X-CSRF-Token':token(),...(options.headers||{})}});
    let data;try{data=await response.json();}catch{throw Error('No se pudo leer la respuesta. Revisa tu conexión y vuelve a intentar.');}
    if(!response.ok){if(response.status===401 && !$('login'))location.reload();throw Error(data.error||'No se pudo completar el envío.');}
    return data;
  }
  function showError(form,message){const box=form.querySelector('.error');box.textContent=message;box.hidden=false;box.focus();}
  async function sending(form,fn){const button=form.querySelector('[type=submit]'),label=button.textContent;button.disabled=true;button.textContent='Enviando…';form.querySelector('.error').hidden=true;try{await fn();}catch(error){showError(form,error.message);}finally{button.disabled=false;button.textContent=label;}}
  function go(name){for(const view of document.querySelectorAll('.view'))view.hidden=view.id!==name;window.scrollTo({top:0,behavior:'smooth'});}
  document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>go(button.dataset.go)));
  $('ver-clave')?.addEventListener('click',()=>{const input=$('clave');input.type=input.type==='password'?'text':'password';$('ver-clave').textContent=input.type==='password'?'Mostrar':'Ocultar';});
  $('login')?.addEventListener('submit',event=>{event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;sending(form,async()=>{await api('/ingresar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});location.reload();});});
  $('salir')?.addEventListener('click',async()=>{try{await api('/salir',{method:'POST'});location.reload();}catch(error){alert(error.message);}});
  async function load(){
    state=await api('/datos');$('csrf').value=state.csrf;
    $('nombre').textContent=state.personal.nombre.split(/\s+/)[0];$('proyecto').textContent=state.personal.proyecto||'TU ESPACIO';
    $('sol-nombre').value=state.personal.nombre;
    $('sol-dni').value=state.personal.documento;
    $('sol-supervisor').value=state.personal.supervisor || '';
    if ($('sol-proyecto').options.length === 1) {
      state.proyectos.forEach(p => $('sol-proyecto').add(new Option(p === 'PEXT' ? p : p[0] + p.slice(1).toLowerCase(), p)));
    }
    $('sol-proyecto').value=state.proyecto_default;
    actualizarPago();
    $('total').textContent=$('total-rendir').textContent=money(state.total);
    const pending=state.depositos.filter(d=>Number(d.pendiente)>0);$('cantidad').textContent=pending.length?`${pending.length} depósito${pending.length===1?'':'s'} pendiente${pending.length===1?'':'s'} de sustentar`:'Estás al día con tus rendiciones de prueba';
    const list=$('depositos');list.replaceChildren();
    if(!state.depositos.length){const empty=el('div',undefined,'empty');empty.append(el('strong','No tienes depósitos pendientes'),el('span','Aquí aparecerán los códigos depositados a tu documento que todavía requieren evidencia.'));list.append(empty);}
    state.depositos.forEach(d=>{
      const button=el('button',undefined,'deposit');button.type='button';button.disabled=Number(d.pendiente)<=0;
      const text=el('span');text.append(el('strong',d.codigo),el('small',button.disabled?'Enviado en pruebas':d.motivo||'Pendiente de sustento'));
      button.append(text,el('span',money(d.pendiente),'amount'));button.addEventListener('click',()=>{
        list.querySelectorAll('.deposit').forEach(b=>b.classList.toggle('selected',b===button));
        $('rendir').reset();clearPhotos();keys.rendicion=freshKey();$('rendir').querySelector('.error').hidden=true;
        $('referencia').value=d.referencia;$('deposito-titulo').textContent=d.codigo;$('monto-rendir').value=d.pendiente;
        $('saldo-deposito').textContent=`Disponible en pruebas: ${money(d.pendiente)}. Puedes rendir una parte.`;
        $('rendir').hidden=false;$('rendir').scrollIntoView({behavior:'smooth',block:'start'});
      });list.append(button);
    });
    $('lista-recientes').replaceChildren();$('recientes').hidden=!state.recientes.length;
    state.recientes.forEach(r=>{const item=el('div',undefined,'recent'),desc=el('span');desc.append(el('span',r.tipo==='solicitud'?'Solicitud enviada':'Rendición enviada'),el('small',new Date(r.creado).toLocaleString('es-PE',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})));item.append(desc,el('strong',money(r.monto)));$('lista-recientes').append(item);});
    $('cargando').hidden=true;$('portal').hidden=false;
  }
  async function success(data,message){await load();$('mensaje-exito').textContent=message;$('codigo-exito').textContent='PRUEBA · '+data.id.slice(0,8).toUpperCase();go('exito');}
  function actualizarPago() {
    const medio = $('medio_pago').value;
    const billetera = medio === 'Yape' || medio === 'Plin';
    for (const [contenedor, campo, activo] of [
      ['pago-billetera', 'numero-billetera', billetera],
      ['pago-cuenta', 'cuenta-cci', medio === 'Transferencia bancaria'],
      ['pago-titular', 'titular', billetera || medio === 'Transferencia bancaria']
    ]) {
      $(contenedor).hidden = !activo;
      $(campo).disabled = !activo;
      $(campo).required = activo;
    }
  }
  $('medio_pago')?.addEventListener('change', actualizarPago);
  for (const campo of ['site', 'wo']) {
    let espera, consulta;
    const lista = $('sugerencias-' + campo);
    const limpiar = () => {
      clearTimeout(espera);
      consulta?.abort();
      lista.replaceChildren();
    };
    $('sol-proyecto')?.addEventListener('change', limpiar);
    $('solicitar')?.addEventListener('reset', limpiar);
    function buscar() {
      limpiar();
      const q = $(campo).value.trim(), proyecto = $('sol-proyecto').value;
      if (!proyecto || q.length < 2) {
        lista.textContent = proyecto ? 'Escribe al menos dos caracteres.' : 'Selecciona un proyecto.';
        return;
      }
      espera = setTimeout(async () => {
        const actual = new AbortController();
        consulta = actual;
        try {
          const parametros = new URLSearchParams({campo, q, proyecto});
          const resultado = await api('/sugerencias?' + parametros, {signal: actual.signal});
          if (actual.signal.aborted) return;
          const botones = resultado.opciones.map(valor => {
            const boton = el('button', valor);
            boton.type = 'button';
            boton.onclick = () => {
              $(campo).value = valor;
              limpiar();
            };
            return boton;
          });
          lista.replaceChildren(...botones);
          if (!botones.length) lista.textContent = 'Sin coincidencias para este proyecto.';
        } catch (error) {
          if (!actual.signal.aborted) lista.textContent = 'No se pudieron cargar las sugerencias.';
        }
      }, 250);
    }
    $(campo)?.addEventListener('input', buscar);
  }
  const montoSolicitud = $('monto-sol');
  let ultimoMonto = '';
  montoSolicitud?.addEventListener('input', () => {
    if (/^[0-9]*(?:[.,][0-9]{0,2})?$/.test(montoSolicitud.value)) {
      ultimoMonto = montoSolicitud.value;
    } else {
      montoSolicitud.value = ultimoMonto;
    }
  });
  $('solicitar')?.addEventListener('reset', () => { ultimoMonto = ''; });
  $('solicitar')?.addEventListener('submit',event=>{
    event.preventDefault();
    const form=event.currentTarget;
    if(!form.reportValidity())return;
    const campos = new FormData(form);
    const gastos = campos.getAll('tipo_gasto');
    if (!gastos.length) {
      showError(form, 'Selecciona al menos un tipo de gasto.');
      return;
    }
    keys.solicitud ||= freshKey();
    sending(form,async()=>{
      const data=Object.fromEntries(campos);
      data.tipo_gasto = gastos;
      data.cuenta = data.medio_pago === 'No aplica' ? '' :
        data.medio_pago === 'Transferencia bancaria' ? $('cuenta-cci').value : $('numero-billetera').value;
      data.nonce=keys.solicitud;
      const result=await api('/solicitar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      keys.solicitud=null;
      form.reset();
      await success(result,'Tu solicitud quedó guardada en el espacio de pruebas.');
    });
  });
  function clearPhotos(){files=[];renderPhotos();}
  function renderPhotos(){previewUrls.forEach(URL.revokeObjectURL);previewUrls=[];$('fotos').replaceChildren();files.forEach((file,index)=>{const card=el('div',undefined,'photo'),img=el('img'),remove=el('button','×');const url=URL.createObjectURL(file);previewUrls.push(url);img.src=url;img.alt=`Comprobante ${index+1}`;remove.type='button';remove.setAttribute('aria-label',`Quitar foto ${index+1}`);remove.addEventListener('click',()=>{files.splice(index,1);renderPhotos();});card.append(img,remove);$('fotos').append(card);});}
  async function compress(file){
    if(file.size>10*1024*1024)throw Error('Cada foto debe pesar como máximo 10 MB.');
    if(!/^image\//.test(file.type))throw Error('Selecciona solo fotos de tus comprobantes.');
    try{const image=await createImageBitmap(file,{imageOrientation:'from-image'});const ratio=Math.min(1,1600/Math.max(image.width,image.height));const canvas=document.createElement('canvas');canvas.width=Math.round(image.width*ratio);canvas.height=Math.round(image.height*ratio);canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);image.close();const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.82));return blob?new File([blob],'comprobante.jpg',{type:'image/jpeg'}):file;}catch{return file;}
  }
  for(const id of ['camara','galeria'])$(id)?.addEventListener('change',async event=>{
    const chosen=Array.from(event.target.files);event.target.value='';const form=$('rendir');
    if(files.length+chosen.length>8){showError(form,'Puedes adjuntar como máximo 8 fotos.');return;}
    try{const ready=[];for(const file of chosen)ready.push(await compress(file));files.push(...ready);renderPhotos();}catch(error){showError(form,error.message);}
  });
  $('rendir')?.addEventListener('submit',event=>{event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;if(!files.length){showError(form,'Agrega al menos una foto del comprobante.');return;}keys.rendicion ||= freshKey();sending(form,async()=>{const data=new FormData(form);data.set('nonce',keys.rendicion);files.forEach(f=>data.append('fotos',f));const result=await api('/rendir',{method:'POST',body:data});keys.rendicion=null;form.reset();clearPhotos();form.hidden=true;await success(result,'Tu rendición y tus fotos quedaron guardadas por separado para la prueba.');});});
  if($('portal'))load().catch(error=>{const box=$('cargando');box.setAttribute('role','alert');box.textContent=error.message;const retry=el('button','Volver a intentar','back');retry.type='button';retry.onclick=()=>location.reload();box.append(retry);});
})();
