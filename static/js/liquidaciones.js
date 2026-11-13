/* Liquidaciones · todas las evidencias de cada caso (Cotizaciones y Caja Chica), ordenadas y descargables. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const icono = nombre => { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const plata = v => { const n = Number(v || 0); return n >= 1e6 ? 'S/ ' + (n / 1e6).toFixed(2) + ' M' : n >= 1e3 ? 'S/ ' + Math.round(n / 1e3).toLocaleString('es-PE') + ' mil' : dinero(n); };
  const avisar = m => (window.nucleusAlert || alert)(m);
  const plano = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const fecha = t => { const s = String(t || ''); return s ? s.replace('T', ' ').slice(0, 16) : '—'; };
  const dialogo = $('cc-solicitud-dialogo');
  const CLIENTES = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};

  let tab = 'cotizaciones', chip = '', orden = null;
  try { tab = localStorage.getItem('lq-tab') || tab; } catch (_) {}
  const datos = {cotizaciones: null, cajachica: null};
  const seleccion = {cotizaciones: new Set(), cajachica: new Set()};

  // ── Evidencias: chip verde (está), rojo (falta) o gris (no aplica) ──
  const ESTADO_EVID = {Completo: 'ok', Pendiente: 'falta', 'No aplica': 'na'};
  function chipEvid(texto, estado, accion, titulo) {
    // <span role="button">: el decorador de botones del sitio no le cambia el color.
    const b = el('span', 'lq-evid lq-evid-' + (ESTADO_EVID[estado] || estado || 'na') + (accion ? ' lq-evid-accion' : ''));
    if (accion) {
      b.setAttribute('role', 'button'); b.tabIndex = 0;
      b.addEventListener('click', e => { e.stopPropagation(); accion(); });
      b.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); accion(); } });
    }
    b.title = titulo || texto; b.append(el('span', null, texto)); return b;
  }
  const abrir = url => window.open(url, '_blank', 'noopener');
  function enlace(texto, url, simbolo = 'fa-download') {
    const a = el('a', 'lq-descarga'); a.href = url; a.target = '_blank'; a.rel = 'noopener';
    a.append(icono(simbolo), el('span', null, texto)); return a;
  }

  // ── Columnas por pestaña ──
  const COL = {
    cotizaciones: [
      {id: 'numero', titulo: 'N.º / cliente', ancho: 'minmax(170px, 1.1fr)', texto: c => c.cotizacion + ' ' + c.correlativo + ' ' + (CLIENTES[c.cliente] || c.cliente),
       celda: c => { const s = el('span', 'lq-dos'); const a = el('a', 'cc-codigo-link', c.cotizacion); a.href = '#'; a.addEventListener('click', e => { e.preventDefault(); verCotizacion(c); });
         s.append(a, el('small', null, c.correlativo + ' · ' + (CLIENTES[c.cliente] || c.cliente || '—'))); return s; }},
      {id: 'site', titulo: 'Site / WO', ancho: 'minmax(170px, 1.1fr)', texto: c => c.site + ' ' + c.wo,
       celda: c => { const s = el('span', 'lq-dos'); s.append(el('span', null, c.site || '—'), el('small', null, c.wo || 'Sin WO')); return s; }},
      {id: 'estado', titulo: 'Estado', ancho: 'minmax(150px, 1fr)', texto: c => c.pestana + ' ' + c.estado_pago,
       celda: c => { const s = el('span', 'lq-dos'); s.append(el('span', 'cc-chip lq-p-' + c.pestana_clave, c.pestana), el('small', null, c.estado_pago || c.interaccion || '—')); return s; }},
      {id: 'ejecucion', titulo: 'Ejecución', ancho: 'minmax(130px, .8fr)', texto: c => c.estado_operativo || c.estatus || '—',
       celda: c => el('span', 'cc-chip lq-o', c.estado_operativo || c.estatus || '—')},
      {id: 'evidencias', titulo: 'Evidencias', ancho: 'minmax(300px, 2fr)', texto: c => Object.entries(c.evidencias).map(([k, v]) => k + ':' + v).join(' '),
       celda: c => {
         const s = el('span', 'lq-evids'), e = c.evidencias;
         s.append(chipEvid('PDF', e.cotizacion, c.generada ? () => abrir('/liquidaciones/api/registros/' + c.id + '/pdf') : null, 'Cotización generada'),
           chipEvid('Correo', e.correo, c.correo_cliente ? () => abrir(c.correo_cliente) : null, 'Correo de aprobación del cliente'),
           chipEvid('Depósito' + (c.fotos_deposito.length > 1 ? ' ' + c.fotos_deposito.length : ''), e.deposito, c.fotos_deposito.length ? () => verCotizacion(c) : null, 'Capturas de depósito'),
           chipEvid('Factura', e.factura, c.facturas.length ? () => verCotizacion(c) : null, 'Facturas y OC del proveedor'),
           chipEvid('Fotos', e.sustento, c.tiene_sustento ? () => verCotizacion(c, true) : null, 'Fotos del sustento'));
         return s;
       }},
      {id: 'avance', titulo: 'Avance', ancho: 'minmax(90px, .6fr)', num: true, texto: c => c.avance + ' %', orden: c => c.avance,
       celda: c => { const s = el('span', 'lq-avance'); const b = el('span', 'lq-avance-barra'); const f = el('span'); f.style.width = c.avance + '%'; f.dataset.nivel = c.avance >= 100 ? 'ok' : c.avance >= 50 ? 'medio' : 'bajo'; b.append(f); s.append(b, el('small', null, c.avance + ' %')); return s; }},
      {id: 'liquidacion', titulo: 'Liquidación', ancho: 'minmax(120px, .8fr)', texto: c => c.seguimiento.estado_liquidacion || 'Pendiente'},
      {id: 'monto', titulo: 'Sub total + FEE', ancho: 'minmax(120px, .8fr)', num: true, texto: c => dinero(c.monto), orden: c => Number(c.monto) || 0,
       celda: c => el('strong', 'cc-num', dinero(c.monto))},
    ],
    cajachica: [
      {id: 'codigo', titulo: 'Código / técnico', ancho: 'minmax(190px, 1.2fr)', texto: c => c.codigo + ' ' + c.tecnico + ' ' + c.documento,
       celda: c => { const s = el('span', 'lq-dos'); const a = el('a', 'cc-codigo-link', c.codigo); a.href = '#'; a.addEventListener('click', e => { e.preventDefault(); verCajaChica(c); });
         s.append(a, el('small', null, c.tecnico + ' · ' + c.proyecto)); return s; }},
      {id: 'cotizacion', titulo: 'Cotización', ancho: 'minmax(150px, .9fr)', texto: c => c.cotizacion || '—'},
      {id: 'site', titulo: 'Site / CM', ancho: 'minmax(170px, 1fr)', texto: c => c.site + ' ' + c.wo,
       celda: c => { const s = el('span', 'lq-dos'); s.append(el('span', null, c.site || '—'), el('small', null, c.wo || '—')); return s; }},
      {id: 'estado', titulo: 'Estado', ancho: 'minmax(130px, .8fr)', texto: c => c.estado, celda: c => el('span', 'cc-chip lq-s-' + c.estado_clave.toLowerCase(), c.estado)},
      {id: 'tipos', titulo: 'Tipo', ancho: 'minmax(120px, .7fr)', texto: c => c.tipos.join(' · '),
       celda: c => { const s = el('span', 'lq-evids'); c.tipos.forEach(t => s.append(el('span', 'cc-chip ' + (t === 'Refacturable' ? 'cc-refacturable' : 'cc-gasto-cobra'), t))); return s; }},
      {id: 'montos', titulo: 'Depositado · gastado · devuelto', ancho: 'minmax(210px, 1.2fr)', num: true, texto: c => dinero(c.depositado) + ' ' + dinero(c.gastado), orden: c => Number(c.depositado) || 0,
       celda: c => { const s = el('span', 'lq-dos lq-num'); s.append(el('strong', null, c.depositado ? dinero(c.depositado) : 'Sin depósito'), el('small', null, 'Gastó ' + dinero(c.gastado) + ' · devolvió ' + dinero(c.devuelto))); return s; }},
      {id: 'evidencias', titulo: 'Evidencias', ancho: 'minmax(330px, 2fr)', texto: c => '',
       celda: c => {
         const s = el('span', 'lq-evids'), deposito = !!c.depositado;
         s.append(chipEvid('Depósito', c.deposito ? 'Completo' : deposito ? 'Pendiente' : 'No aplica', c.deposito ? () => abrir(c.deposito.url) : null),
           chipEvid('Boletas ' + c.boletas.length, c.boletas.length ? 'Completo' : deposito ? 'Pendiente' : 'No aplica', c.boletas.length ? () => verCajaChica(c) : null),
           chipEvid('Evidencias ' + c.evidencias.length, c.evidencias.length ? 'Completo' : deposito ? 'Pendiente' : 'No aplica', c.evidencias.length ? () => verCajaChica(c) : null),
           chipEvid('Devolución', c.devolucion ? 'Completo' : Number(c.devuelto) > 0 || c.estado_clave === 'POR_DEVOLVER' ? 'Pendiente' : 'No aplica', c.devolucion ? () => abrir(c.devolucion.url) : null),
           chipEvid('Correo', c.correo ? 'Completo' : 'No aplica', c.correo ? () => abrir(c.correo.url) : null, 'Correo de validación'));
         return s;
       }},
    ],
  };

  // ── Filtros rápidos (chips) ──
  const CHIPS = {
    cotizaciones: [['', 'Todas'], ['p:cliente', 'Cliente'], ['p:cajachica', 'Caja chica'], ['p:sustentar', 'Operaciones'], ['p:atendido', 'Atendido'],
      ['incompleto', 'Expediente incompleto'], ['listo', 'Listo para liquidar']],
    cajachica: [['', 'Todas'], ['s:VALIDADO', 'Por depositar'], ['s:DEPOSITADO', 'Depositada'], ['s:POR_DEVOLVER', 'Por devolver'], ['s:SUSTENTO', 'Sustentada'], ['s:ARCHIVADO', 'Archivada'],
      ['sinfoto', 'Sin foto de depósito'], ['completo', 'Expediente completo']],
  };
  function pasaChip(c) {
    if (!chip) return true;
    if (tab === 'cotizaciones') {
      if (chip.startsWith('p:')) return c.pestana_clave === chip.slice(2);
      return chip === 'listo' ? c.avance >= 100 : c.avance < 100;
    }
    if (chip.startsWith('s:')) return c.estado_clave === chip.slice(2);
    if (chip === 'sinfoto') return !!c.depositado && !c.deposito;
    return !!c.deposito && c.boletas.length > 0 && c.evidencias.length > 0 && (!(Number(c.devuelto) > 0) || !!c.devolucion);
  }
  const lista = () => datos[tab] || [];
  function visibles() {
    const q = plano($('cc-buscar').value.trim());
    let filas = lista().filter(c => pasaChip(c) && (!q || plano(COL[tab].map(col => col.texto(c)).join(' ')).includes(q)));
    if (orden) {
      const col = COL[tab].find(x => x.id === orden.col), v = col.orden || col.texto;
      filas = [...filas].sort((a, b) => { const x = v(a), y = v(b); return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'es')) * orden.dir; });
    }
    return filas;
  }
  const montoDe = c => Number(tab === 'cotizaciones' ? c.monto : c.depositado) || 0;

  function pintar() {
    document.querySelectorAll('.lq-tab').forEach(b => { b.classList.toggle('activa', b.dataset.tab === tab); b.setAttribute('aria-selected', String(b.dataset.tab === tab)); });
    for (const t of ['cotizaciones', 'cajachica']) {
      const filas = datos[t] || [];
      document.querySelector('[data-cuenta="' + t + '"]').textContent = datos[t] ? filas.length : '…';
      const suma = filas.reduce((s, c) => s + (Number(t === 'cotizaciones' ? c.monto : c.depositado) || 0), 0);
      const p = document.querySelector('[data-plata="' + t + '"]'); p.textContent = plata(suma); p.title = 'Total: ' + dinero(suma);
    }
    const chips = $('lq-chips'); chips.replaceChildren();
    for (const [clave, texto] of CHIPS[tab]) {
      const b = el('button', 'lq-chip' + (chip === clave ? ' activo' : '')); b.type = 'button';
      const n = clave ? lista().filter(c => { const g = chip; chip = clave; const r = pasaChip(c); chip = g; return r; }).length : lista().length;
      b.append(el('span', null, texto), el('strong', null, String(n)));
      b.addEventListener('click', () => { chip = chip === clave ? '' : clave; pintar(); });
      chips.append(b);
    }
    // Encabezado
    const cols = COL[tab];
    $('lq-tabla').style.setProperty('--cc-cols', ['40px', '86px', ...cols.map(c => c.ancho)].join(' '));
    $('lq-tabla').style.setProperty('--cc-min', (cols.reduce((s, c) => s + parseInt(c.ancho.slice(7), 10), 0) + 140 + 12 * cols.length) + 'px');
    const cab = $('lq-encabezado'); cab.replaceChildren();
    const filas = visibles();
    const todas = Object.assign(el('input'), {type: 'checkbox', title: 'Seleccionar todo lo visible'});
    todas.checked = filas.length > 0 && filas.every(c => seleccion[tab].has(c.id));
    todas.addEventListener('change', () => { filas.forEach(c => todas.checked ? seleccion[tab].add(c.id) : seleccion[tab].delete(c.id)); pintar(); });
    const celdaTodas = el('div', 'cc-th cc-th-nombre cc-acciones-cab cc-seleccion'); celdaTodas.append(todas);
    cab.append(celdaTodas, el('div', 'cc-th cc-th-nombre cc-acciones-cab cc-col-acciones', 'Acciones'));
    for (const col of cols) {
      const th = el('div', 'cc-th' + (col.num ? ' cc-th-num' : '')), fila = el('div', 'cc-th-fila');
      const sentido = orden?.col === col.id ? orden.dir : 0;
      const b = el('button', 'cc-th-btn' + (sentido ? ' activo' : '')); b.type = 'button'; b.title = 'Ordenar';
      b.append(icono(sentido === 1 ? 'fa-arrow-up-short-wide' : sentido === -1 ? 'fa-arrow-down-wide-short' : 'fa-sort'));
      b.addEventListener('click', () => { orden = sentido === 1 ? {col: col.id, dir: -1} : sentido === -1 ? null : {col: col.id, dir: 1}; pintar(); });
      fila.append(el('span', 'cc-th-nombre', col.titulo), b); th.append(fila); cab.append(th);
    }
    // Filas
    const cuerpo = $('lq-lista'); cuerpo.replaceChildren();
    for (const id of [...seleccion[tab]]) if (!filas.some(c => c.id === id)) seleccion[tab].delete(id);
    $('lq-zip').hidden = !seleccion[tab].size;
    $('lq-zip').title = 'Descargar ' + seleccion[tab].size + ' expediente(s) en un ZIP';
    if (!datos[tab]) { cuerpo.append(el('p', 'cc-vacio', 'Cargando…')); return; }
    if (!filas.length) { cuerpo.append(el('p', 'cc-vacio', 'No hay casos con estos filtros.')); return; }
    for (const c of filas.slice(0, 600)) {
      const fila = el('div', 'cc-card cc-resumen cc-fila-solicitud');
      const sel = el('span', 'cc-seleccion'), check = Object.assign(el('input'), {type: 'checkbox', checked: seleccion[tab].has(c.id)});
      check.setAttribute('aria-label', 'Seleccionar ' + (c.cotizacion || c.codigo));
      check.addEventListener('change', () => { check.checked ? seleccion[tab].add(c.id) : seleccion[tab].delete(c.id); pintar(); });
      sel.append(check);
      const acciones = el('span', 'cc-acciones-rapidas cc-col-acciones');
      acciones.append(redondo('Ver evidencias', 'cn-azul', 'fa-eye', () => tab === 'cotizaciones' ? verCotizacion(c) : verCajaChica(c)),
        redondo('Descargar expediente (ZIP)', 'cn-morado', 'fa-file-zipper', () => descargarZip([c.id])));
      fila.append(sel, acciones, ...COL[tab].map(col => col.celda ? col.celda(c) : el('span', null, col.texto(c))));
      cuerpo.append(fila);
    }
    if (filas.length > 600) cuerpo.append(el('p', 'cc-vacio', 'Se muestran 600 de ' + filas.length + '. Usa la búsqueda o los filtros para ver el resto.'));
  }
  function redondo(titulo, clase, simbolo, fn, grande) {
    const b = el('button', (grande ? 'cc-dialogo-icono cn-redondo cn-grande ' : 'cc-rapida cn-redondo ') + clase); b.type = 'button';
    b.title = titulo; b.setAttribute('aria-label', titulo); b.append(icono(simbolo));
    b.addEventListener('click', async e => { e.stopPropagation(); b.disabled = true; try { await fn(); } finally { b.disabled = false; } });
    return b;
  }

  // ── Descargas ──
  async function descargarZip(ids) {
    const url = tab === 'cotizaciones' ? '/liquidaciones/api/registros/expedientes' : '/liquidaciones/api/v2/caja-chica/expedientes';
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ids})});
    if (!r.ok) { avisar((await r.json().catch(() => ({}))).error || 'No se pudo preparar el expediente.'); return; }
    const nombre = decodeURIComponent((r.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i)?.[1] || 'Expedientes.zip');
    const a = el('a'); a.href = URL.createObjectURL(await r.blob()); a.download = nombre; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  $('lq-zip').addEventListener('click', () => descargarZip([...seleccion[tab]]));
  $('lq-excel').addEventListener('click', () => {
    if (typeof XLSX === 'undefined') { avisar('Librería de exportación no disponible.'); return; }
    const filas = visibles().map(c => tab === 'cotizaciones' ? {
      'Correlativo': c.correlativo, 'N.º cotización': c.cotizacion, 'Cliente': CLIENTES[c.cliente] || c.cliente, 'Site': c.site, 'N.º WO': c.wo,
      'Objetivo': c.objetivo, 'Estado': c.pestana, 'Interacción': c.interaccion, 'Estado de pago': c.estado_pago, 'Estado operativo': c.estado_operativo,
      'Cotizada': c.fechas.cotizada, 'Aprobada': c.fechas.aprobada, 'Pagada': c.fechas.pagada, 'Facturas proveedor': c.fechas.facturas,
      'PDF cotización': c.evidencias.cotizacion, 'Correo cliente': c.evidencias.correo, 'Captura depósito': c.evidencias.deposito,
      'Factura proveedor': c.evidencias.factura, 'Fotos sustento': c.evidencias.sustento, 'Depósitos Caja Chica': c.depositos_cc.map(d => d.codigo).join(', '),
      'Avance %': c.avance, 'AJB / EJB': c.seguimiento.codigo_ajb_ejb, 'N.º Expense': c.seguimiento.numero_expense,
      'Estado de liquidación': c.seguimiento.estado_liquidacion || 'Pendiente', 'Mes de cierre': c.seguimiento.mes_cierre, 'N.º PO': c.seguimiento.numero_po,
      'Observación': c.seguimiento.observacion, 'Sub total + FEE': Number(c.monto) || 0,
    } : {
      'Código': c.codigo, 'Técnico': c.tecnico, 'DNI': c.documento, 'Proyecto': c.proyecto, 'Cotización': c.cotizacion, 'Site': c.site, 'CM/PM/PLM': c.wo,
      'Tipo': c.tipos.join(' · '), 'Estado': c.estado, 'Depositado el': fecha(c.depositado_en), 'Solicitado': Number(c.total) || 0,
      'Depositado': Number(c.depositado) || 0, 'Gastado': Number(c.gastado) || 0, 'Devuelto': Number(c.devuelto) || 0,
      'Foto depósito': c.deposito ? 'Sí' : 'No', 'Boletas': c.boletas.length, 'Evidencias': c.evidencias.length,
      'Captura devolución': c.devolucion ? 'Sí' : 'No', 'Correo validación': c.correo ? 'Sí' : 'No',
    });
    const libro = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filas), tab === 'cotizaciones' ? 'Cotizaciones' : 'Caja Chica');
    XLSX.writeFile(libro, 'Liquidaciones_' + (tab === 'cotizaciones' ? 'Cotizaciones' : 'CajaChica') + '.xlsx');
  });

  // ── Ventanas de detalle ──
  function ficha(simbolo, titulo, filas) {
    const caja = el('section', 'cc-ficha'), h = el('h4', 'cc-ficha-titulo'); h.append(icono(simbolo), el('span', null, titulo)); caja.append(h);
    const dl = el('dl', 'cc-ficha-datos');
    for (const [k, v] of filas) { if (!v && v !== 0) continue; const f = el('div', 'cc-ficha-fila'); f.append(el('dt', null, k), el('dd', null, String(v))); dl.append(f); }
    caja.append(dl); return caja;
  }
  function grupoEvid(simbolo, titulo, estado, contenido) {
    const g = el('section', 'lq-grupo lq-grupo-' + (ESTADO_EVID[estado] || 'na'));
    const h = el('h5', 'lq-grupo-titulo'); h.append(icono(simbolo), el('span', null, titulo), el('small', null, estado === 'Completo' ? '✓ Completo' : estado || 'No aplica'));
    g.append(h); if (contenido) g.append(contenido); return g;
  }
  function galeria(fotos) {
    const tira = el('div', 'lq-galeria');
    for (const f of fotos) {
      const a = el('a', 'lq-foto'); a.href = f.url; a.target = '_blank'; a.rel = 'noopener'; a.title = f.titulo;
      const img = el('img'); img.src = f.url; img.alt = f.titulo; img.loading = 'lazy';
      img.addEventListener('error', () => img.replaceWith(el('span', 'lq-foto-archivo', '📄')));
      a.append(img, el('small', null, f.titulo)); tira.append(a);
    }
    return tira;
  }
  function ventana(titulo, izquierda, derecha, botones) {
    $('cc-solicitud-titulo').textContent = titulo;
    const acciones = $('lq-dialogo-acciones'); acciones.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    acciones.prepend(...botones.map(b => redondo(...b, true)));
    const cols = el('div', 'cc-validacion-columnas'); cols.append(izquierda, derecha);
    $('cc-solicitud-contenido').replaceChildren(cols);
    if (!dialogo.open) dialogo.showModal();
  }

  async function verCotizacion(c, enfocarFotos) {
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(ficha('fa-file-lines', 'Detalle', [['N.º', c.cotizacion + ' · ' + c.correlativo], ['Cliente', CLIENTES[c.cliente] || c.cliente], ['Site', c.site], ['N.º WO', c.wo],
      ['Objetivo', c.objetivo], ['Supervisor', c.supervisor], ['Sub total + FEE', dinero(c.monto)], ['Estado', c.pestana], ['Interacción', c.interaccion],
      ['Estado de pago', c.estado_pago], ['Ejecución', c.estado_operativo || c.estatus]]));
    // Línea de tiempo del caso.
    const linea = el('section', 'cc-ficha'); const hl = el('h4', 'cc-ficha-titulo'); hl.append(icono('fa-timeline'), el('span', null, 'Línea de tiempo')); linea.append(hl);
    const pasos = el('ol', 'lq-linea');
    for (const [k, t] of [['cotizada', 'Cotizada'], ['enviada', 'Enviada al cliente'], ['aprobada', 'Aprobada'], ['pagada', 'Pagada'], ['facturas', 'Facturas del proveedor'], ['atendida', 'Atendida']]) {
      if (k === 'facturas' && !c.fechas.facturas && c.interaccion !== 'Proveedor') continue;
      const li = el('li', c.fechas[k] ? 'hecho' : ''); li.append(el('strong', null, t), el('small', null, fecha(c.fechas[k]))); pasos.append(li);
    }
    linea.append(pasos); izquierda.append(linea);
    // Seguimiento de liquidación (lo que se llena a mano).
    const form = el('form', 'cc-ficha lq-seguimiento'); form.noValidate = true;
    const hf = el('h4', 'cc-ficha-titulo'); hf.append(icono('fa-pen-to-square'), el('span', null, 'Seguimiento de liquidación')); form.append(hf);
    const rejilla = el('div', 'cn-op-rejilla'); form.append(rejilla);
    const campo = (nombre, titulo, control, ancho) => { const l = el('label', 'cc-pendiente-campo' + (ancho ? ' cn-ancho' : '')); l.append(el('span', null, titulo), control); control.name = nombre; control.value = c.seguimiento[nombre] || ''; rejilla.append(l); return control; };
    campo('codigo_ajb_ejb', 'Código AJB / EJB', Object.assign(el('input'), {maxLength: 200}));
    campo('numero_expense', 'N.º Expense', Object.assign(el('input'), {maxLength: 200}));
    const est = el('select'); ['Pendiente', 'En borrador', 'En revisión', 'Observado', 'Rechazado', 'Aprobado', 'Con PO'].forEach(o => est.add(new Option(o, o)));
    campo('estado_liquidacion', 'Estado de liquidación', est); if (!est.value) est.value = 'Pendiente';
    campo('mes_cierre', 'Mes de cierre', Object.assign(el('input'), {type: 'month'}));
    campo('numero_po', 'N.º PO', Object.assign(el('input'), {maxLength: 200}));
    campo('observacion', 'Observación', Object.assign(el('textarea'), {rows: 3, maxLength: 4000}), true);
    const error = el('p', 'cc-alerta'); error.hidden = true; form.append(error);
    izquierda.append(form);

    // Derecha: todas las evidencias, cada una descargable.
    const derecha = el('div', 'cc-validacion-derecha lq-evidencias');
    const e = c.evidencias;
    derecha.append(grupoEvid('fa-file-pdf', 'Cotización generada', e.cotizacion, c.generada ? enlace('Descargar PDF', '/liquidaciones/api/registros/' + c.id + '/pdf') : null));
    derecha.append(grupoEvid('fa-envelope', 'Correo de aprobación del cliente', e.correo, c.correo_cliente ? enlace(c.nombre_correo || 'Descargar correo', c.correo_cliente) : null));
    const deps = el('div');
    if (c.fotos_deposito.length) deps.append(galeria(c.fotos_deposito));
    if (c.depositos_cc.length) {
      const t = el('table', 'cn-depositos-tabla'); const cab = el('tr'); ['Código', 'Técnico', 'Estado', 'Monto'].forEach(x => cab.append(el('th', null, x))); t.append(cab);
      c.depositos_cc.forEach(d => { const f = el('tr'); const a = el('a', 'cc-codigo-link', d.codigo); a.href = '/caja-chica/#solicitud-' + d.id; a.target = '_blank'; const td = el('td'); td.append(a);
        f.append(td, el('td', null, d.tecnico), el('td', null, d.estado), el('td', 'cc-num', dinero(d.monto))); t.append(f); });
      deps.append(t);
    }
    derecha.append(grupoEvid('fa-money-bill-transfer', 'Capturas de depósito', e.deposito, deps.children.length ? deps : null));
    const fact = el('div', 'lq-lista-descargas');
    c.facturas.forEach((u, n) => fact.append(enlace('Factura ' + (n + 1), u)));
    c.ocs.forEach((u, n) => fact.append(enlace('OC ' + (n + 1), u)));
    derecha.append(grupoEvid('fa-file-invoice', 'Facturas y OC del proveedor', e.factura, fact.children.length ? fact : null));
    const fotos = el('div', 'lq-sustento'); fotos.append(el('p', 'cc-nota', c.tiene_sustento ? 'Cargando fotos…' : 'Sin fotos de sustento.'));
    const grupoFotos = grupoEvid('fa-camera', 'Fotos del sustento (antes / durante / después)', e.sustento, fotos);
    derecha.append(grupoFotos);
    derecha.append(grupoEvid('fa-file-zipper', 'Expediente completo', 'Completo', enlace('Descargar expediente (ZIP)', '/liquidaciones/api/registros/' + c.id + '/expediente', 'fa-file-zipper')));

    ventana('Liquidación · ' + c.cotizacion + ' · ' + (CLIENTES[c.cliente] || c.cliente || ''), izquierda, derecha, [
      ['Descargar expediente (ZIP)', 'cn-morado', 'fa-file-zipper', () => descargarZip([c.id])],
      ['Guardar seguimiento', 'cn-verde', 'fa-floppy-disk', async () => {
        error.hidden = true;
        const cambios = Object.fromEntries([...form.elements].filter(x => x.name).map(x => [x.name, x.value.trim()]));
        const r = await fetch('/liquidaciones/api/registros/' + c.id + '?resumen=1', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cambios)});
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { error.textContent = j.error || 'No se pudo guardar.'; error.hidden = false; return; }
        Object.assign(c.seguimiento, cambios); pintar(); avisar('Seguimiento guardado: ' + c.cotizacion + '.');
      }],
    ]);
    if (c.tiene_sustento) {
      const r = await fetch('/liquidaciones/api/registros/' + c.id + '/sustento'); const j = await r.json().catch(() => ({}));
      const reg = j.registro || {}; fotos.replaceChildren();
      for (const [fase, t] of [['inicio', 'Antes'], ['proceso', 'Durante'], ['cierre', 'Después']]) {
        const lista = (reg.fotos || {})[fase] || [];
        if (!lista.length) continue;
        fotos.append(el('strong', 'lq-fase', t + ' (' + lista.length + ')'), galeria(lista.map((u, n) => ({url: u, titulo: t + ' ' + (n + 1)}))));
      }
      if (!fotos.children.length) fotos.append(el('p', 'cc-nota', 'Sin fotos de sustento.'));
      if (enfocarFotos) grupoFotos.scrollIntoView({block: 'start'});
    }
  }

  function verCajaChica(c) {
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(ficha('fa-file-lines', 'Detalle de la solicitud', [['Código', c.codigo], ['Técnico', c.tecnico + ' · ' + c.documento], ['Proyecto', c.proyecto],
      ['Cotización', c.cotizacion], ['Site', c.site], ['CM / PM / PLM', c.wo], ['Justificación', c.motivo], ['Estado', c.estado],
      ['Solicitado el', fecha(c.creado)], ['Depositado el', fecha(c.depositado_en)], ['Comentario del depósito', c.comentario_deposito]]));
    const totales = el('div', 'cc-rev-totales lq-totales');
    for (const [t, v, cls] of [['Solicitado', c.total], ['Depositado', c.depositado], ['Gastado', c.gastado, 'ok'], ['Devuelto', c.devuelto, 'dev'], ['Por rendir', c.por_rendir, 'rev']]) {
      const d = el('div', cls ? 'cc-rev-' + cls : null); d.append(el('small', null, t), el('strong', null, dinero(v))); totales.append(d);
    }
    izquierda.append(totales);
    const conceptos = el('section', 'cc-ficha'); const hc = el('h4', 'cc-ficha-titulo'); hc.append(icono('fa-list-check'), el('span', null, 'Conceptos')); conceptos.append(hc);
    const t = el('table', 'cn-depositos-tabla'); const cab = el('tr'); ['Concepto', 'Tipo', 'Solicitado', 'Gastó', 'Estado'].forEach(x => cab.append(el('th', null, x))); t.append(cab);
    c.items.forEach(i => { const f = el('tr'); f.append(el('td', null, i.concepto), el('td', null, i.tipo || '—'), el('td', 'cc-num', dinero(i.monto)), el('td', 'cc-num', i.gastado ? dinero(i.gastado) : '—'), el('td', null, i.estado)); t.append(f); });
    conceptos.append(t); izquierda.append(conceptos);

    const derecha = el('div', 'cc-validacion-derecha lq-evidencias'), deposito = !!c.depositado;
    derecha.append(grupoEvid('fa-money-bill-transfer', 'Foto del depósito', c.deposito ? 'Completo' : deposito ? 'Pendiente' : 'No aplica', c.deposito ? galeria([c.deposito]) : null));
    derecha.append(grupoEvid('fa-receipt', 'Boletas / facturas (' + c.boletas.length + ')', c.boletas.length ? 'Completo' : deposito ? 'Pendiente' : 'No aplica', c.boletas.length ? galeria(c.boletas) : null));
    derecha.append(grupoEvid('fa-camera', 'Evidencias del gasto (' + c.evidencias.length + ')', c.evidencias.length ? 'Completo' : deposito ? 'Pendiente' : 'No aplica', c.evidencias.length ? galeria(c.evidencias) : null));
    derecha.append(grupoEvid('fa-hand-holding-dollar', 'Captura de la devolución', c.devolucion ? 'Completo' : Number(c.devuelto) > 0 || c.estado_clave === 'POR_DEVOLVER' ? 'Pendiente' : 'No aplica', c.devolucion ? galeria([c.devolucion]) : null));
    derecha.append(grupoEvid('fa-envelope', 'Correo de validación', c.correo ? 'Completo' : 'No aplica', c.correo ? enlace('Descargar correo', c.correo.url) : null));
    derecha.append(grupoEvid('fa-file-zipper', 'Expediente completo', 'Completo', enlace('Descargar expediente (ZIP)', '#', 'fa-file-zipper')));
    derecha.lastChild.querySelector('a').addEventListener('click', e => { e.preventDefault(); descargarZip([c.id]); });
    ventana('Liquidación · ' + c.codigo + ' · ' + c.tecnico, izquierda, derecha, [['Descargar expediente (ZIP)', 'cn-morado', 'fa-file-zipper', () => descargarZip([c.id])]]);
  }

  // ── Pestañas, búsqueda, tuerca y carga ──
  document.querySelectorAll('.lq-tab').forEach(b => b.addEventListener('click', () => {
    tab = b.dataset.tab; chip = ''; orden = null; try { localStorage.setItem('lq-tab', tab); } catch (_) {} pintar(); cargar(tab);
  }));
  $('cc-buscar').addEventListener('input', pintar);
  const menu = $('lq-ajustes-menu'), botonMenu = $('lq-ajustes-btn');
  botonMenu.addEventListener('click', e => { e.stopPropagation(); menu.hidden = !menu.hidden; botonMenu.setAttribute('aria-expanded', String(!menu.hidden)); });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true; });
  menu.addEventListener('click', e => { const b = e.target.closest('[data-accion]'); if (!b) return; menu.hidden = true; if (b.dataset.accion === 'limpiar') { chip = ''; orden = null; $('cc-buscar').value = ''; pintar(); } });
  async function cargar(t) {
    if (datos[t]) return;
    const r = await fetch(t === 'cotizaciones' ? '/liquidaciones/api/v2/cotizaciones' : '/liquidaciones/api/v2/caja-chica');
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('lq-lista').replaceChildren(el('p', 'cc-vacio', j.error || 'No se pudo cargar.')); return; }
    datos[t] = t === 'cotizaciones' ? j.cotizaciones : j.solicitudes;
    pintar();
  }
  if (!['cotizaciones', 'cajachica'].includes(tab)) tab = 'cotizaciones';
  pintar();
  cargar(tab).then(() => cargar(tab === 'cotizaciones' ? 'cajachica' : 'cotizaciones'));
})();
