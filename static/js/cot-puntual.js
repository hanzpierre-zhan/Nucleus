// Dashboard de Cotizaciones con información puntual (estilo Claro). Usa los filtros de dashboard-finanzas.js.
(function () {
  'use strict';
  const P = window.DashPuntual; if (!P) return;
  const {el, fmtNum, soles, solesCorto, pct, suma, promedio, diasEntre, COLOR} = P;
  const $ = id => document.getElementById(id);
  const norm = v => String(v || '').normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toUpperCase();
  const tipo = r => { const g = norm(r.gasto); return g === 'GASTO COBRA' ? 'Gasto Cobra' : g === 'REFACTURABLE' ? 'Refacturable' : 'Otros'; };
  const enviadas = r => ['cliente', 'sustentar', 'atendido'].includes(r.pestania);
  const aprobadas = r => ['sustentar', 'atendido'].includes(r.pestania);
  const respuesta = r => { const d = diasEntre(r.f_cot, r.f_apr); return d !== null && d >= 0 ? d : null; };
  const COLUMNAS = [
    ['N.º', r => r.n || ''], ['Cliente', r => r.cliente], ['Proyecto', r => r.proyecto], ['Estado', r => r.estado],
    ['Tipo de gasto', r => r.gasto], ['Importe', r => soles(r.monto), r => r.monto, true],
    ['Días en la etapa', r => r.dias_etapa ?? '', r => r.dias_etapa ?? '', true], ['Generó', r => r.genero], ['Fecha', r => r.dia || ''],
  ];
  let ctx = null;
  const escalaElegida = P.periodo('cp-periodo', () => ctx && ctx.redibujar());
  const verDetalle = (titulo, filas) => P.detalle($('cp-detalle'), titulo, filas, COLUMNAS, 'cotizaciones-detalle');
  const tooltipMonto = filas => ({callbacks: {label: c => { const f = filas[c.dataIndex] || []; return fmtNum(f.length) + ' cotizaciones · ' + soles(suma(f, r => r.monto)); }}});

  function kpis(filas, backlog, previo, mes) {
    const caja = $('cp-kpis'); caja.replaceChildren();
    const activas = filas.filter(r => r.pestania !== 'cancelado'), activasPrev = previo ? previo.filter(r => r.pestania !== 'cancelado') : null;
    const total = suma(activas, r => r.monto), totalPrev = activasPrev ? suma(activasPrev, r => r.monto) : null;
    const periodo = mes ? 'en ' + P.nombreMes(mes) : 'en el periodo';
    caja.append(P.kpi('Cotizado ' + periodo, P.valor(soles(total), '', P.delta(total, totalPrev)),
      fmtNum(activas.length) + ' cotizaciones' + (totalPrev !== null ? ' · ' + P.nombreMes(P.mesAnterior(mes)) + ': ' + solesCorto(totalPrev) : ''),
      () => verDetalle('Cotizado ' + periodo, activas)));

    const espera = backlog.filter(r => r.pestania === 'cliente');
    caja.append(P.kpi('Esperando respuesta del cliente', P.doble(P.valor(fmtNum(espera.length), '', null, 'Cotizaciones'), P.valor(solesCorto(suma(espera, r => r.monto)), '', null, 'Importe')),
      'Al corte, todos los meses', () => verDetalle('Esperando respuesta del cliente', espera)));

    const tasa = (lista) => pct(lista.filter(aprobadas).length, lista.filter(enviadas).length);
    const t = tasa(filas), tPrev = previo ? tasa(previo) : null;
    caja.append(P.kpi('Tasa de aprobación', P.valor(t === null ? '—' : fmtNum(t, 1) + '%', '', P.delta(t, tPrev, {relativo: false, unidad: 'pp'})),
      fmtNum(filas.filter(aprobadas).length) + ' aprobadas de ' + fmtNum(filas.filter(enviadas).length) + ' enviadas', () => verDetalle('Cotizaciones aprobadas', filas.filter(aprobadas))));

    const resp = filas.map(respuesta).filter(d => d !== null), respPrev = previo ? previo.map(respuesta).filter(d => d !== null) : [];
    const pr = promedio(resp), prPrev = promedio(respPrev);
    caja.append(P.kpi('Respuesta del cliente', P.valor(pr === null ? '—' : fmtNum(pr, 1) + ' días', '', P.delta(pr, prPrev, {mejorSube: false, relativo: false, unidad: 'd'})),
      'Promedio de cotizado a aprobado · ' + fmtNum(resp.length) + ' casos', () => verDetalle('Cotizaciones con respuesta del cliente', filas.filter(r => respuesta(r) !== null))));

    const porEjecutar = backlog.filter(r => r.pestania === 'sustentar'), cobra = porEjecutar.filter(r => tipo(r) === 'Gasto Cobra'), refact = porEjecutar.filter(r => tipo(r) === 'Refacturable');
    caja.append(P.kpi('Aprobadas sin ejecutar', P.doble(P.valor(solesCorto(suma(cobra, r => r.monto)), '', null, 'Gasto Cobra', COLOR.cobra), P.valor(solesCorto(suma(refact, r => r.monto)), '', null, 'Refacturable', COLOR.refact)),
      fmtNum(porEjecutar.length) + ' cotizaciones al corte', () => verDetalle('Aprobadas sin ejecutar', porEjecutar)));

    const viejas = espera.filter(r => (r.dias_etapa ?? 0) > 15), mayor = Math.max(0, ...espera.map(r => r.dias_etapa ?? 0));
    caja.append(P.kpi('Sin respuesta hace más de 15 días', P.valor(fmtNum(viejas.length), viejas.length ? 'dor-mal' : 'dor-ok'),
      soles(suma(viejas, r => r.monto)) + (espera.length ? ' · la más antigua: ' + fmtNum(mayor) + ' días' : ''), () => verDetalle('Sin respuesta del cliente hace más de 15 días', viejas)));
  }

  function embudo(filas, canceladas) {
    const etapas = [['Registradas', filas.filter(r => r.pestania !== 'cancelado'), '#173E76'], ['Enviadas al cliente', filas.filter(enviadas), COLOR.azul],
      ['Aprobadas', filas.filter(aprobadas), COLOR.refact], ['Atendidas', filas.filter(r => r.pestania === 'atendido'), '#0f6e56'], ['Canceladas', canceladas, COLOR.mal]];
    const grupos = etapas.map(e => e[1]);
    const o = P.opciones({horizontal: true, tooltip: tooltipMonto(grupos), alClic: i => verDetalle(etapas[i][0], grupos[i])});
    P.montar('cp-embudo', {type: 'bar', data: {labels: etapas.map(e => e[0]), datasets: [{data: grupos.map(g => g.length), backgroundColor: etapas.map(e => e[2]), borderRadius: 8, borderSkipped: false, maxBarThickness: 26,
      formato: (v, i) => fmtNum(v) + ' · ' + solesCorto(suma(grupos[i], r => r.monto))}]}, options: o}, grupos.some(g => g.length));
  }

  function antiguedad(backlog) {
    const espera = backlog.filter(r => r.pestania === 'cliente');
    const t = P.tramos(espera, r => r.dias_etapa ?? null, [['0 a 7 días', 0, 7, COLOR.ok], ['8 a 15 días', 8, 15, COLOR.medio], ['16 a 30 días', 16, 30, COLOR.mal], ['Más de 30 días', 31, 1e9, COLOR.muyMal]]);
    const grupos = t.map(x => x.filas);
    const o = P.opciones({tooltip: tooltipMonto(grupos), alClic: i => verDetalle('Esperando al cliente · ' + t[i].nombre, grupos[i])});
    P.montar('cp-antiguedad', {type: 'bar', data: {labels: t.map(x => x.nombre), datasets: [{data: grupos.map(g => g.length), backgroundColor: t.map(x => x.color), borderRadius: 8, borderSkipped: false, maxBarThickness: 54,
      formato: (v, i) => fmtNum(v) + ' · ' + solesCorto(suma(grupos[i], r => r.monto))}]}, options: o}, espera.length > 0);
  }

  function clientes(filas) {
    const activas = filas.filter(r => r.pestania !== 'cancelado');
    const nombres = [...new Set(activas.map(r => r.cliente))].sort((a, b) => suma(activas.filter(r => r.cliente === b), r => r.monto) - suma(activas.filter(r => r.cliente === a), r => r.monto)).slice(0, 8);
    const tipos = [['Gasto Cobra', COLOR.cobra], ['Refacturable', COLOR.refact], ['Otros', COLOR.gris]].filter(([t]) => activas.some(r => tipo(r) === t));
    const celda = (c, t) => activas.filter(r => r.cliente === c && tipo(r) === t);
    const o = P.opciones({horizontal: true, apilado: true, formatoEje: solesCorto,
      tooltip: {callbacks: {label: c => { const f = celda(nombres[c.dataIndex], tipos[c.datasetIndex][0]); return tipos[c.datasetIndex][0] + ': ' + soles(suma(f, r => r.monto)) + ' · ' + fmtNum(f.length) + ' cotizaciones'; }}},
      alClic: (i, d) => verDetalle(nombres[i] + ' · ' + tipos[d][0], celda(nombres[i], tipos[d][0]))});
    o.plugins.legend.display = true; o.plugins.legend.position = 'top'; o.plugins.legend.align = 'end';
    P.montar('cp-clientes', {type: 'bar', data: {labels: nombres, datasets: tipos.map(([t, c]) => ({label: t, data: nombres.map(n => suma(celda(n, t), r => r.monto)), backgroundColor: c, borderRadius: 6, maxBarThickness: 24}))}, options: o},
      activas.some(r => r.monto), solesCorto);
  }

  function evolucion(filas) {
    const escala = escalaElegida(), bucket = d => window.ClaroModel.bucket(d, escala);
    const activas = filas.filter(r => r.pestania !== 'cancelado');
    const periodos = [...new Set([...activas.filter(r => r.dia).map(r => bucket(r.dia)), ...activas.filter(r => r.dia_aprobacion).map(r => bucket(r.dia_aprobacion))])].sort();
    const cot = periodos.map(p => activas.filter(r => r.dia && bucket(r.dia) === p)), apr = periodos.map(p => activas.filter(r => r.dia_aprobacion && bucket(r.dia_aprobacion) === p));
    const etiqueta = p => escala === 'mes' ? P.nombreMes(p) : escala === 'anio' ? p : new Intl.DateTimeFormat('es-PE', {day: 'numeric', month: 'short'}).format(new Date(p + 'T12:00:00'));
    const o = P.opciones({formatoEje: solesCorto, alClic: (i, d) => verDetalle((d ? 'Aprobado' : 'Cotizado') + ' · ' + etiqueta(periodos[i]), (d ? apr : cot)[i]),
      tooltip: {callbacks: {title: c => (escala === 'semana' ? 'Semana del ' : '') + etiqueta(periodos[c[0].dataIndex]), label: c => c.dataset.label + ': ' + soles(c.parsed.y) + ' · ' + fmtNum((c.datasetIndex ? apr : cot)[c.dataIndex].length)}}});
    o.interaction = {mode: 'index', intersect: false};
    o.plugins.legend.display = true; o.plugins.legend.position = 'top'; o.plugins.legend.align = 'end';
    const caja = $('cp-evolucion').parentElement; caja.style.minWidth = periodos.length > 12 ? periodos.length * 56 + 'px' : '';
    P.montar('cp-evolucion', {type: 'bar', data: {labels: periodos.map(etiqueta), datasets: [
      {label: 'Cotizado', data: cot.map(f => suma(f, r => r.monto)), backgroundColor: COLOR.celeste, borderRadius: 8, borderSkipped: false, maxBarThickness: 34, order: 2},
      {type: 'line', label: 'Aprobado', data: apr.map(f => suma(f, r => r.monto)), borderColor: COLOR.refact, backgroundColor: COLOR.refact, borderWidth: 2.5, tension: .35, pointRadius: 3.5, order: 1},
    ]}, options: o}, periodos.length > 0, solesCorto);
  }

  function render(filas, contexto) {
    ctx = contexto;
    const meses = ctx.mesesElegidos(), mes = meses.length === 1 ? meses[0] : '';
    const previo = mes ? ctx.filtrar({month: [P.mesAnterior(mes)], day: ''}) : null;
    const backlog = ctx.filtrar({month: [], day: ''});
    const canceladas = ctx.filtrar({incluirCanceladas: true}).filter(r => r.pestania === 'cancelado');
    $('cp-detalle').hidden = true;
    kpis(filas, backlog, previo, mes);
    embudo(filas, canceladas);
    antiguedad(backlog);
    clientes(filas);
    evolucion(filas);
  }

  window.CotPuntual = {render};
}());
