/* Caja Chica · portal del técnico: solicitar por ítems y rendir cada ítem. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = '/form-pruebas/caja-chica';
  const ESTADOS = {PENDIENTE: 'En validación', VALIDADO: 'Por depositar', DEPOSITADO: 'Por rendir',
                   POR_DEVOLVER: 'Falta la devolución', ARCHIVADO: 'Archivado', RECHAZADO: 'Rechazado: corrige y reenvía', ANULADO: 'Anulado'};
  const ITEM = {POR_RENDIR: 'Por rendir', EN_REVISION: 'En revisión', APROBADO: 'Aprobado', RECHAZADO: 'Rechazado: vuelve a rendir'};
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const numero = v => { const t = String(v || '').replace(/\s/g, '').replace(/,(?=\d{3}(\D|$))/g, '').replace(',', '.'); return /^\d+(\.\d{1,2})?$/.test(t) ? Number(t) : NaN; };
  let datos = null, corrigiendo = null;  // corrigiendo = solicitud rechazada que se está reenviando

  async function api(ruta, opciones = {}, prefijo = base) {
    const r = await fetch(prefijo + ruta, {credentials: 'same-origin', ...opciones, headers: {'X-CSRF-Token': $('csrf').value, ...(opciones.headers || {})}});
    let j; try { j = await r.json(); } catch { throw Error('No se pudo leer la respuesta. Revisa tu conexión.'); }
    if (r.status === 401 || (r.status === 403 && j.codigo === 'CAMBIAR_CLAVE')) { location.href = '/form-pruebas/'; throw Error(j.error); }
    if (!r.ok) throw Error(j.error || 'No se pudo completar el envío.');
    return j;
  }
  function ver(id) { document.querySelectorAll('.view').forEach(v => { v.hidden = v.id !== id; }); window.scrollTo({top: 0, behavior: 'smooth'}); }
  async function enviando(boton, caja, fn) {
    const texto = boton.textContent; boton.disabled = true; boton.textContent = 'Enviando…'; caja.hidden = true;
    try { await fn(); } catch (e) { caja.textContent = e.message; caja.hidden = false; caja.focus(); }
    finally { boton.disabled = false; boton.textContent = texto; }
  }

  // ── Lista de solicitudes ──
  function foto(sid, nombre, texto) { const a = el('a', 'cc-foto', texto); a.href = base + '/foto/' + sid + '/' + nombre; a.target = '_blank'; a.rel = 'noopener'; return a; }
  function formRendir(sol, item) {
    const form = el('form', 'cc-rendir'); form.noValidate = true;
    const campos = [['ruc', 'RUC del comprobante', 'numeric', '20123456789'], ['comprobante', 'N° de boleta o factura', 'text', 'F001-000123'],
                    ['monto_gastado', 'Monto gastado (S/)', 'decimal', item.monto]];
    for (const [nombre, titulo, modo, ejemplo] of campos) {
      const id = 'r' + item.id + '-' + nombre, label = el('label', null, titulo), input = el('input');
      label.htmlFor = id; Object.assign(input, {id, name: nombre, inputMode: modo, placeholder: ejemplo, required: true, maxLength: 40});
      form.append(label, input);
    }
    const lf = el('label', null, 'Fotos del comprobante (1 a 5)'), fotos = el('input'); lf.htmlFor = 'r' + item.id + '-fotos';
    Object.assign(fotos, {id: 'r' + item.id + '-fotos', type: 'file', name: 'fotos', accept: 'image/*', multiple: true, required: true});
    const error = el('div', 'error'); error.setAttribute('role', 'alert'); error.tabIndex = -1; error.hidden = true;
    const boton = el('button', 'primary wide', 'Rendir ítem ' + item.numero); boton.type = 'submit';
    form.append(lf, fotos, error, boton);
    form.addEventListener('submit', e => { e.preventDefault(); enviando(boton, error, async () => {
      if (!fotos.files.length) throw Error('Adjunta al menos una foto del comprobante.');
      if (fotos.files.length > 5) throw Error('Adjunta como máximo 5 fotos.');
      await api('/' + sol.id + '/item/' + item.id + '/rendir', {method: 'POST', body: new FormData(form)});
      await cargar();
    }); });
    return form;
  }
  function formDevolucion(sol) {
    const form = el('form', 'cc-rendir'); form.noValidate = true;
    form.append(el('p', 'notice', 'Gastaste menos de lo depositado. Devuelve ' + dinero(sol.diferencia) + ' y adjunta la foto del depósito.'));
    const monto = el('input'); Object.assign(monto, {name: 'monto', value: sol.diferencia, readOnly: true});
    const archivo = el('input'); Object.assign(archivo, {type: 'file', name: 'foto', accept: 'image/*', required: true});
    const error = el('div', 'error'); error.hidden = true; error.tabIndex = -1;
    const boton = el('button', 'primary wide', 'Registrar devolución'); boton.type = 'submit';
    form.append(el('label', null, 'Monto a devolver (S/)'), monto, el('label', null, 'Foto del depósito'), archivo, error, boton);
    form.addEventListener('submit', e => { e.preventDefault(); enviando(boton, error, async () => {
      if (!archivo.files.length) throw Error('Adjunta la foto del depósito de devolución.');
      await api('/' + sol.id + '/devolucion', {method: 'POST', body: new FormData(form)}); await cargar();
    }); });
    return form;
  }
  const fechaLima = new Intl.DateTimeFormat('es-PE', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Lima'
  });
  let filtroRendicion = 'Por rendir';
  function montoPendiente(sol) {
    if (sol.estado === 'POR_DEVOLVER') return sol.devolucion_foto ? 0 : Math.round(Number(sol.diferencia) * 100);
    if (sol.estado !== 'DEPOSITADO') return 0;
    return sol.items.filter(item => ['POR_RENDIR', 'RECHAZADO'].includes(item.estado))
      .reduce((suma, item) => suma + Math.round(Number(item.monto) * 100), 0);
  }
  function rechazado(sol) {
    return sol.estado === 'RECHAZADO' || (sol.estado === 'DEPOSITADO' && sol.items.some(item => item.estado === 'RECHAZADO'))
      || (sol.estado === 'POR_DEVOLVER' && sol.historial?.at(-1)?.accion === 'rechazar devolución');
  }
  function actualizarAntiguedad() {
    document.querySelectorAll('[data-cc-solicitada]').forEach(indicador => {
      const horas = Math.max(0, Math.floor((Date.now() - Date.parse(indicador.dataset.ccSolicitada)) / 3600000));
      const dias = Math.floor(horas / 24), resto = horas % 24;
      indicador.dataset.nivel = horas >= 24 ? 'rojo' : horas >= 12 ? 'amarillo' : 'normal';
      indicador.textContent = (dias ? dias + ' d ' : '') + resto + ' h desde la solicitud';
    });
  }
  setInterval(actualizarAntiguedad, 60000);
  function fichaDeposito(sol) {
    const descripcion = el('span');
    descripcion.append(el('strong', null, sol.codigo),
      el('span', 'cc-estado cc-' + sol.estado.toLowerCase(), rechazado(sol) ? 'Rechazado' : ESTADOS[sol.estado]),
      el('small', null, 'Motivo: ' + (sol.motivo || 'Sin motivo registrado')));
    const ultimo = sol.historial?.at(-1);
    const rechazo = sol.motivo_rechazo || sol.items.find(item => item.estado === 'RECHAZADO')?.motivo_rechazo
      || (ultimo?.accion === 'rechazar devolución' ? ultimo.motivo : '');
    if (rechazo) descripcion.append(el('small', null, 'Motivo del rechazo: ' + rechazo));
    const fecha = sol.creado ? sol.creado + 'Z' : '';
    if (Number.isFinite(Date.parse(fecha))) {
      const momento = el('time', 'solicitud-fecha', 'Solicitado el ' + fechaLima.format(new Date(fecha)));
      momento.dateTime = fecha;
      const antiguedad = el('span', 'solicitud-antiguedad');
      antiguedad.dataset.ccSolicitada = fecha;
      descripcion.append(momento, antiguedad);
    }
    const montos = el('span', 'cc-rendir-importes');
    const pendiente = montoPendiente(sol);
    montos.append(el('strong', 'cc-rendir-monto', dinero(pendiente ? pendiente / 100 : sol.total)),
      el('small', null, sol.estado === 'POR_DEVOLVER' ? 'Por devolver' : pendiente ? 'Por rendir' : 'Solicitado'));
    if (pendiente > 0 && pendiente !== Math.round(Number(sol.total) * 100)) {
      montos.append(el('small', null, 'Total solicitado: ' + dinero(sol.total)));
    }
    return [descripcion, montos];
  }
  function abrirRendicion(sol) {
    const detalle = $('cc-detalle-contenido');
    const resumen = el('div', 'deposit');
    resumen.append(...fichaDeposito(sol));
    detalle.replaceChildren(resumen);
    $('cc-titulo-rendir').textContent = sol.estado === 'RECHAZADO' ? 'Solicitud rechazada' : 'Rendir depósito';
    for (const item of sol.items) {
      const fila = el('section', 'card cc-item-fila');
      const cab = el('div', 'cc-item-cabecera');
      cab.append(el('strong', null, item.tipo_gasto), el('span', 'cc-chip cc-' + item.estado.toLowerCase(), ITEM[item.estado]));
      fila.append(cab, el('small', null, (item.descripcion ? item.descripcion + ' · ' : '') + dinero(item.monto)));
      if (item.motivo_rechazo) fila.append(el('p', 'notice', 'Rechazado: ' + item.motivo_rechazo));
      if (item.fotos.length) {
        const fotos = el('div', 'cc-fotos');
        item.fotos.forEach((nombre, i) => fotos.append(foto(sol.id, nombre, 'Foto ' + (i + 1))));
        fila.append(fotos);
      }
      if (sol.estado === 'DEPOSITADO' && ['POR_RENDIR', 'RECHAZADO'].includes(item.estado)) fila.append(formRendir(sol, item));
      detalle.append(fila);
    }
    if (sol.estado === 'POR_DEVOLVER' && !sol.devolucion_foto) detalle.append(formDevolucion(sol));
    if (sol.estado === 'RECHAZADO') {
      const corregir = el('button', 'primary wide', 'Corregir y reenviar');
      corregir.type = 'button';
      corregir.addEventListener('click', () => abrirFormulario(sol));
      detalle.append(corregir);
    }
    actualizarAntiguedad();
    ver('cc-detalle-rendicion');
    $('cc-titulo-rendir').focus({preventScroll: true});
  }
  function pintar() {
    const grupos = {
      'Por rendir': datos.solicitudes.filter(sol => montoPendiente(sol) > 0 && !rechazado(sol)),
      'Rechazado': datos.solicitudes.filter(rechazado)
    };
    const total = datos.solicitudes.reduce((suma, sol) => suma + montoPendiente(sol), 0);
    $('cc-pendiente').textContent = dinero(total / 100);
    const filtros = $('cc-filtros');
    filtros.replaceChildren();
    for (const [estado, solicitudes] of Object.entries(grupos)) {
      const boton = el('button', 'filtro-rendicion', estado);
      boton.type = 'button';
      boton.append(el('span', null, String(solicitudes.length)));
      boton.setAttribute('aria-pressed', String(estado === filtroRendicion));
      boton.addEventListener('click', () => {
        filtroRendicion = estado;
        pintar();
        filtros.querySelector('[aria-pressed=true]').focus();
      });
      filtros.append(boton);
    }
    const lista = $('cc-lista');
    lista.replaceChildren();
    const solicitudes = grupos[filtroRendicion];
    if (!solicitudes.length) lista.append(el('p', 'empty', filtroRendicion === 'Por rendir'
      ? 'No tienes depósitos pendientes por rendir.' : 'No tienes registros rechazados.'));
    for (const sol of solicitudes) {
      const ficha = el('button', 'deposit');
      ficha.type = 'button';
      ficha.append(...fichaDeposito(sol));
      ficha.addEventListener('click', () => abrirRendicion(sol));
      lista.append(ficha);
    }
    actualizarAntiguedad();
  }
  async function cargar() { datos = await api('/datos'); pintar(); $('cargando').hidden = true; ver('cc-inicio'); }

  // ── Nueva solicitud ──
  function itemsSeleccionados() {
    return [...$('cc-items').querySelectorAll('.expense-card')]
      .filter(card => card.querySelector('[type=checkbox]').checked)
      .map(card => ({
        ...Object.fromEntries([...card.querySelectorAll('[data-campo]')]
          .map(control => [control.dataset.campo, control.value.trim()])),
        descripcion: card.dataset.descripcion
      }));
  }
  function total() {
    const items = itemsSeleccionados();
    const suma = items.reduce((centimos, item) => centimos + Math.round((numero(item.monto) || 0) * 100), 0);
    $('cc-cantidad').textContent = items.length + (items.length === 1 ? ' gasto' : ' gastos');
    $('cc-subtotal').textContent = $('cc-total').textContent = dinero(suma / 100);
  }
  function mostrarConceptos(seleccionados = [], mostrarAnteriores = false) {
    const proyecto = $('cc-proyecto').value;
    const catalogo = datos.catalogo.filter(concepto => concepto.proyectos[proyecto]);
    const porNombre = new Map(catalogo.map(concepto => [concepto.nombre, concepto]));
    const nombresSeleccionados = new Set(seleccionados.map(item => item.tipo_gasto));
    const filas = seleccionados.filter(item => mostrarAnteriores || porNombre.has(item.tipo_gasto))
      .map(item => [porNombre.get(item.tipo_gasto) || {
        nombre: item.tipo_gasto, descripcion: 'Este concepto ya no está disponible para el proyecto.',
        proyectos: {}, correo: item.requiere_correo
      }, item]);
    catalogo.filter(concepto => !nombresSeleccionados.has(concepto.nombre))
      .forEach(concepto => filas.push([concepto]));
    $('cc-items').replaceChildren(...filas.map(([concepto, valores], indice) => {
      const card = $('cc-item-plantilla').content.firstElementChild.cloneNode(true);
      const checkbox = card.querySelector('[type=checkbox]');
      const detalle = card.querySelector('.expense-amount');
      const correo = card.querySelector('[data-correo]');
      card.dataset.descripcion = valores?.descripcion || '';
      card.querySelector('[data-nombre]').textContent = concepto.nombre;
      card.querySelector('.expense-criterion').textContent = concepto.descripcion || '';
      card.querySelector('.expense-classification').textContent = concepto.proyectos[proyecto] || valores?.tipo_presupuesto || '';
      checkbox.value = concepto.nombre;
      checkbox.checked = Boolean(valores);
      correo.hidden = !concepto.correo;
      detalle.querySelectorAll('[data-campo]').forEach(control => {
        control.id = 'cc-' + control.dataset.campo + '-' + indice;
        control.previousElementSibling.htmlFor = control.id;
        if (control.type === 'email') control.disabled = !concepto.correo;
        if (valores && !control.disabled) control.value = valores[control.dataset.campo] ?? '';
      });
      detalle.hidden = !checkbox.checked;
      checkbox.addEventListener('change', () => {
        detalle.hidden = !checkbox.checked;
        total();
      });
      card.querySelector('[data-campo=monto]').addEventListener('input', total);
      return card;
    }));
    total();
  }
  // Nueva solicitud (sol vacío) o corrección de una rechazada (precargada con sus datos).
  function actualizarResponsables(valor = '') {
    const control = $('cc-responsable');
    control.replaceChildren(new Option('Selecciona un responsable', ''));
    Object.entries(datos.responsables[$('cc-proyecto').value] || {}).forEach(([id, nombre]) => control.add(new Option(nombre, id)));
    control.value = [...control.options].some(o => o.value === valor) ? valor : '';
  }
  function actualizarBilletera() {
    $('cc-billetera-numero').hidden = $('cc-numero-billetera').disabled = $('cc-billetera').value === 'No aplica';
  }
  function abrirFormulario(sol) {
    corrigiendo = sol || null;
    const form = $('cc-form'); form.reset();
    form.querySelector('.error').hidden = true;
    $('cc-rechazo').hidden = !sol;
    $('cc-volver-solicitud').hidden = !sol;
    $('cc-volver-portal').hidden = Boolean(sol);
    form.querySelector('[type=submit]').textContent = sol ? 'Reenviar solicitud' : 'Enviar solicitud';
    $('cc-dni').value = datos.personal.documento || '';
    $('cc-tecnico').value = datos.personal.nombre || '';
    $('cc-supervisor').value = datos.personal.supervisor || '';
    if (sol) {
      $('cc-rechazo').textContent = 'Rechazada: ' + sol.motivo_rechazo;
      $('cc-proyecto').value = sol.proyecto; $('cc-motivo').value = sol.motivo;
      $('cc-banco').value = sol.banco; $('cc-cuenta').value = sol.cuenta;
    } else {
      if (datos?.proyecto) $('cc-proyecto').value = datos.proyecto;
    }
    mostrarConceptos(sol?.items, Boolean(sol));
    const extra = sol?.formulario || {};
    $('cc-site').value = extra.site || '';
    $('cc-wo').value = extra.wo || '';
    $('cc-titular').value = extra.titular || '';
    $('cc-billetera').value = extra.tipo_billetera || 'No aplica';
    $('cc-numero-billetera').value = extra.numero_billetera || '';
    actualizarResponsables(extra.responsable_validacion_id);
    actualizarBilletera();
    ver('cc-solicitud');
  }
  $('cc-proyecto').addEventListener('change', () => {
    actualizarResponsables();
    mostrarConceptos(itemsSeleccionados());
  });
  $('cc-billetera').addEventListener('change', actualizarBilletera);
  $('cc-cuenta').addEventListener('input', ({target}) => {
    target.value = target.value.replace(/[^0-9]/g, '').slice(0, 20);
  });
  for (const campo of ['site', 'wo']) {
    const input = $('cc-' + campo);
    const lista = $('cc-sugerencias-' + campo);
    let espera, consulta;
    function limpiar() {
      clearTimeout(espera);
      consulta?.abort();
      lista.replaceChildren();
    }
    $('cc-form').addEventListener('reset', limpiar);
    $('cc-proyecto').addEventListener('change', () => {
      input.value = '';
      limpiar();
    });
    input.addEventListener('input', () => {
      limpiar();
      const q = input.value.trim(), proyecto = $('cc-proyecto').value;
      if (q.length < 2 || !proyecto) return;
      espera = setTimeout(async () => {
        const actual = new AbortController();
        consulta = actual;
        try {
          const parametros = new URLSearchParams({campo, q, proyecto});
          const {opciones} = await api('/sugerencias?' + parametros, {signal: actual.signal}, '/form-pruebas');
          if (actual.signal.aborted) return;
          const botones = opciones.map(valor => {
            const boton = el('button', null, valor);
            boton.type = 'button';
            boton.addEventListener('click', () => { input.value = valor; limpiar(); });
            return boton;
          });
          lista.replaceChildren(...botones);
          if (!botones.length) lista.textContent = 'Sin coincidencias para este proyecto.';
        } catch {
          if (!actual.signal.aborted) lista.textContent = 'No se pudieron cargar las sugerencias.';
        }
      }, 250);
    });
  }
  $('cc-exito-volver').addEventListener('click', () => ver('cc-inicio'));
  document.querySelectorAll('[data-cc-volver]').forEach(b => b.addEventListener('click', () => ver('cc-inicio')));
  $('cc-form').addEventListener('submit', e => {
    e.preventDefault(); const form = e.currentTarget, error = form.querySelector('.error');
    enviando(form.querySelector('[type=submit]'), error, async () => {
      if (!/^[0-9]{20}$/.test($('cc-cuenta').value)) throw Error('Ingresa el CCI de 20 dígitos.');
      const items = itemsSeleccionados();
      if (!items.length) throw Error('Selecciona al menos un concepto.');
      items.forEach(item => {
        if (!(numero(item.monto) > 0)) throw Error(item.tipo_gasto + ': escribe un monto mayor a cero.');
      });
      const cuerpo = {...Object.fromEntries(new FormData(form)), items};
      const ruta = corrigiendo ? '/' + corrigiendo.id + '/reenviar' : '/solicitar';
      const r = await api(ruta, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo)});
      $('cc-exito-titulo').textContent = corrigiendo ? '¡Solicitud reenviada!' : '¡Solicitud enviada!';
      $('codigo-exito').textContent = r.solicitud.codigo;
      $('total-exito').textContent = dinero(r.solicitud.total);
      datos.solicitudes = [r.solicitud, ...datos.solicitudes.filter(sol => sol.id !== r.solicitud.id)];
      pintar();
      corrigiendo = null;
      ver('cc-exito');
      $('cc-exito-titulo').focus();
    });
  });

  cargar().then(() => {
    // "Solicitar" del inicio del portal llega con #nueva: abre directo el formulario.
    if (location.hash === '#nueva') { history.replaceState(null, '', location.pathname); abrirFormulario(); }
  }).catch(e => { const c = $('cargando'); c.setAttribute('role', 'alert'); c.textContent = e.message; });
})();
