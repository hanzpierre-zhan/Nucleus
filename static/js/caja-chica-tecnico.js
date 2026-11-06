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

  async function api(ruta, opciones = {}) {
    const r = await fetch(base + ruta, {credentials: 'same-origin', ...opciones, headers: {'X-CSRF-Token': $('csrf').value, ...(opciones.headers || {})}});
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
  function pintar() {
    const lista = $('cc-lista'); lista.replaceChildren();
    if (!datos.solicitudes.length) lista.append(el('p', 'cc-vacio', 'Aún no tienes solicitudes de Caja Chica.'));
    for (const sol of datos.solicitudes) {
      const card = el('details', 'card cc-sol'); card.open = ['DEPOSITADO', 'POR_DEVOLVER', 'RECHAZADO'].includes(sol.estado);
      const resumen = el('summary', 'cc-sol-cabecera');
      resumen.append(el('strong', null, sol.codigo), el('span', 'cc-estado cc-' + sol.estado.toLowerCase(), ESTADOS[sol.estado] || sol.estado), el('span', 'cc-monto', dinero(sol.total)));
      card.append(resumen, el('p', 'cc-motivo', sol.motivo));
      if (sol.motivo_rechazo) card.append(el('p', 'notice', 'Motivo: ' + sol.motivo_rechazo));
      if (sol.estado === 'DEPOSITADO') card.append(el('p', 'cc-avance', sol.avance + ' · ' + dinero(sol.pendiente) + ' pendientes'));
      for (const item of sol.items) {
        const fila = el('div', 'cc-item-fila');
        const cab = el('div', 'cc-item-cabecera');
        cab.append(el('strong', null, 'Ítem ' + item.numero + ' · ' + item.tipo_gasto), el('span', 'cc-chip cc-' + item.estado.toLowerCase(), ITEM[item.estado]));
        fila.append(cab, el('small', null, (item.descripcion ? item.descripcion + ' · ' : '') + dinero(item.monto)));
        if (item.motivo_rechazo) fila.append(el('p', 'notice', 'Rechazado: ' + item.motivo_rechazo));
        if (item.fotos.length) { const f = el('div', 'cc-fotos'); item.fotos.forEach((n, i) => f.append(foto(sol.id, n, 'Foto ' + (i + 1)))); fila.append(f); }
        if (sol.estado === 'DEPOSITADO' && ['POR_RENDIR', 'RECHAZADO'].includes(item.estado)) fila.append(formRendir(sol, item));
        card.append(fila);
      }
      if (sol.estado === 'POR_DEVOLVER' && !sol.devolucion_foto) card.append(formDevolucion(sol));
      if (sol.estado === 'POR_DEVOLVER' && sol.devolucion_foto) card.append(el('p', 'cc-avance', 'Devolución enviada: en revisión.'));
      if (sol.estado === 'RECHAZADO') {
        const corregir = el('button', 'primary wide', 'Corregir y reenviar'); corregir.type = 'button';
        corregir.addEventListener('click', () => abrirFormulario(sol));
        card.append(corregir);
      }
      lista.append(card);
    }
  }
  async function cargar() { datos = await api('/datos'); pintar(); $('cargando').hidden = true; ver('cc-inicio'); }

  // ── Nueva solicitud ──
  function total() {
    const suma = [...document.querySelectorAll('#cc-items [data-campo=monto]')].reduce((s, i) => s + (numero(i.value) || 0), 0);
    $('cc-total').textContent = dinero(suma);
  }
  function renumerar() {
    const items = document.querySelectorAll('#cc-items .cc-item');
    items.forEach((it, i) => { it.querySelector('.cc-item-cabecera strong').textContent = 'Ítem ' + (i + 1); it.querySelector('.cc-quitar').hidden = items.length === 1; });
    total();
  }
  function opcionesItem(item, seleccionado) {
    const select = item.querySelector('[data-campo=tipo_gasto]');
    const proyecto = $('cc-proyecto').value;
    const disponibles = datos.catalogo.filter(c => c.proyectos[proyecto]);
    select.replaceChildren(new Option('Selecciona', ''));
    disponibles.forEach(c => select.add(new Option(c.nombre, c.nombre)));
    select.value = disponibles.some(c => c.nombre === seleccionado) ? seleccionado : '';
    reglaItem(item);
  }
  function reglaItem(item) {
    const nombre = item.querySelector('[data-campo=tipo_gasto]').value;
    const regla = datos.catalogo.find(c => c.nombre === nombre);
    const nota = item.querySelector('[data-regla]');
    nota.hidden = !regla;
    nota.textContent = regla ? [regla.proyectos[$('cc-proyecto').value], regla.descripcion].filter(Boolean).join(' · ') : '';
    const correo = item.querySelector('[data-campo=correo_validador]');
    correo.parentElement.hidden = correo.disabled = !regla?.correo;
    correo.required = !correo.disabled;
    if (correo.disabled) correo.value = '';
  }
  function agregarItem(valores) {
    const nuevo = $('cc-item-plantilla').content.firstElementChild.cloneNode(true);
    opcionesItem(nuevo, valores?.tipo_gasto);
    nuevo.querySelectorAll('[data-campo]').forEach(c => {
      const id = 'cc-' + c.dataset.campo + '-' + Math.random().toString(36).slice(2, 8); c.id = id; c.previousElementSibling.htmlFor = id;
      if (valores && valores[c.dataset.campo] !== undefined && !c.disabled && c.dataset.campo !== 'tipo_gasto') c.value = valores[c.dataset.campo];
    });
    nuevo.querySelector('[data-campo=tipo_gasto]').addEventListener('change', () => {
      nuevo.querySelector('[data-campo=correo_validador]').value = '';
      reglaItem(nuevo);
    });
    nuevo.querySelector('[data-campo=monto]').addEventListener('input', total);
    nuevo.querySelector('.cc-quitar').addEventListener('click', () => { nuevo.remove(); renumerar(); });
    $('cc-items').append(nuevo); renumerar();
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
    const form = $('cc-form'); form.reset(); $('cc-items').replaceChildren();
    form.querySelector('.error').hidden = true;
    $('cc-rechazo').hidden = !sol;
    form.querySelector('[type=submit]').textContent = sol ? 'Reenviar solicitud' : 'Enviar solicitud';
    $('cc-dni').value = datos.personal.documento || '';
    $('cc-tecnico').value = datos.personal.nombre || '';
    $('cc-supervisor').value = datos.personal.supervisor || '';
    if (sol) {
      $('cc-rechazo').textContent = 'Rechazada: ' + sol.motivo_rechazo;
      $('cc-proyecto').value = sol.proyecto; $('cc-motivo').value = sol.motivo;
      $('cc-banco').value = sol.banco; $('cc-cuenta').value = sol.cuenta;
      sol.items.forEach(agregarItem);
    } else {
      if (datos?.proyecto) $('cc-proyecto').value = datos.proyecto;
      agregarItem();
    }
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
  $('cc-agregar').addEventListener('click', () => agregarItem());
  $('cc-proyecto').addEventListener('change', () => {
    actualizarResponsables();
    document.querySelectorAll('#cc-items .cc-item').forEach(item => opcionesItem(item, item.querySelector('[data-campo=tipo_gasto]').value));
  });
  $('cc-billetera').addEventListener('change', actualizarBilletera);
  $('cc-nueva').addEventListener('click', () => abrirFormulario());
  document.querySelectorAll('[data-cc-volver]').forEach(b => b.addEventListener('click', () => ver('cc-inicio')));
  $('cc-form').addEventListener('submit', e => {
    e.preventDefault(); const form = e.currentTarget, error = form.querySelector('.error');
    enviando(form.querySelector('[type=submit]'), error, async () => {
      const items = [...document.querySelectorAll('#cc-items .cc-item')].map(it => Object.fromEntries([...it.querySelectorAll('[data-campo]')].map(c => [c.dataset.campo, c.value.trim()])));
      items.forEach((it, i) => { if (!it.tipo_gasto || !(numero(it.monto) > 0)) throw Error('Ítem ' + (i + 1) + ': elige el tipo de gasto y escribe un monto mayor a cero.'); });
      const cuerpo = {...Object.fromEntries(new FormData(form)), items};
      const ruta = corrigiendo ? '/' + corrigiendo.id + '/reenviar' : '/solicitar';
      const r = await api(ruta, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo)});
      alert('Solicitud ' + r.solicitud.codigo + (corrigiendo ? ' corregida y reenviada' : ' enviada') + ' por ' + dinero(r.solicitud.total) + '.');
      corrigiendo = null;
      await cargar();
    });
  });

  cargar().then(() => {
    // "Solicitar" del inicio del portal llega con #nueva: abre directo el formulario.
    if (location.hash === '#nueva') { history.replaceState(null, '', location.pathname); abrirFormulario(); }
  }).catch(e => { const c = $('cargando'); c.setAttribute('role', 'alert'); c.textContent = e.message; });
})();
