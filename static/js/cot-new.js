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
  // Casillas para marcar una o varias cotizaciones y eliminarlas (solo administradores y supervisores).
  const puedeEliminar = seccion.dataset.eliminar === 'si';
  const seleccionadas = new Set();
  const botonEliminar = $('cc-eliminar');
  let eliminando = false;
  const proyectoId = seccion.dataset.proyecto;
  const clasico = '/switch_project/' + proyectoId + '?next=/';
  const dialogo = $('cc-solicitud-dialogo');
  const NOMBRE_TAB = Object.fromEntries([...document.querySelectorAll('.cn-tab')].map(b => [b.dataset.tab, b.textContent.trim().replace(/\s+\d+\s+S\/.*$/s, '').trim()]));
  const COLOR_ESTADO = {registro: 'cn-e-registro', cliente: 'cn-e-cliente', cajachica: 'cn-e-atendido', proveedor: 'cn-e-proveedor', sustentar: 'cn-e-sustentar', atendido: 'cn-e-atendido', cancelado: 'cn-e-cancelado'};
  const CLIENTES = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};

  let usuarios = {};
  // Muestra el nombre completo del usuario de Nucleus (rhuaman → Ricardo Huaman).
  const nombreDe = u => usuarios[String(u || '').trim().toLowerCase()] || u;
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
  // Cómo se atiende la cotización aprobada: Caja chica, Proveedor o Tránsito.
  const atencion = c => ({'caja chica': 'Caja chica', proveedor: 'Proveedor', transito: 'Tránsito', 'tránsito': 'Tránsito'})[String(c['TIPO GASTO APROBACION'] || '').trim().toLowerCase()] || '';
  // Estados independientes de la pestaña: corren desde que el cliente aprueba.
  const CHIP_PAGO = {'Pendiente Depósito': 'cn-p-pendiente', 'Depositado Caja Chica': 'cn-a-caja', 'Depositado sin proveedor': 'cn-a-transito', 'Facturado Proveedor': 'cn-a-proveedor'};
  const CHIP_OPERATIVO = {'Pdt. ejecutar': 'cn-o-pendiente', 'En ejecución': 'cn-o-ejecucion', 'Ejecutado en campo': 'cn-o-ejecutado', 'Sustentado': 'cn-o-sustentado'};
  const CHIP_ATENCION = {'Caja chica': 'cn-a-caja', Proveedor: 'cn-a-proveedor', 'Tránsito': 'cn-a-transito'};
  const fechaTexto = t => { const v = fechaValor(t); return v ? new Date(v).toLocaleDateString('es-PE') : (t || '—'); };

  const listaWo = v => String(v || '').split(/\s*[,;|\n]\s*/).map(t => t.trim()).filter(Boolean);
  const acumuladoCC = c => (c.depositos_cc || []).reduce((t, d) => t + Number(d.monto || 0), 0);
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
    nombreCliente: {titulo: 'Nombre de cliente', ancho: 'minmax(150px, 1.1fr)', texto: c => c['NOMBRE CLIENTE'] || '—'},
    site: {titulo: 'Nombre del site', ancho: 'minmax(150px, 1.1fr)', texto: c => c['NOMBRE SITE'] || '—'},
    // Varios WO: una línea con la cantidad (clic: lista); uno solo se ve tal cual.
    wo: {titulo: 'N.º WO', ancho: 'minmax(130px, .9fr)', texto: c => c['NUMERO WO'] || '—', celda: c => {
      const lista = listaWo(c['NUMERO WO']);
      if (lista.length < 2) return el('span', null, lista[0] || '—');
      const b = el('button', 'cn-depositos-resumen'); b.type = 'button';
      b.title = lista.join(', '); b.setAttribute('aria-label', 'Ver ' + lista.length + ' WO');
      b.append(el('span', null, lista.length + ' WO'), icono('fa-chevron-right'));
      b.addEventListener('click', e => { e.stopPropagation(); verWos(c, lista); });
      return b;
    }},
    motivo: {titulo: 'Motivo', ancho: 'minmax(200px, 1.8fr)', texto: c => c.MOTIVO || c.OBJETIVO || '—', clase: 'cn-motivo'},
    supervisor: {titulo: 'Supervisor', ancho: 'minmax(140px, 1fr)', texto: c => c.SUPERVISOR || '—'},
    gestor: {titulo: 'Solicitante', ancho: 'minmax(120px, .9fr)', texto: c => nombreDe(c['SOLICITADO POR'] || c.GESTOR) || '—'},
    cotizador: {titulo: 'Cotizador', ancho: 'minmax(130px, .9fr)', texto: c => nombreDe(c.COTIZADOR || c['COTIZADO POR']) || '—'},
    estado: {titulo: 'Estado', ancho: 'minmax(130px, .9fr)', texto: c => estadoTexto(c),
             celda: c => el('span', 'cc-chip ' + (COLOR_ESTADO[c.pestanas[0]] || ''), estadoTexto(c))},
    atencion: {titulo: 'Interacción', ancho: 'minmax(110px, .8fr)', texto: c => atencion(c) || '—',
               celda: c => atencion(c) ? el('span', 'cc-chip ' + CHIP_ATENCION[atencion(c)], atencion(c)) : el('span', null, '—')},
    pago: {titulo: 'Estado de pago', ancho: 'minmax(150px, 1fr)', texto: c => c.estado_pago || '—',
           celda: c => c.estado_pago ? el('span', 'cc-chip ' + (CHIP_PAGO[c.estado_pago] || ''), c.estado_pago) : el('span', null, '—')},
    operativo: {titulo: 'Estado operativo', ancho: 'minmax(140px, .9fr)', texto: c => c.estado_operativo || '—',
                celda: c => c.estado_operativo ? el('span', 'cc-chip ' + (CHIP_OPERATIVO[c.estado_operativo] || ''), c.estado_operativo) : el('span', null, '—')},
    provision: {titulo: 'Provisión', ancho: 'minmax(110px, .7fr)', num: true, texto: c => c.PROVISION ? dinero(c.PROVISION) : '—', orden: c => Number(c.PROVISION) || 0,
                celda: c => c.PROVISION ? el('strong', 'cc-num cn-provision-texto', dinero(c.PROVISION)) : el('span', null, '—')},
    monto: {titulo: 'Sub total + FEE', ancho: 'minmax(120px, .8fr)', num: true, texto: c => dinero(c.monto), orden: c => Number(c.monto) || 0,
            celda: c => el('strong', 'cc-num', dinero(c.monto))},
    // Depósitos de Caja Chica que citan esta cotización: uno se ve tal cual; varios, cantidad y acumulado (clic: lista).
    depositos: {titulo: 'Depósitos Caja Chica', ancho: 'minmax(170px, 1.1fr)', num: true,
                texto: c => (c.depositos_cc || []).map(d => d.codigo + ' ' + dinero(d.monto)).join(' · ') || '—',
                orden: c => acumuladoCC(c),
                celda: c => {
                  const lista = c.depositos_cc || [];
                  if (!lista.length) return el('span', null, '—');
                  const b = el('button', 'cn-depositos-resumen'); b.type = 'button';
                  b.title = 'Ver depósitos de Caja Chica'; b.setAttribute('aria-label', 'Ver ' + lista.length + ' depósitos de Caja Chica');
                  b.append(el('span', null, lista.length === 1 ? lista[0].codigo : lista.length + ' depósitos'),
                    el('strong', 'cc-num', dinero(acumuladoCC(c))), icono('fa-chevron-right'));
                  b.addEventListener('click', e => { e.stopPropagation(); verDepositos(c); });
                  return b;
                }},
  };
  // "Interacción" y la provisión van junto al cliente para verlos sin desplazar la tabla.
  let columnas = Object.keys(COLUMNAS).filter(k => !['atencion', 'pago', 'operativo', 'provision'].includes(k)); columnas.splice(3, 0, 'atencion', 'pago', 'operativo', 'provision');
  function estadoTexto(c) {
    if (c._PAGO_PENDIENTE && c.pestanas.some(p => ['cajachica', 'proveedor'].includes(p))) return 'Por pagar';
    return c.pestanas[0] === 'sustentar' ? 'En operaciones' : (c['ESTADO COTIZACION'] || 'Pdt. Cotización');
  }
  try {
    const guardadas = JSON.parse(localStorage.getItem('cn-columnas') || 'null');
    if (Array.isArray(guardadas) && guardadas.length === columnas.length && columnas.every(c => guardadas.includes(c))) columnas = guardadas;
  } catch (_) {}
  const guardarColumnas = () => { try { localStorage.setItem('cn-columnas', JSON.stringify(columnas)); } catch (_) {} };
  const plano = t => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function plantilla() {
    const minimo = columnas.reduce((s, c) => s + parseInt(COLUMNAS[c].ancho.slice(7), 10), 0) + 12 * columnas.length + 140 + (puedeEliminar ? 52 : 0);
    $('cn-tabla').style.setProperty('--cc-min', minimo + 'px');
    return [...(puedeEliminar ? ['40px'] : []), '112px', ...columnas.map(c => COLUMNAS[c].ancho)].join(' ');
  }

  function pintarEncabezado() {
    $('cn-tabla').style.setProperty('--cc-cols', plantilla());
    const cab = $('cn-encabezado');
    const activo = document.activeElement, foco = activo && cab.contains(activo) && activo.dataset.buscar
      ? {col: activo.dataset.buscar, ini: activo.selectionStart, fin: activo.selectionEnd} : null;
    cab.replaceChildren();
    if (puedeEliminar) {
      const celdaTodas = el('div', 'cc-th cc-th-nombre cc-acciones-cab cc-seleccion');
      const todas = Object.assign(el('input'), {type: 'checkbox', title: 'Seleccionar todas las visibles'});
      const visibles = base().map(c => c.key);
      todas.checked = visibles.length > 0 && visibles.every(k => seleccionadas.has(k));
      todas.addEventListener('change', () => { visibles.forEach(k => todas.checked ? seleccionadas.add(k) : seleccionadas.delete(k)); pintar(); });
      celdaTodas.append(todas);
      cab.append(celdaTodas);
    }
    cab.append(el('div', 'cc-th cc-th-nombre cc-acciones-cab cc-col-acciones', 'Acciones'));
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
  function campo(form, etiqueta, control, clase) {
    const l = el('label', 'cc-pendiente-campo' + (clase ? ' ' + clase : ''));
    l.append(el('span', null, etiqueta), control); form.append(l); return control;
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
  // Selector de varios valores (WO o site): chips y buscador en una sola caja, con lista desplegable.
  // buscar(texto) devuelve [{valor, detalle}] o un texto de aviso; Enter agrega lo escrito.
  function selectorChips({valores = [], buscar, placeholder, mayusculas = true, vacio}) {
    const env = el('div', 'cn-buscador'), caja = el('div', 'cn-multi'), lista = el('div', 'cn-opciones'); lista.hidden = true;
    const input = Object.assign(el('input'), {type: 'text', placeholder, autocomplete: 'off'});
    const flecha = icono('fa-chevron-down'); flecha.classList.add('cn-multi-flecha');
    const elegidos = new Set(valores.map(v => String(v).trim()).filter(Boolean));
    caja.append(input, flecha); env.append(caja, lista);
    const normal = v => { v = String(v || '').trim().replace(/[,;]+$/, ''); return mayusculas ? v.toUpperCase() : v; };
    function pintar() {
      caja.querySelectorAll('.cn-chip').forEach(c => c.remove());
      for (const v of elegidos) {
        const c = el('span', 'cn-chip', v), x = el('button', null, '×'); x.type = 'button'; x.title = 'Quitar';
        x.addEventListener('click', e => { e.stopPropagation(); elegidos.delete(v); pintar(); env.dispatchEvent(new Event('cambio')); });
        c.append(x); caja.insertBefore(c, input);
      }
    }
    const agregar = v => { v = normal(v); if (v) elegidos.add(v); input.value = ''; pintar(); env.dispatchEvent(new Event('cambio')); abrir(); };
    let turno = 0;
    async function abrir() {
      const t = ++turno, texto = input.value.trim();
      const r = await buscar(texto);
      if (t !== turno) return;
      if (typeof r === 'string') { lista.replaceChildren(el('p', 'cc-nota', r)); lista.hidden = false; return; }
      const libres = r.filter(o => !elegidos.has(o.valor));
      lista.replaceChildren(...libres.slice(0, 20).map(o => {
        const b = el('button', 'cn-opcion'); b.type = 'button'; b.append(el('strong', null, o.valor));
        if (o.detalle) b.append(el('small', null, o.detalle));
        b.addEventListener('click', () => { agregar(o.valor); input.focus(); }); return b;
      }));
      if (!libres.length) lista.append(el('p', 'cc-nota', vacio ? vacio(texto) : 'Sin coincidencias. Escribe y presiona Enter para agregarlo.'));
      lista.hidden = false;
      // Si no hay espacio abajo dentro de la ventana, la lista se abre hacia arriba.
      const marco = (env.closest('#cc-solicitud-contenido') || document.body).getBoundingClientRect(), pos = caja.getBoundingClientRect();
      lista.classList.toggle('cn-arriba', pos.bottom + lista.offsetHeight + 8 > marco.bottom && pos.top - lista.offsetHeight > marco.top);
    }
    caja.addEventListener('click', () => input.focus());
    input.addEventListener('focus', abrir);
    input.addEventListener('input', () => { clearTimeout(input._t); input._t = setTimeout(abrir, input.value.trim() ? 250 : 0); });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); agregar(input.value); }
      else if (e.key === 'Backspace' && !input.value && elegidos.size) { elegidos.delete([...elegidos].pop()); pintar(); }
      else if (e.key === 'Escape') { e.stopPropagation(); lista.hidden = true; }
    });
    const cerrar = e => { if (!env.isConnected) return document.removeEventListener('click', cerrar); if (!env.contains(e.target)) lista.hidden = true; };
    document.addEventListener('click', cerrar);
    pintar();
    env.valores = () => { if (input.value.trim()) agregar(input.value); return [...elegidos]; };
    env.limpiar = () => { elegidos.clear(); input.value = ''; pintar(); lista.hidden = true; };
    env.abrir = abrir; env.input = input;
    return env;
  }
  // WO registrados en un proyecto FLM (los del site primero; sin texto, los más recientes).
  async function buscarWosDe(proyecto, texto, delSite = []) {
    if (!proyecto) return 'Elige primero el proyecto.';
    let encontrados = [];
    if (texto.length !== 1) {
      const r = await fetch('/api/cot-new/wos?' + new URLSearchParams({proyecto, q: texto}));
      encontrados = (await r.json().catch(() => ({}))).wos || [];
    }
    const t = texto.toUpperCase();
    return [...new Set([...delSite, ...encontrados])].filter(w => !t || w.toUpperCase().includes(t)).map(w => ({valor: w}));
  }
  async function buscarSitesDe(proyecto, texto) {
    if (!proyecto) return 'Elige primero el proyecto.';
    const r = await fetch('/api/cot-new/sites?' + new URLSearchParams({proyecto, q: texto}));
    return ((await r.json().catch(() => ({}))).sites || []).map(s => ({valor: s.site, detalle: [s.codigo, s.distrito, s.provincia].filter(Boolean).join(' · '), site: s}));
  }
  function nuevoRegistro() {
    $('cc-solicitud-titulo').textContent = 'Nuevo registro · cotización';
    const acciones = $('cn-dialogo-acciones');
    acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    // Izquierda: proyecto, nombre de cliente, site (con sus datos) y WO.
    const izq = el('form', 'cc-ficha vn-form cn-registro'); izq.noValidate = true;
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-location-dot'), el('span', null, 'Proyecto y site')); izq.append(h);
    const proyecto = el('select'); proyecto.add(new Option('Selecciona el proyecto', ''));
    (CN_CFG.proyectos || []).forEach(p => proyecto.add(new Option(p, p)));
    campo(izq, 'Proyecto', proyecto);
    const nombreCliente = el('select');
    const pintarNombresCliente = () => {
      const familia = proyecto.value.replace('FLM - ', '');
      nombreCliente.replaceChildren(new Option(proyecto.value ? 'Selecciona el nombre del cliente' : 'Elige primero el proyecto', ''));
      (CN_CFG.nombres_cliente?.[familia] || []).forEach(n => nombreCliente.add(new Option(n, n)));
      nombreCliente.disabled = !proyecto.value;
    };
    pintarNombresCliente();
    campo(izq, 'Nombre de cliente', nombreCliente);
    const buscarSite = Object.assign(el('input'), {type: 'text', placeholder: 'Escribe el nombre o código del site', autocomplete: 'off'});
    const listaSites = el('div', 'cn-opciones'); listaSites.hidden = true;
    const envSite = el('div', 'cn-buscador'); envSite.append(buscarSite, listaSites);
    campo(izq, 'Nombre del site (registrados en el proyecto)', envSite, 'cn-ancho');
    const auto = el('div', 'cn-auto');
    const dato = t => { const d = el('div'); const v = el('strong', null, '—'); d.append(el('small', null, t), v); auto.append(d); return v; };
    const vCodigo = dato('Código'), vDistrito = dato('Distrito'), vProvincia = dato('Provincia'), vRegion = dato('Región');
    izq.append(auto, el('p', 'cc-nota', 'Código, distrito, provincia y región se llenan solos al elegir el site.'));
    let sitesWo = [];
    const selWo = selectorChips({placeholder: 'Agregar WO…', buscar: texto => buscarWosDe(proyecto.value, texto, sitesWo),
      vacio: t => t.length >= 2 ? 'No hay WO con "' + t.toUpperCase() + '" en ' + proyecto.value + '. Si es correcto, presiona Enter.' : 'Escribe el WO y presiona Enter.'});
    campo(izq, 'N.º WO (puedes elegir varios)', selWo, 'cn-ancho');
    // Derecha: clasificación y justificación.
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
    const justificacion = campo(der, 'Justificación de la solicitud', Object.assign(el('textarea'), {rows: 4, maxLength: 500}));
    der.append(el('p', 'cc-nota', 'Explica brevemente qué se necesita cotizar. Al enviar queda en Registro como "Pdt. Cotización".'));
    const error = el('p', 'cc-alerta'); error.hidden = true; der.append(error);

    let siteElegido = null, buscaSite = 0;
    const limpiarSite = () => {
      siteElegido = null; vCodigo.textContent = vDistrito.textContent = vProvincia.textContent = vRegion.textContent = '—';
      sitesWo = [];
    };
    proyecto.addEventListener('change', () => {
      buscarSite.value = ''; limpiarSite(); selWo.limpiar(); listaSites.hidden = true;
      pintarNombresCliente();
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
      selWo.input.focus();
    }
    acciones.prepend(botonRedondo(['Enviar registro', 'cn-verde', 'fa-paper-plane', async () => {
      error.hidden = true;
      try {
        const wos = selWo.valores();
        if (!proyecto.value) throw Error('Elige el proyecto.');
        if (!nombreCliente.value) throw Error('Elige el nombre del cliente.');
        if (!siteElegido) throw Error('Elige el site de la lista.');
        if (!concepto.value) throw Error('Elige el tipo de concepto.');
        if (!cotizador.value) throw Error('Elige el usuario cotizador.');
        if (!justificacion.value.trim()) throw Error('Escribe la justificación de la solicitud.');
        const familia = proyecto.value.replace('FLM - ', '');
        const ahora = new Date(); ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
        const datos = {CLIENTE: familia, 'PROYECTO FLM': proyecto.value, FECHA: ahora.toISOString().slice(0, 16).replace('T', ' '),
          'NOMBRE CLIENTE': nombreCliente.value,
          'NOMBRE SITE': siteElegido.site, 'CODIGO SITE': siteElegido.codigo, DISTRITO: siteElegido.distrito, PROVINCIA: siteElegido.provincia,
          REGION: siteElegido.region, DEPARTAMENTO: siteElegido.region, 'NUMERO WO': wos.join(', '),
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
  // ── Generar cotización: detalle a la izquierda; ítems, FEE único y total a la derecha ──
  function editorCotizacion(c) {
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(ficha('fa-file-lines', 'Detalle', [['Fecha', fechaTexto(c.FECHA)], ['Cliente', CLIENTES[c.familia] || c.CLIENTE],
      ['Nombre de cliente', c['NOMBRE CLIENTE']], ['Tipo de concepto', c['TIPO DE CONCEPTO'] || c['TIPO DE COTIZACION']],
      ['Tipo de gasto', c['TIPO DE GASTO']], ['Cotizador', nombreDe(c.COTIZADOR)], ['Solicitante', nombreDe(c['SOLICITADO POR'] || c.GESTOR)]]));
    const textos = el('form', 'cc-ficha cn-editor-textos'); textos.noValidate = true;
    const ht = el('h4', 'cc-ficha-titulo'); ht.append(icono('fa-pen-to-square'), el('span', null, 'Datos de la cotización')); textos.append(ht);
    const proyectoFlm = c['PROYECTO FLM'] || (c.familia ? 'FLM - ' + c.familia : '');
    const partes = v => String(v || '').split(/\s*[,;]\s*/).filter(Boolean);
    // Supervisor: lista homologada; si el registro trae otro nombre parecido, se elige el homologado.
    const supervisor = el('select'); supervisor.add(new Option('Selecciona el supervisor', ''));
    const lista = CN_CFG.supervisores || [];
    lista.forEach(n => supervisor.add(new Option(n, n)));
    const actual = String(c.SUPERVISOR || '').trim();
    const parecido = lista.find(n => plano(n) === plano(actual)) || lista.find(n => plano(n).split(' ').every(p => plano(actual).includes(p)));
    if (actual && !parecido) supervisor.add(new Option(actual, actual));
    supervisor.value = parecido || actual;
    campo(textos, 'Supervisor', supervisor);
    const selWo = selectorChips({valores: partes(c['NUMERO WO']), placeholder: 'Agregar otro WO…', buscar: t => buscarWosDe(proyectoFlm, t)});
    campo(textos, 'N.º WO', selWo);
    const selSite = selectorChips({valores: c['NOMBRE SITE'] ? [c['NOMBRE SITE']] : [], placeholder: 'Agregar otro site…', mayusculas: false,
      buscar: t => buscarSitesDe(proyectoFlm, t)});
    campo(textos, 'Nombre del site', selSite);
    const area = (v, filas) => Object.assign(el('textarea'), {value: v || '', rows: filas, maxLength: 300});
    const objetivo = campo(textos, 'Objetivo (título de la cotización)', area(c.OBJETIVO || c.MOTIVO, 2));
    const motivo = campo(textos, 'Motivo', area(c.MOTIVO, 3));
    izquierda.append(textos);

    const derecha = el('section', 'cc-ficha cn-items');
    const cabeza = el('div', 'cn-editor-cabeza'), t = el('h4', 'cc-ficha-titulo'); t.append(icono('fa-list-check'), el('span', null, 'Ítems'));
    const feeInicial = (c.items || []).map(i => i.fee).find(f => f !== undefined && f !== '') ?? '5';
    const fee = Object.assign(el('input', 'cn-item-num'), {value: String(feeInicial).replace('%', ''), inputMode: 'decimal'});
    const feeCaja = el('label', 'cn-editor-fee'); feeCaja.append(el('span', null, 'FEE %'), fee);
    cabeza.append(t, feeCaja);
    const tabla = el('table', 'cn-items-tabla cn-items-editar');
    const cab = el('tr'); ['#', 'Tipo', 'Descripción', 'Und', 'Cant.', 'V. unit.', 'Total', ''].forEach(x => cab.append(el('th', null, x)));
    const cuerpo = el('tbody'), pieTabla = el('tfoot'), filaPie = el('tr');
    const totVu = el('td', 'cc-num cn-pie-vu'), totFee = el('td', 'cc-num cn-pie-total');
    const etiquetaPie = el('td', 'cn-pie-etiqueta', 'Total valor unitario · Sub total + FEE'); etiquetaPie.colSpan = 5;
    filaPie.append(etiquetaPie, totVu, totFee, el('td')); pieTabla.append(filaPie);
    tabla.append(cab, cuerpo, pieTabla);
    const sub = el('span'), feeMonto = el('span'), feeTexto = el('span', 'cc-nota'), total = el('strong');
    function fila(item = {}) {
      const tr = el('tr'), n = el('td', 'cn-item-n');
      const tipo = el('select'); TIPOS_ITEM.forEach(x => tipo.add(new Option(x, x))); tipo.value = TIPOS_ITEM.includes(item.tipo) ? item.tipo : 'REEMBOLSABLE';
      const entrada = (v, cls, modo) => Object.assign(el('input', cls), {value: v ?? '', inputMode: modo || 'text'});
      const texto = entrada(item.texto || item.descripcion, 'cn-item-texto'), und = entrada(item.und || 'UND', 'cn-item-und');
      const cant = entrada(item.cantidad || '1', 'cn-item-num', 'decimal'), vu = entrada(item.valor_unitario, 'cn-item-num', 'decimal');
      const tot = el('td', 'cc-num cn-item-total');
      const quitar = el('button', 'cn-item-quitar'); quitar.type = 'button'; quitar.title = 'Quitar ítem'; quitar.append(icono('fa-trash-can'));
      quitar.addEventListener('click', () => { tr.remove(); recalcular(); });
      [cant, vu].forEach(i => i.addEventListener('input', recalcular));
      const td = x => { const d = el('td'); d.append(x); return d; };
      tr.append(n, td(tipo), td(texto), td(und), td(cant), td(vu), tot, td(quitar));
      tr.leer = () => {
        const base = Math.round(num(cant.value) * num(vu.value) * 100) / 100, f = num(fee.value);
        return {base, item: {tipo: tipo.value, texto: texto.value.trim(), und: und.value.trim(), cantidad: cant.value.trim(), valor_unitario: vu.value.trim(),
          fee: String(f), valor_total: (Math.round(base * (1 + f / 100) * 100) / 100).toFixed(2), comentarios: item.comentarios || ''}};
      };
      tr.pintar = i => { n.textContent = i + 1; tot.textContent = dinero(tr.leer().base); };
      cuerpo.append(tr); return tr;
    }
    function recalcular() {
      let s = 0; [...cuerpo.children].forEach((tr, i) => { tr.pintar(i); s += tr.leer().base; });
      const f = num(fee.value), m = Math.round(s * f) / 100;
      totVu.textContent = dinero(s); totFee.textContent = dinero(s + m);
      sub.textContent = dinero(s); feeTexto.textContent = 'FEE ' + f + '%'; feeMonto.textContent = dinero(m); total.textContent = dinero(s + m);
      t.lastChild.textContent = 'Ítems (' + cuerpo.children.length + ')';
    }
    fee.addEventListener('input', recalcular);
    (c.items || []).forEach(i => fila(i)); if (!cuerpo.children.length) fila();
    const agregar = el('button', 'cc-btn cn-agregar-item'); agregar.type = 'button'; agregar.append(icono('fa-plus'), el('span', null, ' Agregar ítem'));
    agregar.addEventListener('click', () => { fila().querySelector('.cn-item-texto').focus(); recalcular(); });
    const resumen = el('div', 'cn-resumen');
    const linea = (a, b) => { const d = el('div'); d.append(a, b); return d; };
    resumen.append(linea(el('span', 'cc-nota', 'Sub total'), sub), linea(feeTexto, feeMonto));
    const pie = el('div', 'cn-total'); pie.append(el('span', null, 'Sub total + FEE'), total);
    const envoltura = el('div', 'cn-items-scroll'); envoltura.append(tabla);
    const error = errorCaja();
    derecha.append(cabeza, envoltura, agregar, resumen, pie, error);
    recalcular();

    async function guardar() {
      const leidos = [...cuerpo.children].map(tr => tr.leer().item).filter(i => i.texto || num(i.valor_unitario));
      if (leidos.some(i => !i.texto || !(num(i.valor_unitario) > 0) || !(num(i.cantidad) > 0))) throw Error('Cada ítem necesita descripción, cantidad y valor unitario.');
      if (!leidos.length) throw Error('Agrega al menos un ítem.');
      if (!motivo.value.trim()) throw Error('Escribe el motivo.');
      if (!objetivo.value.trim()) throw Error('Escribe el objetivo (título de la cotización).');
      const s = leidos.reduce((a, i) => a + num(i.valor_total), 0);
      const r = await fetch('/api/cot-new/guardar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key,
        data: {MOTIVO: motivo.value.trim(), OBJETIVO: objetivo.value.trim() || motivo.value.trim(), SUPERVISOR: supervisor.value,
          'NUMERO WO': selWo.valores().join(', '), 'NOMBRE SITE': selSite.valores().join(', '), ITEMS_JSON: JSON.stringify(leidos), 'SUB TOTAL + FEE': s.toFixed(2)}})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error || j.success === false) throw Error(j.error || 'No se pudo guardar la cotización.');
      return s;
    }
    const guardarSolo = async () => { await guardar(); await cargar(); avisar('Cotización guardada.'); };
    const generar = async () => {
      const s = await guardar();
      const ok = await (window.nucleusConfirm ? window.nucleusConfirm('Se descargará el PDF de ' + (c['N° COTIZACION'] || c.key) + ' por ' + dinero(s) + ' y pasará a Cliente.',
        'Generar cotización', {okText: 'Generar', circular: true}) : confirm('¿Generar la cotización?'));
      if (!ok) { await cargar(); return; }
      await generarClave(c.key); dialogo.close(); await cargar();
    };
    ventana((c['N° COTIZACION'] || c.key) + ' · ' + (CLIENTES[c.familia] || c.CLIENTE || ''), izquierda, derecha, [
      ['Plantilla de ítems (en Cotizaciones)', 'cn-azul', 'fa-file-excel', abrirClasico],
      ['Guardar', 'cn-neutro', 'fa-floppy-disk', conErrorEn(error, guardarSolo)],
      ['Generar: PDF y pasa a Cliente', 'cn-verde', 'fa-paper-plane', conErrorEn(error, generar)]]);
    $('cc-solicitud-contenido').firstChild.classList.add('cn-editor');
  }
  // ── Pago: foto del pago; la fecha y hora se graban solas. Pasa a Operaciones (y Tránsito si corresponde) ──
  function pagar(c) {
    const izquierda = fichasDetalle(c);
    const derecha = el('div', 'cc-validacion-derecha cn-columna-archivos');
    const caja = el('section', 'cc-ficha cn-aprobacion');
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-money-bill-wave'), el('span', null, 'Pago')); caja.append(h);
    const esTransito = atencion(c) === 'Tránsito', aPagar = esTransito ? num(c['MONTO TRANSITO']) : num(c.monto);
    const monto = el('div', 'cn-total'); monto.append(el('span', null, 'Monto a pagar · ' + (atencion(c) || '')), el('strong', null, dinero(aPagar)));
    // Solo la captura (imagen) del depósito; no se acepta PDF.
    const foto = zonaArchivo('Captura del depósito', 'Toca para adjuntar la foto o captura del depósito', 'image/*');
    const tras = atencion(c) === 'Tránsito' ? ' y queda en Tránsito hasta encontrar proveedor' : '';
    caja.append(monto);
    caja.append(foto, el('p', 'cc-nota', 'La fecha y hora del pago se registran solas al confirmar. Pasa a Operaciones' + tras + '.'));
    const error = errorCaja(); caja.append(error);
    derecha.append(fichaItems(c), caja);
    ventana('Registrar pago · ' + (c['N° COTIZACION'] || c.key), izquierda, derecha, [['Confirmar pago', 'cn-verde', 'fa-check', conErrorEn(error, async () => {
      if (!foto.input.files.length) throw Error('Adjunta la captura del depósito.');
      const subido = await subir('/api/cotizacion/subir_pago', c.key, foto.input.files[0]);
      const r = await fetch('/api/cot-new/pagar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key, foto: subido.url})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(j.error || 'No se pudo registrar el pago.');
      dialogo.close(); await cargar();
      avisar('Pago registrado: ' + (c['N° COTIZACION'] || c.key) + ' pasó a Operaciones' + (atencion(c) === 'Tránsito' ? ' y a Tránsito.' : '.'));
    })]]);
  }
  function pedirMonto(c) {
    return new Promise(resolve => {
      const d = el('dialog', 'cc-motivo'), form = el('form', 'cc-motivo-form'); form.method = 'dialog';
      const cabeza = el('header', 'cc-motivo-cabeza'), marca = el('span', 'cc-motivo-icono'); marca.append(icono('fa-shoe-prints'));
      const textos = el('div'); textos.append(el('h3', null, 'Pasar a Tránsito'), el('p', null, (c['N° COTIZACION'] || c.key) + ' · Sub total + FEE ' + dinero(c.monto))); cabeza.append(marca, textos);
      const monto = Object.assign(el('input'), {type: 'text', inputMode: 'decimal', value: Number(c.monto || 0).toFixed(2)});
      const pie = el('nav', 'cc-motivo-pie');
      const cancelar = el('button', 'cc-motivo-cancelar', 'Cancelar'); cancelar.type = 'button';
      const ok = el('button', 'cc-motivo-ok'); ok.type = 'submit'; ok.value = 'ok'; ok.append(icono('fa-shoe-prints'), el('span', null, 'Pasar'));
      pie.append(cancelar, ok);
      form.append(cabeza, el('span', 'cc-motivo-etiqueta', 'Monto a depositar para Tránsito (S/)'), monto,
        el('small', 'cc-nota', 'La provisión del 20 % se verá como sugerencia al pasar a Proveedor.'), pie); d.append(form);
      const validar = () => { ok.disabled = !(num(monto.value) > 0); }; monto.addEventListener('input', validar); validar();
      cancelar.addEventListener('click', () => d.close(''));
      d.addEventListener('close', () => { resolve(d.returnValue === 'ok' ? monto.value : null); d.remove(); });
      document.body.append(d); d.showModal(); monto.select();
    });
  }
  // Tránsito → Proveedor: muestra lo pagado, la captura del depósito y el 20 % sugerido antes de pasar.
  function transitoAProveedor(c) {
    const izquierda = fichasDetalle(c);
    const derecha = el('div', 'cc-validacion-derecha cn-columna-archivos');
    const caja = el('section', 'cc-ficha cn-aprobacion');
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-shoe-prints'), el('span', null, 'Pago en Tránsito')); caja.append(h);
    const pagado = num(c['MONTO PAGADO'] || c['MONTO TRANSITO']);
    const provision = Math.round(pagado * 20) / 100;
    caja.append(ficha('fa-clock', '', [['Pagado el', c['FECHA PAGO']], ['Pagado por', c['PAGADO POR'] && nombreDe(c['PAGADO POR'])]]).querySelector('dl'));
    // Captura del depósito: imagen (o enlace si es PDF).
    const url = c['FOTO PAGO'];
    if (url) {
      const a = el('a', 'cn-captura-pago'); a.href = url; a.target = '_blank'; a.rel = 'noopener'; a.title = 'Abrir captura del depósito';
      const img = el('img'); img.src = url; img.alt = 'Captura del depósito'; img.loading = 'lazy'; a.append(img);
      caja.append(el('span', 'cc-motivo-etiqueta', 'Captura del depósito'), a);
    } else caja.append(el('p', 'cc-nota', 'Sin captura del depósito.'));
    const fila = (texto, valor, clase) => { const d = el('div', 'cn-total' + (clase ? ' ' + clase : '')); d.append(el('span', null, texto), el('strong', null, dinero(valor))); return d; };
    caja.append(fila('Monto pagado (Tránsito)', pagado),
      fila('Provisión sugerida (20 %)', provision, 'cn-provision'),
      fila('Total con el 20 %', pagado + provision, 'cn-total-final'),
      el('p', 'cc-nota', 'El 20 % es una sugerencia para negociar con el proveedor.'));
    const error = errorCaja(); caja.append(error);
    derecha.append(fichaItems(c), caja);
    ventana('Pasar a Proveedor · ' + (c['N° COTIZACION'] || c.key), izquierda, derecha, [['Pasar a Proveedor', 'cn-morado', 'fa-file-invoice', conErrorEn(error, async () => {
      const r = await fetch('/api/cot-new/mover', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key, desde: 'transito', hacia: 'proveedor'})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(j.error || 'No se pudo mover la cotización.');
      dialogo.close(); await cargar();
      avisar((c['N° COTIZACION'] || c.key) + ' pasó a Proveedor.');
    })]]);
  }
  async function moverA(c, desde, hacia, nombre) {
    let monto = '';
    if (hacia === 'transito') { monto = await pedirMonto(c); if (monto === null) return; }
    const ok = hacia === 'transito' || await (window.nucleusConfirm ? window.nucleusConfirm((c['N° COTIZACION'] || c.key) + ' pasará a ' + nombre + '.', 'Pasar a ' + nombre, {okText: 'Pasar', circular: true})
      : confirm('¿Pasar a ' + nombre + '?'));
    if (!ok) return;
    const r = await fetch('/api/cot-new/mover', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key, desde, hacia, monto_transito: monto})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { avisar(j.error || 'No se pudo mover la cotización.'); return; }
    if (dialogo.open) dialogo.close();
    await cargar();
    avisar((c['N° COTIZACION'] || c.key) + ' pasó a ' + nombre + '.');
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
    ['Aprobada', c['FECHA APROBACION']], ['Interacción', c['TIPO GASTO APROBACION']], ['Sub total + FEE', dinero(c.monto)]]);
  function verWos(c, lista) {
    const tabla = el('table', 'cn-depositos-tabla');
    const cab = el('tr'); ['#', 'N.º WO'].forEach(t => cab.append(el('th', null, t))); tabla.append(cab);
    lista.forEach((w, n) => { const f = el('tr'); f.append(el('td', null, String(n + 1)), el('td', null, w)); tabla.append(f); });
    const caja = el('section', 'cc-ficha'); const h = el('h4', 'cc-ficha-titulo');
    h.append(icono('fa-list-ol'), el('span', null, lista.length + ' WO · ' + (c['NOMBRE SITE'] || ''))); caja.append(h, tabla);
    ventana('WO · ' + (c['N° COTIZACION'] || c.key), caja, null, []);
  }
  // Lista de depósitos de Caja Chica asociados; cada código abre su solicitud en Caja Chica.
  function verDepositos(c) {
    const lista = c.depositos_cc || [];
    const tabla = el('table', 'cn-depositos-tabla');
    const cab = el('tr'); ['Código', 'Técnico', 'Estado', 'Monto'].forEach(t => cab.append(el('th', null, t)));
    tabla.append(cab);
    lista.forEach(d => {
      const f = el('tr'), a = el('a', 'cc-codigo-link', d.codigo);
      a.href = '/caja-chica/#solicitud-' + d.id; a.target = '_blank'; a.rel = 'noopener';
      const td = el('td'); td.append(a);
      f.append(td, el('td', null, d.tecnico || '—'), el('td', null, d.estado || '—'), el('td', 'cc-num', dinero(d.monto)));
      tabla.append(f);
    });
    const pie = el('tr', 'cn-depositos-pie');
    pie.append(el('td', null, 'Acumulado (' + lista.length + ')'), el('td'), el('td'), el('td', 'cc-num', dinero(acumuladoCC(c))));
    tabla.append(pie);
    const caja = el('section', 'cc-ficha'); const h = el('h4', 'cc-ficha-titulo');
    h.append(icono('fa-wallet'), el('span', null, 'Depósitos de Caja Chica')); caja.append(h, tabla);
    ventana('Depósitos · ' + (c['N° COTIZACION'] || c.key), caja, null, []);
  }
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
    const izquierda = fichasDetalle(c);
    const form = el('form', 'cc-ficha cn-aprobacion'); form.noValidate = true;
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-check'), el('span', null, 'Conformidad del cliente')); form.append(h);
    const correo = zonaArchivo('Correo de aprobación', 'Toca para adjuntar .msg, PDF o imagen', '.msg,.eml,.pdf,.jpg,.jpeg,.png,.webp');
    form.append(correo);
    // La fecha de aprobación no se escribe: se registra sola con la hora de Perú al aprobar.
    // Interacción: dos botones (mismo diseño que Gasto Cobra / Refacturable).
    const tipo = Object.assign(el('input'), {type: 'hidden', value: {Proveedor: 'Proveedor', 'Tránsito': 'Tránsito'}[atencion(c)] || 'Caja Chica'});
    const segmento = el('div', 'cn-segmento');
    [['Caja Chica', 'Caja chica'], ['Proveedor', 'Proveedor'], ['Tránsito', 'Tránsito']].forEach(([v, t]) => {
      const b = el('button', v === tipo.value ? 'activo' : '', t); b.type = 'button';
      b.addEventListener('click', () => { tipo.value = v; segmento.querySelectorAll('button').forEach(x => x.classList.toggle('activo', x === b)); tipo.dispatchEvent(new Event('change')); });
      segmento.append(b);
    });
    segmento.append(tipo);
    const lTipo = el('div', 'cc-pendiente-campo'); lTipo.append(el('span', null, 'Interacción'), segmento); correo.after(lTipo);
    // Tránsito: cuánto se deposita por Caja chica mientras se busca proveedor (por defecto, el total de la cotización).
    const montoTransito = Object.assign(el('input'), {type: 'text', inputMode: 'decimal', placeholder: '0.00', value: c['MONTO TRANSITO'] || Number(c.monto || 0).toFixed(2)});
    const lMonto = el('label', 'cc-pendiente-campo'); lMonto.append(el('span', null, 'Monto a depositar para Tránsito (S/)'), montoTransito,
      el('small', 'cc-nota', 'La provisión del 20 % se verá como sugerencia al pasar a Proveedor.'));
    lTipo.after(lMonto);
    const verMonto = () => { lMonto.hidden = tipo.value !== 'Tránsito'; };
    tipo.addEventListener('change', verMonto); verMonto();
    const comentario = campo(form, 'Comentario', Object.assign(el('input'), {maxLength: 500}));
    const derecha = el('div', 'cc-validacion-derecha cn-columna-archivos');
    const error = errorCaja();
    form.append(error);
    derecha.append(fichaItems(c), form);
    ventana('Aprobar · ' + (c['N° COTIZACION'] || c.key), izquierda, derecha, [['Aprobar', 'cn-verde', 'fa-check', conErrorEn(error, async () => {
      if (!correo.input.files.length) throw Error('Adjunta el correo de aprobación del cliente.');
      if (tipo.value === 'Tránsito' && !(num(montoTransito.value) > 0)) throw Error('Escribe el monto a depositar para Tránsito.');
      const subido = await subir('/api/cotizacion/subir_correo', c.key, correo.input.files[0]);
      const hoy = new Date(); hoy.setMinutes(hoy.getMinutes() - hoy.getTimezoneOffset());
      const extra = {tipo_gasto_aprobacion: tipo.value, fecha_aprobacion: hoy.toISOString().slice(0, 19).replace('T', ' '), comentario: comentario.value.trim(),
                     adjunto_correo: subido.url, nombre_correo: subido.nombre, monto_transito: tipo.value === 'Tránsito' ? montoTransito.value : ''};
      await accion(c, 'conformar_aprobacion', extra);
      dialogo.close();
    })]]);
  }

  // Proveedor: una fila por factura (N.º, OC, subtotal y su archivo).
  function proveedor(c) {
    const izquierda = fichasDetalle(c);
    const derecha = el('div', 'cc-validacion-derecha cn-columna-archivos');
    const caja = el('section', 'cc-ficha');
    const t = el('h4', 'cc-ficha-titulo'); t.append(icono('fa-file-invoice'), el('span', null, 'Facturas del proveedor')); caja.append(t);
    const lista = el('div', 'cn-facturas');
    const total = el('strong');
    const recalcular = () => {
      total.textContent = dinero([...lista.children].reduce((s, f) => s + num(f.subtotal.value), 0));
      [...lista.children].forEach((f, n) => { f.numero.textContent = 'Factura ' + (n + 1); });
    };
    const fila = (r = {}) => {
      const f = el('div', 'cn-factura');
      const cabeza = el('div', 'cn-factura-cabeza'); f.numero = el('strong');
      const quitar = el('button', 'cn-factura-quitar'); quitar.type = 'button'; quitar.title = 'Quitar factura'; quitar.setAttribute('aria-label', 'Quitar factura'); quitar.append(icono('fa-trash-can'));
      quitar.addEventListener('click', () => { f.remove(); recalcular(); });
      cabeza.append(f.numero, quitar);
      const datos = el('div', 'cn-factura-datos');
      const entrada = (v, modo, ph) => Object.assign(el('input'), {type: 'text', value: v ?? '', inputMode: modo || 'text', placeholder: ph || ''});
      f.factura = campo(datos, 'N.º factura', entrada(r.factura, 'text', 'F001-000123'));
      f.oc = campo(datos, 'N.º OC', entrada(r.oc, 'text', 'OC-0001'));
      f.subtotal = campo(datos, 'Subtotal (S/)', entrada(r.subtotal, 'decimal', '0.00'));
      f.subtotal.addEventListener('input', recalcular);
      // Adjuntar: botón claro con el nombre del archivo elegido o enlace a la factura ya cargada.
      f.url = r.url || '';
      const adjuntar = el('label', 'cn-factura-adjunto');
      f.archivo = Object.assign(el('input'), {type: 'file', accept: '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp', hidden: true});
      const texto = el('span'), detalle = el('small');
      const pintar = () => {
        const elegido = f.archivo.files[0];
        adjuntar.classList.toggle('lleno', !!(elegido || f.url));
        texto.textContent = elegido ? elegido.name : f.url ? 'Factura cargada · toca para cambiarla' : 'Adjuntar factura';
        detalle.textContent = elegido ? 'Se sube al guardar' : f.url ? '' : 'PDF, Word, Excel o imagen';
      };
      f.archivo.addEventListener('change', pintar);
      adjuntar.append(f.archivo, icono('fa-paperclip'), texto, detalle);
      const pie = el('div', 'cn-factura-pie'); pie.append(adjuntar);
      if (f.url) { const ver = el('a', 'cn-factura-ver'); ver.href = f.url; ver.target = '_blank'; ver.rel = 'noopener'; ver.title = 'Ver factura'; ver.append(icono('fa-eye')); pie.append(ver); }
      pintar();
      f.append(cabeza, datos, pie);
      lista.append(f); recalcular();
    };
    (Array.isArray(c._PROVEEDOR_REGISTROS) && c._PROVEEDOR_REGISTROS.length ? c._PROVEEDOR_REGISTROS : [{}]).forEach(fila);
    const agregar = el('button', 'cc-btn cn-agregar-item'); agregar.type = 'button'; agregar.append(icono('fa-plus'), el('span', null, ' Agregar factura'));
    agregar.addEventListener('click', () => fila());
    const pieTotal = el('div', 'cn-total'); pieTotal.append(el('span', null, 'Total facturado'), total);
    const error = errorCaja();
    caja.append(lista, agregar, pieTotal);
    if (c.PROVISION) { const prov = el('div', 'cn-total cn-provision'); prov.append(el('span', null, 'Provisión de Tránsito (20 %)'), el('strong', null, dinero(c.PROVISION))); caja.append(prov); }
    caja.append(error);
    derecha.append(fichaItems(c), caja);
    ventana('Proveedor · ' + (c['N° COTIZACION'] || c.key), izquierda, derecha, [['Guardar facturas', 'cn-verde', 'fa-floppy-disk', conErrorEn(error, async () => {
      const registros = [];
      for (const f of lista.children) {
        let url = f.url;
        if (f.archivo.files.length) url = (await subir('/api/cotizacion/subir_factura_proveedor', c.key, f.archivo.files[0])).url;
        registros.push({factura: f.factura.value.trim(), oc: f.oc.value.trim(), subtotal: f.subtotal.value.trim(), url});
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
  // ── Operaciones: ficha de sustento (mismos datos que Cotizaciones) con el diseño nuevo ──
  // Un sustento por WO. Izquierda: datos del trabajo y descripción. Derecha: foto de ubicación, evidencia por ítem y pago.
  const OP_CAMPOS = [['ajb_ejb', 'AJB / EJB'], ['expense', 'Expense'], ['site_name', 'Nombre del sitio'], ['site_id', 'Código del sitio'],
    ['site_type', 'Tipo de site'], ['region', 'Región'], ['site_address', 'Ubicación del sitio', true], ['district', 'Distrito'], ['province', 'Provincia']];
  const OP_RESPALDO = {site_name: ['NOMBRE SITE'], site_id: ['CODIGO SITE'], site_address: ['DIRECCION'], site_type: ['TIPO SITE'],
    district: ['DISTRITO'], province: ['PROVINCIA'], region: ['REGION', 'DEPARTAMENTO']};
  const OP_FASES = [['before', 'Antes'], ['during', 'Durante'], ['after', 'Después']];
  const aLocal = s => { const m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/); return m ? m[1] + '-' + m[2] + '-' + m[3] + 'T' + m[4] + ':' + m[5] : ''; };
  const deLocal = s => s ? s.replace('T', ' ') + ':00' : '';
  async function leerJson(r) { return r.json().catch(() => ({})); }

  async function operaciones(c, indice) {
    const r = await fetch('/api/cotizacion/sustento?key=' + encodeURIComponent(c.key));
    const j = await leerJson(r);
    if (!r.ok || !j.success) { avisar(j.error || 'No se pudo cargar el sustento.'); return; }
    // FLM - PEXT conserva el formulario anterior.
    if ([c.CLIENTE, c.familia, ...j.wos.map(w => w.proyecto_nombre)].some(v => String(v || '').toUpperCase().includes('PEXT'))) { sustento(c); return; }
    const lista = j.wos.length ? j.wos : [{wo: '', encontrado: true, wo_data: j.cotizacion_data, bloqueado: j.sustento_aprobado}];
    const i = indice ?? lista.findIndex(w => w.encontrado);
    if (i < 0) { avisar('Primero registra los WO en el FLM correspondiente.'); return; }
    const entry = lista[i], datos = entry.wo_data || {}, manual = datos._SUSTENTO_MANUAL || {};
    const editable = puedeGestionar && tab === 'sustentar' && !j.sustento_aprobado && !entry.bloqueado;
    const ctx = {subiendo: 0};
    const entrada = (valor, tipo) => { const x = Object.assign(el('input'), {type: tipo || 'text', value: valor || '', disabled: !editable}); return x; };

    // Izquierda: datos del trabajo y del sitio.
    const izquierda = el('div', 'cc-validacion-izquierda');
    const datosForm = el('form', 'cc-ficha cn-op-form'); datosForm.noValidate = true;
    const h1 = el('h4', 'cc-ficha-titulo'); h1.append(icono('fa-location-dot'), el('span', null, 'Datos del trabajo y del sitio')); datosForm.append(h1);
    const rejilla = el('div', 'cn-op-rejilla'); datosForm.append(rejilla);
    campo(rejilla, 'N.º presupuesto', Object.assign(entrada(c['N° COTIZACION'] || c.key), {disabled: true}));
    const campoWo = campo(rejilla, 'N.º WO', Object.assign(entrada(manual.wo ?? entry.wo), {maxLength: 100}));
    const valores = {};
    for (const [k, t, ancho] of OP_CAMPOS) {
      const inicial = manual[k] ?? (OP_RESPALDO[k] || [k.toUpperCase()]).map(x => datos[x] || j.cotizacion_data?.[x]).find(Boolean) ?? '';
      valores[k] = campo(rejilla, t, Object.assign(entrada(inicial), {maxLength: k === 'site_address' ? 2000 : 300}), ancho ? 'cn-ancho' : '');
    }
    const responsable = campo(rejilla, 'Responsable del trabajo', Object.assign(entrada(manual.work_responsible), {maxLength: 300}), 'cn-ancho');
    const listaResp = el('datalist'); listaResp.id = 'cn-op-responsables'; responsable.setAttribute('list', listaResp.id); rejilla.append(listaResp);
    fetch('/api/cotizacion/sustento/responsables').then(leerJson).then(x => (x.opciones || []).forEach(o => listaResp.append(new Option(o)))).catch(() => {});
    const inicio = campo(rejilla, 'Fecha de inicio', entrada(aLocal(datos['INICIO EJECUCION']), 'datetime-local'));
    const fin = campo(rejilla, 'Fecha de fin', entrada(aLocal(datos['FIN EJECUCION']), 'datetime-local'));
    valores.work_responsible = responsable;
    const desc = el('form', 'cc-ficha cn-op-form'); desc.noValidate = true;
    const h2 = el('h4', 'cc-ficha-titulo'); h2.append(icono('fa-align-left'), el('span', null, 'Descripción del trabajo')); desc.append(h2);
    const bitacora = {};
    [['INICIO', 'Antecedentes'], ['PROCESO', 'Objetivos'], ['CIERRE', 'Detalles del trabajo realizado']].forEach(([fase, t]) => {
      bitacora[fase] = campo(desc, t, Object.assign(el('textarea'), {rows: 3, value: datos['_BITACORA_' + fase] || '', disabled: !editable}));
    });
    izquierda.append(datosForm, desc);
    if (c['OBSERVACION SUSTENTO']) izquierda.append(ficha('fa-triangle-exclamation', 'Observación anterior', [['Motivo', c['OBSERVACION SUSTENTO']]]));

    // Derecha: foto de ubicación, evidencia por ítem y pago.
    const derecha = el('div', 'cc-validacion-derecha cn-columna-archivos');
    const estado = el('p', 'cc-nota'); estado.setAttribute('role', 'status');
    const ubic = el('section', 'cc-ficha');
    const h3 = el('h4', 'cc-ficha-titulo'); h3.append(icono('fa-image'), el('span', null, 'Foto de la ubicación del sitio')); ubic.append(h3);
    const zonaUbic = el('label', 'cc-validacion-zona cn-op-ubicacion');
    const archivoUbic = Object.assign(el('input'), {type: 'file', accept: 'image/jpeg,image/png,image/webp,image/heic,image/heif', hidden: true, disabled: !editable});
    let fotoUbic = manual.location_picture || '';
    function pintarUbic() {
      zonaUbic.replaceChildren(archivoUbic);
      if (fotoUbic) {
        const img = el('img'); img.src = fotoUbic; img.alt = 'Ubicación del sitio'; zonaUbic.append(img);
        if (editable) {
          const quitar = el('button', 'cn-op-quitar'); quitar.type = 'button'; quitar.title = 'Eliminar foto de ubicación'; quitar.append(icono('fa-xmark'));
          quitar.addEventListener('click', async e => {
            e.preventDefault(); e.stopPropagation();
            if (!await (window.nucleusConfirm ? window.nucleusConfirm('¿Eliminar la foto de ubicación?') : confirm('¿Eliminar la foto?'))) return;
            const x = await fetch('/api/cotizacion/sustento/foto/eliminar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key, wo: entry.wo, url: fotoUbic})});
            const y = await leerJson(x); if (!x.ok || !y.success) { estado.textContent = y.error || 'No se pudo eliminar.'; return; }
            fotoUbic = ''; pintarUbic();
          });
          zonaUbic.append(quitar);
        }
      } else zonaUbic.append(icono('fa-camera'), el('strong', null, editable ? 'Seleccionar foto de ubicación' : 'Sin foto de ubicación'), el('small', null, 'JPG, PNG o WebP · máximo 20 MB'));
    }
    archivoUbic.addEventListener('change', async () => {
      const f = archivoUbic.files[0]; if (!f) return;
      ctx.subiendo++; estado.textContent = 'Guardando foto de ubicación…';
      try {
        const cuerpo = new FormData(); cuerpo.append('key', c.key); cuerpo.append('wo', entry.wo); cuerpo.append('foto', f);
        const x = await fetch('/api/cotizacion/sustento/ubicacion', {method: 'POST', body: cuerpo}); const y = await leerJson(x);
        if (!x.ok || !y.success) throw Error(y.error || 'No se pudo subir la foto.');
        fotoUbic = y.url; pintarUbic(); estado.textContent = 'Foto de ubicación guardada.';
      } catch (e) { estado.textContent = e.message; } finally { ctx.subiendo--; archivoUbic.value = ''; }
    });
    pintarUbic(); ubic.append(zonaUbic);

    const evid = el('section', 'cc-ficha');
    const h4 = el('h4', 'cc-ficha-titulo'); h4.append(icono('fa-list-check'), el('span', null, 'Evidencia de los ítems (' + (j.items || []).length + ')')); evid.append(h4);
    if (!(j.items || []).length) evid.append(el('p', 'cc-nota', 'La cotización no tiene ítems. Agrégalos al generar la cotización.'));
    const fotosItems = manual.item_photos || {}, detalles = manual.item_details || {}, lecturas = [];
    for (const item of (j.items || [])) {
      const caja = el('details', 'cn-op-item'); const previo = detalles[item.key] || {};
      caja.open = !!(fotosItems[item.key] || []).length;
      const cabeza = el('summary'); const cuenta = el('small');
      cabeza.append(el('span', null, 'Ítem ' + item.numero + ' · ' + item.texto), cuenta); caja.append(cabeza);
      const codigo = previo.unique_code || item.unique_code || '8828126757', fila = (j.lpu || []).find(x => x.code === codigo);
      const campos = el('div', 'cn-op-rejilla');
      const sel = el('select'); sel.disabled = !editable;
      (j.lpu || []).forEach(x => sel.add(new Option(x.code, x.code))); if (!(j.lpu || []).some(x => x.code === codigo)) sel.add(new Option(codigo, codigo)); sel.value = codigo;
      campo(campos, 'Código único', sel);
      const v = (k, def) => (previo.unique_code ? previo[k] : undefined) ?? def;
      const unidad = campo(campos, 'Unidad', entrada(v('unit', fila?.unit ?? item.und ?? '')));
      const esp = campo(campos, 'Descripción de la partida (Esp)', Object.assign(el('textarea'), {rows: 2, value: v('description_es', fila?.description_es ?? item.texto ?? ''), disabled: !editable}), 'cn-ancho');
      const eng = campo(campos, 'LPU description (Eng)', Object.assign(el('textarea'), {rows: 2, value: v('description_en', fila?.description_en ?? ''), disabled: !editable}), 'cn-ancho');
      const act = campo(campos, 'Descripción de la actividad', Object.assign(el('textarea'), {rows: 2, value: v('activity', fila?.activity || fila?.description_es || ''), disabled: !editable}), 'cn-ancho');
      const obs = campo(campos, 'Comentario', entrada(previo.remarks === item.texto ? '' : (previo.remarks || '')), 'cn-ancho');
      sel.addEventListener('change', () => { const x = (j.lpu || []).find(y => y.code === sel.value); if (!x) return; unidad.value = x.unit || ''; esp.value = x.description_es || ''; eng.value = x.description_en || ''; act.value = x.activity || x.description_es || ''; });
      caja.append(campos);
      lecturas.push(() => [item.key, {unique_code: sel.value, unit: unidad.value, description_es: esp.value, description_en: eng.value, activity: act.value, remarks: obs.value}]);
      const fases = el('div', 'cn-op-fases'); caja.append(fases);
      const pintarFotos = () => {
        const fotos = fotosItems[item.key] || [];
        cuenta.textContent = fotos.length + ' foto' + (fotos.length === 1 ? '' : 's');
        fases.replaceChildren(...OP_FASES.map(([fase, t]) => {
          const s = el('div', 'cn-op-fase'); s.append(el('span', 'cc-nota', t));
          const tira = el('div', 'cn-op-tira');
          fotos.forEach((f, n) => {
            if ((f.phase || 'before') !== fase) return;
            const fig = el('figure'), a = el('a'), img = el('img'); a.href = f.url; a.target = '_blank'; a.rel = 'noopener'; img.src = f.url; img.loading = 'lazy'; img.alt = t + ' · ítem ' + item.numero; a.append(img); fig.append(a);
            if (editable) {
              const q = el('button', 'cn-op-quitar'); q.type = 'button'; q.title = 'Eliminar foto'; q.append(icono('fa-xmark'));
              q.addEventListener('click', async () => {
                if (!await (window.nucleusConfirm ? window.nucleusConfirm('¿Eliminar esta foto?') : confirm('¿Eliminar esta foto?'))) return;
                const x = await fetch('/api/cotizacion/sustento/foto/eliminar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: c.key, wo: entry.wo, item_key: item.key, url: f.url})});
                const y = await leerJson(x); if (!x.ok || !y.success) { estado.textContent = y.error || 'No se pudo eliminar.'; return; }
                fotosItems[item.key] = y.photos || []; pintarFotos();
              });
              fig.append(q);
            }
            tira.append(fig);
          });
          if (editable) {
            const add = el('label', 'cn-op-agregar'); const inp = Object.assign(el('input'), {type: 'file', accept: 'image/*', multiple: true, hidden: true});
            add.append(icono('fa-plus'), inp);
            inp.addEventListener('change', async () => {
              ctx.subiendo++; estado.textContent = 'Guardando fotos…';
              try {
                for (const f of inp.files) {
                  const cuerpo = new FormData(); cuerpo.append('key', c.key); cuerpo.append('wo', entry.wo); cuerpo.append('item_key', item.key); cuerpo.append('phase', fase); cuerpo.append('foto', f);
                  const x = await fetch('/api/cotizacion/sustento/item-foto', {method: 'POST', body: cuerpo}); const y = await leerJson(x);
                  if (!x.ok || !y.success) throw Error(y.error || 'No se pudo guardar la foto.');
                  fotosItems[item.key] = y.photos;
                }
                estado.textContent = 'Fotos guardadas.';
              } catch (e) { estado.textContent = e.message; } finally { ctx.subiendo--; pintarFotos(); }
            });
            tira.append(add);
          }
          s.append(tira); return s;
        }));
      };
      pintarFotos(); evid.append(caja);
    }
    const pago = ficha('fa-money-bill-wave', 'Pago', [['Interacción', atencion(c)], ['Pagado', c['FECHA PAGO'] && (c['FECHA PAGO'] + ' · ' + nombreDe(c['PAGADO POR']))]]);
    if (c['FOTO PAGO']) { const a = el('a', 'cc-codigo-link', 'Ver foto del pago'); a.href = c['FOTO PAGO']; a.target = '_blank'; a.rel = 'noopener'; pago.append(a); }
    derecha.append(ubic, evid, pago, estado);

    // Guardado: igual que Cotizaciones (solo envía lo cambiado y avisa si otra persona lo modificó).
    const leerManual = () => ({wo: campoWo.value.trim(), ...Object.fromEntries(Object.entries(valores).map(([k, x]) => [k, x.value])), item_details: Object.fromEntries(lecturas.map(f => f()))});
    const leerEvidencia = () => ({_BITACORA_INICIO: bitacora.INICIO.value, _BITACORA_PROCESO: bitacora.PROCESO.value, _BITACORA_CIERRE: bitacora.CIERRE.value,
      'INICIO EJECUCION': deLocal(inicio.value), 'FIN EJECUCION': deLocal(fin.value)});
    const baseManual = leerManual(), vista = leerEvidencia();
    const baseEvidencia = Object.fromEntries(Object.keys(vista).map(k => [k, datos[k] || '']));
    async function guardar(finalizar) {
      if (!editable) return;
      if (ctx.subiendo) throw Error('Espera a que termine la carga de fotos.');
      if ([inicio, fin].some(x => x.validity.badInput)) throw Error('Completa la fecha y la hora de inicio y de fin.');
      const ahora = leerEvidencia(), evidencia = Object.fromEntries(Object.entries(ahora).filter(([k, x]) => x !== vista[k]));
      const x = await fetch(finalizar ? '/api/cotizacion/sustento/guardar' : '/api/cotizacion/sustento/wo', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key: c.key, wo: entry.wo, evidencia, base_evidencia: baseEvidencia, manual: leerManual(), base_manual: baseManual})});
      const y = await leerJson(x);
      if (!x.ok || !y.success) throw Error(y.error || 'No se pudo guardar el sustento.');
      Object.assign(vista, ahora); Object.assign(baseManual, leerManual());
      Object.keys(evidencia).forEach(k => { baseEvidencia[k] = y.wo_data?.[k] || ''; });
      if (y.wo !== undefined) entry.wo = y.wo;
    }
    const error = errorCaja(); derecha.append(error);
    const botones = [];
    if ((j.items || []).length) botones.push(['Generar expediente (Excel)', 'cn-azul', 'fa-file-excel', conErrorEn(error, async () => {
      await guardar(false);
      const x = await fetch('/api/cotizacion/sustento/expediente?' + new URLSearchParams({key: c.key, wo: entry.wo}));
      if (!x.ok) throw Error((await leerJson(x)).error || 'No se pudo generar el expediente.');
      const nombre = (x.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i)?.[1];
      descargar(await x.blob(), nombre ? decodeURIComponent(nombre) : 'Expediente_' + (c['N° COTIZACION'] || c.key) + '.xlsx');
    })]);
    if (editable) botones.push(['Guardar', 'cn-neutro', 'fa-floppy-disk', conErrorEn(error, async () => { await guardar(false); estado.textContent = 'Sustento guardado.'; })],
      ['Enviar a Atendido', 'cn-verde', 'fa-paper-plane', conErrorEn(error, async () => {
        if (!await (window.nucleusConfirm ? window.nucleusConfirm('Se guardará el sustento y la cotización pasará a Atendido.', 'Enviar a Atendido', {okText: 'Enviar', circular: true}) : confirm('¿Enviar a Atendido?'))) return;
        await guardar(true); dialogo.close(); await cargar(); avisar((c['N° COTIZACION'] || c.key) + ' pasó a Atendido.');
      })]);
    ventana('Operaciones · ' + (c['N° COTIZACION'] || c.key) + ' · ' + (CLIENTES[c.familia] || c.CLIENTE || ''), izquierda, derecha, botones);
    $('cc-solicitud-contenido').firstChild.classList.add('cn-operaciones');
    // Un sustento por WO: botones arriba para cambiar de WO (guarda antes de cambiar).
    if (lista.length > 1) {
      const wos = el('nav', 'cn-op-wos');
      lista.forEach((w, n) => {
        const b = el('button', n === i ? 'activo' : '', w.wo || 'Sin WO'); b.type = 'button'; b.disabled = !w.encontrado;
        if (!w.encontrado) b.title = 'WO no registrado en su FLM';
        b.addEventListener('click', async () => { if (n === i) return; try { await guardar(false); operaciones(c, n); } catch (e) { error.textContent = e.message; error.hidden = false; } });
        wos.append(b);
      });
      $('cc-solicitud-contenido').prepend(wos);
    }
  }
  // Solo la carga de fotos del sustento se hace todavía en Cotizaciones.
  const abrirClasico = () => location.assign(clasico);
  function accionesDe(c) {
    const p = tab;
    const lista = [];
    if (!puedeGestionar) return lista;
    if (p === 'registro') lista.push(['Generar cotización', 'cn-verde', 'fa-file-invoice-dollar', () => editorCotizacion(c)],
      ['Anular', 'cn-rojo', 'fa-ban', conMotivo(c, 'cancelar', 'Anular cotización', 'Anular', 'fa-ban')]);
    else if (p === 'cliente') lista.push(['Aprobar (conformidad del cliente)', 'cn-verde', 'fa-check', () => aprobar(c)],
      ['Anular', 'cn-rojo', 'fa-ban', conMotivo(c, 'cancelar', 'Anular cotización', 'Anular', 'fa-ban')]);
    else if (p === 'sustentar') lista.push(['Ficha de sustento y pasar a Atendido', 'cn-azul', 'fa-screwdriver-wrench', () => operaciones(c)]);
    else if (p === 'atendido') lista.push(['Revisar sustento', 'cn-verde', 'fa-magnifying-glass', () => sustento(c)]);
    else if (p === 'cajachica') {
      lista.push(['Registrar pago', 'cn-verde', 'fa-money-bill-wave', () => pagar(c)]);
    } else if (p === 'proveedor') {
      lista.push(['Factura y OC del proveedor', 'cn-morado', 'fa-file-arrow-up', () => proveedor(c)]);
      lista.push(['Derivar a Caja chica', 'cn-naranja', 'fa-wallet', () => moverA(c, 'proveedor', 'cajachica', 'Caja chica')]);
    } else if (p === 'transito') lista.push(['Pasar a Proveedor (se encontró proveedor)', 'cn-morado', 'fa-file-invoice', () => transitoAProveedor(c)]);
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
  // Detalle (izquierda) e ítems (derecha): los usan la vista de detalle y la de aprobar.
  function fichasDetalle(c) {
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(
      ficha('fa-file-lines', 'Detalle de la cotización', [['Fecha', fechaTexto(c.FECHA)], ['Nombre de cliente', c['NOMBRE CLIENTE']], ['Site', c['NOMBRE SITE']], ['N.º WO', c['NUMERO WO']],
        ['Motivo', c.MOTIVO], ['Objetivo', c.OBJETIVO !== c.MOTIVO ? c.OBJETIVO : ''], ['Supervisor', c.SUPERVISOR],
        ['Departamento', c.DEPARTAMENTO], ['Tipo de gasto', c['TIPO DE GASTO']], ['Tipo', c['TIPO DE COTIZACION']], ['Código interno', c['CODIGO INTERNO']]]),
      ficha('fa-users', 'Responsables', [['Solicitante', nombreDe(c['SOLICITADO POR'])], ['Gestor', nombreDe(c.GESTOR)], ['Cotizador asignado', nombreDe(c.COTIZADOR)], ['Cotizado por', nombreDe(c['COTIZADO POR'])],
        ['Fecha cotizado', c['FECHA COTIZADO']], ['Enviado al cliente', c['FECHA ENVIO CLIENTE']], ['Aprobado', c['FECHA APROBACION']]]));
    const estado = [['Estado', c['ESTADO COTIZACION'] || 'Pdt. Cotización'], ['Rechazo', c['MOTIVO RECHAZO'] && (c['MOTIVO RECHAZO'] + ' · ' + (c['FECHA RECHAZO'] || ''))],
      ['Anulación', c['MOTIVO CANCELACION'] && (c['MOTIVO CANCELACION'] + ' · ' + (c['FECHA CANCELACION'] || ''))],
      ['Comentario', c['COMENTARIO APROBACION']], ['Interacción', atencion(c)],
      ['Estado de pago', c.estado_pago], ['Estado operativo', c.estado_operativo],
      ['Pago', c['FECHA PAGO'] ? c['FECHA PAGO'] + ' · ' + nombreDe(c['PAGADO POR']) : (c._PAGO_PENDIENTE ? 'Por pagar' : '')],
      ['Monto a depositar (Tránsito)', c['MONTO TRANSITO'] && dinero(c['MONTO TRANSITO'])], ['Monto pagado', c['MONTO PAGADO'] && c['FECHA PAGO'] && dinero(c['MONTO PAGADO'])],
      ['Provisión (20 %)', c.PROVISION && dinero(c.PROVISION)], ['Proveedor', c['NOMBRE DE PROVEEDOR']],
      ['Factura', c['NUMERO FACTURA PROVEEDOR']], ['OC', c['NUMERO OC PROVEEDOR']],
      ['Tránsito', c.transito && ('Enviada ' + (c.transito.fecha || '') + ' · ' + (c.transito.usuario || ''))]];
    izquierda.append(ficha('fa-flag', 'Estado', estado));
    return izquierda;
  }
  function fichaItems(c) {
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
    return items;
  }
  function verDetalle(c) {
    $('cc-solicitud-titulo').textContent = [c['N° COTIZACION'] || c.key, CLIENTES[c.familia] || c.CLIENTE].filter(Boolean).join(' · ');
    const acciones = $('cn-dialogo-acciones');
    acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    acciones.prepend(...accionesDe(c).map(a => botonRedondo(a, 'cn-grande')));
    const izquierda = fichasDetalle(c), derecha = el('div', 'cc-validacion-derecha'); derecha.append(fichaItems(c));
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
    // Lo marcado que ya no se ve (otra pestaña, filtro o búsqueda) se desmarca.
    const clavesVisibles = new Set(visibles.map(c => c.key));
    for (const k of seleccionadas) if (!clavesVisibles.has(k)) seleccionadas.delete(k);
    if (botonEliminar) botonEliminar.disabled = eliminando || !seleccionadas.size;
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
      if (puedeEliminar) {
        const celda = el('span', 'cc-seleccion');
        const check = Object.assign(el('input'), {type: 'checkbox', checked: seleccionadas.has(c.key)});
        check.setAttribute('aria-label', 'Seleccionar ' + (c['N° COTIZACION'] || c.key));
        check.addEventListener('change', () => { if (check.checked) seleccionadas.add(c.key); else seleccionadas.delete(c.key); pintar(); });
        celda.append(check);
        fila.append(celda);
      }
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

  botonEliminar?.addEventListener('click', async () => {
    const keys = [...seleccionadas];
    if (!keys.length || eliminando) return;
    const texto = keys.length === 1 ? '¿Eliminar la cotización seleccionada?' : '¿Eliminar las ' + keys.length + ' cotizaciones seleccionadas?';
    if (!await (window.nucleusConfirm ? window.nucleusConfirm(texto) : confirm(texto))) return;
    eliminando = true; botonEliminar.disabled = true;
    try {
      const r = await fetch('/api/cot-new/eliminar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({keys})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error) throw Error(j.error || 'No se pudieron eliminar las cotizaciones.');
      const borradas = new Set(keys);
      cotizaciones = cotizaciones.filter(c => !borradas.has(c.key));
      seleccionadas.clear();
    } catch (e) { avisar(e.message); } finally { eliminando = false; pintar(); }
  });

  async function cargar() {
    const r = await fetch('/api/cot-new/lista'); const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('cn-lista').replaceChildren(el('p', 'cc-alerta', j.error || 'No se pudieron cargar las cotizaciones.')); return; }
    cotizaciones = j.cotizaciones; usuarios = j.usuarios || {}; pintar();
  }
  pintarEncabezado();
  cargar();
})();
