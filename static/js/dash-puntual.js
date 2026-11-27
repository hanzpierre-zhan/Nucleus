// Piezas comunes de los dashboards "puntuales" (Cotizaciones y Caja Chica) con el mismo estilo que el de Claro:
// tarjetas dor-kpi, gráficos con el número siempre visible y detalle al hacer clic. Solo lee datos.
(function () {
  'use strict';
  const el = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt !== undefined && txt !== null) n.textContent = txt; return n; };
  const fmtNum = (v, d = 0) => new Intl.NumberFormat('es-PE', {minimumFractionDigits: d, maximumFractionDigits: d}).format(v || 0);
  const soles = v => 'S/ ' + new Intl.NumberFormat('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(v || 0);
  const solesCorto = v => 'S/ ' + new Intl.NumberFormat('es-PE', {notation: 'compact', maximumFractionDigits: 1}).format(v || 0);
  const pct = (a, b) => b ? 100 * a / b : null;
  const suma = (lista, f) => lista.reduce((t, r) => t + (Number(f(r)) || 0), 0);
  const promedio = lista => lista.length ? lista.reduce((a, b) => a + b, 0) / lista.length : null;
  const diasEntre = (a, b) => (a && b) ? Math.round((Date.parse(b.slice(0, 10) + 'T12:00:00') - Date.parse(a.slice(0, 10) + 'T12:00:00')) / 864e5) : null;
  const mesAnterior = mes => { const [y, m] = mes.split('-').map(Number); const d = new Date(y, m - 2, 15); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
  const nombreMes = mes => new Intl.DateTimeFormat('es-PE', {month: 'long'}).format(new Date(mes + '-15T12:00:00'));
  const css = k => getComputedStyle(document.querySelector('.di-page') || document.body).getPropertyValue(k).trim();
  const COLOR = {cobra: '#2a78d6', refact: '#1baf7a', ok: '#1baf7a', medio: '#eda100', mal: '#e34948', muyMal: '#a32d2d', gris: '#898781', azul: '#2a78d6', celeste: '#7fb2ee'};

  // ── Tarjetas (mismo HTML que las de Claro) ──
  function kpi(titulo, cuerpo, pie, alClic) {
    const a = el('article', 'dor-kpi'); a.append(el('h2', null, titulo), cuerpo); if (pie) a.append(el('p', null, pie));
    if (alClic) { a.tabIndex = 0; a.addEventListener('click', alClic); a.addEventListener('keydown', e => { if (e.key === 'Enter') alClic(); }); } else a.style.cursor = 'default';
    return a;
  }
  function valor(txt, cls, delta, etiqueta, punto) {
    const s = el('div', 'dor-valor');
    if (etiqueta) { const e = el('span', punto ? 'dor-punto' : '', etiqueta); if (punto) e.style.setProperty('--c', punto); s.append(e); }
    s.append(el('strong', cls || '', txt));
    if (delta) s.append(el('small', 'dor-delta ' + delta.cls, delta.txt));
    return s;
  }
  function doble(...valores) { const d = el('div', valores.length > 2 ? 'dor-triple' : 'dor-doble'); d.append(...valores); return d; }
  // delta: compara a contra b. mejorSube indica si subir es bueno (verde) o malo (rojo); null = sin color.
  function delta(a, b, {mejorSube = true, unidad = '%', relativo = true, dec = 1} = {}) {
    if (a === null || b === null || a === undefined || b === undefined) return null;
    const d = relativo ? (b ? 100 * (a - b) / b : null) : a - b;
    if (d === null) return null;
    if (Math.abs(d) < 0.05) return {txt: '= sin cambio', cls: ''};
    return {txt: (d > 0 ? '▲ ' : '▼ ') + fmtNum(Math.abs(d), dec) + ' ' + unidad, cls: mejorSube === null ? '' : (d > 0) === mejorSube ? 'sube' : 'baja'};
  }

  // ── Gráficos ──
  const graficos = new Map();
  function etiquetas(formato) {
    return {id: 'puntualValores', afterDatasetsDraw(chart) {
      const {ctx, chartArea: area} = chart, ocupados = [];
      ctx.save(); ctx.font = '600 10.5px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.lineWidth = 3; ctx.lineJoin = 'round'; ctx.strokeStyle = css('--ios-card-bg'); ctx.fillStyle = css('--ios-label');
      for (const meta of chart.getSortedVisibleDatasetMetas().slice().reverse()) {
        const ds = chart.data.datasets[meta.index];
        if (ds.sinEtiqueta) continue;
        const horizontal = meta.vScale && meta.vScale.axis === 'x', apilado = meta.type === 'bar' && meta.vScale && meta.vScale.options.stacked;
        meta.data.forEach((p, i) => {
          const v = ds.data[i]; if (typeof v !== 'number' || !v || p.skip) return;
          const txt = (ds.formato || formato)(v, i, ds), w = ctx.measureText(txt).width;
          let {x, y} = p;
          if (horizontal) {
            if (apilado) { if (Math.abs(x - p.base) < w + 8) return; x = (x + p.base) / 2; }
            else x += x + w + 8 <= area.right ? w / 2 + 6 : -w / 2 - 6;
          } else if (apilado) { if (Math.abs(y - p.base) < 15) return; y = (y + p.base) / 2; }
          else y -= 10;
          x = Math.max(area.left + w / 2, Math.min(area.right - w / 2, x)); y = Math.max(area.top + 6, Math.min(area.bottom - 6, y));
          const caja = {l: x - w / 2 - 3, r: x + w / 2 + 3, t: y - 7, b: y + 7};
          if (ocupados.some(o => caja.l < o.r && caja.r > o.l && caja.t < o.b && caja.b > o.t)) return;
          ocupados.push(caja); ctx.strokeText(txt, x, y); ctx.fillText(txt, x, y);
        });
      }
      ctx.restore();
    }};
  }
  function opciones({horizontal = false, apilado = false, formatoEje = v => fmtNum(v), tooltip, alClic} = {}) {
    const texto = css('--ios-secondary'), linea = css('--ios-hairline');
    const valores = {beginAtZero: true, stacked: apilado, grace: '18%', grid: {color: linea}, border: {display: false}, ticks: {color: texto, font: {size: 10}, maxTicksLimit: 5, callback: formatoEje}};
    const nombres = {stacked: apilado, grid: {display: false}, border: {display: false}, ticks: {color: texto, font: {size: 10.5}, autoSkip: !horizontal, maxRotation: 0}};
    return {responsive: true, maintainAspectRatio: false, indexAxis: horizontal ? 'y' : 'x', layout: {padding: {top: 14, right: horizontal ? 18 : 6}},
      interaction: {mode: 'nearest', intersect: true},
      scales: horizontal ? {x: valores, y: nombres} : {x: nombres, y: valores},
      onHover: (e, items, chart) => { chart.canvas.style.cursor = items.length && alClic ? 'pointer' : 'default'; },
      onClick: (e, items, chart) => { if (items.length && alClic) alClic(items[0].index, items[0].datasetIndex, chart); },
      plugins: {legend: {display: false, labels: {color: texto}}, tooltip: tooltip || {}}};
  }
  function montar(id, config, hayDatos, formato = v => fmtNum(v)) {
    const lienzo = document.getElementById(id); if (!lienzo || !window.Chart) return;
    graficos.get(id)?.destroy(); graficos.delete(id);
    const caja = lienzo.parentElement; caja.querySelector('.df-empty')?.remove();
    lienzo.hidden = !hayDatos;
    if (!hayDatos) { caja.append(el('span', 'df-empty', 'Sin datos para esta selección')); return; }
    config.plugins = [...(config.plugins || []), etiquetas(formato)];
    graficos.set(id, new Chart(lienzo, config));
  }

  // ── Detalle (tabla bajo los gráficos, como en Claro) ──
  function detalle(caja, titulo, filas, columnas, archivo) {
    caja.hidden = false; caja.replaceChildren();
    const cab = el('header'), t = el('div'); t.append(el('h2', null, titulo), el('p', null, fmtNum(filas.length) + ' registros'));
    const acciones = el('div', 'dor-detalle-acciones');
    const excel = el('button', null, 'Excel'); excel.type = 'button';
    excel.addEventListener('click', () => {
      const libro = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(libro, XLSX.utils.aoa_to_sheet([columnas.map(c => c[0]), ...filas.map(r => columnas.map(c => c[2] ? c[2](r) : c[1](r)))]), 'Detalle');
      XLSX.writeFile(libro, archivo + '.xlsx');
    });
    const cerrar = el('button', null, 'Cerrar'); cerrar.type = 'button'; cerrar.addEventListener('click', () => { caja.hidden = true; });
    acciones.append(excel, cerrar); cab.append(t, acciones);
    const scroll = el('div', 'dor-tabla-scroll'), tabla = el('table', 'dor-tabla'), thead = el('thead'), tr = el('tr');
    columnas.forEach(c => tr.append(el('th', c[3] ? 'dor-num' : '', c[0]))); thead.append(tr);
    const tbody = el('tbody');
    filas.slice(0, 500).forEach(r => { const f = el('tr'); columnas.forEach(c => f.append(el('td', c[3] ? 'dor-num' : '', c[1](r)))); tbody.append(f); });
    tabla.append(thead, tbody); scroll.append(tabla); caja.append(cab, scroll);
    if (filas.length > 500) caja.append(el('p', 'df-caption', 'Se muestran 500 de ' + fmtNum(filas.length) + '. Descarga el Excel para verlos todos.'));
    caja.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // Antigüedad en tramos
  function tramos(lista, dias, cortes) {
    return cortes.map(([nombre, min, max, color]) => {
      const filas = lista.filter(r => { const d = dias(r); return d !== null && d >= min && d <= max; });
      return {nombre, filas, color};
    });
  }

  // Botones "Por día / Por semana" (como "Del día / Acumulado" en Claro).
  function periodo(id, alCambiar) {
    const caja = document.getElementById(id); if (!caja) return () => 'dia';
    caja.addEventListener('click', e => {
      const b = e.target.closest('button[data-periodo]'); if (!b) return;
      caja.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); alCambiar();
    });
    return () => caja.querySelector('button[aria-pressed="true"]')?.dataset.periodo || 'dia';
  }

  window.DashPuntual = {periodo, el, fmtNum, soles, solesCorto, pct, suma, promedio, diasEntre, mesAnterior, nombreMes, css, COLOR,
    kpi, valor, doble, delta, opciones, montar, detalle, tramos};
}());
