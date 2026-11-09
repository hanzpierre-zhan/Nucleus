/* Cot_New · Cotizaciones con el diseño de Caja Chica: pestañas, tuerca, tabla con filtros y detalle. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const icono = nombre => { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const avisar = m => (window.nucleusAlert || alert)(m);
  const seccion = document.querySelector('.cn-gestion');
  const puedeGestionar = seccion.dataset.gestionar === 'si';
  const proyectoId = seccion.dataset.proyecto;
  const clasico = '/switch_project/' + proyectoId + '?next=/';
  const dialogo = $('cc-solicitud-dialogo');
  const NOMBRE_TAB = Object.fromEntries([...document.querySelectorAll('.cn-tab')].map(b => [b.dataset.tab, b.textContent.trim().replace(/\s+\d+\s+S\/.*$/s, '').trim()]));
  const COLOR_ESTADO = {registro: 'cn-e-registro', cliente: 'cn-e-cliente', sustentar: 'cn-e-sustentar', atendido: 'cn-e-atendido', cancelado: 'cn-e-cancelado'};
  const CLIENTES = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};

  let cotizaciones = [], tab = 'registro', cliente = '', orden = null, filtros = {}, busquedas = {};
  try { tab = localStorage.getItem('cn-tab') || tab; } catch (_) {}
  if (!document.querySelector('.cn-tab[data-tab="' + tab + '"]')) tab = 'registro';

  // Fecha guardada como '2026-11-07 15:57' o '07/11/2026': se ordena por su valor real.
  function fechaValor(t) {
    const s = String(t || '').trim();
    let m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (m) return new Date(+m[1], m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)).getTime();
    m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    return m ? new Date(+m[3], m[2] - 1, +m[1]).getTime() : 0;
  }
  const fechaTexto = t => { const v = fechaValor(t); return v ? new Date(v).toLocaleDateString('es-PE') : (t || '—'); };

  // ── Columnas ──
  const COLUMNAS = {
    numero: {titulo: 'N.º cotización', ancho: 'minmax(150px, 1fr)', texto: c => c['N° COTIZACION'] || c.key, celda: c => {
      const a = el('a', 'cc-codigo-link', c['N° COTIZACION'] || c.key); a.href = '#cot-' + c.id;
      a.addEventListener('click', e => { e.preventDefault(); verDetalle(c); }); return a;
    }},
    fecha: {titulo: 'Fecha', ancho: 'minmax(100px, .7fr)', texto: c => fechaTexto(c.FECHA), orden: c => fechaValor(c.FECHA)},
    cliente: {titulo: 'Cliente', ancho: 'minmax(100px, .7fr)', texto: c => CLIENTES[c.familia] || c.CLIENTE || '—', celda: c => {
      const nombre = CLIENTES[c.familia];
      return el('span', nombre ? 'project-badge project-badge--' + c.familia.toLowerCase() : null, nombre || c.CLIENTE || '—');
    }},
    site: {titulo: 'Nombre del site', ancho: 'minmax(150px, 1.1fr)', texto: c => c['NOMBRE SITE'] || '—'},
    wo: {titulo: 'N.º WO', ancho: 'minmax(130px, .9fr)', texto: c => c['NUMERO WO'] || '—'},
    motivo: {titulo: 'Motivo', ancho: 'minmax(200px, 1.8fr)', texto: c => c.MOTIVO || c.OBJETIVO || '—', clase: 'cn-motivo'},
    supervisor: {titulo: 'Supervisor', ancho: 'minmax(140px, 1fr)', texto: c => c.SUPERVISOR || '—'},
    gestor: {titulo: 'Solicitado por', ancho: 'minmax(120px, .9fr)', texto: c => c['SOLICITADO POR'] || c.GESTOR || '—'},
    cotizador: {titulo: 'Cotizador', ancho: 'minmax(130px, .9fr)', texto: c => c.COTIZADOR || c['COTIZADO POR'] || '—'},
    estado: {titulo: 'Estado', ancho: 'minmax(130px, .9fr)', texto: c => c['ESTADO COTIZACION'] || 'Pdt. Cotización',
             celda: c => el('span', 'cc-chip ' + (COLOR_ESTADO[c.pestanas[0]] || ''), c['ESTADO COTIZACION'] || 'Pdt. Cotización')},
    monto: {titulo: 'Sub total + FEE', ancho: 'minmax(120px, .8fr)', num: true, texto: c => dinero(c.monto), orden: c => Number(c.monto) || 0,
            celda: c => el('strong', 'cc-num', dinero(c.monto))},
  };
  let columnas = Object.keys(COLUMNAS);
  try {
    const guardadas = JSON.parse(localStorage.getItem('cn-columnas') || 'null');
    if (Array.isArray(guardadas) && guardadas.length === columnas.length && columnas.every(c => guardadas.includes(c))) columnas = guardadas;
  } catch (_) {}
  const guardarColumnas = () => { try { localStorage.setItem('cn-columnas', JSON.stringify(columnas)); } catch (_) {} };
  const plano = t => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function plantilla() {
    const minimo = columnas.reduce((s, c) => s + parseInt(COLUMNAS[c].ancho.slice(7), 10), 0) + 12 * columnas.length + 140;
    $('cn-tabla').style.setProperty('--cc-min', minimo + 'px');
    return ['112px', ...columnas.map(c => COLUMNAS[c].ancho)].join(' ');
  }

  function pintarEncabezado() {
    $('cn-tabla').style.setProperty('--cc-cols', plantilla());
    const cab = $('cn-encabezado');
    const activo = document.activeElement, foco = activo && cab.contains(activo) && activo.dataset.buscar
      ? {col: activo.dataset.buscar, ini: activo.selectionStart, fin: activo.selectionEnd} : null;
    cab.replaceChildren(el('div', 'cc-th cc-th-nombre cc-acciones-cab', 'Acciones'));
    for (const id of columnas) {
      const col = COLUMNAS[id], th = el('div', 'cc-th' + (col.num ? ' cc-th-num' : ''));
      const fila = el('div', 'cc-th-fila'); fila.draggable = true; fila.title = 'Arrastra para mover la columna';
      const sentido = orden?.col === id ? orden.dir : 0;
      const ordenar = el('button', 'cc-th-btn' + (sentido ? ' activo' : '')); ordenar.type = 'button';
      ordenar.append(icono(sentido === 1 ? 'fa-arrow-up-short-wide' : sentido === -1 ? 'fa-arrow-down-wide-short' : 'fa-sort'));
      ordenar.title = sentido === 1 ? 'De menor a mayor · clic: de mayor a menor' : sentido === -1 ? 'De mayor a menor · clic: quitar orden' : 'Ordenar de menor a mayor';
      ordenar.addEventListener('click', e => { e.stopPropagation(); orden = sentido === 1 ? {col: id, dir: -1} : sentido === -1 ? null : {col: id, dir: 1}; pintar(); });
      const filtrar = el('button', 'cc-th-btn' + (filtros[id] ? ' activo' : '')); filtrar.type = 'button';
      filtrar.append(icono('fa-filter')); filtrar.title = 'Filtrar ' + col.titulo;
      filtrar.addEventListener('click', e => { e.stopPropagation(); abrirFiltro(id, filtrar); });
      fila.append(el('span', 'cc-th-nombre', col.titulo), ordenar, filtrar);
      const buscar = el('input', 'cc-th-buscar'); buscar.dataset.buscar = id;
      Object.assign(buscar, {type: 'search', value: busquedas[id] || '', placeholder: 'Buscar…'});
      buscar.setAttribute('aria-label', 'Buscar en ' + col.titulo);
      buscar.addEventListener('input', () => { if (buscar.value.trim()) busquedas[id] = buscar.value; else delete busquedas[id]; pintar(); });
      th.append(fila, buscar);
      fila.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', id); th.classList.add('arrastrando'); });
      th.addEventListener('dragover', e => { e.preventDefault(); const r = th.getBoundingClientRect(), antes = e.clientX < r.left + r.width / 2; th.classList.toggle('soltar-antes', antes); th.classList.toggle('soltar-despues', !antes); });
      th.addEventListener('dragleave', () => th.classList.remove('soltar-antes', 'soltar-despues'));
      th.addEventListener('drop', e => {
        e.preventDefault();
        const origen = e.dataTransfer.getData('text/plain');
        if (!COLUMNAS[origen] || origen === id) return pintarEncabezado();
        const antes = th.classList.contains('soltar-antes');
        columnas = columnas.filter(c => c !== origen);
        columnas.splice(columnas.indexOf(id) + (antes ? 0 : 1), 0, origen);
        guardarColumnas(); pintar();
      });
      cab.append(th);
    }
    if (foco) { const i = cab.querySelector('[data-buscar="' + foco.col + '"]'); if (i) { i.focus(); i.setSelectionRange(foco.ini, foco.fin); } }
  }

  // Filtro por columna: lista de valores de la pestaña, como en Excel.
  function abrirFiltro(id, boton) {
    const caja = $('cn-filtro');
    if (!caja.hidden && caja.dataset.col === id) { caja.hidden = true; return; }
    const col = COLUMNAS[id], valores = [...new Set(base(id).map(col.texto))].sort((a, b) => a.localeCompare(b, 'es', {numeric: true}));
    const marcados = new Set(filtros[id] || valores);
    caja.dataset.col = id; caja.replaceChildren();
    const buscar = Object.assign(el('input'), {type: 'search', placeholder: 'Buscar en ' + col.titulo.toLowerCase()});
    const lista = el('div', 'cc-filtro-valores');
    const todos = el('label', 'cc-todos'), todosCheck = Object.assign(el('input'), {type: 'checkbox'}); todos.append(todosCheck, 'Seleccionar todo');
    const checks = valores.map(v => { const l = el('label'), c = Object.assign(el('input'), {type: 'checkbox', value: v, checked: marcados.has(v)}); l.append(c, v || '(vacío)'); return l; });
    const sincronizar = () => { const v = checks.filter(l => !l.hidden); todosCheck.checked = v.length > 0 && v.every(l => l.firstChild.checked); };
    todosCheck.addEventListener('change', () => checks.filter(l => !l.hidden).forEach(l => { l.firstChild.checked = todosCheck.checked; }));
    checks.forEach(l => l.firstChild.addEventListener('change', sincronizar));
    buscar.addEventListener('input', () => { const t = plano(buscar.value.trim()); checks.forEach(l => { l.hidden = t && !plano(l.textContent).includes(t); }); sincronizar(); });
    lista.append(todos, ...checks);
    const limpiar = el('button', 'cc-btn', 'Limpiar'), aplicar = el('button', 'cc-btn cc-ok', 'Aplicar');
    limpiar.type = aplicar.type = 'button';
    limpiar.addEventListener('click', () => { delete filtros[id]; caja.hidden = true; pintar(); });
    aplicar.addEventListener('click', () => {
      const elegidos = checks.filter(l => l.firstChild.checked).map(l => l.firstChild.value);
      if (elegidos.length === valores.length) delete filtros[id]; else filtros[id] = elegidos;
      caja.hidden = true; pintar();
    });
    const pie = el('div', 'cc-filtro-pie'); pie.append(limpiar, aplicar);
    caja.append(buscar, lista, pie); sincronizar(); caja.hidden = false;
    const r = boton.getBoundingClientRect();
    caja.style.top = Math.min(r.bottom + 6, innerHeight - caja.offsetHeight - 8) + 'px';
    caja.style.left = Math.max(8, Math.min(r.left - 8, innerWidth - caja.offsetWidth - 8)) + 'px';
    buscar.focus();
  }
  document.addEventListener('click', e => { const c = $('cn-filtro'); if (!c.hidden && !c.contains(e.target)) c.hidden = true; });

  const delCliente = () => cotizaciones.filter(c => !cliente || c.familia === cliente);
  function base(excepto) {
    const texto = plano($('cc-buscar').value.trim());
    const filas = delCliente().filter(c => c.pestanas.includes(tab)
      && (!texto || plano([c['N° COTIZACION'], c.key, c['NOMBRE SITE'], c['NUMERO WO'], c.MOTIVO, c.SUPERVISOR].join(' ')).includes(texto))
      && Object.entries(filtros).every(([id, vals]) => id === excepto || vals.includes(COLUMNAS[id].texto(c)))
      && Object.entries(busquedas).every(([id, t]) => plano(COLUMNAS[id].texto(c)).includes(plano(t.trim()))));
    const col = orden && COLUMNAS[orden.col];
    filas.sort(col ? (a, b) => (col.orden ? col.orden(a) - col.orden(b)
      : String(col.texto(a)).localeCompare(String(col.texto(b)), 'es', {numeric: true, sensitivity: 'base'})) * orden.dir || b.id - a.id
      : (a, b) => fechaValor(b.FECHA) - fechaValor(a.FECHA) || b.id - a.id);
    return filas;
  }

  // ── Acciones (botones redondos) ──
  async function accion(c, nombre, extra = {}) {
    const r = await fetch('/api/cotizacion/accion', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: c.key, accion: nombre, ...extra})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw Error(j.error || 'No se pudo completar la acción.');
    await cargar();
  }
  function pedirMotivo(titulo, subtitulo, okText, iconoNombre) {
    return new Promise(resolve => {
      const d = el('dialog', 'cc-motivo'), form = el('form', 'cc-motivo-form'); form.method = 'dialog';
      const cabeza = el('header', 'cc-motivo-cabeza'), marca = el('span', 'cc-motivo-icono'); marca.append(icono(iconoNombre));
      const textos = el('div'); textos.append(el('h3', null, titulo), el('p', null, subtitulo)); cabeza.append(marca, textos);
      const texto = Object.assign(el('textarea'), {rows: 3, maxLength: 300, placeholder: 'Escribe el motivo…'});
      const pie = el('nav', 'cc-motivo-pie');
      const cancelar = el('button', 'cc-motivo-cancelar', 'Cancelar'); cancelar.type = 'button';
      const ok = el('button', 'cc-motivo-ok'); ok.type = 'submit'; ok.value = 'ok'; ok.append(icono(iconoNombre), el('span', null, okText));
      pie.append(cancelar, ok);
      form.append(cabeza, el('span', 'cc-motivo-etiqueta', 'Motivo'), texto, pie); d.append(form);
      const validar = () => { ok.disabled = !texto.value.trim(); }; texto.addEventListener('input', validar); validar();
      cancelar.addEventListener('click', () => d.close(''));
      d.addEventListener('close', () => { resolve(d.returnValue === 'ok' ? texto.value.trim() : null); d.remove(); });
      document.body.append(d); d.showModal(); texto.focus();
    });
  }
  const conMotivo = (c, nombre, titulo, okText, iconoNombre) => async () => {
    const motivo = await pedirMotivo(titulo, (c['N° COTIZACION'] || c.key) + ' · ' + (c['NOMBRE SITE'] || ''), okText, iconoNombre);
    if (motivo === null) return;
    try { await accion(c, nombre, {motivo}); if (dialogo.open) dialogo.close(); } catch (e) { avisar(e.message); }
  };
  // ── Nueva cotización: datos a la izquierda, ítems a la derecha; guarda con el alta de Cotizaciones ──
  const TIPOS_ITEM = ['REEMBOLSABLE', 'LPU', 'GASTO COBRA'];
  const num = v => { const n = Number(String(v ?? '').replace(',', '.')); return Number.isFinite(n) ? n : 0; };
  function campo(form, etiqueta, control) {
    const l = el('label', 'cc-pendiente-campo'); l.append(el('span', null, etiqueta), control); form.append(l); return control;
  }
  function filaItem(cuerpo, recalcular, item = {}) {
    const tr = el('tr');
    const tipo = el('select'); TIPOS_ITEM.forEach(t => tipo.add(new Option(t, t))); tipo.value = item.tipo || 'REEMBOLSABLE';
    const entrada = (v, cls, modo) => Object.assign(el('input', cls), {value: v ?? '', inputMode: modo || 'text'});
    const texto = entrada(item.texto, 'cn-item-texto'), und = entrada(item.und || 'UND', 'cn-item-und');
    const cant = entrada(item.cantidad || '1', 'cn-item-num', 'decimal'), vu = entrada(item.valor_unitario, 'cn-item-num', 'decimal');
    const fee = entrada(item.fee ?? (tipo.value === 'REEMBOLSABLE' ? '5' : '0'), 'cn-item-num', 'decimal');
    const total = el('td', 'cc-num cn-item-total');
    const quitar = el('button', 'cn-item-quitar', '×'); quitar.type = 'button'; quitar.title = 'Quitar ítem';
    quitar.addEventListener('click', () => { tr.remove(); recalcular(); });
    tipo.addEventListener('change', () => { fee.value = tipo.value === 'REEMBOLSABLE' ? '5' : '0'; recalcular(); });
    [cant, vu, fee].forEach(i => i.addEventListener('input', recalcular));
    const td = n => { const c = el('td'); c.append(n); return c; };
    const tdq = el('td'); tdq.append(quitar);
    tr.append(td(tipo), td(texto), td(und), td(cant), td(vu), td(fee), total, tdq);
    tr.leer = () => {
      const t = Math.round(num(cant.value) * num(vu.value) * (1 + num(fee.value) / 100) * 100) / 100;
      return {tipo: tipo.value, texto: texto.value.trim(), und: und.value.trim(), cantidad: cant.value.trim(),
              valor_unitario: vu.value.trim(), fee: fee.value.trim(), valor_total: t.toFixed(2), comentarios: ''};
    };
    tr.pintar = () => { total.textContent = dinero(tr.leer().valor_total); };
    cuerpo.append(tr); recalcular();
    return tr;
  }
  function nuevaCotizacion() {
    $('cc-solicitud-titulo').textContent = 'Nueva cotización';
    const acciones = $('cn-dialogo-acciones');
    acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    const form = el('form', 'cc-ficha vn-form'); form.noValidate = true;
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-file-lines'), el('span', null, 'Datos')); form.append(h);
    const cliente = el('select'); Object.entries(CLIENTES).forEach(([v, t]) => cliente.add(new Option(t, v)));
    cliente.value = window._cnUltimoCliente || 'CLARO';
    campo(form, 'Cliente', cliente);
    const ahora = new Date(); ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
    const fecha = campo(form, 'Fecha', Object.assign(el('input'), {type: 'datetime-local', value: ahora.toISOString().slice(0, 16)}));
    const lista = el('datalist'); lista.id = 'cn-supervisores';
    [...new Set(cotizaciones.map(c => c.SUPERVISOR).filter(Boolean))].sort().forEach(s => lista.append(new Option(s)));
    form.append(lista);
    const supervisor = campo(form, 'Supervisor', Object.assign(el('input'), {maxLength: 150})); supervisor.setAttribute('list', 'cn-supervisores');
    const site = campo(form, 'Nombre del site', Object.assign(el('input'), {maxLength: 150}));
    const wo = campo(form, 'N.º WO', Object.assign(el('input'), {maxLength: 100, placeholder: 'CM-AAAAMMDD-NNNNNNNN'}));
    const motivo = campo(form, 'Motivo', Object.assign(el('input'), {maxLength: 300}));
    const objetivo = campo(form, 'Objetivo', Object.assign(el('input'), {maxLength: 300}));
    const tipoGasto = el('select'); ['Refacturable', 'Gasto Cobra'].forEach(t => tipoGasto.add(new Option(t, t))); campo(form, 'Tipo de gasto', tipoGasto);
    const departamento = campo(form, 'Departamento', Object.assign(el('input'), {maxLength: 80}));
    form.append(el('p', 'cc-nota', 'El N.º de cotización se asigna solo al guardar.'));
    const derecha = el('section', 'cc-ficha cn-items');
    const t = el('h4', 'cc-ficha-titulo'); t.append(icono('fa-list-check'), el('span', null, 'Ítems de la cotización')); derecha.append(t);
    const tabla = el('table', 'cn-items-tabla cn-items-editar');
    const cab = el('tr'); ['Tipo', 'Descripción', 'Und', 'Cant.', 'V. unit.', 'FEE %', 'Total', ''].forEach(x => cab.append(el('th', null, x)));
    const cuerpo = el('tbody'); tabla.append(cab, cuerpo);
    const total = el('strong');
    const recalcular = () => {
      let suma = 0; [...cuerpo.children].forEach(tr => { if (tr.leer) { tr.pintar(); suma += num(tr.leer().valor_total); } });
      total.textContent = dinero(suma);
    };
    const agregar = el('button', 'cc-btn cn-agregar-item', '+ Agregar ítem'); agregar.type = 'button';
    agregar.addEventListener('click', () => filaItem(cuerpo, recalcular).querySelector('.cn-item-texto').focus());
    const pie = el('div', 'cn-total'); pie.append(el('span', null, 'Sub total + FEE'), total);
    const envoltura = el('div', 'cn-items-scroll'); envoltura.append(tabla);
    derecha.append(envoltura, agregar, pie);
    filaItem(cuerpo, recalcular);
    const error = el('p', 'cc-alerta'); error.hidden = true; form.append(error);
    const columnasDetalle = el('div', 'cc-validacion-columnas cn-nueva'); columnasDetalle.append(form, derecha);

    async function guardar(generarDespues) {
      error.hidden = true;
      const items = [...cuerpo.children].map(tr => tr.leer()).filter(i => i.texto || num(i.valor_unitario));
      if (items.some(i => !i.texto || !(num(i.valor_unitario) > 0) || !(num(i.cantidad) > 0))) throw Error('Cada ítem necesita descripción, cantidad y valor unitario.');
      if (generarDespues && !items.length) throw Error('Agrega al menos un ítem antes de generar.');
      if (!motivo.value.trim()) throw Error('Escribe el motivo.');
      const subtotal = items.reduce((s, i) => s + num(i.valor_total), 0);
      const datos = {CLIENTE: cliente.value, FECHA: fecha.value.replace('T', ' '), SUPERVISOR: supervisor.value.trim(),
        'NOMBRE SITE': site.value.trim(), 'NUMERO WO': wo.value.trim(), MOTIVO: motivo.value.trim(), OBJETIVO: objetivo.value.trim() || motivo.value.trim(),
        'TIPO DE GASTO': tipoGasto.value, DEPARTAMENTO: departamento.value.trim(), 'ESTADO COTIZACION': 'Pdt. Cotización',
        ITEMS_JSON: JSON.stringify(items), 'SUB TOTAL + FEE': subtotal > 0 ? subtotal.toFixed(2) : ''};
      const r = await fetch('/api/cot-new/agregar', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key: '', data: datos, numeracion_modo: 'automatico'})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error) throw Error(j.error || 'No se pudo guardar la cotización.');
      window._cnUltimoCliente = cliente.value;
      if (generarDespues) await generarClave(j.key);
      dialogo.close();
      await cargar();
      avisar('Cotización ' + j.key + (generarDespues ? ' generada: pasó a Cliente.' : ' guardada en Registro.'));
    }
    const conError = fn => async () => { try { await fn(); } catch (e) { error.textContent = e.message; error.hidden = false; } };
    acciones.prepend(botonRedondo(['Guardar y generar (pasa a Cliente)', 'cn-verde', 'fa-paper-plane', conError(() => guardar(true))], 'cn-grande'));
    acciones.prepend(botonRedondo(['Guardar en Registro', 'cn-azul', 'fa-floppy-disk', conError(() => guardar(false))], 'cn-grande'));
    $('cc-solicitud-contenido').replaceChildren(columnasDetalle);
    if (!dialogo.open) dialogo.showModal();
    motivo.focus();
  }
  // ── Nuevo registro (solicitud): proyecto FLM, site registrado, WO, tipo de gasto y de concepto ──
  const CN_CFG = JSON.parse(document.getElementById('cn-config')?.textContent || '{}');
  function nuevoRegistro() {
    $('cc-solicitud-titulo').textContent = 'Nuevo registro · cotización';
    const acciones = $('cn-dialogo-acciones');
    acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    // Izquierda: proyecto, site (con sus datos), WO y justificación.
    const izq = el('form', 'cc-ficha vn-form cn-registro'); izq.noValidate = true;
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-location-dot'), el('span', null, 'Proyecto y site')); izq.append(h);
    const proyecto = el('select'); proyecto.add(new Option('Selecciona el proyecto', ''));
    (CN_CFG.proyectos || []).forEach(p => proyecto.add(new Option(p, p)));
    campo(izq, 'Proyecto', proyecto);
    const buscarSite = Object.assign(el('input'), {type: 'text', placeholder: 'Escribe el nombre o código del site', autocomplete: 'off'});
    const listaSites = el('div', 'cn-opciones'); listaSites.hidden = true;
    const envSite = el('div', 'cn-buscador'); envSite.append(buscarSite, listaSites);
    campo(izq, 'Nombre del site (registrados en el proyecto)', envSite);
    const auto = el('div', 'cn-auto');
    const dato = t => { const d = el('div'); const v = el('strong', null, '—'); d.append(el('small', null, t), v); auto.append(d); return v; };
    const vCodigo = dato('Código'), vDistrito = dato('Distrito'), vProvincia = dato('Provincia'), vRegion = dato('Región');
    izq.append(auto, el('p', 'cc-nota', 'Código, distrito, provincia y región se llenan solos al elegir el site.'));
    const wos = new Set();
    const chips = el('div', 'cn-chips');
    const otroWo = Object.assign(el('input'), {type: 'text', placeholder: 'Escribe parte del WO para buscarlo, o el WO completo y Enter', autocomplete: 'off'});
    // Agregar el WO escrito (con Enter o coma; al enviar también se toma lo que quedó escrito).
    const agregarEscrito = () => {
      const w = otroWo.value.trim().toUpperCase().replace(/[,;]+$/, '');
      if (w) { wos.add(w); otroWo.value = ''; pintarChips(); mostrarWos(); }
    };
    const listaWo = el('div', 'cn-opciones'); listaWo.hidden = true;
    const envWo = el('div', 'cn-buscador'); envWo.append(chips, otroWo, listaWo);
    campo(izq, 'N.º WO (puedes elegir varios)', envWo);
    const justificacion = campo(izq, 'Justificación de la solicitud', Object.assign(el('textarea'), {rows: 4, maxLength: 500}));
    // Derecha: clasificación.
    const der = el('section', 'cc-ficha');
    const h2 = el('h4', 'cc-ficha-titulo'); h2.append(icono('fa-tag'), el('span', null, 'Clasificación')); der.append(h2);
    const gasto = el('div', 'cn-segmento'); let tipoGasto = 'Gasto Cobra';
    ['Gasto Cobra', 'Refacturable'].forEach(t => {
      const b = el('button', t === tipoGasto ? 'activo' : '', t); b.type = 'button';
      b.addEventListener('click', () => { tipoGasto = t; gasto.querySelectorAll('button').forEach(x => x.classList.toggle('activo', x === b)); });
      gasto.append(b);
    });
    const lGasto = el('label', 'cc-pendiente-campo'); lGasto.append(el('span', null, 'Tipo de gasto'), gasto); der.append(lGasto);
    const concepto = el('select'); concepto.add(new Option('Selecciona el tipo de concepto', ''));
    (CN_CFG.tipos_concepto || []).forEach(t => concepto.add(new Option(t, t)));
    campo(der, 'Tipo de concepto', concepto);
    const cotizador = el('select'); cotizador.add(new Option('Selecciona el cotizador', ''));
    (CN_CFG.cotizadores || []).forEach(c => cotizador.add(new Option(c.nombre, c.nombre)));
    campo(der, 'Usuario cotizador', cotizador);
    der.append(el('p', 'cc-nota', 'Al enviar queda en Registro como "Pdt. Cotización" para que la coticen.'));
    const error = el('p', 'cc-alerta'); error.hidden = true; der.append(error);

    let siteElegido = null, buscaSite = 0, sitesWo = [];
    const limpiarSite = () => {
      siteElegido = null; vCodigo.textContent = vDistrito.textContent = vProvincia.textContent = vRegion.textContent = '—';
      sitesWo = [];
    };
    proyecto.addEventListener('change', () => {
      buscarSite.value = ''; limpiarSite(); wos.clear(); pintarChips(); listaSites.hidden = listaWo.hidden = true; encontradosWo = [];
    });
    // La lista de sites sale al tocar el campo (sin escribir) y se filtra al escribir.
    buscarSite.addEventListener('focus', () => { if (!siteElegido) cargarSites(); });
    buscarSite.addEventListener('input', () => { limpiarSite(); cargarSites(); });
    const avisoProyecto = lista => { lista.replaceChildren(el('p', 'cc-nota', 'Elige primero el proyecto.')); lista.hidden = false; };
    function cargarSites() {
      if (!proyecto.value) { avisoProyecto(listaSites); return; }
      const turno = ++buscaSite;
      clearTimeout(buscarSite._t);
      buscarSite._t = setTimeout(async () => {
        const r = await fetch('/api/cot-new/sites?' + new URLSearchParams({proyecto: proyecto.value, q: buscarSite.value.trim()}));
        const j = await r.json().catch(() => ({}));
        if (turno !== buscaSite) return;
        listaSites.replaceChildren(...(j.sites || []).map(s => {
          const b = el('button', 'cn-opcion'); b.type = 'button';
          b.append(el('strong', null, s.site), el('small', null, [s.codigo, s.distrito, s.provincia].filter(Boolean).join(' · ')));
          b.addEventListener('click', () => elegirSite(s));
          return b;
        }));
        if (!(j.sites || []).length) listaSites.append(el('p', 'cc-nota', 'Sin sites con ese nombre en ' + proyecto.value + '.'));
        listaSites.hidden = false;
      }, buscarSite.value.trim() ? 250 : 0);
    }
    async function elegirSite(s) {
      siteElegido = s; buscarSite.value = s.site; listaSites.hidden = true;
      vCodigo.textContent = s.codigo || '—'; vDistrito.textContent = s.distrito || '—'; vProvincia.textContent = s.provincia || '—'; vRegion.textContent = s.region || '—';
      const r = await fetch('/api/cot-new/wos?' + new URLSearchParams({proyecto: proyecto.value, codigo: s.codigo, nombre: s.nombre}));
      sitesWo = (await r.json().catch(() => ({}))).wos || [];
      mostrarWos();
    }
    // Mientras escribes: WO del site elegido y, además, los WO del proyecto que contienen lo escrito.
    let buscaWo = 0, encontradosWo = [];
    function buscarWos() {
      if (!proyecto.value) { avisoProyecto(listaWo); return; }
      const texto = otroWo.value.trim();
      const turno = ++buscaWo;
      clearTimeout(otroWo._t);
      if (texto.length === 1) { mostrarWos(); return; }
      otroWo._t = setTimeout(async () => {
        const r = await fetch('/api/cot-new/wos?' + new URLSearchParams({proyecto: proyecto.value, q: texto}));  // sin texto: los más recientes
        const j = await r.json().catch(() => ({}));
        if (turno !== buscaWo) return;
        encontradosWo = j.wos || []; mostrarWos();
      }, texto ? 250 : 0);
    }
    function mostrarWos() {
      const texto = otroWo.value.trim().toUpperCase();
      const libres = [...new Set([...sitesWo, ...encontradosWo])].filter(w => !wos.has(w) && (!texto || w.toUpperCase().includes(texto)));
      listaWo.replaceChildren(...libres.slice(0, 20).map(w => {
        const b = el('button', 'cn-opcion', w); b.type = 'button';
        b.addEventListener('click', () => { wos.add(w); otroWo.value = ''; pintarChips(); mostrarWos(); });
        return b;
      }));
      if (!libres.length) listaWo.append(el('p', 'cc-nota', texto.length >= 2 ? 'No hay WO registrados con "' + texto + '" en ' + proyecto.value + '. Si es correcto, presiona Enter para agregarlo.'
        : 'No hay WO registrados en ' + proyecto.value + '. Escribe el WO y presiona Enter.'));
      listaWo.hidden = false;
    }
    function pintarChips() {
      chips.replaceChildren(...[...wos].map(w => {
        const c = el('span', 'cn-chip', w); const x = el('button', null, '×'); x.type = 'button'; x.title = 'Quitar';
        x.addEventListener('click', () => { wos.delete(w); pintarChips(); mostrarWos(); }); c.append(x); return c;
      }));
    }
    // Al tocar el campo: los WO del site elegido o, si no hay, los más recientes del proyecto.
    otroWo.addEventListener('focus', () => { if (!proyecto.value) return avisoProyecto(listaWo); if (!sitesWo.length && !encontradosWo.length) buscarWos(); else mostrarWos(); });
    otroWo.addEventListener('input', buscarWos);
    otroWo.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ',') return;
      e.preventDefault(); agregarEscrito();
    });

    acciones.prepend(botonRedondo(['Enviar registro', 'cn-verde', 'fa-paper-plane', async () => {
      error.hidden = true;
      try {
        agregarEscrito();
        if (!proyecto.value) throw Error('Elige el proyecto.');
        if (!siteElegido) throw Error('Elige el site de la lista.');
        if (!concepto.value) throw Error('Elige el tipo de concepto.');
        if (!cotizador.value) throw Error('Elige el usuario cotizador.');
        if (!justificacion.value.trim()) throw Error('Escribe la justificación de la solicitud.');
        const familia = proyecto.value.replace('FLM - ', '');
        const ahora = new Date(); ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
        const datos = {CLIENTE: familia, 'PROYECTO FLM': proyecto.value, FECHA: ahora.toISOString().slice(0, 16).replace('T', ' '),
          'NOMBRE SITE': siteElegido.site, 'CODIGO SITE': siteElegido.codigo, DISTRITO: siteElegido.distrito, PROVINCIA: siteElegido.provincia,
          REGION: siteElegido.region, DEPARTAMENTO: siteElegido.region, 'NUMERO WO': [...wos].join(', '),
          'TIPO DE GASTO': tipoGasto, 'TIPO DE CONCEPTO': concepto.value, 'TIPO DE COTIZACION': concepto.value,
          COTIZADOR: cotizador.value, 'COTIZADOR USUARIO': (CN_CFG.cotizadores || []).find(c => c.nombre === cotizador.value)?.usuario || '',
          MOTIVO: justificacion.value.trim(), OBJETIVO: justificacion.value.trim(), 'ESTADO COTIZACION': 'Pdt. Cotización',
          ITEMS_JSON: '[]', 'SUB TOTAL + FEE': ''};
        const r = await fetch('/api/cot-new/agregar', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({key: '', data: datos, numeracion_modo: 'automatico'})});
        const j = await r.json().catch(() => ({}));
        if (!r.ok || j.error) throw Error(j.error || 'No se pudo enviar el registro.');
        dialogo.close(); await cargar();
        avisar('Registro ' + j.key + ' enviado: quedó en Registro como Pdt. Cotización.');
      } catch (e) { error.textContent = e.message; error.hidden = false; }
    }], 'cn-grande'));
    // Las listas de sugerencias se cierran al hacer clic fuera de su buscador.
    izq.addEventListener('click', e => {
      if (!envSite.contains(e.target)) listaSites.hidden = true;
      if (!envWo.contains(e.target)) listaWo.hidden = true;
    });
    const cols = el('div', 'cc-validacion-columnas cn-registro-cols'); cols.append(izq, der);
    $('cc-solicitud-contenido').replaceChildren(cols);
    if (!dialogo.open) dialogo.showModal();
    proyecto.focus();
  }
  // Generar: descarga el PDF (queda como generada) y la cotización pasa a Cliente.
  async function generarClave(key) {
    const r = await fetch('/api/cot-new/generar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key})});
    if (!r.ok) throw Error((await r.json().catch(() => ({}))).error || 'No se pudo generar el PDF.');
    descargar(await r.blob(), key + '.pdf');
    const a = await fetch('/api/cotizacion/accion', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key, accion: 'generar'})});
    const j = await a.json().catch(() => ({}));
    if (!a.ok || j.success === false) throw Error(j.error || 'Se generó el PDF, pero no pasó a Cliente.');
  }
  async function generarCotizacion(c) {
    if (!(c.items || []).length) { avisar('Agrega ítems a la cotización antes de generarla.'); return; }
    const ok = await (window.nucleusConfirm ? window.nucleusConfirm('Se descargará el PDF de ' + (c['N° COTIZACION'] || c.key) + ' por ' + dinero(c.monto) + ' y pasará a Cliente.',
      'Generar cotización', {okText: 'Generar', circular: true}) : confirm('¿Generar la cotización?'));
    if (!ok) return;
    try { await generarClave(c.key); if (dialogo.open) dialogo.close(); await cargar(); } catch (e) { avisar(e.message); }
  }
  // ── Flujo dentro de Cot_New: aprobar, proveedor, sustento y atención (mismos servicios de Cotizaciones) ──
  async function subir(ruta, key, archivo) {
    const datos = new FormData(); datos.append('key', key); datos.append('adjunto', archivo);
    const r = await fetch(ruta, {method: 'POST', body: datos});
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.url) throw Error(j.error || 'No se pudo subir el archivo.');
    return j;
  }
  function ventana(titulo, izquierda, derecha, botones) {
    $('cc-solicitud-titulo').textContent = titulo;
    const acciones = $('cn-dialogo-acciones');
    acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    acciones.prepend(...botones.map(b => botonRedondo(b, 'cn-grande')));
    const cols = el('div', 'cc-validacion-columnas' + (derecha ? '' : ' cc-una-columna'));
    cols.append(izquierda); if (derecha) cols.append(derecha);
    $('cc-solicitud-contenido').replaceChildren(cols);
    if (!dialogo.open) dialogo.showModal();
  }
  const resumenCot = c => ficha('fa-file-lines', 'Cotización', [['N.º', c['N° COTIZACION'] || c.key], ['Cliente', CLIENTES[c.familia] || c.CLIENTE],
    ['Site', c['NOMBRE SITE']], ['N.º WO', c['NUMERO WO']], ['Motivo', c.MOTIVO], ['Enviada', c['FECHA ENVIO CLIENTE']],
    ['Aprobada', c['FECHA APROBACION']], ['Se atiende con', c['TIPO GASTO APROBACION']], ['Sub total + FEE', dinero(c.monto)]]);
  function zonaArchivo(texto, ayuda, acepta) {
    const zona = el('label', 'cc-validacion-zona');
    const input = Object.assign(el('input'), {type: 'file', accept: acepta});
    const pie = el('small', null, ayuda);
    zona.append(input, icono('fa-paperclip'), el('strong', null, texto), pie);
    input.addEventListener('change', () => { const f = input.files[0]; pie.textContent = f ? f.name + ' · toca para cambiarlo' : ayuda; zona.classList.toggle('con-archivo', !!f); });
    zona.input = input; return zona;
  }
  const errorCaja = () => { const e = el('p', 'cc-alerta'); e.hidden = true; return e; };
  const conErrorEn = (caja, fn) => async () => { caja.hidden = true; try { await fn(); } catch (e) { caja.textContent = e.message; caja.hidden = false; } };

  // Aprobar: conformidad del cliente (correo), fecha y si se atiende con Caja chica o Proveedor.
  function aprobar(c) {
    const izquierda = el('div'); izquierda.append(resumenCot(c));
    const form = el('form', 'cc-ficha vn-form'); form.noValidate = true;
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-check'), el('span', null, 'Conformidad del cliente')); form.append(h);
    const ahora = new Date(); ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
    const fecha = campo(form, 'Fecha de aprobación', Object.assign(el('input'), {type: 'datetime-local', value: ahora.toISOString().slice(0, 16)}));
    const tipo = el('select'); [['Caja Chica', 'Caja chica'], ['Proveedor', 'Proveedor']].forEach(([v, t]) => tipo.add(new Option(t, v)));
    if (c['TIPO GASTO APROBACION']) tipo.value = /prov/i.test(c['TIPO GASTO APROBACION']) ? 'Proveedor' : 'Caja Chica';
    campo(form, 'Se atiende con', tipo);
    const proveedor = campo(form, 'Nombre del proveedor', Object.assign(el('input'), {maxLength: 200, value: c['NOMBRE DE PROVEEDOR'] || ''}));
    const comentario = campo(form, 'Comentario', Object.assign(el('input'), {maxLength: 500}));
    izquierda.append(form);
    const derecha = el('div', 'cn-columna-archivos');
    const correo = zonaArchivo('Correo de aprobación', 'Toca para adjuntar .msg, PDF o imagen', '.msg,.eml,.pdf,.jpg,.jpeg,.png,.webp');
    const cotProv = zonaArchivo('Cotización del proveedor', 'Opcional · PDF, Word, Excel o imagen', '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp');
    const verProveedor = () => { const p = tipo.value === 'Proveedor'; proveedor.closest('label').hidden = !p; cotProv.hidden = !p; };
    tipo.addEventListener('change', verProveedor); verProveedor();
    const error = errorCaja();
    derecha.append(correo, cotProv, error);
    ventana('Aprobar · ' + (c['N° COTIZACION'] || c.key), izquierda, derecha, [['Aprobar', 'cn-verde', 'fa-check', conErrorEn(error, async () => {
      if (!correo.input.files.length) throw Error('Adjunta el correo de aprobación del cliente.');
      if (tipo.value === 'Proveedor' && !proveedor.value.trim()) throw Error('Escribe el nombre del proveedor.');
      const subido = await subir('/api/cotizacion/subir_correo', c.key, correo.input.files[0]);
      const extra = {tipo_gasto_aprobacion: tipo.value, fecha_aprobacion: fecha.value.replace('T', ' '), comentario: comentario.value.trim(),
                     nombre_proveedor: tipo.value === 'Proveedor' ? proveedor.value.trim() : '', adjunto_correo: subido.url, nombre_correo: subido.nombre};
      if (tipo.value === 'Proveedor' && cotProv.input.files.length) extra.adjunto_cotizacion_proveedor = (await subir('/api/cotizacion/subir_cotizacion_proveedor', c.key, cotProv.input.files[0])).url;
      await accion(c, 'conformar_aprobacion', extra);
      dialogo.close();
    })]]);
  }

  // Proveedor: una fila por factura (N.º, OC, subtotal y su archivo).
  function proveedor(c) {
    const izquierda = el('div'); izquierda.append(resumenCot(c));
    const derecha = el('section', 'cc-ficha cn-items');
    const t = el('h4', 'cc-ficha-titulo'); t.append(icono('fa-file-invoice'), el('span', null, 'Facturas del proveedor')); derecha.append(t);
    const tabla = el('table', 'cn-items-tabla cn-items-editar');
    const cab = el('tr'); ['N.º factura', 'N.º OC', 'Subtotal', 'Archivo', ''].forEach(x => cab.append(el('th', null, x)));
    const cuerpo = el('tbody'); tabla.append(cab, cuerpo);
    const total = el('strong');
    const recalcular = () => { total.textContent = dinero([...cuerpo.children].reduce((s, tr) => s + num(tr.subtotal.value), 0)); };
    const fila = (r = {}) => {
      const tr = el('tr');
      const entrada = (v, cls, modo) => Object.assign(el('input', cls), {value: v ?? '', inputMode: modo || 'text'});
      tr.factura = entrada(r.factura, 'cn-item-texto'); tr.oc = entrada(r.oc, 'cn-item-und'); tr.subtotal = entrada(r.subtotal, 'cn-item-num', 'decimal');
      tr.url = r.url || '';
      const archivo = Object.assign(el('input'), {type: 'file', accept: '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp'});
      const estado = el('small', 'cc-nota', r.url ? 'Cargada' : '');
      archivo.addEventListener('change', () => { estado.textContent = archivo.files[0] ? archivo.files[0].name : (tr.url ? 'Cargada' : ''); });
      tr.archivo = archivo;
      const quitar = el('button', 'cn-item-quitar', '×'); quitar.type = 'button'; quitar.addEventListener('click', () => { tr.remove(); recalcular(); });
      tr.subtotal.addEventListener('input', recalcular);
      const td = (...n) => { const x = el('td'); x.append(...n); return x; };
      tr.append(td(tr.factura), td(tr.oc), td(tr.subtotal), td(archivo, estado), td(quitar));
      cuerpo.append(tr); recalcular();
    };
    (Array.isArray(c._PROVEEDOR_REGISTROS) && c._PROVEEDOR_REGISTROS.length ? c._PROVEEDOR_REGISTROS : [{}]).forEach(fila);
    const agregar = el('button', 'cc-btn cn-agregar-item', '+ Agregar factura'); agregar.type = 'button'; agregar.addEventListener('click', () => fila());
    const pie = el('div', 'cn-total'); pie.append(el('span', null, 'Total facturado'), total);
    const error = errorCaja();
    const envoltura = el('div', 'cn-items-scroll'); envoltura.append(tabla);
    derecha.append(envoltura, agregar, pie, error);
    ventana('Proveedor · ' + (c['N° COTIZACION'] || c.key), izquierda, derecha, [['Guardar facturas', 'cn-verde', 'fa-floppy-disk', conErrorEn(error, async () => {
      const registros = [];
      for (const tr of cuerpo.children) {
        let url = tr.url;
        if (tr.archivo.files.length) url = (await subir('/api/cotizacion/subir_factura_proveedor', c.key, tr.archivo.files[0])).url;
        registros.push({factura: tr.factura.value.trim(), oc: tr.oc.value.trim(), subtotal: tr.subtotal.value.trim(), url});
      }
      const r = await fetch('/api/cotizacion/proveedor', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key, registros})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error) throw Error(j.error || 'No se pudieron guardar las facturas.');
      dialogo.close(); await cargar();
    })]]);
  }

  // Sustento: fotos y bitácora por WO; desde aquí se pasa a Atendido o se revisa (aprobar / rechazar).
  async function sustento(c) {
    const r = await fetch('/api/cotizacion/sustento?key=' + encodeURIComponent(c.key));
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) { avisar(j.error || 'No se pudo cargar el sustento.'); return; }
    const izquierda = el('div'); izquierda.append(resumenCot(c));
    if (c['OBSERVACION SUSTENTO']) izquierda.append(ficha('fa-triangle-exclamation', 'Observación anterior', [['Motivo', c['OBSERVACION SUSTENTO']]]));
    const derecha = el('div');
    for (const w of (j.wos.length ? j.wos : [{wo: 'Sin WO', encontrado: false}])) {
      const caja = el('section', 'cc-ficha');
      const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-camera'), el('span', null, 'WO ' + (w.wo || '—'))); caja.append(h);
      if (!w.encontrado) { caja.append(el('p', 'cc-nota', 'El WO no está registrado en su FLM.')); derecha.append(caja); continue; }
      for (const fase of ['inicio', 'proceso', 'cierre']) {
        const fotos = (w.fotos_urls?.[fase] || []).filter(Boolean);
        caja.append(el('p', 'cn-fase', fase[0].toUpperCase() + fase.slice(1) + ' · ' + fotos.length + ' foto' + (fotos.length === 1 ? '' : 's')));
        if (fotos.length) {
          const tira = el('div', 'cc-rev-miniaturas');
          fotos.forEach(u => { const a = el('a'); a.href = u; a.target = '_blank'; a.rel = 'noopener'; const img = el('img'); img.src = u; img.loading = 'lazy'; img.alt = fase; a.append(img); tira.append(a); });
          caja.append(tira);
        }
        if (w.bitacoras?.[fase]) caja.append(el('small', 'cc-nota', w.bitacoras[fase]));
      }
      derecha.append(caja);
    }
    const botones = [];
    if (tab === 'sustentar') botones.push(['Pasar a Atendido', 'cn-verde', 'fa-circle-check', async () => {
      if (!await (window.nucleusConfirm ? window.nucleusConfirm('La cotización pasará a Atendido para revisar su sustento.', 'Pasar a Atendido', {okText: 'Pasar', circular: true}) : confirm('¿Pasar a Atendido?'))) return;
      try { await accion(c, 'pasar_atendido'); dialogo.close(); } catch (e) { avisar(e.message); }
    }]);
    if (tab === 'atendido' && !j.sustento_aprobado) botones.push(
      ['Aprobar sustento', 'cn-verde', 'fa-check', async () => { try { await accion(c, 'aprobar_sustento'); dialogo.close(); } catch (e) { avisar(e.message); } }],
      ['Rechazar sustento: vuelve a Sustentar', 'cn-naranja', 'fa-rotate-left', conMotivo(c, 'rechazar_sustento', 'Rechazar sustento', 'Rechazar', 'fa-rotate-left')]);
    botones.push(['Cargar o editar fotos (en Cotizaciones)', 'cn-azul', 'fa-images', abrirClasico]);
    ventana('Sustento · ' + (c['N° COTIZACION'] || c.key) + (j.sustento_aprobado ? ' · aprobado' : ''), izquierda, derecha, botones);
  }
  // Solo la carga de fotos del sustento se hace todavía en Cotizaciones.
  const abrirClasico = () => location.assign(clasico);
  function accionesDe(c) {
    const p = tab;
    const lista = [];
    if (!puedeGestionar) return lista;
    if (p === 'registro') lista.push(['Generar cotización (PDF y pasa a Cliente)', 'cn-verde', 'fa-paper-plane', () => generarCotizacion(c)],
      ['Rechazar', 'cn-naranja', 'fa-rotate-left', conMotivo(c, 'rechazar', 'Rechazar cotización', 'Rechazar', 'fa-rotate-left')],
      ['Anular', 'cn-rojo', 'fa-ban', conMotivo(c, 'cancelar', 'Anular cotización', 'Anular', 'fa-ban')]);
    else if (p === 'cliente') lista.push(['Aprobar (conformidad del cliente)', 'cn-verde', 'fa-check', () => aprobar(c)],
      ['Rechazar: vuelve a Registro', 'cn-naranja', 'fa-rotate-left', conMotivo(c, 'rechazar', 'Rechazar cotización', 'Rechazar', 'fa-rotate-left')],
      ['Anular', 'cn-rojo', 'fa-ban', conMotivo(c, 'cancelar', 'Anular cotización', 'Anular', 'fa-ban')]);
    else if (p === 'sustentar') lista.push(['Sustento del WO y pasar a Atendido', 'cn-azul', 'fa-camera', () => sustento(c)]);
    else if (p === 'atendido') lista.push(['Revisar sustento', 'cn-verde', 'fa-magnifying-glass', () => sustento(c)]);
    else if (p === 'proveedor') lista.push(['Facturas del proveedor', 'cn-morado', 'fa-file-invoice', () => proveedor(c)]);
    return lista;
  }
  function botonRedondo([titulo, clase, simbolo, fn], tamano) {
    // Fila: mismo botón redondo de Caja Chica (cc-rapida); ventana: botón grande junto a la X.
    const b = el('button', (tamano ? 'cc-dialogo-icono cn-redondo ' : 'cc-rapida cn-redondo ') + clase + (tamano ? ' ' + tamano : '')); b.type = 'button';
    b.title = titulo; b.setAttribute('aria-label', titulo); b.append(icono(simbolo));
    b.addEventListener('click', async e => { e.stopPropagation(); b.disabled = true; try { await fn(); } finally { b.disabled = false; } });
    return b;
  }

  // ── Detalle: datos a la izquierda; ítems y monto a la derecha ──
  function ficha(iconoNombre, titulo, filas) {
    const caja = el('section', 'cc-ficha'), cabeza = el('h4', 'cc-ficha-titulo');
    cabeza.append(icono(iconoNombre), el('span', null, titulo));
    const lista = el('dl', 'cc-ficha-datos');
    for (const [k, v] of filas) { if (!v) continue; const f = el('div', 'cc-ficha-fila'); f.append(el('dt', null, k), el('dd', null, v)); lista.append(f); }
    caja.append(cabeza, lista); return caja;
  }
  function verDetalle(c) {
    $('cc-solicitud-titulo').textContent = [c['N° COTIZACION'] || c.key, CLIENTES[c.familia] || c.CLIENTE].filter(Boolean).join(' · ');
    const acciones = $('cn-dialogo-acciones');
    acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    acciones.prepend(...accionesDe(c).map(a => botonRedondo(a, 'cn-grande')));
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(
      ficha('fa-file-lines', 'Detalle de la cotización', [['Fecha', fechaTexto(c.FECHA)], ['Site', c['NOMBRE SITE']], ['N.º WO', c['NUMERO WO']],
        ['Motivo', c.MOTIVO], ['Objetivo', c.OBJETIVO !== c.MOTIVO ? c.OBJETIVO : ''], ['Supervisor', c.SUPERVISOR],
        ['Departamento', c.DEPARTAMENTO], ['Tipo de gasto', c['TIPO DE GASTO']], ['Tipo', c['TIPO DE COTIZACION']], ['Código interno', c['CODIGO INTERNO']]]),
      ficha('fa-users', 'Responsables', [['Solicitado por', c['SOLICITADO POR']], ['Gestor', c.GESTOR], ['Cotizador asignado', c.COTIZADOR], ['Cotizado por', c['COTIZADO POR']],
        ['Fecha cotizado', c['FECHA COTIZADO']], ['Enviado al cliente', c['FECHA ENVIO CLIENTE']], ['Aprobado', c['FECHA APROBACION']]]));
    const estado = [['Estado', c['ESTADO COTIZACION'] || 'Pdt. Cotización'], ['Rechazo', c['MOTIVO RECHAZO'] && (c['MOTIVO RECHAZO'] + ' · ' + (c['FECHA RECHAZO'] || ''))],
      ['Anulación', c['MOTIVO CANCELACION'] && (c['MOTIVO CANCELACION'] + ' · ' + (c['FECHA CANCELACION'] || ''))],
      ['Comentario', c['COMENTARIO APROBACION']], ['Gasto', c['TIPO GASTO APROBACION']], ['Proveedor', c['NOMBRE DE PROVEEDOR']],
      ['Factura', c['NUMERO FACTURA PROVEEDOR']], ['OC', c['NUMERO OC PROVEEDOR']],
      ['Tránsito', c.transito && ('Enviada ' + (c.transito.fecha || '') + ' · ' + (c.transito.usuario || ''))]];
    izquierda.append(ficha('fa-flag', 'Estado', estado));
    const derecha = el('div', 'cc-validacion-derecha');
    const items = el('section', 'cc-ficha cn-items');
    const t = el('h4', 'cc-ficha-titulo'); t.append(icono('fa-list-check'), el('span', null, 'Ítems de la cotización (' + c.items.length + ')'));
    const tabla = el('table', 'cn-items-tabla');
    const cab = el('tr'); ['Descripción', 'Und', 'Cant.', 'V. unit.', 'Total'].forEach(h => cab.append(el('th', null, h)));
    tabla.append(cab);
    for (const i of c.items) {
      const tr = el('tr');
      tr.append(el('td', null, i.texto || i.descripcion || '—'), el('td', null, i.und || ''), el('td', 'cc-num', i.cantidad || ''),
        el('td', 'cc-num', i.valor_unitario ? dinero(i.valor_unitario) : ''), el('td', 'cc-num', i.valor_total ? dinero(i.valor_total) : ''));
      tabla.append(tr);
    }
    if (!c.items.length) { const tr = el('tr'); const td = el('td', 'cc-nota', 'Sin ítems registrados.'); td.colSpan = 5; tr.append(td); tabla.append(tr); }
    const total = el('div', 'cn-total'); total.append(el('span', null, 'Sub total + FEE'), el('strong', null, dinero(c.monto)));
    items.append(t, tabla, total);
    derecha.append(items);
    const columnasDetalle = el('div', 'cc-validacion-columnas'); columnasDetalle.append(izquierda, derecha);
    $('cc-solicitud-contenido').replaceChildren(columnasDetalle);
    if (!dialogo.open) dialogo.showModal();
  }

  // ── Pintar ──
  const resumenPlata = s => 'S/ ' + s.toLocaleString('es-PE', {minimumFractionDigits: s >= 1000 || !s ? 0 : 2, maximumFractionDigits: s >= 1000 ? 0 : 2});
  function pintar() {
    pintarCliente();
    document.querySelectorAll('.cn-tab').forEach(b => { b.classList.toggle('activa', b.dataset.tab === tab); b.setAttribute('aria-selected', b.dataset.tab === tab); });
    document.querySelectorAll('[data-cuenta]').forEach(n => { n.textContent = delCliente().filter(c => c.pestanas.includes(n.dataset.cuenta)).length; });
    document.querySelectorAll('[data-plata]').forEach(p => {
      const suma = delCliente().filter(c => c.pestanas.includes(p.dataset.plata)).reduce((t, c) => t + Number(c.monto || 0), 0);
      p.textContent = resumenPlata(suma); p.title = 'Total: ' + dinero(suma);
    });
    pintarEncabezado();
    const lista = $('cn-lista'); lista.replaceChildren();
    const visibles = base();
    $('cc-excel').disabled = !cotizaciones.length;
    if (!visibles.length) {
      const hay = Object.keys(filtros).length || Object.keys(busquedas).length || $('cc-buscar').value.trim();
      lista.append(el('p', 'cc-vacio', hay ? 'Ninguna cotización coincide con los filtros.' : 'No hay cotizaciones en esta etapa.'));
      return;
    }
    for (const c of visibles) {
      const fila = el('div', 'cc-card cc-resumen cc-fila-solicitud');
      const controles = el('span', 'cc-acciones-rapidas cc-col-acciones');
      const botones = accionesDe(c).map(a => botonRedondo(a));
      if (!botones.length) botones.push(botonRedondo(['Ver detalle', 'cn-neutro', 'fa-eye', () => verDetalle(c)]));
      controles.append(...botones);
      fila.append(controles);
      for (const id of columnas) { const col = COLUMNAS[id]; fila.append(col.celda ? col.celda(c) : el('span', col.clase || null, col.texto(c))); }
      lista.append(fila);
    }
  }

  // ── Cliente (píldora) ──
  const botonCliente = $('cn-cliente-btn'), menuCliente = $('cn-cliente-menu');
  const cerrarCliente = () => { menuCliente.hidden = true; botonCliente.setAttribute('aria-expanded', 'false'); };
  const opcionesCliente = [['', 'Todos los clientes'], ...Object.entries(CLIENTES)].map(([valor, texto]) => {
    const b = el('button', 'cc-proyecto-opcion'); b.type = 'button'; b.setAttribute('role', 'option'); b.dataset.valor = valor;
    const punto = el('span', 'cc-proyecto-punto ' + (valor ? 'project-badge--' + valor.toLowerCase() : 'cc-proyecto-todos'));
    b.append(icono('fa-check cc-proyecto-check'), punto, el('span', null, texto), el('span', 'cc-proyecto-cuenta', '0'));
    b.addEventListener('click', () => { cerrarCliente(); cliente = valor; pintar(); });
    menuCliente.append(b); return b;
  });
  botonCliente.addEventListener('click', e => { e.stopPropagation(); const abrir = menuCliente.hidden; menuCliente.hidden = !abrir; botonCliente.setAttribute('aria-expanded', String(abrir)); });
  document.addEventListener('click', e => { if (!menuCliente.hidden && !menuCliente.contains(e.target)) cerrarCliente(); });
  function pintarCliente() {
    $('cc-proyecto-texto').textContent = cliente ? CLIENTES[cliente] : 'Todos los clientes';
    botonCliente.closest('.cc-proyecto-pill').classList.toggle('activo', !!cliente);
    opcionesCliente.forEach(b => {
      b.setAttribute('aria-selected', String(b.dataset.valor === cliente));
      b.lastChild.textContent = cotizaciones.filter(c => !b.dataset.valor || c.familia === b.dataset.valor).length;
    });
  }

  // ── Exportar ──
  const excel = $('cc-excel'), menuExportar = $('cn-exportar-menu');
  const cerrarExportar = () => { menuExportar.hidden = true; excel.setAttribute('aria-expanded', 'false'); };
  excel.addEventListener('click', e => {
    e.stopPropagation();
    if (!menuExportar.hidden) return cerrarExportar();
    $('cn-exportar-pestana').textContent = NOMBRE_TAB[tab] + ' · ' + base().length + ' cotizaciones';
    $('cn-exportar-todo').textContent = 'Todas las pestañas · ' + delCliente().length + ' cotizaciones';
    menuExportar.hidden = false; excel.setAttribute('aria-expanded', 'true');
  });
  document.addEventListener('click', e => { if (!menuExportar.hidden && !menuExportar.contains(e.target)) cerrarExportar(); });
  menuExportar.querySelectorAll('.cc-exportar-opcion').forEach(o => o.addEventListener('click', async () => {
    cerrarExportar();
    const todo = o.dataset.alcance === 'todo', ids = (todo ? delCliente() : base()).map(c => c.id);
    if (!ids.length) return;
    excel.disabled = true;
    try {
      const r = await fetch('/api/cot-new/exportar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(ids)});
      if (!r.ok) throw Error('No se pudo exportar.');
      descargar(await r.blob(), todo ? 'Cotizaciones.xlsx' : 'Cotizaciones-' + NOMBRE_TAB[tab] + '.xlsx');
    } catch (e) { avisar(e.message); } finally { excel.disabled = false; }
  }));
  function descargar(blob, nombre) {
    const a = el('a'); a.href = URL.createObjectURL(blob); a.download = nombre; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ── Tuerca ──
  const ajustes = $('cn-ajustes-btn'), menu = $('cn-ajustes-menu');
  const cerrarMenu = () => { menu.hidden = true; ajustes.setAttribute('aria-expanded', 'false'); };
  ajustes.addEventListener('click', e => { e.stopPropagation(); const abrir = menu.hidden; menu.hidden = !abrir; ajustes.setAttribute('aria-expanded', String(abrir)); });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) cerrarMenu(); });
  menu.addEventListener('click', async e => {
    const opcion = e.target.closest('[data-accion]'); if (!opcion) return;
    e.stopPropagation(); cerrarMenu();
    const a = opcion.dataset.accion;
    if (a === 'clasico') return location.assign(clasico);
    if (a === 'pdfs') return $('cn-pdfs').showModal();
    if (a === 'copiar') {
      const filas = base(), texto = [columnas.map(c => COLUMNAS[c].titulo).join('\t'),
        ...filas.map(f => columnas.map(c => String(COLUMNAS[c].texto(f)).replace(/\s+/g, ' ')).join('\t'))].join('\n');
      try { await navigator.clipboard.writeText(texto); avisar(filas.length + ' filas copiadas. Pégalas en Excel o Google Sheets.'); }
      catch (_) { avisar('No se pudo copiar al portapapeles.'); }
      return;
    }
    if (a === 'limpiar') { filtros = {}; busquedas = {}; orden = null; cliente = ''; $('cc-buscar').value = ''; }
    if (a === 'restablecer') { columnas = Object.keys(COLUMNAS); guardarColumnas(); }
    pintar();
  });
  // PDFs en lote: el mismo servicio de Cotizaciones.
  const formPdfs = $('cn-pdfs-form');
  formPdfs.querySelector('.cc-motivo-cancelar').addEventListener('click', () => $('cn-pdfs').close());
  formPdfs.addEventListener('submit', async e => {
    e.preventDefault();
    const error = formPdfs.querySelector('.cc-alerta'); error.hidden = true;
    try {
      const r = await fetch('/api/cotizacion/descargar_lote', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({desde: formPdfs.desde.value, hasta: formPdfs.hasta.value})});
      if (!r.ok) throw Error((await r.json().catch(() => ({}))).error || 'No se pudieron descargar los PDFs.');
      descargar(await r.blob(), 'Cotizaciones-' + formPdfs.desde.value + '_' + formPdfs.hasta.value + '.zip');
      $('cn-pdfs').close();
    } catch (err) { error.textContent = err.message; error.hidden = false; }
  });

  document.querySelectorAll('.cn-tab').forEach(b => b.addEventListener('click', () => {
    tab = b.dataset.tab; filtros = {}; busquedas = {};
    try { localStorage.setItem('cn-tab', tab); } catch (_) {}
    pintar();
  }));
  $('cc-buscar').addEventListener('input', pintar);
  $('cn-nueva')?.addEventListener('click', nuevoRegistro);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { $('cn-filtro').hidden = true; cerrarMenu(); cerrarExportar(); cerrarCliente(); } });

  async function cargar() {
    const r = await fetch('/api/cot-new/lista'); const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('cn-lista').replaceChildren(el('p', 'cc-alerta', j.error || 'No se pudieron cargar las cotizaciones.')); return; }
    cotizaciones = j.cotizaciones; pintar();
  }
  pintarEncabezado();
  cargar();
})();
