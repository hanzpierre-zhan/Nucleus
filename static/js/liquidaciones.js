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
  // Fechas de ejecución: se muestran cortas (dd/mm/aaaa) y con color para ubicarlas rápido.
  const fechaCorta = t => {
    const s = String(t || '').trim();
    if (!s) return '';
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    return m ? m[3] + '/' + m[2] + '/' + m[1] : s;
  };
  function chipFecha(valor, tipo, estado) {
    const texto = fechaCorta(valor);
    // Sin estado de ejecución el caso aún no llega a esa etapa: se muestra "—", no "Pendiente".
    const chip = el('span', 'lq-fecha lq-fecha-' + (estado ? (texto ? tipo : 'pendiente') : 'na'),
      estado ? (texto || 'Pendiente') : '—');
    chip.title = estado
      ? (tipo === 'inicio' ? 'Inicio' : 'Fin') + ' de ejecución' + (texto ? ': ' + texto : ' (sin registrar)')
      : 'Aún no aplica';
    return chip;
  }
  const fechaEjecucion = (c, campo) => c.estado_operativo ? fechaCorta(c[campo]) || 'Pendiente' : '';
  const dialogo = $('cc-solicitud-dialogo');
  const CLIENTES = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};
  const nombreProyecto = valor => CLIENTES[valor] ? 'FLM - ' + CLIENTES[valor] : valor;
  const COLOR_EJECUCION = {'pendiente': 'pendiente', 'pdt. ejecutar': 'pendiente',
    'en ejecucion': 'curso', 'ejecutado en campo': 'campo', 'sustentado': 'sustentado'};
  const COLOR_LIQUIDACION = {'pendiente': 'pendiente', 'en borrador': 'borrador',
    'en revision': 'curso', 'observado': 'observado', 'rechazado': 'rechazado',
    'aprobado': 'sustentado', 'con po': 'campo'};
  function etiquetaEstado(estado, colores) {
    const etiqueta = el('span', 'cc-chip lq-o', estado);
    etiqueta.dataset.tonoEstado = colores[plano(estado.trim())] || '';
    return etiqueta;
  }
  const estadoLiquidacion = c => c.seguimiento.estado_liquidacion || 'Pendiente';

  let tab = 'cotizaciones', chip = '', orden = null, filtros = {}, busquedas = {};
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

  const EXPORTACION = {
    cotizaciones: {
      'Correlativo': c => c.correlativo, 'N.º cotización': c => c.cotizacion,
      'Proyecto': c => nombreProyecto(c.cliente), 'Site': c => c.site, 'Número de Ticket': c => c.wo,
      'Descripción': c => c.objetivo, 'Fecha de solicitud': c => fechaSolicitud(c), 'Tipo de gasto': c => c.tipo_presupuesto,
      'Estado de cotización': c => c.pestana, 'Estado de ejecución': c => c.estado_operativo,
      'Inicio de ejecución': c => fechaEjecucion(c, 'inicio_ejecucion'), 'Fin de ejecución': c => fechaEjecucion(c, 'fin_ejecucion'),
      'Correo de validación del cliente': c => c.nombre_correo,
      'Número de factura del proveedor': c => c.numero_factura_proveedor,
      'Número de OC del proveedor': c => c.numero_oc_proveedor,
      'Monto de factura del proveedor': c => c.monto_factura_proveedor === '' || c.monto_factura_proveedor == null
        ? null : Number(c.monto_factura_proveedor),
      'Evidencias adicionales': c => (c.evidencias_adicionales || []).map(a => a.nombre).join(' · '),
      'Avance %': c => c.avance, 'AJB / EJB': c => c.seguimiento.codigo_ajb_ejb, 'N.º Expense': c => c.seguimiento.numero_expense,
      'Estado de liquidación': estadoLiquidacion,
      'Mes de cierre': c => c.seguimiento.mes_cierre, 'N.º PO': c => c.seguimiento.numero_po,
      'Observación': c => c.seguimiento.observacion,
      'Subtotal sin FEE': c => c.subtotal_sin_fee === '' || c.subtotal_sin_fee == null ? null : Number(c.subtotal_sin_fee),
      'Sub total + FEE': c => Number(c.monto) || 0,
    },
    cajachica: {
      'Código': c => c.codigo, 'Técnico': c => c.tecnico, 'DNI': c => c.documento, 'Proyecto': c => c.proyecto,
      'Cotización': c => c.cotizacion, 'Site': c => c.site, 'CM/PM/PLM': c => c.wo,
      'Tipo de gasto': c => c.tipos.join(' · '), 'Fecha de solicitud': c => fechaSolicitud(c),
      'Estado de Caja Chica': c => c.estado, 'Depositado el': c => fecha(c.depositado_en),
      'Solicitado': c => Number(c.total) || 0, 'Depositado': c => Number(c.depositado) || 0,
      'Gastado': c => Number(c.gastado) || 0, 'Devuelto': c => Number(c.devuelto) || 0,
      'Boletas': c => c.boletas.length, 'Evidencias': c => c.evidencias.length,
    },
  };
  const IMPORTES = new Set(['Solicitado', 'Depositado', 'Gastado', 'Devuelto', 'Monto de factura del proveedor']);

  // ── Columnas por pestaña ──
  const COL = {
    cotizaciones: [
      {id: 'numero', titulo: 'N.º cotización', ancho: 'minmax(170px, 1.1fr)', texto: c => c.cotizacion || '—',
       celda: c => { const a = el('a', 'cc-codigo-link', c.cotizacion || '—'); a.href = '#'; a.addEventListener('click', e => { e.preventDefault(); verCotizacion(c); }); return a; }},
      {id: 'estado', titulo: 'Estado de cotización', ancho: 'minmax(185px, 1fr)', texto: c => c.pestana || '—',
       celda: c => el('span', 'cc-chip lq-p-' + c.pestana_clave, c.pestana || '—')},
      {id: 'ejecucion', titulo: 'Estado de ejecución', ancho: 'minmax(180px, .8fr)', texto: c => c.estado_operativo || '—',
       celda: c => etiquetaEstado(c.estado_operativo || '—', COLOR_EJECUCION)},
      {id: 'inicio', titulo: 'Inicio de ejecución', ancho: 'minmax(140px, .7fr)',
       texto: c => fechaEjecucion(c, 'inicio_ejecucion') || '—', orden: c => c.inicio_ejecucion || '',
       celda: c => chipFecha(c.inicio_ejecucion, 'inicio', c.estado_operativo)},
      {id: 'fin', titulo: 'Fin de ejecución', ancho: 'minmax(140px, .7fr)',
       texto: c => fechaEjecucion(c, 'fin_ejecucion') || '—', orden: c => c.fin_ejecucion || '',
       celda: c => chipFecha(c.fin_ejecucion, 'fin', c.estado_operativo)},
      ...[
        ['cotizacion', 'Cotización PDF', 145, 'Cotización PDF', 'Cotización PDF',
          c => c.generada && (() => abrir('/liquidaciones/api/registros/' + c.id + '/pdf'))],
        ['correo', 'Correo', 145, 'Correo de validación del cliente', 'Validación cliente',
          c => c.correo_cliente && (() => abrir(c.correo_cliente))],
        ['sustento', 'Reporte fotográfico', 180, 'Reporte fotográfico de Operaciones', 'Expediente generado',
          c => c.tiene_sustento && (() => verCotizacion(c, true))],
        ['factura', 'Factura + OC', 140, 'Factura y OC del proveedor', 'Factura + OC',
          c => (c.facturas.length || c.ocs.length) && (() => verCotizacion(c))],
      ].map(([clave, titulo, ancho, detalle, accionTexto, accion]) => ({
        id: 'evidencia-' + clave, titulo, ancho: 'minmax(' + ancho + 'px, 1fr)',
        texto: c => c.evidencias[clave] || 'No aplica',
        celda: c => {
          const estado = c.evidencias[clave] || 'No aplica';
          return chipEvid(estado === 'Completo' ? accionTexto : estado, estado, accion(c), detalle + ' · ' + estado);
        },
      })),
      {id: 'adicionales', titulo: 'Evidencias adicionales', ancho: 'minmax(165px, 1fr)',
       texto: c => (c.evidencias_adicionales || []).map(a => a.nombre).join(' · '),
       celda: c => {
         const cantidad = (c.evidencias_adicionales || []).length;
         return chipEvid(cantidad ? 'Adjuntos (' + cantidad + ')' : '+ Adjuntar',
           cantidad ? 'Completo' : 'No aplica', () => verCotizacion(c, 'adicionales'), 'Adjuntar o ver evidencia adicional');
       }},
      {id: 'avance', titulo: 'Avance %', ancho: 'minmax(90px, .6fr)', num: true, filtro: c => c.avance >= 100 ? '100 %' : c.avance >= 50 ? '50 a 99 %' : 'Menos de 50 %', texto: c => c.avance + ' %', orden: c => c.avance,
       celda: c => { const s = el('span', 'lq-avance'); const b = el('span', 'lq-avance-barra'); const f = el('span'); f.style.width = c.avance + '%'; f.dataset.nivel = c.avance >= 100 ? 'ok' : c.avance >= 50 ? 'medio' : 'bajo'; b.append(f); s.append(b, el('small', null, c.avance + ' %')); return s; }},
      {id: 'liquidacion', titulo: 'Estado de liquidación', ancho: 'minmax(195px, .8fr)', texto: estadoLiquidacion,
       celda: c => etiquetaEstado(estadoLiquidacion(c), COLOR_LIQUIDACION)},
      {id: 'subtotal', titulo: 'Subtotal sin FEE', ancho: 'minmax(155px, .8fr)', num: true,
       texto: c => EXPORTACION.cotizaciones['Subtotal sin FEE'](c) === null ? '—' : dinero(c.subtotal_sin_fee),
       orden: c => EXPORTACION.cotizaciones['Subtotal sin FEE'](c) ?? -Infinity},
      {id: 'monto', titulo: 'Sub total + FEE', ancho: 'minmax(120px, .8fr)', num: true, sinFiltro: true, texto: c => dinero(c.monto), orden: c => Number(c.monto) || 0,
       celda: c => el('strong', 'cc-num', dinero(c.monto))},
    ],
    cajachica: [
      {id: 'codigo', titulo: 'Código', ancho: 'minmax(135px, 1fr)', texto: c => c.codigo || '—',
       celda: c => { const a = el('a', 'cc-codigo-link', c.codigo || '—'); a.href = '#'; a.addEventListener('click', e => { e.preventDefault(); verCajaChica(c); }); return a; }},
      {id: 'cotizacion', titulo: 'Cotización', ancho: 'minmax(150px, .9fr)', texto: c => c.cotizacion || '—'},
      {id: 'estado', titulo: 'Estado de Caja Chica', ancho: 'minmax(185px, .8fr)', texto: c => c.estado, celda: c => el('span', 'cc-chip lq-s-' + c.estado_clave.toLowerCase(), c.estado)},
      {id: 'tipos', titulo: 'Tipo de gasto', ancho: 'minmax(120px, .7fr)', texto: c => c.tipos.join(' · '),
       celda: c => { const s = el('span', 'lq-evids'); c.tipos.forEach(t => s.append(el('span', 'cc-chip ' + (t === 'Refacturable' ? 'cc-refacturable' : 'cc-gasto-cobra'), t))); return s; }},
      {id: 'evidencias', titulo: 'Archivos y evidencias', ancho: 'minmax(330px, 2fr)', texto: c => '', sinFiltro: true,
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

  // Conserva las celdas visuales y añade los campos del Excel que no tienen columna propia.
  for (const [origen, campos] of Object.entries(EXPORTACION)) {
    const titulos = new Set(COL[origen].map(col => col.titulo));
    for (const [indice, [titulo, leer]] of Object.entries(campos).entries()) {
      if (titulos.has(titulo)) continue;
      const importe = IMPORTES.has(titulo);
      const numerico = importe || ['Boletas', 'Evidencias'].includes(titulo);
      COL[origen].push({
        id: 'excel-' + indice, titulo, ancho: titulo === 'Descripción' ? 'minmax(245px, 1.4fr)'
          : titulo.length > 22 ? 'minmax(215px, 1fr)' : 'minmax(145px, 1fr)',
        num: numerico,
        texto: c => {
          const valor = leer(c);
          return valor == null || valor === '' ? '—' : importe ? dinero(valor) : String(valor);
        },
        orden: numerico ? c => leer(c) ?? -Infinity : undefined,
        celda: titulo === 'Proyecto' ? c => {
          const nombre = leer(c) || '—';
          const marca = window.NucleusProjectBadge?.brand(nombre);
          return el('span', marca ? 'project-badge project-badge--' + marca : '', nombre);
        } : undefined,
      });
    }
    const identificadores = origen === 'cotizaciones'
      ? ['N.º cotización', 'Correlativo', 'Proyecto', 'Site', 'Número de Ticket']
      : ['Código', 'Técnico', 'DNI', 'Proyecto', 'Cotización', 'Site', 'CM/PM/PLM'];
    const columnas = COL[origen];
    COL[origen] = [
      ...identificadores.map(titulo => columnas.find(col => col.titulo === titulo)),
      ...columnas.filter(col => !identificadores.includes(col.titulo)),
    ];
  }

  // ── Filtros rápidos (chips) ──
  const CHIPS = {
    cotizaciones: [['incompleto', 'Expediente incompleto'], ['listo', 'Listo para liquidar']],
    cajachica: [['sinfoto', 'Sin foto de depósito'], ['completo', 'Expediente completo']],
  };
  function pasaChip(c, clave = chip) {
    if (!clave) return true;
    if (tab === 'cotizaciones') {
      return clave === 'listo' ? c.avance >= 100 : c.avance < 100;
    }
    if (clave === 'sinfoto') return !!c.depositado && !c.deposito;
    return !!c.deposito && c.boletas.length > 0 && c.evidencias.length > 0 && (!(Number(c.devuelto) > 0) || !!c.devolucion);
  }
  const lista = () => datos[tab] || [];
  const filtroProyecto = $('lq-proyecto'), filtroMes = $('lq-mes'), filtroGasto = $('lq-gasto');
  const proyectoDe = c => (tab === 'cotizaciones' ? c.cliente : c.proyecto) || '';
  const fechaSolicitud = c => tab === 'cotizaciones' ? c.fechas?.solicitud || c.fechas?.cotizada : c.creado;
  function mesDe(c) {
    const fecha = String(fechaSolicitud(c) || '').trim();
    const iso = /^(\d{4})-(\d{2})-\d{2}/.exec(fecha);
    const local = /^\d{1,2}[/-](\d{1,2})[/-](\d{4})(?:\D|$)/.exec(fecha);
    const [anio, mes] = iso ? [iso[1], iso[2]] : local ? [local[2], local[1].padStart(2, '0')] : ['', ''];
    return Number(mes) >= 1 && Number(mes) <= 12 ? anio + '-' + mes : '';
  }
  const gastosDe = c => tab === 'cotizaciones' ? [c.tipo_presupuesto] : (c.tipos || []);
  const nombreGasto = texto => ({'gasto cobra': 'Gasto Cobra', refacturable: 'Refacturable'}[plano(texto).trim()] || texto);
  function actualizarOpciones() {
    const filas = lista();
    const proyectos = [...new Set(filas.map(proyectoDe).filter(Boolean))].sort();
    const meses = [...new Set(filas.map(mesDe).filter(Boolean))].sort().reverse();
    const gastos = [...new Set(filas.flatMap(gastosDe).filter(Boolean).map(nombreGasto))].sort();
    const formatoMes = new Intl.DateTimeFormat('es-PE', {month: 'long', year: 'numeric', timeZone: 'UTC'});
    for (const [campo, opciones, etiqueta] of [
      [filtroProyecto, proyectos, nombreProyecto],
      [filtroMes, meses, v => formatoMes.format(new Date(v + '-01T00:00:00Z'))],
      [filtroGasto, gastos, v => v],
    ]) {
      const actual = campo.value;
      campo.replaceChildren(campo.options[0], ...opciones.map(v => new Option(etiqueta(v), v)));
      campo.value = opciones.includes(actual) ? actual : '';
    }
  }
  function visibles() {
    const q = plano($('cc-buscar').value.trim());
    let filas = lista().filter(c => pasaChip(c) && (!q || plano(COL[tab].map(col => col.texto(c)).join(' ')).includes(q))
      && (!filtroProyecto.value || proyectoDe(c) === filtroProyecto.value)
      && (!filtroMes.value || mesDe(c) === filtroMes.value)
      && (!filtroGasto.value || gastosDe(c).some(g => nombreGasto(g) === filtroGasto.value))
      && COL[tab].every(col => !busquedas[col.id] || plano(col.texto(c)).includes(plano(busquedas[col.id].trim())))
      && Object.entries(filtros).every(([id, vals]) => { const col = COL[tab].find(x => x.id === id); return !col || vals.includes(valorFiltro(col, c)); }));
    if (orden) {
      const col = COL[tab].find(x => x.id === orden.col), v = col.orden || col.texto;
      filas = [...filas].sort((a, b) => { const x = v(a), y = v(b); return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'es')) * orden.dir; });
    }
    return filas;
  }
  const valorFiltro = (col, c) => String((col.filtro || col.texto)(c) ?? '').trim();
  // Filtro por columna: lista de valores, como en Caja Chica (con lo demás ya filtrado).
  function abrirFiltro(col, boton) {
    const caja = $('lq-filtro');
    if (!caja.hidden && caja.dataset.col === col.id) { caja.hidden = true; return; }
    const guardado = filtros[col.id]; delete filtros[col.id];
    const valores = [...new Set(visibles().map(c => valorFiltro(col, c)))].sort((a, b) => a.localeCompare(b, 'es', {numeric: true}));
    if (guardado) filtros[col.id] = guardado;
    const marcados = new Set(guardado || valores);
    caja.dataset.col = col.id; caja.replaceChildren();
    const buscar = el('input'); Object.assign(buscar, {type: 'search', placeholder: 'Buscar en ' + col.titulo.toLowerCase()});
    const lista = el('div', 'cc-filtro-valores');
    const todos = el('label', 'cc-todos'), todosCheck = el('input'); todosCheck.type = 'checkbox'; todos.append(todosCheck, 'Seleccionar todo');
    const checks = valores.map(v => { const l = el('label'), ch = el('input'); ch.type = 'checkbox'; ch.value = v; ch.checked = marcados.has(v); l.append(ch, v || '(vacío)'); return l; });
    const sincronizar = () => { const v = checks.filter(l => !l.hidden); todosCheck.checked = v.length > 0 && v.every(l => l.firstChild.checked); };
    todosCheck.addEventListener('change', () => { checks.filter(l => !l.hidden).forEach(l => { l.firstChild.checked = todosCheck.checked; }); });
    checks.forEach(l => l.firstChild.addEventListener('change', sincronizar));
    buscar.addEventListener('input', () => { const t = plano(buscar.value.trim()); checks.forEach(l => { l.hidden = t && !plano(l.textContent).includes(t); }); sincronizar(); });
    lista.append(todos, ...checks);
    if (!valores.length) lista.append(el('p', 'cc-nota', 'Sin valores.'));
    const limpiar = el('button', 'cc-btn', 'Limpiar'), aplicar = el('button', 'cc-btn cc-ok', 'Aplicar');
    limpiar.type = aplicar.type = 'button';
    limpiar.addEventListener('click', () => { delete filtros[col.id]; caja.hidden = true; pintar(); });
    aplicar.addEventListener('click', () => {
      const elegidos = checks.filter(l => l.firstChild.checked).map(l => l.firstChild.value);
      if (elegidos.length === valores.length) delete filtros[col.id]; else filtros[col.id] = elegidos;
      caja.hidden = true; pintar();
    });
    const pie = el('div', 'cc-filtro-pie'); pie.append(limpiar, aplicar);
    caja.append(buscar, lista, pie); sincronizar();
    caja.hidden = false;
    const r = boton.getBoundingClientRect();
    caja.style.top = Math.min(r.bottom + 6, innerHeight - caja.offsetHeight - 8) + 'px';
    caja.style.left = Math.max(8, Math.min(r.left - 8, innerWidth - caja.offsetWidth - 8)) + 'px';
    buscar.focus();
  }
  document.addEventListener('click', e => { const c = $('lq-filtro'); if (c && !c.hidden && !c.contains(e.target)) c.hidden = true; });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('lq-filtro')) $('lq-filtro').hidden = true; });
  function pintar() {
    const filasFiltradas = visibles();
    document.querySelectorAll('.lq-tab').forEach(b => { b.classList.toggle('activa', b.dataset.tab === tab); b.setAttribute('aria-selected', String(b.dataset.tab === tab)); });
    for (const t of ['cotizaciones', 'cajachica']) {
      const filas = t === tab ? filasFiltradas : datos[t] || [];
      document.querySelector('[data-cuenta="' + t + '"]').textContent = datos[t] ? filas.length : '…';
      const suma = filas.reduce((s, c) => s + (Number(t === 'cotizaciones' ? c.monto : c.depositado) || 0), 0);
      const p = document.querySelector('[data-plata="' + t + '"]'); p.textContent = plata(suma); p.title = 'Total: ' + dinero(suma);
    }
    const chips = $('lq-chips'); chips.replaceChildren();
    for (const [clave, texto] of CHIPS[tab]) {
      const b = el('button', 'lq-chip' + (chip === clave ? ' activo' : '')); b.type = 'button';
      const n = filasFiltradas.filter(c => pasaChip(c, clave)).length;
      b.append(el('span', null, texto), el('strong', null, String(n)));
      b.addEventListener('click', () => { chip = chip === clave ? '' : clave; pintar(); });
      chips.append(b);
    }
    // Encabezado
    const cols = COL[tab];
    $('lq-tabla').style.setProperty('--cc-cols', ['40px', '86px', ...cols.map(c => c.ancho)].join(' '));
    $('lq-tabla').style.setProperty('--cc-min', (cols.reduce((s, c) => s + parseInt(c.ancho.slice(7), 10), 0) + 140 + 12 * cols.length) + 'px');
    const cab = $('lq-encabezado');
    const activo = document.activeElement;
    const foco = cab.contains(activo) && activo.dataset.buscar
      ? {col: activo.dataset.buscar, inicio: activo.selectionStart, fin: activo.selectionEnd} : null;
    cab.replaceChildren();
    const filas = filasFiltradas;
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
      fila.append(el('span', 'cc-th-nombre', col.titulo), b);
      if (!col.sinFiltro) {
        const f = el('button', 'cc-th-btn' + (filtros[col.id] ? ' activo' : '')); f.type = 'button';
        f.append(icono('fa-filter')); f.title = f.ariaLabel = 'Filtrar ' + col.titulo;
        f.addEventListener('click', e => { e.stopPropagation(); abrirFiltro(col, f); });
        fila.append(f);
      }
      const buscar = el('input', 'cc-th-buscar');
      Object.assign(buscar, {type: 'search', value: busquedas[col.id] || '', placeholder: 'Buscar…'});
      buscar.dataset.buscar = col.id;
      buscar.setAttribute('aria-label', 'Buscar en ' + col.titulo);
      buscar.addEventListener('input', () => {
        if (buscar.value.trim()) busquedas[col.id] = buscar.value;
        else delete busquedas[col.id];
        pintar();
      });
      th.append(fila, buscar); cab.append(th);
    }
    if (foco) {
      const buscar = cab.querySelector('[data-buscar="' + foco.col + '"]');
      if (buscar) { buscar.focus({preventScroll: true}); buscar.setSelectionRange(foco.inicio, foco.fin); }
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
      fila.append(sel, acciones, ...COL[tab].map(col => {
        if (col.celda) return col.celda(c);
        const texto = col.texto(c);
        const celda = el('span', 'lq-celda-texto' + (col.num ? ' cc-num' : ''), texto);
        if (texto) celda.title = texto;
        return celda;
      }));
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
    const url = tab === 'cotizaciones' ? '/liquidaciones/api/registros/expedientes?documentos=liquidacion' : '/liquidaciones/api/v2/caja-chica/expedientes';
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ids})});
    if (!r.ok) { avisar((await r.json().catch(() => ({}))).error || 'No se pudo preparar el expediente.'); return; }
    const nombre = decodeURIComponent((r.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i)?.[1] || 'Expedientes.zip');
    const a = el('a'); a.href = URL.createObjectURL(await r.blob()); a.download = nombre; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  $('lq-zip').addEventListener('click', () => descargarZip([...seleccion[tab]]));
  $('lq-excel').addEventListener('click', () => {
    if (typeof XLSX === 'undefined') { avisar('Librería de exportación no disponible.'); return; }
    const filas = visibles().map(c => Object.fromEntries(
      Object.entries(EXPORTACION[tab]).map(([titulo, leer]) => [titulo, leer(c)])));
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

  async function verCotizacion(c, enfocar) {
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(ficha('fa-file-lines', 'Detalle', [['N.º', c.cotizacion + ' · ' + c.correlativo], ['Cliente', CLIENTES[c.cliente] || c.cliente], ['Site', c.site], ['Número de Ticket', c.wo],
      ['Descripción', c.objetivo], ['Supervisor', c.supervisor], ['Sub total + FEE', dinero(c.monto)], ['Estado', c.pestana],
      ['Estado de pago', c.estado_pago], ['Estado de ejecución', c.estado_operativo],
      ['Inicio de ejecución', fechaEjecucion(c, 'inicio_ejecucion') || '—'], ['Fin de ejecución', fechaEjecucion(c, 'fin_ejecucion') || '—']]));
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
    derecha.append(grupoEvid('fa-envelope', 'Correo de validación del cliente', e.correo, c.correo_cliente ? enlace(c.nombre_correo || 'Descargar correo', c.correo_cliente) : null));
    const fact = el('div', 'lq-lista-descargas');
    c.facturas.forEach((u, n) => fact.append(enlace('Factura ' + (n + 1), u)));
    c.ocs.forEach((u, n) => fact.append(enlace('OC ' + (n + 1), u)));
    derecha.append(grupoEvid('fa-file-invoice', 'Facturas y OC del proveedor', e.factura, fact.children.length ? fact : null));
    const fotos = el('div', 'lq-sustento');
    if (c.tiene_sustento) fotos.append(enlace('Descargar reporte fotográfico (ZIP)',
      '/liquidaciones/api/registros/' + c.id + '/expediente?documentos=reporte', 'fa-file-zipper'));
    const galeriaReporte = el('div');
    fotos.append(galeriaReporte);
    const grupoFotos = grupoEvid('fa-camera', 'Expediente del reporte fotográfico', e.sustento, fotos);
    derecha.append(grupoFotos);
    const adicionales = el('div', 'lq-lista-descargas');
    const archivos = el('div', 'lq-lista-descargas');
    const adjuntar = el('input');
    Object.assign(adjuntar, {type: 'file', accept: '.pdf,.msg,.eml,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp'});
    adjuntar.setAttribute('aria-label', 'Adjuntar evidencia adicional');
    const estadoAdjunto = el('p', 'cc-nota');
    estadoAdjunto.setAttribute('role', 'status');
    const verAdjuntos = () => archivos.replaceChildren(...(c.evidencias_adicionales || [])
      .map(a => enlace(a.nombre, a.url)));
    verAdjuntos();
    adjuntar.addEventListener('change', async () => {
      const archivo = adjuntar.files[0];
      if (!archivo) return;
      const datos = new FormData();
      datos.append('origen_id', c.id);
      datos.append('adjunto', archivo);
      adjuntar.disabled = true;
      estadoAdjunto.textContent = 'Subiendo evidencia…';
      try {
        const r = await fetch('/api/cotizacion/subir_evidencia_liquidacion', {method: 'POST', body: datos});
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.success) throw new Error(j.error || 'No se pudo adjuntar la evidencia.');
        (c.evidencias_adicionales ||= []).push({nombre: j.nombre, url: j.url});
        verAdjuntos();
        pintar();
        estadoAdjunto.textContent = 'Evidencia adjuntada.';
      } catch (error) {
        estadoAdjunto.textContent = error.message;
      } finally {
        adjuntar.disabled = false;
        adjuntar.value = '';
      }
    });
    adicionales.append(archivos, adjuntar, estadoAdjunto);
    const grupoAdicional = grupoEvid('fa-paperclip', 'Evidencia adicional', '', adicionales);
    derecha.append(grupoAdicional);

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
    if (enfocar === 'adicionales') grupoAdicional.scrollIntoView({block: 'nearest'});
    if (c.tiene_sustento) {
      const r = await fetch('/liquidaciones/api/registros/' + c.id + '/sustento'); const j = await r.json().catch(() => ({}));
      const reg = j.registro || {};
      for (const [fase, t] of [['inicio', 'Antes'], ['proceso', 'Durante'], ['cierre', 'Después']]) {
        const lista = (reg.fotos || {})[fase] || [];
        if (!lista.length) continue;
        galeriaReporte.append(el('strong', 'lq-fase', t + ' (' + lista.length + ')'), galeria(lista.map((u, n) => ({url: u, titulo: t + ' ' + (n + 1)}))));
      }
      if (!galeriaReporte.children.length) galeriaReporte.append(el('p', 'cc-nota', 'Sin fotos de sustento.'));
      if (enfocar === true) grupoFotos.scrollIntoView({block: 'start'});
    }
  }

  function verCajaChica(c) {
    const izquierda = el('div', 'cc-validacion-izquierda');
    izquierda.append(ficha('fa-file-lines', 'Detalle de la solicitud', [['Código', c.codigo], ['Técnico', c.tecnico + ' · ' + c.documento], ['Proyecto', c.proyecto],
      ['Cotización', c.cotizacion], ['Site', c.site], ['CM / PM / PLM', c.wo], ['Justificación', c.motivo], ['Estado de Caja Chica', c.estado],
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
    tab = b.dataset.tab; chip = ''; orden = null; filtros = {}; busquedas = {}; $('lq-filtro').hidden = true; try { localStorage.setItem('lq-tab', tab); } catch (_) {} actualizarOpciones(); pintar(); cargar(tab);
  }));
  $('cc-buscar').addEventListener('input', pintar);
  for (const campo of [filtroProyecto, filtroMes, filtroGasto]) campo.addEventListener('change', pintar);
  const menu = $('lq-ajustes-menu'), botonMenu = $('lq-ajustes-btn');
  botonMenu.addEventListener('click', e => { e.stopPropagation(); menu.hidden = !menu.hidden; botonMenu.setAttribute('aria-expanded', String(!menu.hidden)); });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true; });
  menu.addEventListener('click', e => { const b = e.target.closest('[data-accion]'); if (!b) return; menu.hidden = true; if (b.dataset.accion === 'limpiar') { chip = ''; orden = null; filtros = {}; busquedas = {}; $('cc-buscar').value = filtroProyecto.value = filtroMes.value = filtroGasto.value = ''; pintar(); } });
  async function cargar(t) {
    if (datos[t]) return;
    const r = await fetch(t === 'cotizaciones' ? '/liquidaciones/api/v2/cotizaciones' : '/liquidaciones/api/v2/caja-chica');
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('lq-lista').replaceChildren(el('p', 'cc-vacio', j.error || 'No se pudo cargar.')); return; }
    datos[t] = t === 'cotizaciones' ? j.cotizaciones : j.solicitudes;
    if (t === tab) actualizarOpciones();
    pintar();
  }
  if (!['cotizaciones', 'cajachica'].includes(tab)) tab = 'cotizaciones';
  pintar();
  cargar(tab).then(() => cargar(tab === 'cotizaciones' ? 'cajachica' : 'cotizaciones'));
})();
