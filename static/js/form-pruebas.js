(() => {
  'use strict';
  const base = '/form-pruebas', $ = id => document.getElementById(id);
  let state = null, files = [], previewUrls = [];
  let filtroRendicion = 'Por rendir';
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
  const fechaLima = new Intl.DateTimeFormat('es-PE', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Lima'
  });
  function actualizarAntiguedad(indicador) {
    const horas = Math.max(0, Math.floor((Date.now() - Date.parse(indicador.dataset.solicitada)) / 3600000));
    indicador.dataset.nivel = horas >= 24 ? 'rojo' : horas >= 12 ? 'amarillo' : 'normal';
    indicador.textContent = horas ? `${horas} h desde la solicitud` : 'Menos de 1 h desde la solicitud';
  }
  function agregarFechaSolicitud(ficha, fecha) {
    if (!fecha || !Number.isFinite(Date.parse(fecha))) {
      ficha.append(el('small', 'Fecha de solicitud no disponible', 'solicitud-fecha'));
      return;
    }
    const momento = el('time', 'Solicitado el ' + fechaLima.format(new Date(fecha)), 'solicitud-fecha');
    momento.dateTime = fecha;
    const indicador = el('span', undefined, 'solicitud-antiguedad');
    indicador.dataset.solicitada = fecha;
    actualizarAntiguedad(indicador);
    ficha.append(momento, indicador);
  }
  if ($('portal')) setInterval(() => {
    document.querySelectorAll('[data-solicitada]').forEach(actualizarAntiguedad);
  }, 60000);
  function etiquetaEstado(estado) {
    const etiqueta = el('span', 'Estado: ' + estado, 'estado-deposito');
    etiqueta.dataset.estado = estado.toLowerCase();
    return etiqueta;
  }
  function abrirRendicion(deposito) {
    const form = $('rendir');
    if ($('referencia').value !== deposito.referencia) {
      form.reset();
      clearPhotos();
      keys.rendicion = freshKey();
      form.querySelector('.error').hidden = true;
      $('referencia').value = deposito.referencia;
      mostrarConceptos(deposito);
    }
    $('rendir').dataset.saldo = deposito.pendiente;
    actualizarCuadre();
    const resumen = $('resumen-deposito');
    const encabezado = el('div', undefined, 'solicitud-cabecera');
    encabezado.append(el('strong', deposito.codigo), el('strong', money(deposito.monto), 'amount'));
    resumen.replaceChildren(encabezado, etiquetaEstado(deposito.estado),
      el('p', 'Motivo: ' + (deposito.motivo || 'Sin motivo registrado')),
      el('p', 'Saldo por rendir: ' + money(deposito.pendiente)));
    agregarFechaSolicitud(resumen, deposito.fecha_solicitud);
    go('detalle-rendicion');
    $('titulo-rendir').focus({preventScroll: true});
  }
  function mostrarHistorial(registros) {
    const historial = $('historial-solicitudes');
    historial.replaceChildren();
    for (const registro of registros) {
      const ficha = el('article', undefined, 'solicitud-registro');
      const monto = registro.monto !== '' && Number.isFinite(Number(registro.monto)) ? money(registro.monto) : '';
      const encabezado = el('div', undefined, 'solicitud-cabecera');
      encabezado.append(el('strong', registro.codigo));
      if (monto) encabezado.append(el('strong', monto, 'amount'));
      ficha.append(encabezado, etiquetaEstado(registro.estado));
      if (registro.prueba) ficha.append(el('p', 'Solicitud de prueba', 'hint'));
      ficha.append(el('p', 'Motivo: ' + (registro.motivo || 'Sin motivo registrado')));
      agregarFechaSolicitud(ficha, registro.fecha_solicitud);
      if (registro.rechazo) ficha.append(el('p', 'Motivo del rechazo: ' + registro.rechazo));
      historial.append(ficha);
    }
  }
  function mostrarRendicion() {
    const pendientes = state.depositos.filter(deposito => Number(deposito.pendiente) > 0);
    const rechazados = state.historial.filter(registro => registro.estado === 'Rechazado');
    const grupos = new Map([['Por rendir', pendientes], ['Rechazado', rechazados]]);
    const filtros = $('filtros-rendicion');
    filtros.replaceChildren();
    for (const [estado, registros] of grupos) {
      const boton = el('button', estado, 'filtro-rendicion');
      boton.type = 'button';
      boton.append(el('span', String(registros.length)));
      boton.setAttribute('aria-pressed', String(estado === filtroRendicion));
      boton.addEventListener('click', () => {
        filtroRendicion = estado;
        mostrarRendicion();
        filtros.querySelector('[aria-pressed=true]').focus();
      });
      filtros.append(boton);
    }
    const lista = $('depositos');
    lista.replaceChildren();
    const consulta = $('buscar-rendicion').value.trim().toLocaleLowerCase('es');
    const registros = grupos.get(filtroRendicion).filter(registro =>
      [registro.codigo, registro.motivo].some(valor => String(valor || '').toLocaleLowerCase('es').includes(consulta)));
    const mostrarRechazados = filtroRendicion === 'Rechazado';
    mostrarHistorial(mostrarRechazados ? registros : []);
    if (!registros.length) lista.append(el('p', consulta ? 'No encontramos coincidencias.' : 'No tienes registros en este estado.', 'empty'));
    if (mostrarRechazados) return;
    for (const deposito of registros) {
      const ficha = el('button', undefined, 'deposit');
      const descripcion = el('span');
      descripcion.append(el('strong', deposito.codigo), etiquetaEstado(deposito.estado),
        el('small', 'Motivo: ' + (deposito.motivo || 'Sin motivo registrado')));
      agregarFechaSolicitud(descripcion, deposito.fecha_solicitud);
      const importes = el('span');
      importes.append(el('strong', money(deposito.monto), 'amount'),
        el('small', 'Pendiente: ' + money(deposito.pendiente)));
      ficha.append(descripcion, importes);
      ficha.type = 'button';
      ficha.addEventListener('click', () => abrirRendicion(deposito));
      lista.append(ficha);
    }
  }
  $('buscar-rendicion')?.addEventListener('input', mostrarRendicion);
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
    actualizarResponsables();
    actualizarClasificacion();
    actualizarPago();
    $('total').textContent=$('total-rendir').textContent=money(state.total);
    const pending=state.depositos.filter(d=>Number(d.pendiente)>0);$('cantidad').textContent=pending.length?`${pending.length} depósito${pending.length===1?'':'s'} pendiente${pending.length===1?'':'s'} de sustentar`:'Estás al día con tus rendiciones de prueba';
    mostrarRendicion();
    $('lista-recientes').replaceChildren();$('recientes').hidden=!state.recientes.length;
    state.recientes.forEach(r=>{const item=el('div',undefined,'recent'),desc=el('span');desc.append(el('span',r.tipo==='solicitud'?'Solicitud enviada':'Rendición enviada'),el('small',new Date(r.creado).toLocaleString('es-PE',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})));item.append(desc,el('strong',money(r.monto)));$('lista-recientes').append(item);});
    const avisos = $('avisos-pago');
    const novedades = state.historial.filter(r => ['Pagado', 'Rechazado'].includes(r.estado)).slice(0, 5);
    avisos.replaceChildren(...novedades.map(r => el('p', r.estado + ' · ' + r.codigo, 'notice')));
    avisos.hidden = !novedades.length;
    $('cargando').hidden=true;$('portal').hidden=false;
  }
  async function actualizarRendicion() {
    const boton = $('actualizar-rendicion');
    if (boton.disabled) return;
    boton.disabled = true;
    boton.textContent = 'Actualizando…';
    try {
      await load();
      boton.textContent = 'Actualizar estado';
    } catch {
      boton.textContent = 'Reintentar actualización';
    } finally {
      boton.disabled = false;
    }
  }
  $('actualizar-rendicion')?.addEventListener('click', actualizarRendicion);
  document.querySelectorAll('[data-go=rendicion]').forEach(boton => boton.addEventListener('click', () => {
    filtroRendicion = 'Por rendir';
    if (state) mostrarRendicion();
    actualizarRendicion();
  }));
  async function success(data, message) {
    const solicitud = Boolean(data.codigo);
    $('mensaje-exito').textContent = message;
    $('codigo-etiqueta').textContent = solicitud ? 'Código de depósito de prueba' : 'Código de envío de prueba';
    $('codigo-exito').textContent = data.codigo || data.id.slice(0, 8).toUpperCase();
    $('total-exito-grupo').hidden = $('aviso-rendicion').hidden = $('ver-solicitud').hidden = !solicitud;
    $('total-exito').textContent = solicitud ? money(data.monto) : '';
    go('exito');
    await actualizarRendicion();
  }
  function actualizarPago() {
    const aplica = $('tipo-billetera').value !== 'No aplica';
    $('pago-billetera').hidden = !aplica;
    $('numero-billetera').disabled = !aplica;
    $('numero-billetera').required = aplica;
  }
  $('tipo-billetera')?.addEventListener('change', actualizarPago);
  function actualizarResponsables() {
    const select = $('responsable_validacion');
    const proyecto = $('sol-proyecto').value;
    const responsables = Object.entries(state?.responsables_validacion?.[proyecto] || {});
    responsables.sort(([, a], [, b]) => a.localeCompare(b, 'es'));
    select.replaceChildren(new Option(
      responsables.length ? 'Selecciona' : proyecto ? 'Sin responsables asignados' : 'Selecciona un proyecto', ''
    ));
    for (const [id, nombre] of responsables) select.add(new Option(nombre, id));
    select.disabled = !responsables.length;
  }
  $('sol-proyecto')?.addEventListener('change', actualizarResponsables);
  for (const campo of ['site', 'wo']) {
    let espera, consulta;
    const lista = $('sugerencias-' + campo);
    const limpiar = () => {
      clearTimeout(espera);
      consulta?.abort();
      lista.replaceChildren();
    };
    $('sol-proyecto')?.addEventListener('change', () => {
      $(campo).value = '';
      limpiar();
    });
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
  let partidas = [];
  function actualizarClasificacion() {
    const proyecto = $('sol-proyecto').value;
    for (const casilla of $('solicitar').querySelectorAll('[data-regla]')) {
      const regla = JSON.parse(casilla.dataset.regla);
      const clasificacion = proyecto && (typeof regla === 'string' ? regla : regla[proyecto]);
      const tarjeta = casilla.closest('.expense-card');
      tarjeta.hidden = casilla.disabled = !clasificacion;
      if (!clasificacion) casilla.checked = false;
      tarjeta.querySelector('.expense-classification').textContent = clasificacion || '';
    }
    actualizarPartidas();
  }
  $('sol-proyecto')?.addEventListener('change', actualizarClasificacion);
  function actualizarTotal() {
    const centimos = partidas.reduce((total, {input}) => {
      const [soles, decimal = ''] = input.value.split(/[.,]/);
      return total + Number(soles) * 100 + Number(decimal.padEnd(2, '0'));
    }, 0);
    $('gastos-cantidad').textContent = partidas.length === 1 ? '1 gasto' : `${partidas.length} gastos`;
    $('gastos-subtotal').textContent = $('gastos-total').textContent = money(centimos / 100);
  }
  function actualizarPartidas() {
    const importes = new Map(partidas.map(p => [JSON.stringify([p.categoria, p.detalle]), p.input.value]));
    const seleccion = $('solicitar').querySelectorAll('[data-categoria]:checked');
    partidas = Array.from(seleccion, casilla => ({
      categoria: casilla.dataset.categoria,
      detalle: casilla.value,
      etiqueta: casilla.dataset.etiqueta,
      contenedor: casilla.closest('.expense-card').querySelector('.expense-amount')
    }));
    document.querySelectorAll('#solicitar .expense-amount').forEach(contenedor => contenedor.replaceChildren());
    for (const [indice, partida] of partidas.entries()) {
      const {categoria, detalle} = partida;
      const input = el('input');
      input.id = 'importe-gasto-' + indice;
      input.type = 'text';
      input.inputMode = 'decimal';
      input.pattern = '[0-9]+([.,][0-9]{1,2})?';
      input.maxLength = 9;
      input.required = true;
      input.placeholder = '0.00';
      let ultimoMonto = importes.get(JSON.stringify([categoria, detalle])) || '';
      input.value = ultimoMonto;
      input.addEventListener('input', () => {
        if (/^[0-9]*(?:[.,][0-9]{0,2})?$/.test(input.value)) ultimoMonto = input.value;
        else input.value = ultimoMonto;
        actualizarTotal();
      });
      const label = el('label', 'Monto', 'expense-amount-label');
      label.htmlFor = input.id;
      input.setAttribute('aria-label', 'Monto en soles de ' + partida.etiqueta);
      const monto = el('div', undefined, 'money-input');
      monto.append(el('span', 'S/'), input);
      partida.contenedor.append(label, monto);
      partida.input = input;
    }
    actualizarTotal();
  }
  $('solicitar')?.addEventListener('change', event => {
    if (event.target.matches('.expense-options input[type="checkbox"]')) actualizarPartidas();
  });
  $('solicitar')?.addEventListener('reset', () => {
    partidas = [];
    queueMicrotask(actualizarClasificacion);
    queueMicrotask(actualizarResponsables);
  });
  if ($('solicitar')) actualizarClasificacion();
  $('solicitar')?.addEventListener('submit',event=>{
    event.preventDefault();
    const form=event.currentTarget;
    if(!form.reportValidity())return;
    const campos = new FormData(form);
    const gastos = [...new Set(partidas.map(partida => partida.categoria))];
    if (!gastos.length) {
      showError(form, 'Selecciona al menos un gasto.');
      return;
    }
    keys.solicitud ||= freshKey();
    sending(form,async()=>{
      const data=Object.fromEntries(campos);
      data.tipo_gasto = gastos;
      data.partidas = partidas.map(({categoria, detalle, input}) => ({categoria, detalle, monto: input.value}));
      for (const categoria of gastos) {
        const campo = 'detalle_' + categoria.toLowerCase();
        data[campo] = campos.getAll(campo);
      }
      data.nonce=keys.solicitud;
      const result=await api('/solicitar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      keys.solicitud=null;
      form.reset();
      await success(result,'Tu solicitud quedó guardada en el espacio de pruebas.');
    });
  });
  function activarConsultaRuc(ruc, resultado) {
    let consulta;
    ruc.addEventListener('input', async () => {
      consulta?.abort();
      resultado.hidden = !/^[0-9]{11}$/.test(ruc.value);
      if (resultado.hidden) return;
      const actual = new AbortController();
      consulta = actual;
      resultado.textContent = 'Consultando RUC…';
      try {
        const datos = await api('/ruc/' + ruc.value, {signal: actual.signal});
        if (actual.signal.aborted) return;
        if (datos.resultado === 'encontrado') {
          resultado.textContent = datos.razon_social + (datos.activo ? ' · Activo' : ' · No activo');
        } else {
          resultado.textContent = datos.resultado === 'no_encontrado'
            ? 'RUC no encontrado. Revisa los dígitos.'
            : 'Consulta de RUC no disponible en este momento.';
        }
      } catch {
        if (!actual.signal.aborted) resultado.textContent = 'No se pudo consultar el RUC. Revisa la conexión.';
      }
    });
  }
  function mostrarConceptos(deposito) {
    const conceptos = deposito.partidas?.length ? deposito.partidas : [{
      etiqueta: deposito.motivo || 'Gasto del depósito',
      monto: deposito.monto
    }];
    const contenedor = $('conceptos-rendir');
    contenedor.replaceChildren();
    $('nombre-foto-devolucion').textContent = '＋ Adjuntar foto de la devolución';
    for (const concepto of conceptos) {
      const bloque = el('section', undefined, 'concepto-rendir');
      const filas = el('div');
      const agregar = el('button', '＋ Agregar comprobante', 'quiet');
      agregar.type = 'button';
      agregar.addEventListener('click', () => {
        const fila = $('plantilla-comprobante').content.firstElementChild.cloneNode(true);
        const tipo = fila.querySelector('[data-campo=tipo]');
        const ruc = fila.querySelector('[data-campo=ruc]');
        activarConsultaRuc(ruc, fila.querySelector('[data-resultado-ruc]'));
        const quitar = fila.querySelector('[data-quitar]');
        const foto = fila.querySelector('[data-campo=foto]');
        foto.addEventListener('change', () => {
          fila.querySelector('[data-nombre-foto]').textContent = foto.files[0]?.name || '＋ Adjuntar foto del comprobante';
        });
        tipo.addEventListener('change', () => { ruc.required = tipo.value === 'Factura'; });
        quitar.addEventListener('click', () => {
          fila.remove();
          agregar.disabled = false;
          actualizarCuadre();
          agregar.focus();
        });
        filas.append(fila);
        agregar.disabled = filas.children.length >= 8;
        tipo.focus();
      });
      bloque.append(el('h3', concepto.etiqueta));
      if (concepto.monto != null && concepto.monto !== '' && Number.isFinite(Number(concepto.monto))) {
        bloque.append(el('p', 'Monto solicitado ' + money(concepto.monto)));
      }
      bloque.append(el('p', undefined, 'gastado-concepto'), filas, agregar);
      contenedor.append(bloque);
    }
  }
  function aCentimos(valor) {
    const partes = /^([0-9]{1,6})(?:[.,]([0-9]{1,2}))?$/.exec(valor);
    if (!partes) return 0;
    return Number(partes[1]) * 100 + Number((partes[2] || '').padEnd(2, '0'));
  }
  function actualizarCuadre() {
    const saldo = aCentimos($('rendir').dataset.saldo);
    let gastado = 0;
    for (const bloque of $('conceptos-rendir').children) {
      const subtotal = Array.from(bloque.querySelectorAll('[data-campo=monto]'))
        .reduce((total, campo) => total + aCentimos(campo.value), 0);
      bloque.querySelector('.gastado-concepto').textContent = 'Gastado ' + money(subtotal / 100);
      gastado += subtotal;
    }
    const diferencia = saldo - gastado;
    const devolucion = $('devolucion-rendir');
    devolucion.hidden = devolucion.disabled = diferencia <= 0;
    $('monto-devolucion').value = (Math.max(diferencia, 0) / 100).toFixed(2);
    $('cuadre-rendicion').textContent = diferencia < 0
      ? 'El total supera el saldo por ' + money(-diferencia / 100)
      : diferencia === 0 ? 'Saldo completo ' + money(saldo / 100) : '';
    return diferencia >= 0;
  }
  $('conceptos-rendir')?.addEventListener('input', actualizarCuadre);
  $('foto-devolucion')?.addEventListener('change', event => {
    $('nombre-foto-devolucion').textContent = event.target.files[0]?.name || '＋ Adjuntar foto de la devolución';
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
  $('rendir')?.addEventListener('submit', event => {
    event.preventDefault();
    const form = event.currentTarget;
    const cuadra = actualizarCuadre();
    if (!form.reportValidity()) return;
    if (!cuadra) {
      showError(form, $('cuadre-rendicion').textContent);
      return;
    }
    if (form.querySelectorAll('.comprobante-rendir').length > 24) {
      showError(form, 'Puedes adjuntar hasta 24 comprobantes por rendición.');
      return;
    }
    keys.rendicion ||= freshKey();
    sending(form, async () => {
      const data = new FormData(form);
      data.set('nonce', keys.rendicion);
      const adjuntos = [];
      const grupos = Array.from($('conceptos-rendir').children, (bloque, indice) =>
        Array.from(bloque.querySelectorAll('.comprobante-rendir'), (fila, posicion) => {
          const campo = nombre => fila.querySelector(`[data-campo=${nombre}]`);
          adjuntos.push([`comprobante-${indice}-${posicion}`, campo('foto').files[0]]);
          return {tipo: campo('tipo').value, ruc: campo('ruc').value, monto: campo('monto').value};
        })
      );
      data.set('comprobantes', JSON.stringify(grupos));
      if (!$('devolucion-rendir').disabled) {
        data.set('foto_devolucion', await compress($('foto-devolucion').files[0]));
      }
      files.forEach(foto => data.append('evidencia', foto));
      for (const [nombre, foto] of adjuntos) data.append(nombre, await compress(foto));
      const result = await api('/rendir', {method: 'POST', body: data});
      keys.rendicion = null;
      form.reset();
      $('referencia').value = '';
      clearPhotos();
      const aviso = result.fotos_comprobante_repetidas
        ? ' Se detectó una foto repetida. El validador revisará el comprobante.' : '';
      await success(result, 'Tu rendición quedó guardada en el espacio de pruebas.' + aviso);
    });
  });
  if($('portal'))load().catch(error=>{const box=$('cargando');box.setAttribute('role','alert');box.textContent=error.message;const retry=el('button','Volver a intentar','back');retry.type='button';retry.onclick=()=>location.reload();box.append(retry);});
})();
