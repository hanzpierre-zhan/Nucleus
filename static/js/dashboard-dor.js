/* Claro · Operación diaria CM: el mismo análisis que el reporte diario del cliente, con nuestros datos.
   - Todos los gráficos muestran su número (etiqueta fija), no solo al pasar el mouse.
   - Clic en un punto, barra o celda: pregunta y abre el detalle de esos tickets.
   - Los valores por día son "del día" (SLA, flujo, cierres) o "al cierre del día" (backlog). El SLA tiene además modo acumulado. */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('dor-data').textContent);
  const $ = id => document.getElementById(id);
  const el = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt !== undefined) n.textContent = txt; return n; };
  const C = {azul: '#2a78d6', naranja: '#eb6834', verde: '#1baf7a', ambar: '#eda100', rojo: '#e34948', lima: '#97C459', gris: '#898781', violeta: '#6250d6'};
  const COLOR_REGION = r => ({LIMA: C.azul, CENTRO: C.naranja})[r] || C.violeta;
  const META = D.meta_sla || 95, META_EF = D.meta_eficiencia || 2, BASE = D.linea_base || {};
  const num = (v, d = 0) => Number(v).toLocaleString('es-PE', {minimumFractionDigits: d, maximumFractionDigits: d});
  const pct = (a, b) => b ? a / b * 100 : null;
  const dia = s => s ? String(s).slice(0, 10) : '';
  const corto = d => d.slice(8, 10) + '/' + d.slice(5, 7);
  const largo = d => d ? d.slice(8, 10) + '/' + d.slice(5, 7) + '/' + d.slice(0, 4) : '';
  const fechaHora = s => s ? s.slice(8, 10) + '/' + s.slice(5, 7) + '/' + s.slice(2, 4) + ' ' + s.slice(11, 16) : '';
  const horas = (a, b) => a && b ? (Date.parse(b) - Date.parse(a)) / 36e5 : null;
  const mediana = arr => { if (!arr.length) return null; const s = [...arr].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const nombreRegion = r => r === 'LIMA' ? 'Lima' : r === 'CENTRO' ? 'Centro' : r.charAt(0) + r.slice(1).toLowerCase();
  const inicio = r => r.creado || r.despacho;

  // ── Estado de filtros ──
  const st = {dias: 15, modo: 'dia'};
  const FILTROS = {region: 'region', oficina: 'oficina', contrata: 'contrata', tecnico: 'tecnico'};
  if ($('dor-rm')) FILTROS.rm = 'rm';
  const E = D.etiquetas || {};
  // Filtros con casillas: se pueden marcar varias opciones (ninguna marcada = todas).
  const elegidos = {region: new Set(), oficina: new Set(), contrata: new Set(), tecnico: new Set(), rm: new Set()};
  const textoOpcion = (id, v) => id === 'region' ? nombreRegion(v) : v;
  function resumenMulti(id) {
    const s = elegidos[id], caja = $('dor-' + id);
    if (!s.size) return caja.dataset.todos;
    if (s.size === 1) return textoOpcion(id, [...s][0]);
    return s.size + ' seleccionados';
  }
  function armarMulti(id, campo) {
    const caja = $('dor-' + id), valores = [...new Set(D.rows.map(r => r[campo]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
    const boton = el('button', 'dor-multi-btn'); boton.type = 'button'; boton.setAttribute('aria-haspopup', 'listbox');
    const pop = el('div', 'dor-multi-pop'); pop.hidden = true;
    const buscar = Object.assign(el('input'), {type: 'search', placeholder: 'Buscar…'});
    const lista = el('div', 'dor-multi-lista');
    const todos = el('label', 'dor-multi-todos'), chTodos = Object.assign(el('input'), {type: 'checkbox'}); todos.append(chTodos, ' Seleccionar todo');
    const checks = valores.map(v => { const l = el('label'), c = Object.assign(el('input'), {type: 'checkbox', value: v}); l.append(c, ' ' + textoOpcion(id, v)); return l; });
    const sincronizar = () => {
      checks.forEach(l => { l.firstChild.checked = elegidos[id].has(l.firstChild.value); });
      const vis = checks.filter(l => !l.hidden); chTodos.checked = vis.length > 0 && vis.every(l => l.firstChild.checked);
      boton.textContent = resumenMulti(id); boton.classList.toggle('activo', elegidos[id].size > 0);
    };
    checks.forEach(l => l.firstChild.addEventListener('change', () => { l.firstChild.checked ? elegidos[id].add(l.firstChild.value) : elegidos[id].delete(l.firstChild.value); sincronizar(); pintar(); }));
    chTodos.addEventListener('change', () => { checks.filter(l => !l.hidden).forEach(l => chTodos.checked ? elegidos[id].add(l.firstChild.value) : elegidos[id].delete(l.firstChild.value));
      if (elegidos[id].size === valores.length) elegidos[id].clear(); sincronizar(); pintar(); });
    buscar.addEventListener('input', () => { const q = buscar.value.trim().toLowerCase(); checks.forEach(l => { l.hidden = q && !l.textContent.toLowerCase().includes(q); }); sincronizar(); });
    const limpiar = el('button', 'dor-multi-limpiar', 'Limpiar'); limpiar.type = 'button';
    limpiar.addEventListener('click', () => { elegidos[id].clear(); sincronizar(); pintar(); });
    lista.append(todos, ...checks);
    pop.append(buscar, lista, limpiar);
    pop.addEventListener('click', e => e.stopPropagation());
    boton.addEventListener('click', e => { e.stopPropagation(); const abrir = pop.hidden; document.querySelectorAll('.dor-multi-pop').forEach(x => { x.hidden = true; }); pop.hidden = !abrir; if (abrir) buscar.focus(); });
    caja.replaceChildren(boton, pop); caja._sincronizar = sincronizar; sincronizar();
  }
  for (const [id, campo] of Object.entries(FILTROS)) armarMulti(id, campo);
  document.addEventListener('click', () => document.querySelectorAll('.dor-multi-pop').forEach(x => { x.hidden = true; }));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.dor-multi-pop').forEach(x => { x.hidden = true; }); });
  if (D.operador !== 'PEXT' && D.rows.some(r => r.contrata === 'COBRA')) { elegidos.contrata.add('COBRA'); $('dor-contrata')._sincronizar(); }

  function dias(n, hasta) {
    const out = [], fin = new Date(hasta + 'T12:00:00');
    for (let i = n - 1; i >= 0; i--) { const d = new Date(fin); d.setDate(fin.getDate() - i); out.push(d.toISOString().slice(0, 10)); }
    return out;
  }
  function universo() {
    const sinDesp = $('dor-sin-despachar').checked, pasa = (id, v) => !elegidos[id].size || elegidos[id].has(v);
    return D.rows.filter(r => pasa('region', r.region) && pasa('oficina', r.oficina) && pasa('contrata', r.contrata) && pasa('tecnico', r.tecnico) && pasa('rm', r.rm) && (sinDesp || r.despacho));
  }
  // Abierto al cierre del día d (backlog): ya existía, no se había completado ni cancelado hasta ese día.
  const abiertoAl = (r, d) => inicio(r) && dia(inicio(r)) <= d && !(r.completado && (!r.cierre || dia(r.cierre) <= d)) && !(r.cancelado && (!r.cancelacion || dia(r.cancelacion) <= d));
  const cerroEl = (r, d) => r.completado && dia(r.cierre) === d;
  const diasDesdeDespacho = r => r.despacho && r.cierre ? Math.round((Date.parse(dia(r.cierre)) - Date.parse(dia(r.despacho))) / 864e5) : null;

  // ── Gráficos: etiquetas fijas, línea de SLA partida en la meta, clic al detalle ──
  const tema = () => { const s = getComputedStyle(document.body); return {texto: s.getPropertyValue('--ios-label').trim() || '#e5e7eb', suave: s.getPropertyValue('--ios-secondary').trim() || C.gris}; };
  const etiquetas = {
    id: 'etiquetas',
    afterDatasetsDraw(ch) {
      const ctx = ch.ctx, horizontal = ch.options.indexAxis === 'y', t = tema();
      ch.data.datasets.forEach((ds, i) => {
        const o = ds.etiqueta; if (!o || !ch.isDatasetVisible(i)) return;
        ctx.save(); ctx.font = '600 10.5px system-ui, -apple-system, Segoe UI, sans-serif'; ctx.textBaseline = 'middle';
        ch.getDatasetMeta(i).data.forEach((e, j) => {
          const v = ds.data[j];
          if (v === null || v === undefined || (!o.cero && Number(v) === 0)) return;
          const txt = o.fmt ? o.fmt(v, j) : String(v); if (!txt) return;
          let x = e.x, y = e.y; ctx.textAlign = 'center';
          if (o.pos === 'centro') { if (horizontal) x = (e.x + e.base) / 2; else y = (e.y + e.base) / 2; }
          else if (o.pos === 'fin') { ctx.textAlign = 'left'; x = e.x + 5; }
          else if (o.pos === 'abajo') y = e.y + 12;
          else y = e.y - 9;
          if (o.pos === 'centro' && (horizontal ? Math.abs(e.x - e.base) : Math.abs(e.y - e.base)) < 14) return;
          ctx.fillStyle = typeof o.color === 'function' ? o.color(v, j) : (o.color || t.texto);
          ctx.fillText(txt, x, y);
        });
        ctx.restore();
      });
    },
  };
  // La línea de SLA es verde sobre la meta y roja debajo, cambiando justo donde cruza el 95 %.
  const corteMeta = {
    id: 'corteMeta',
    beforeDatasetsDraw(ch) {
      const ds = ch.data.datasets[0], y = ch.scales.y, a = ch.chartArea; if (!a || !ds) return;
      const r = Math.min(1, Math.max(0, (y.getPixelForValue(META) - a.top) / (a.bottom - a.top)));
      const g = ch.ctx.createLinearGradient(0, a.top, 0, a.bottom);
      g.addColorStop(0, C.verde); g.addColorStop(r, C.verde); g.addColorStop(r, C.rojo); g.addColorStop(1, C.rojo);
      ds.borderColor = g;
    },
  };
  // La app usa zoom (75 % en computadora) y Chart.js ubica mal el mouse (abría otro día u otra barra).
  // Por eso el dashboard calcula él mismo qué barra o punto está bajo el mouse, con las medidas reales en pantalla,
  // y con eso abre el detalle y mueve el cuadro de información. Así el número que ves es el que se abre.
  function posicion(ch, ev) {
    const r = ch.canvas.getBoundingClientRect(); if (!r.width || !r.height) return null;
    return {x: (ev.clientX - r.left) / r.width * ch.width, y: (ev.clientY - r.top) / r.height * ch.height};
  }
  function tocado(ch, p) {
    if (!p) return null;
    const a = ch.chartArea, horizontal = ch.options.indexAxis === 'y';
    if (p.x < a.left - 8 || p.x > a.right + 8 || p.y < a.top - 12 || p.y > a.bottom + 8) return null;
    const visibles = ch.data.datasets.map((ds, i) => i).filter(i => ch.isDatasetVisible(i) && !ch.data.datasets[i].sinClic);
    if (ch.config.type === 'bar') {
      // Barra: el punto tiene que caer dentro del rectángulo de la barra.
      for (const i of visibles) {
        const datos = ch.getDatasetMeta(i).data;
        for (let j = 0; j < datos.length; j++) {
          const v = ch.data.datasets[i].data[j]; if (!v) continue;
          const e = datos[j].getProps(['x', 'y', 'base', 'width', 'height'], true);
          const dentro = horizontal
            ? p.y >= e.y - e.height / 2 && p.y <= e.y + e.height / 2 && p.x >= Math.min(e.base, e.x) - 2 && p.x <= Math.max(e.base, e.x) + 2
            : p.x >= e.x - e.width / 2 && p.x <= e.x + e.width / 2 && p.y >= Math.min(e.y, e.base) - 10 && p.y <= Math.max(e.y, e.base) + 2;
          if (dentro) return {datasetIndex: i, index: j};
        }
      }
      return null;
    }
    // Áreas apiladas (cierre según días): la franja donde cae el mouse, en el día más cercano.
    if (ch.config.options.bandas) {
      const pts = ch.getDatasetMeta(visibles[0]).data; let j = 0;
      pts.forEach((e, k) => { if (Math.abs(e.x - p.x) < Math.abs(pts[j].x - p.x)) j = k; });
      for (const i of visibles) {
        const arriba = ch.getDatasetMeta(i).data[j].y, k = visibles.indexOf(i), abajo = k ? ch.getDatasetMeta(visibles[k - 1]).data[j].y : a.bottom;
        if (p.y >= arriba - 4 && p.y <= abajo + 4 && ch.data.datasets[i].data[j] !== null) return {datasetIndex: i, index: j};
      }
      return null;
    }
    // Líneas: el punto más cercano (a no más de 40 px).
    let mejor = null, dist = 40;
    for (const i of visibles) ch.getDatasetMeta(i).data.forEach((e, j) => {
      if (ch.data.datasets[i].data[j] === null || ch.data.datasets[i].data[j] === undefined) return;
      const d = Math.hypot(e.x - p.x, e.y - p.y); if (d < dist) { dist = d; mejor = {datasetIndex: i, index: j}; }
    });
    return mejor;
  }
  function mostrarInfo(ch, t) {
    if (!t) { ch.setActiveElements([]); ch.tooltip.setActiveElements([], {x: 0, y: 0}); ch.update('none'); return; }
    // El cuadro muestra todas las series de esa fecha/fila, como antes; se resalta la tocada.
    const todos = ch.data.datasets.map((ds, i) => ({datasetIndex: i, index: t.index}))
      .filter(x => ch.isDatasetVisible(x.datasetIndex) && ch.data.datasets[x.datasetIndex].data[x.index] !== null && ch.data.datasets[x.datasetIndex].data[x.index] !== undefined);
    const e = ch.getDatasetMeta(t.datasetIndex).data[t.index];
    ch.setActiveElements([t]); ch.tooltip.setActiveElements(todos.length ? todos : [t], {x: e.x, y: e.y}); ch.update('none');
  }
  function escuchar(canvas) {
    if (canvas._dorListo) return; canvas._dorListo = true;
    canvas.addEventListener('mousemove', ev => {
      const ch = Chart.getChart(canvas); if (!ch) return;
      const t = tocado(ch, posicion(ch, ev)), clave = t ? t.datasetIndex + ':' + t.index : '';
      canvas.style.cursor = t && canvas._dorDetalle ? 'pointer' : 'default';
      if (clave !== canvas._dorUltimo) { canvas._dorUltimo = clave; mostrarInfo(ch, t); }
    });
    canvas.addEventListener('mouseleave', () => { const ch = Chart.getChart(canvas); canvas._dorUltimo = ''; if (ch) mostrarInfo(ch, null); });
    canvas.addEventListener('click', ev => {
      const ch = Chart.getChart(canvas); if (!ch || !canvas._dorDetalle) return;
      const t = tocado(ch, posicion(ch, ev)); if (!t) return;
      ev.stopPropagation();
      const r = canvas._dorDetalle(t.datasetIndex, t.index); if (r) preguntar(r.titulo, r.filas);
    });
  }
  const graficos = {};
  function grafico(id, config, detalle) {
    graficos[id]?.destroy();
    const t = tema(), horizontal = config.options?.indexAxis === 'y';
    const ejes = {grid: {color: 'rgba(137,135,129,.16)'}, ticks: {color: t.suave, font: {size: 10.5}}};
    // Chart.js solo escucha clics para la leyenda; el mouse sobre los datos lo maneja el dashboard (ver arriba).
    const base = {responsive: true, maintainAspectRatio: false, animation: false, layout: {padding: {top: 20, right: horizontal ? 70 : 12}},
      events: ['click'],
      plugins: {legend: {position: 'top', align: 'start', labels: {color: t.suave, boxWidth: 10, boxHeight: 10, font: {size: 11}, filter: it => !it.text.startsWith('·')}},
        tooltip: {events: []}},
      scales: {x: {...ejes, grid: {display: horizontal, color: ejes.grid.color}}, y: {...ejes, grid: {display: !horizontal, color: ejes.grid.color}}}};
    const o = config.options || {};
    config.options = {...base, ...o, plugins: {...base.plugins, ...(o.plugins || {}), tooltip: {...base.plugins.tooltip, ...(o.plugins?.tooltip || {})}},
      scales: {x: {...base.scales.x, ...(o.scales?.x || {})}, y: {...base.scales.y, ...(o.scales?.y || {})}}};
    config.plugins = [etiquetas, ...(config.plugins || [])];
    const canvas = $(id);
    canvas._dorDetalle = detalle || null; canvas._dorUltimo = '';
    escuchar(canvas);
    graficos[id] = new Chart(canvas, config);
  }

  // ── Pregunta y detalle ──
  let pendiente = null, filasDetalle = [];
  const ordenes = [...document.querySelectorAll('.dor-detalle-orden')];
  const filtrosDetalle = [...document.querySelectorAll('.dor-detalle-filtro')];
  const indicesDetalle = ordenes.map(boton => Number(boton.parentElement.dataset.detalleCol));
  const compararDetalle = new Intl.Collator('es', { numeric: true, sensitivity: 'base' });
  let ordenDetalle = -1, direccionDetalle = 1;
  filtrosDetalle.forEach(input => input.addEventListener('input', pintarDetalle));
  ordenes.forEach((boton, i) => boton.addEventListener('click', () => {
    direccionDetalle = ordenDetalle === i ? -direccionDetalle : 1;
    ordenDetalle = i;
    pintarDetalle();
  }));
  function preguntar(titulo, filas) {
    pendiente = {titulo, filas};
    $('dor-pregunta-txt').textContent = '¿Abrir el detalle ' + (titulo.startsWith('el ') ? 'del ' + titulo.slice(3) : 'de ' + titulo) + ' (' + filas.length + ' ticket' + (filas.length === 1 ? '' : 's') + ')?';
    $('dor-pregunta').hidden = false;
  }
  $('dor-pregunta-no').addEventListener('click', () => { $('dor-pregunta').hidden = true; });
  document.addEventListener('click', ev => {
    const p = $('dor-pregunta'); if (p.hidden || p.contains(ev.target) || ev.target.closest('canvas, .dor-kpi, .dor-gauge, .dor-celda')) return;
    p.hidden = true;
  });
  $('dor-pregunta-si').addEventListener('click', () => {
    $('dor-pregunta').hidden = true; if (!pendiente) return;
    filasDetalle = pendiente.filas;
    $('dor-detalle-titulo').textContent = 'Selección: ' + pendiente.titulo;
    $('dor-detalle-sub').textContent = $('dor-rango').textContent + filtrosTexto();
    $('dor-buscar').value = '';
    filtrosDetalle.forEach(input => { input.value = ''; });
    ordenDetalle = -1;
    pintarDetalle(); $('dor-detalle').hidden = false;
    $('dor-detalle').scrollIntoView({behavior: 'smooth', block: 'start'});
  });
  $('dor-detalle-cerrar').addEventListener('click', () => { $('dor-detalle').hidden = true; });
  $('dor-buscar').addEventListener('input', pintarDetalle);
  const ESTADO = {completed: 'Cerrado', closed: 'Cerrado', inprocess: 'En proceso', dispatched: 'Despachado', accepted: 'Aceptado', canceled: 'Cancelado', cancelled: 'Cancelado'};
  const columnasDetalle = r => [r.id, r.site, r.oficina, nombreRegion(r.region), r.contrata, r.tecnico, ESTADO[r.estado] || r.estado,
    r.sla === true ? 'Normal' : r.sla === false ? 'Fuera de SLA' : '—', r.parada ? 'Sí' : '', fechaHora(r.creado), fechaHora(r.despacho), fechaHora(r.cierre), r.causa];
  function visiblesDetalle() {
    const q = $('dor-buscar').value.trim().toLowerCase();
    const filtros = filtrosDetalle.map(input => input.value.trim().toLowerCase());
    const filas = filasDetalle.map(r => ({ r, celdas: columnasDetalle(r) })).filter(({ celdas }) =>
      (!q || celdas.join(' ').toLowerCase().includes(q)) &&
      filtros.every((valor, i) => !valor || String(celdas[indicesDetalle[i]] ?? '').toLowerCase().includes(valor)));
    if (ordenDetalle >= 0) {
      const indice = indicesDetalle[ordenDetalle];
      const campoFecha = { 9: 'creado', 10: 'despacho', 11: 'cierre' }[indice];
      const valor = fila => String((campoFecha ? fila.r[campoFecha] : fila.celdas[indice]) ?? '');
      filas.sort((a, b) => compararDetalle.compare(valor(a), valor(b)) * direccionDetalle);
    }
    return filas.map(({ r }) => r);
  }
  function pintarDetalle() {
    ordenes.forEach((boton, i) => {
      const activo = i === ordenDetalle;
      boton.querySelector('span').textContent = activo ? (direccionDetalle === 1 ? '↑' : '↓') : '↕';
      if (activo) boton.parentElement.setAttribute('aria-sort', direccionDetalle === 1 ? 'ascending' : 'descending');
      else boton.parentElement.removeAttribute('aria-sort');
    });
    const filas = visiblesDetalle(), cuerpo = $('dor-detalle-filas'); cuerpo.replaceChildren();
    $('dor-detalle-n').textContent = filas.length + ' tickets';
    for (const r of filas.slice(0, 800)) {
      const tr = el('tr');
      const celdas = columnasDetalle(r);
      indicesDetalle.forEach(i => {
        const v = celdas[i];
        const td = el('td');
        if (i === 6) td.append(el('span', 'dor-chip dor-chip-' + (r.completado ? 'ok' : r.cancelado ? 'gris' : 'proceso'), v));
        else if (i === 7 && v !== '—') td.append(el('span', 'dor-chip dor-chip-' + (r.sla ? 'ok' : 'mal'), v));
        else td.textContent = v;
        tr.append(td);
      });
      cuerpo.append(tr);
    }
  }
  $('dor-excel').addEventListener('click', () => {
    const cab = ['Ticket Id', 'Site ID', 'FM Office', 'Región', 'Contrata', 'Técnico', 'Estado', 'SLA', 'Parada de reloj', 'Creado', 'Despacho', 'Cierre', 'Causa'];
    const elegirColumnas = fila => indicesDetalle.map(i => fila[i]);
    const filas = visiblesDetalle().map(r => elegirColumnas(columnasDetalle(r)));
    const hoja = XLSX.utils.aoa_to_sheet([elegirColumnas(cab), ...filas]);
    hoja['!autofilter'] = { ref: hoja['!ref'] };
    hoja['!cols'] = elegirColumnas([24, 15, 30, 18, 18, 38, 18, 16, 20, 21, 21, 21, 45])
      .map(wch => ({ wch }));
    const libro = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(libro, hoja, 'Detalle CM');
    XLSX.writeFile(libro, 'detalle_operacion_cm.xlsx');
  });
  function filtrosTexto() {
    const partes = [];
    for (const [id, nombre] of [['region', 'Región'], ['oficina', E.oficina || 'FM Office'], ['contrata', 'Contrata'], ['tecnico', 'Técnico'], ['rm', E.rm || 'RM']]) {
      if (elegidos[id].size) partes.push(nombre + ': ' + [...elegidos[id]].map(v => textoOpcion(id, v)).join(', '));
    }
    return partes.length ? ' · ' + partes.join(' · ') : '';
  }

  // ── Pintado ──
  function kpi(titulo, cuerpo, pie) {
    const a = el('article', 'dor-kpi'); a.append(el('h2', null, titulo)); a.append(cuerpo); if (pie) a.append(el('p', null, pie)); return a;
  }
  function valor(txt, cls, delta) {
    const s = el('div', 'dor-valor'); s.append(el('strong', cls || '', txt));
    if (delta) s.append(el('small', 'dor-delta ' + delta.cls, delta.txt)); return s;
  }
  const deltaPp = (a, b, mejorSube = true) => {
    if (a === null || b === null) return null; const d = a - b;
    if (Math.abs(d) < 0.05) return {txt: '= sin cambio', cls: ''};
    return {txt: (d > 0 ? '▲ ' : '▼ ') + num(Math.abs(d), 1) + ' pp', cls: (d > 0) === mejorSube ? 'sube' : 'baja'};
  };
  const nivel = v => v === null ? '' : v >= META ? 'dor-ok' : v >= 85 ? 'dor-medio' : 'dor-mal';

  function pintar() {
    const U = universo();
    const hasta = D.hasta || new Date().toISOString().slice(0, 10);
    const D_ = dias(st.dias, hasta), prev = dias(st.dias, D_[0] && new Date(new Date(D_[0] + 'T12:00:00').getTime() - 864e5).toISOString().slice(0, 10));
    const dentro = (s, lista) => { const x = dia(s); return x >= lista[0] && x <= lista[lista.length - 1]; };
    $('dor-rango').textContent = 'Del ' + largo(D_[0]) + ' al ' + largo(hasta) + ' (' + st.dias + ' días)';
    const regiones = ['LIMA', 'CENTRO', ...[...new Set(U.map(r => r.region))].filter(r => r !== 'LIMA' && r !== 'CENTRO')].filter(r => U.some(x => x.region === r));
    const cierres = U.filter(r => r.completado && dentro(r.cierre, D_)), cierresPrev = U.filter(r => r.completado && dentro(r.cierre, prev));
    const slaDe = lista => { const m = lista.filter(r => r.sla !== null); return {ok: m.filter(r => r.sla).length, n: m.length, pct: pct(m.filter(r => r.sla).length, m.length)}; };
    const sla = slaDe(cierres), slaPrev = slaDe(cierresPrev);
    const desp = lista => { const m = lista.filter(r => diasDesdeDespacho(r) !== null); const k = n => m.filter(r => diasDesdeDespacho(r) === n).length;
      return {mismo: pct(k(0), m.length), segundo: pct(k(1), m.length), n: m.length}; };
    const ds = desp(cierres), dsPrev = desp(cierresPrev);
    const corte = hasta, antes = D_[D_.length - 2] || corte;
    const backlogEn = (d, reg) => U.filter(r => (!reg || r.region === reg) && abiertoAl(r, d));
    // Eficiencia: por cada día, cierres (sin visitas truncas) / técnicos que cerraron ese día; se promedia en el periodo.
    const efDia = (d, reg) => { const c = U.filter(r => r.region === reg && cerroEl(r, d) && r.familia !== 'Visita trunca');
      const t = new Set(c.map(r => r.tecnico).filter(x => x && x !== 'Sin técnico')); return t.size ? {v: c.length / t.size, n: c.length, t: t.size} : null; };

    // KPIs
    const k = $('dor-kpis'); k.replaceChildren();
    k.append(kpi('Cumplimiento de SLA', valor(sla.pct === null ? '—' : num(sla.pct, 1) + '%', nivel(sla.pct), deltaPp(sla.pct, slaPrev.pct)),
      num(sla.ok) + ' de ' + num(sla.n) + ' dentro del SLA · meta ' + META + '%'));
    const cd = el('div', 'dor-doble');
    cd.append(valor(ds.mismo === null ? '—' : num(ds.mismo, 1) + '%', '', deltaPp(ds.mismo, dsPrev.mismo)), valor(ds.segundo === null ? '—' : num(ds.segundo, 1) + '%', '', deltaPp(ds.segundo, dsPrev.segundo)));
    cd.firstChild.prepend(el('span', null, 'Mismo día')); cd.lastChild.prepend(el('span', null, 'Al 2.º día'));
    k.append(kpi('Cierre desde el despacho', cd, ds.n ? 'Acumulado al 2.º día ' + num((ds.mismo || 0) + (ds.segundo || 0), 1) + '% · ' + num(ds.n) + ' cerrados' : ''));
    const ef = el('div', 'dor-doble'); let atendidos = 0, tecDia = 0, diasConDato = 0;
    for (const reg of regiones.slice(0, 2)) {
      const vals = D_.map(d => efDia(d, reg)).filter(Boolean), prom = vals.length ? vals.reduce((s, x) => s + x.v, 0) / vals.length : null;
      vals.forEach(x => { atendidos += x.n; tecDia += x.t; }); diasConDato = Math.max(diasConDato, vals.length);
      const v = valor(prom === null ? '—' : num(prom, 1), prom === null ? '' : prom >= META_EF ? 'dor-ok' : 'dor-mal'); v.prepend(el('span', 'dor-punto', nombreRegion(reg))); v.firstChild.style.setProperty('--c', COLOR_REGION(reg)); ef.append(v);
    }
    k.append(kpi('Eficiencia (tickets por técnico al día)', ef, num(atendidos) + ' atendidos · ' + (diasConDato ? num(tecDia / diasConDato, 1) : '0') + ' técnicos por día · meta ' + META_EF));
    const bl = el('div', 'dor-doble');
    for (const reg of regiones.slice(0, 2)) {
      const hoy = backlogEn(corte, reg).length, ayer = backlogEn(antes, reg).length, d = hoy - ayer;
      const base = BASE[reg]; const v = valor(num(hoy), base !== undefined ? (hoy <= base ? 'dor-ok' : 'dor-mal') : '',
        {txt: d === 0 ? '= sin cambio' : (d > 0 ? '▲ ' : '▼ ') + Math.abs(d), cls: d > 0 ? 'baja' : d < 0 ? 'sube' : ''});
      v.prepend(el('span', 'dor-punto', nombreRegion(reg))); v.firstChild.style.setProperty('--c', COLOR_REGION(reg)); bl.append(v);
    }
    k.append(kpi('Backlog al corte', bl, Object.keys(BASE).length ? 'Línea base ' + regiones.slice(0, 2).map(r => nombreRegion(r) + ' ' + (BASE[r] ?? '—')).join(' · ') : 'Tickets abiertos al cierre del ' + largo(corte)));
    const fl = el('div', 'dor-triple');
    const nDesp = U.filter(r => dentro(r.despacho, D_)).length, nCanc = U.filter(r => r.cancelado && dentro(r.cancelacion, D_)).length;
    [['Despachados', nDesp], ['Cerrados', cierres.length], ['Cancelados', nCanc]].forEach(([t, v]) => { const x = valor(num(v)); x.prepend(el('span', null, t)); fl.append(x); });
    k.append(kpi('Flujo del periodo', fl));
    const pr = el('div', 'dor-triple'), abiertos = backlogEn(corte), enParada = abiertos.filter(r => r.parada);
    const xt = valor(num(enParada.length)); xt.prepend(el('span', null, 'Total')); pr.append(xt);
    for (const reg of regiones.slice(0, 2)) { const x = valor(num(enParada.filter(r => r.region === reg).length)); x.prepend(el('span', 'dor-punto', nombreRegion(reg))); x.firstChild.style.setProperty('--c', COLOR_REGION(reg)); pr.append(x); }
    k.append(kpi('Tickets en parada de reloj', pr, 'De ' + num(abiertos.length) + ' abiertos al corte (con el reloj de SLA en pausa)'));
    [...k.children].forEach((a, i) => a.addEventListener('click', () => {
      const listas = [[cierres, 'los cierres del periodo'], [cierres, 'los cierres del periodo'], [cierres, 'los cierres del periodo'], [abiertos, 'el backlog al ' + largo(corte)], [cierres, 'los cierres del periodo'], [enParada, 'los tickets en parada de reloj']];
      preguntar(listas[i][1], listas[i][0]);
    }));

    // SLA por día (del día o acumulado)
    let acOk = 0, acN = 0;
    const slaDia = D_.map(d => { const c = U.filter(r => cerroEl(r, d) && r.sla !== null); const ok = c.filter(r => r.sla).length; acOk += ok; acN += c.length;
      return {dia: pct(ok, c.length), acu: pct(acOk, acN)}; });
    const serie = slaDia.map(x => { const v = st.modo === 'dia' ? x.dia : x.acu; return v === null ? null : Math.round(v * 10) / 10; });
    const minimo = Math.min(55, ...serie.filter(v => v !== null).map(v => Math.floor(v / 5) * 5 - 5));
    grafico('dor-sla', {type: 'line', plugins: [corteMeta], data: {labels: D_.map(corto), datasets: [
      {label: 'Cumplimiento de SLA', data: serie, borderWidth: 2.5, tension: .35, spanGaps: true, pointRadius: 4, pointHoverRadius: 6,
        pointBackgroundColor: c => (c.raw ?? 0) >= META ? C.verde : C.rojo, pointBorderColor: c => (c.raw ?? 0) >= META ? C.verde : C.rojo,
        etiqueta: {fmt: v => num(v, 1), color: v => v >= META ? C.verde : C.rojo}},
      {label: 'Meta ≥ ' + META + '%', data: D_.map(() => META), borderColor: tema().suave, borderDash: [6, 5], borderWidth: 1.2, pointRadius: 0, sinClic: true}]},
      options: {scales: {y: {min: minimo, max: 102, ticks: {callback: v => v <= 100 ? v + '%' : ''}}}, plugins: {tooltip: {callbacks: {label: c => c.dataset.label + ': ' + (c.raw === null ? '—' : num(c.raw, 1) + '%')}}}}},
      (i, j) => i === 0 ? {titulo: 'los tickets cerrados ' + (st.modo === 'dia' ? 'el ' + largo(D_[j]) : 'del ' + largo(D_[0]) + ' al ' + largo(D_[j])) + ' · SLA ' + num(serie[j], 1) + '%',
        filas: U.filter(r => r.completado && (st.modo === 'dia' ? cerroEl(r, D_[j]) : dia(r.cierre) >= D_[0] && dia(r.cierre) <= D_[j]))} : null);

    // Medidor de SLA promedio
    const g = $('dor-gauge'), v = sla.pct; g.replaceChildren();
    // Como el del cliente: la escala no es pareja; 0–85 % ocupa la parte izquierda, 85–95 % la parte de arriba
    // y 95–100 % la derecha, para que se note bien cuánto falta para la meta.
    const CX = 110, CY = 108, R = 78;
    const grados = p => { p = Math.max(0, Math.min(100, p ?? 0)); return p <= 85 ? 180 - p / 85 * 75 : p <= 95 ? 105 - (p - 85) / 10 * 60 : 45 - (p - 95) / 5 * 45; };
    const punto = (p, r) => { const a = grados(p) * Math.PI / 180; return [CX + r * Math.cos(a), CY - r * Math.sin(a)]; };
    const arco = (desde, hastaP, color) => { const [x0, y0] = punto(desde, R), [x1, y1] = punto(hastaP, R);
      return '<path d="M ' + x0 + ' ' + y0 + ' A ' + R + ' ' + R + ' 0 0 1 ' + x1 + ' ' + y1 + '" stroke="' + color + '" stroke-width="24" fill="none"/>'; };
    const marca = (p, txt, dx = 0) => { const [x, y] = punto(p, R + 22); return '<text x="' + (x + dx) + '" y="' + (y + 4) + '" text-anchor="middle" class="dor-g-eje">' + txt + '</text>'; };
    const sep = p => { const [x0, y0] = punto(p, R - 13), [x1, y1] = punto(p, R + 13); return '<line x1="' + x0 + '" y1="' + y0 + '" x2="' + x1 + '" y2="' + y1 + '" class="dor-g-sep"/>'; };
    const [ax, ay] = punto(v, R - 6);
    g.innerHTML = '<svg viewBox="0 0 220 132" role="img" aria-label="SLA promedio">' + arco(0, 85, C.rojo) + arco(85, 95, C.ambar) + arco(95, 100, C.verde) + sep(85) + sep(95)
      + marca(0, '0%', 4) + marca(85, '85%') + marca(95, '95%', 4) + marca(100, '100%', -6)
      + (v === null ? '' : '<line x1="' + CX + '" y1="' + CY + '" x2="' + ax + '" y2="' + ay + '" class="dor-g-aguja"/><circle cx="' + CX + '" cy="' + CY + '" r="7" class="dor-g-centro"/>') + '</svg>';
    g.append(el('strong', nivel(v), v === null ? 'Sin dato' : num(v, 1) + '%'), el('small', null, 'Meta ≥ ' + META + '% · ' + num(sla.n) + ' cierres'));
    g.onclick = () => preguntar('los cierres del periodo', cierres);

    // Flujo por región
    const flujos = $('dor-flujos'); flujos.replaceChildren();
    for (const reg of regiones) {
      const card = el('article', 'dor-card'), cab = el('header'), txt = el('div');
      txt.append(el('h2', null, 'Flujo de tickets · ' + nombreRegion(reg)), el('p', null, 'Tickets despachados, cerrados y cancelados cada día en ' + nombreRegion(reg) + '.'));
      cab.append(txt); const caja = el('div', 'dor-canvas'), cv = el('canvas'); cv.id = 'dor-flujo-' + reg; cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', 'Flujo de tickets ' + nombreRegion(reg));
      caja.append(cv); card.append(cab, caja); flujos.append(card);
      const R = U.filter(r => r.region === reg);
      const series = [['Despachados', d => R.filter(r => dia(r.despacho) === d), C.azul], ['Cerrados', d => R.filter(r => cerroEl(r, d)), C.verde], ['Cancelados', d => R.filter(r => r.cancelado && dia(r.cancelacion) === d), C.ambar]];
      grafico(cv.id, {type: 'bar', data: {labels: D_.map(corto), datasets: series.map(([label, f, color]) => ({label, data: D_.map(d => f(d).length), backgroundColor: color, borderRadius: 3, maxBarThickness: 16, etiqueta: {color: tema().texto}}))}},
        (i, j) => ({titulo: 'los ' + series[i][0].toLowerCase() + ' de ' + nombreRegion(reg) + ' el ' + largo(D_[j]), filas: series[i][1](D_[j])}));
    }

    // Backlog por región + línea base
    const dsB = [];
    regiones.forEach((reg, i) => {
      dsB.push({label: nombreRegion(reg), data: D_.map(d => backlogEn(d, reg).length), borderColor: COLOR_REGION(reg), backgroundColor: COLOR_REGION(reg), borderWidth: 2, tension: .3, pointRadius: 3,
        etiqueta: {pos: i % 2 ? 'arriba' : 'abajo', color: COLOR_REGION(reg)}, _reg: reg});
      if (BASE[reg] !== undefined) dsB.push({label: 'Línea base ' + nombreRegion(reg) + ' (' + BASE[reg] + ')', data: D_.map(() => BASE[reg]), borderColor: COLOR_REGION(reg), borderDash: [5, 5], borderWidth: 1.2, pointRadius: 0, sinClic: true});
    });
    grafico('dor-backlog', {type: 'line', data: {labels: D_.map(corto), datasets: dsB}, options: {scales: {y: {beginAtZero: true}}}},
      (i, j) => dsB[i]._reg ? {titulo: 'el backlog de ' + nombreRegion(dsB[i]._reg) + ' al cierre del ' + largo(D_[j]), filas: backlogEn(D_[j], dsB[i]._reg)} : null);

    // Antigüedad del backlog al corte
    const tramos = [['0–1 días', 0, 1, C.verde], ['2–3 días', 2, 3, C.lima], ['4–7 días', 4, 7, C.ambar], ['8–15 días', 8, 15, C.naranja], ['Más de 15 días', 16, 1e9, C.rojo]];
    const finCorte = Date.parse(corte + 'T23:59:59');
    const edad = r => Math.floor((finCorte - Date.parse(inicio(r))) / 864e5);
    const enTramo = (reg, t) => backlogEn(corte, reg).filter(r => edad(r) >= t[1] && edad(r) <= t[2]);
    grafico('dor-antiguedad', {type: 'bar', data: {labels: regiones.map(r => nombreRegion(r) + ' (' + backlogEn(corte, r).length + ')'),
      datasets: tramos.map(t => ({label: t[0], data: regiones.map(reg => enTramo(reg, t).length), backgroundColor: t[3], maxBarThickness: 46, etiqueta: {pos: 'centro', color: '#fff'}}))},
      options: {indexAxis: 'y', scales: {x: {stacked: true, beginAtZero: true}, y: {stacked: true}}}},
      (i, j) => ({titulo: 'el backlog de ' + nombreRegion(regiones[j]) + ' con ' + tramos[i][0], filas: enTramo(regiones[j], tramos[i])}));

    // Cierre según días desde el despacho (100 %)
    const grupos = [['Mismo día', n => n === 0, 'rgba(27,175,122,.75)'], ['Segundo día', n => n === 1, 'rgba(42,120,214,.75)'], ['Después del 2.º día', n => n >= 2, 'rgba(235,104,52,.65)']];
    const cierresDia = d => U.filter(r => cerroEl(r, d) && diasDesdeDespacho(r) !== null);
    grafico('dor-dias-cierre', {type: 'line', data: {labels: D_.map(corto), datasets: grupos.map(([label, f, color]) => ({label, fill: true, backgroundColor: color, borderColor: color, pointRadius: 2, tension: .35,
      data: D_.map(d => { const c = cierresDia(d); return c.length ? Math.round(c.filter(r => f(diasDesdeDespacho(r))).length / c.length * 1000) / 10 : null; }),
      etiqueta: {pos: 'abajo', fmt: v => num(v, 1), color: tema().texto}}))},
      options: {bandas: true, scales: {y: {stacked: true, min: 0, max: 100, ticks: {callback: v => v + '%'}}}}},
      (i, j) => ({titulo: 'los cerrados el ' + largo(D_[j]) + ' · ' + grupos[i][0].toLowerCase() + ' ' + num(graficos['dor-dias-cierre'].data.datasets[i].data[j], 1) + '%', filas: cierresDia(D_[j]).filter(r => grupos[i][1](diasDesdeDespacho(r)))}));

    // Eficiencia por día
    const dsE = regiones.map((reg, i) => ({label: nombreRegion(reg), data: D_.map(d => { const x = efDia(d, reg); return x ? Math.round(x.v * 100) / 100 : null; }), spanGaps: true,
      borderColor: COLOR_REGION(reg), backgroundColor: COLOR_REGION(reg), borderWidth: 2, tension: .35, pointRadius: 3, etiqueta: {pos: i % 2 ? 'arriba' : 'abajo', fmt: v => num(v, 1), color: COLOR_REGION(reg)}, _reg: reg}));
    dsE.push({label: 'Meta (' + META_EF + ')', data: D_.map(() => META_EF), borderColor: tema().suave, borderDash: [6, 5], borderWidth: 1.2, pointRadius: 0, sinClic: true});
    grafico('dor-eficiencia', {type: 'line', data: {labels: D_.map(corto), datasets: dsE}, options: {scales: {y: {beginAtZero: true}},
      plugins: {tooltip: {callbacks: {label: c => { if (!dsE[c.datasetIndex]._reg) return c.dataset.label; const x = efDia(D_[c.dataIndex], dsE[c.datasetIndex]._reg);
        return x ? c.dataset.label + ': ' + num(x.v, 2) + ' por técnico · ' + x.n + ' tickets · ' + x.t + ' técnicos' : c.dataset.label + ': —'; }}}}}},
      (i, j) => { if (!dsE[i]._reg) return null; const x = efDia(D_[j], dsE[i]._reg);
        return {titulo: 'los cerrados de ' + nombreRegion(dsE[i]._reg) + ' el ' + largo(D_[j]) + (x ? ' · ' + num(x.v, 2) + ' por técnico (' + x.n + ' tickets ÷ ' + x.t + ' técnicos, sin visitas truncas)' : ''), filas: U.filter(r => r.region === dsE[i]._reg && cerroEl(r, D_[j]))}; });

    // Tiempos de atención por FM Office (+ total por región)
    const filasT = [];
    for (const reg of regiones) {
      const ofis = [...new Set(cierres.filter(r => r.region === reg).map(r => r.oficina))].sort();
      ofis.forEach(o => filasT.push({nombre: o.replace(/^HUAWEI\s+/i, ''), filas: cierres.filter(r => r.oficina === o)}));
      filasT.push({nombre: 'Total ' + nombreRegion(reg), filas: cierres.filter(r => r.region === reg), total: true});
    }
    const med = (filas, a, b) => { const m = mediana(filas.map(r => horas(r[a], r[b])).filter(h => h !== null && h >= 0)); return m === null ? null : Math.round(m * 10) / 10; };
    $('dor-tiempos').parentElement.style.height = Math.max(220, filasT.length * 30 + 70) + 'px';
    grafico('dor-tiempos', {type: 'bar', data: {labels: filasT.map(f => f.nombre), datasets: [
      {label: 'Despacho → llegada', data: filasT.map(f => med(f.filas, 'despacho', 'llegada')), backgroundColor: C.azul, maxBarThickness: 20, etiqueta: {pos: 'centro', fmt: v => num(v, 1), color: '#fff'}},
      {label: 'Llegada → cierre', data: filasT.map(f => med(f.filas, 'llegada', 'cierre')), backgroundColor: C.naranja, maxBarThickness: 20, etiqueta: {pos: 'centro', fmt: v => num(v, 1), color: '#fff'}}]},
      options: {indexAxis: 'y', scales: {x: {stacked: true, beginAtZero: true, title: {display: true, text: 'Horas (mediana)', color: tema().suave}}, y: {stacked: true, ticks: {font: c => ({size: 10.5, weight: filasT[c.index]?.total ? 'bold' : 'normal'})}}}}},
      (i, j) => ({titulo: 'los cierres de ' + filasT[j].nombre + ' · mediana ' + (i ? 'llegada → cierre' : 'despacho → llegada') + ' ' + num(graficos['dor-tiempos'].data.datasets[i].data[j], 1) + ' h', filas: filasT[j].filas}));

    // Causa raíz
    const total = cierres.length;
    const porFam = {}; cierres.forEach(r => { (porFam[r.familia] ||= []).push(r); });
    const porCausa0 = {}; cierres.forEach(r => { porCausa0[r.causa] = (porCausa0[r.causa] || 0) + 1; });
    const fams = Object.keys(porFam).sort((a, b) => porFam[b].length - porFam[a].length);
    const cuenta = f => porFam[f]?.length || 0;
    $('dor-causa-sub').textContent = num(total) + ' tickets cerrados en el periodo, por la causa que registró el técnico al cerrar';
    if (fams.length && !D.resumen_familias) {
      const top = fams[0];
      $('dor-causa-resumen').textContent = top + ' concentra más cierres: ' + cuenta(top) + ' (' + num(pct(cuenta(top), total), 1) + '%). '
        + (fams[1] ? 'Le sigue ' + fams[1] + ' con ' + cuenta(fams[1]) + ' (' + num(pct(cuenta(fams[1]), total), 1) + '%). ' : '') + (porCausa0['(sin causa)'] ? porCausa0['(sin causa)'] + ' cierres no tienen causa registrada.' : '');
    } else if (fams.length) {
      const top = fams[0], energia = cuenta('Corte de energía comercial') + cuenta('Baterías y autonomía');
      $('dor-causa-resumen').textContent = top + ' es la familia con más cierres: ' + cuenta(top) + ' (' + num(pct(cuenta(top), total), 1) + '%). Energía comercial y baterías suman '
        + num(pct(energia, total), 1) + '% de los cierres; ' + cuenta('Baterías y autonomía') + ' son por baterías o baja autonomía (se pueden prevenir). '
        + cuenta('Visita trunca') + ' cierres (' + num(pct(cuenta('Visita trunca'), total), 1) + '%) fueron visitas truncas, ' + cuenta('Falsa alarma o sin falla') + ' falsas alarmas o sin falla y '
        + cuenta('Sin causa registrada') + ' se cerraron sin causa registrada.';
    } else $('dor-causa-resumen').textContent = 'Sin cierres en el periodo.';
    const altoBarras = n => Math.max(240, n * 26 + 70) + 'px';
    $('dor-familias').parentElement.style.height = altoBarras(fams.length);
    const dsFam = regiones.map((reg, i) => ({label: nombreRegion(reg), data: fams.map(f => porFam[f].filter(r => r.region === reg).length), backgroundColor: COLOR_REGION(reg), maxBarThickness: 18,
      etiqueta: i === regiones.length - 1 ? {pos: 'fin', cero: true, fmt: (v, j) => cuenta(fams[j]) + ' · ' + num(pct(cuenta(fams[j]), total), 1) + '%'} : null, _reg: reg}));
    grafico('dor-familias', {type: 'bar', data: {labels: fams, datasets: dsFam}, options: {indexAxis: 'y', scales: {x: {stacked: true, beginAtZero: true}, y: {stacked: true}}}},
      (i, j) => ({titulo: 'los cierres por ' + fams[j] + (dsFam[i]._reg ? ' en ' + nombreRegion(dsFam[i]._reg) : ''), filas: porFam[fams[j]].filter(r => r.region === dsFam[i]._reg)}));
    const porCausa = {}; cierres.forEach(r => { (porCausa[r.causa] ||= []).push(r); });
    const causas = Object.keys(porCausa).sort((a, b) => porCausa[b].length - porCausa[a].length).slice(0, 15);
    let acumulado = 0; const acu = causas.map(c => (acumulado += porCausa[c].length, pct(acumulado, total)));
    $('dor-causas').parentElement.style.height = altoBarras(causas.length);
    const dsCau = regiones.map((reg, i) => ({label: nombreRegion(reg), data: causas.map(c => porCausa[c].filter(r => r.region === reg).length), backgroundColor: COLOR_REGION(reg), maxBarThickness: 18,
      etiqueta: i === regiones.length - 1 ? {pos: 'fin', cero: true, fmt: (v, j) => porCausa[causas[j]].length + ' · ' + num(pct(porCausa[causas[j]].length, total), 1) + '% · ac. ' + num(acu[j], 1) + '%'} : null, _reg: reg}));
    grafico('dor-causas', {type: 'bar', data: {labels: causas.map(c => c.length > 24 ? c.slice(0, 23) + '…' : c), datasets: dsCau},
      options: {indexAxis: 'y', layout: {padding: {top: 20, right: 130}}, scales: {x: {stacked: true, beginAtZero: true}, y: {stacked: true}}}},
      (i, j) => ({titulo: 'los cierres con causa «' + causas[j] + '»' + ' en ' + nombreRegion(dsCau[i]._reg), filas: porCausa[causas[j]].filter(r => r.region === dsCau[i]._reg)}));

    // Familias por FM Office (mapa de calor)
    const tabla = $('dor-calor'); tabla.replaceChildren();
    const ofis = [...new Set(cierres.map(r => r.oficina))].sort((a, b) => cierres.filter(r => r.oficina === b).length - cierres.filter(r => r.oficina === a).length);
    const thead = el('thead'), hr = el('tr'); hr.append(el('th', null, 'FM Office'), el('th', 'dor-num', 'Cerrados')); fams.forEach(f => hr.append(el('th', 'dor-num', f))); thead.append(hr); tabla.append(thead);
    const tb = el('tbody');
    for (const o of ofis) {
      const filas = cierres.filter(r => r.oficina === o), tr = el('tr'), nom = el('td'); nom.append(el('strong', null, o.replace(/^HUAWEI\s+/i, '')), el('small', null, ' · ' + nombreRegion(filas[0].region)));
      tr.append(nom, el('td', 'dor-num', num(filas.length)));
      for (const f of fams) {
        const sel = filas.filter(r => r.familia === f), p = pct(sel.length, filas.length), td = el('td', 'dor-num dor-celda', sel.length ? num(p, 1) + '%' : '');
        if (sel.length) { td.style.setProperty('--a', String(Math.min(.85, .08 + p / 60))); td.title = sel.length + ' tickets'; td.addEventListener('click', () => preguntar('los cierres de ' + o + ' por ' + f, sel)); }
        tr.append(td);
      }
      tb.append(tr);
    }
    tabla.append(tb);
  }

  // ── Eventos ──
  document.querySelectorAll('[data-dias]').forEach(b => b.addEventListener('click', () => {
    st.dias = Number(b.dataset.dias); document.querySelectorAll('[data-dias]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); pintar();
  }));
  document.querySelectorAll('[data-modo]').forEach(b => b.addEventListener('click', () => {
    st.modo = b.dataset.modo; document.querySelectorAll('[data-modo]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); pintar();
  }));
  $('dor-sin-despachar').addEventListener('change', pintar);
  $('dor-limpiar').addEventListener('click', () => { for (const id of Object.keys(FILTROS)) { elegidos[id].clear(); $('dor-' + id)._sincronizar(); } $('dor-sin-despachar').checked = false; pintar(); });
  new MutationObserver(pintar).observe(document.body, {attributes: true, attributeFilter: ['class']});
  pintar();
})();
