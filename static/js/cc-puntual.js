// Dashboard de Caja Chica con información puntual (estilo Claro). Solo lee datos.
(function () {
  'use strict';
  const page = document.querySelector('.cc-puntual'); if (!page) return;
  const P = window.DashPuntual, base = window.NucleusFinanceModel, M = window.NucleusRendicionExecutive;
  const {fmtNum, soles, solesCorto, pct, suma, promedio, diasEntre, COLOR} = P;
  const $ = id => document.getElementById(id);
  const datos = JSON.parse($('di-data').textContent), rows = datos.detalle || [];
  const monto = r => base.amount(r, 'rendicion');
  const tipo = r => { const b = M.budget(r); return b === 'GASTO COBRA' ? 'Gasto Cobra' : b === 'REFACTURABLE' ? 'Refacturable' : 'Otros'; };
  const sinSustento = r => r.etapa === 'EVIDENCIA';
  const sustentado = r => ['SUSTENTO', 'ATENDIDO', 'ARCHIVADO'].includes(r.etapa);
  const rechazado = r => r.veces_rechazado > 0 || r.estado === 'RECHAZADO';
  const tiempo = r => { const d = diasEntre(r.dia_pago, r.dia_sustento); return d !== null && d >= 0 ? d : null; };
  const persona = r => base.person(r, 'rendicion');
  const nombres = new Map(rows.map(r => [persona(r), r.beneficiario || 'Sin beneficiario']));
  const COLUMNAS = [
    ['Código', r => r.codigo || ''], ['Cliente', r => M.client(r)], ['Beneficiario', r => r.beneficiario], ['Site', r => r.site || ''],
    ['Estado', r => window.NucleusRendicionStates?.label(r.estado) || r.estado], ['Presupuesto', r => tipo(r)], ['Tipo de gasto', r => r.gasto],
    ['Importe', r => soles(monto(r)), r => monto(r), true], ['Días en la etapa', r => r.dias_etapa ?? '', r => r.dias_etapa ?? '', true],
    ['Fecha de pago', r => r.dia_pago || ''], ['Fecha de sustento', r => r.dia_sustento || ''],
  ];
  const estado = {month: '', operator: '', budget: '', person: ''};
  const escalaElegida = P.periodo('cc-periodo', () => render());
  const verDetalle = (titulo, filas) => P.detalle($('cc-detalle'), titulo, filas, COLUMNAS, 'caja-chica-detalle');
  const tooltipMonto = (grupos, palabra = 'solicitudes') => ({callbacks: {label: c => { const f = grupos[c.dataIndex] || []; return fmtNum(f.length) + ' ' + palabra + ' · ' + soles(suma(f, monto)); }}});

  function filtrar(cambios = {}) {
    const f = {...estado, ...cambios};
    return rows.filter(r => (!f.month || r.mes === f.month) && (!f.operator || M.client(r) === f.operator) && (!f.budget || M.budget(r) === f.budget) && (!f.person || persona(r) === f.person));
  }

  function kpis(filas, previo, corte) {
    const caja = $('cc-kpis'); caja.replaceChildren();
    const mes = estado.month, periodo = mes ? 'solicitudes de ' + P.nombreMes(mes) : 'todas las solicitudes';
    const dep = filas.filter(r => r.depositado), depPrev = previo ? previo.filter(r => r.depositado) : null;
    const total = suma(dep, monto), totalPrev = depPrev ? suma(depPrev, monto) : null;
    caja.append(P.kpi('Depositado', P.valor(soles(total), '', P.delta(total, totalPrev, {mejorSube: null})),
      fmtNum(dep.length) + ' depósitos · ' + periodo, () => verDetalle('Depositado · ' + periodo, dep)));

    const sus = dep.filter(sustentado), p = pct(suma(sus, monto), total);
    const susPrev = depPrev ? pct(suma(depPrev.filter(sustentado), monto), totalPrev) : null;
    caja.append(P.kpi('Sustentado', P.valor(p === null ? '—' : fmtNum(p, 1) + '%', '', P.delta(p, susPrev, {relativo: false, unidad: 'pp'})),
      soles(suma(sus, monto)) + ' de ' + soles(total), () => verDetalle('Depósitos sustentados', sus)));

    const pend = corte.filter(sinSustento);
    caja.append(P.kpi('Sin sustento al corte', P.doble(P.valor(solesCorto(suma(pend, monto)), pend.length ? 'dor-mal' : 'dor-ok', null, 'Importe'), P.valor(fmtNum(pend.length), '', null, 'Solicitudes')),
      'Depositado y sin sustento cargado · todos los meses', () => verDetalle('Sin sustento al corte', pend)));

    const t = filas.map(tiempo).filter(d => d !== null), tPrev = previo ? previo.map(tiempo).filter(d => d !== null) : [];
    const pr = promedio(t);
    caja.append(P.kpi('Días para sustentar', P.valor(pr === null ? '—' : fmtNum(pr, 1) + ' días', '', P.delta(pr, promedio(tPrev), {mejorSube: false, relativo: false, unidad: 'd'})),
      'Promedio de pago a sustento · ' + fmtNum(t.length) + ' casos', () => verDetalle('Solicitudes con sustento', filas.filter(r => tiempo(r) !== null))));

    const rech = filas.filter(rechazado), obs = corte.filter(r => r.etapa === 'OBSERVADO');
    caja.append(P.kpi('Rechazados y observados', P.doble(P.valor(fmtNum(rech.length), rech.length ? 'dor-mal' : '', null, 'Rechazados'), P.valor(fmtNum(obs.length), obs.length ? 'dor-medio' : '', null, 'Observados hoy')),
      'Rechazados alguna vez en el periodo · observados al corte', () => verDetalle('Rechazados y observados', [...rech, ...obs.filter(r => !rech.includes(r))])));

    const cobra = dep.filter(r => tipo(r) === 'Gasto Cobra'), refact = dep.filter(r => tipo(r) === 'Refacturable');
    caja.append(P.kpi('Depositado por tipo', P.doble(P.valor(solesCorto(suma(cobra, monto)), '', null, 'Gasto Cobra', COLOR.cobra), P.valor(solesCorto(suma(refact, monto)), '', null, 'Refacturable', COLOR.refact)),
      fmtNum(cobra.length) + ' Gasto Cobra · ' + fmtNum(refact.length) + ' Refacturable', () => verDetalle('Depositado por tipo', dep)));
  }

  function evolucion(filas) {
    const escala = escalaElegida(), bucket = d => window.ClaroModel.bucket(d, escala);
    const dep = filas.filter(r => r.depositado && r.dia_pago), sus = filas.filter(r => sustentado(r) && r.dia_sustento);
    const periodos = [...new Set([...dep.map(r => bucket(r.dia_pago)), ...sus.map(r => bucket(r.dia_sustento))])].sort();
    const gDep = periodos.map(p => dep.filter(r => bucket(r.dia_pago) === p)), gSus = periodos.map(p => sus.filter(r => bucket(r.dia_sustento) === p));
    const etiqueta = p => escala === 'mes' ? P.nombreMes(p) : new Intl.DateTimeFormat('es-PE', {day: 'numeric', month: 'short'}).format(new Date(p + 'T12:00:00'));
    const o = P.opciones({formatoEje: solesCorto, alClic: (i, d) => verDetalle((d ? 'Sustentado' : 'Depositado') + ' · ' + etiqueta(periodos[i]), (d ? gSus : gDep)[i]),
      tooltip: {callbacks: {title: c => (escala === 'semana' ? 'Semana del ' : '') + etiqueta(periodos[c[0].dataIndex]), label: c => c.dataset.label + ': ' + soles(c.parsed.y) + ' · ' + fmtNum((c.datasetIndex ? gSus : gDep)[c.dataIndex].length)}}});
    o.interaction = {mode: 'index', intersect: false};
    o.plugins.legend.display = true; o.plugins.legend.position = 'top'; o.plugins.legend.align = 'end';
    $('cc-evolucion').parentElement.style.minWidth = periodos.length > 14 ? periodos.length * 52 + 'px' : '';
    P.montar('cc-evolucion', {type: 'bar', data: {labels: periodos.map(etiqueta), datasets: [
      {label: 'Depositado', data: gDep.map(f => suma(f, monto)), backgroundColor: COLOR.celeste, borderRadius: 8, borderSkipped: false, maxBarThickness: 30, order: 2},
      {type: 'line', label: 'Sustentado', data: gSus.map(f => suma(f, monto)), borderColor: COLOR.refact, backgroundColor: COLOR.refact, borderWidth: 2.5, tension: .35, pointRadius: 3.5, order: 1},
    ]}, options: o}, periodos.length > 0, solesCorto);
  }

  function antiguedad(corte) {
    const pend = corte.filter(sinSustento);
    const t = P.tramos(pend, r => r.dias_etapa ?? null, [['0 a 3 días', 0, 3, COLOR.ok], ['4 a 7 días', 4, 7, COLOR.medio], ['8 a 15 días', 8, 15, COLOR.mal], ['Más de 15 días', 16, 1e9, COLOR.muyMal]]);
    const grupos = t.map(x => x.filas);
    P.montar('cc-antiguedad', {type: 'bar', data: {labels: t.map(x => x.nombre), datasets: [{data: grupos.map(g => suma(g, monto)), backgroundColor: t.map(x => x.color), borderRadius: 8, borderSkipped: false, maxBarThickness: 54,
      formato: (v, i) => solesCorto(v) + ' · ' + fmtNum(grupos[i].length)}]},
      options: P.opciones({formatoEje: solesCorto, tooltip: tooltipMonto(grupos), alClic: i => verDetalle('Sin sustento · ' + t[i].nombre + ' desde el pago', grupos[i])})}, pend.length > 0, solesCorto);
  }

  function apilado(id, filas, clave, nombre, {limite = 10} = {}) {
    const claves = [...new Set(filas.map(clave))].sort((a, b) => suma(filas.filter(r => clave(r) === b), monto) - suma(filas.filter(r => clave(r) === a), monto)).slice(0, limite);
    const tipos = [['Gasto Cobra', COLOR.cobra], ['Refacturable', COLOR.refact], ['Otros', COLOR.gris]].filter(([t]) => filas.some(r => tipo(r) === t));
    const celda = (k, t) => filas.filter(r => clave(r) === k && tipo(r) === t);
    const o = P.opciones({horizontal: true, apilado: true, formatoEje: solesCorto,
      tooltip: {callbacks: {label: c => { const f = celda(claves[c.dataIndex], tipos[c.datasetIndex][0]); return tipos[c.datasetIndex][0] + ': ' + soles(suma(f, monto)) + ' · ' + fmtNum(f.length) + ' solicitudes'; }}},
      alClic: (i, d) => verDetalle(nombre(claves[i]) + ' · ' + tipos[d][0] + ' sin sustento', celda(claves[i], tipos[d][0]))});
    o.plugins.legend.display = true; o.plugins.legend.position = 'top'; o.plugins.legend.align = 'end';
    o.scales.y.ticks.callback = function (v) { const t = nombre(claves[v] || ''); return t.length > 26 ? t.slice(0, 25) + '…' : t; };
    P.montar(id, {type: 'bar', data: {labels: claves.map(nombre), datasets: tipos.map(([t, c]) => ({label: t, data: claves.map(k => suma(celda(k, t), monto)), backgroundColor: c, borderRadius: 6, maxBarThickness: 22}))}, options: o},
      filas.length > 0, solesCorto);
  }

  function render() {
    const filas = filtrar(), previo = estado.month ? filtrar({month: P.mesAnterior(estado.month)}) : null, corte = filtrar({month: ''});
    $('cc-detalle').hidden = true;
    kpis(filas, previo, corte);
    evolucion(filas);
    antiguedad(corte);
    const pend = corte.filter(sinSustento);
    apilado('cc-tecnicos', pend, persona, k => nombres.get(k) || 'Sin beneficiario', {limite: 10});
    apilado('cc-clientes', pend, M.client, k => k, {limite: 8});
    apilado('cc-conceptos', filas.filter(r => r.depositado), r => r.gasto || 'Sin tipo', k => k, {limite: 10});
    $('df-caption').textContent = fmtNum(filas.length) + ' solicitudes en la selección · importes de MONTO PAGO · "al corte" incluye todos los meses con los demás filtros.';
  }

  // Filtros (los mismos de antes) y mes actual por defecto.
  const valores = {month: r => r.mes, operator: M.client, budget: M.budget, person: persona};
  for (const clave of Object.keys(valores)) {
    const sel = $('df-' + clave); if (!sel) continue;
    const lista = [...new Set(rows.map(valores[clave]).filter(Boolean))];
    const texto = v => clave === 'person' ? nombres.get(v) || 'Sin beneficiario' : clave === 'month' ? P.nombreMes(v) + ' ' + v.slice(0, 4) : v;
    lista.sort((a, b) => clave === 'month' ? b.localeCompare(a) : texto(a).localeCompare(texto(b)));
    lista.forEach(v => sel.add(new Option(texto(v), v)));
    sel.addEventListener('change', () => { estado[clave] = sel.value; render(); });
  }
  if (rows.some(r => r.mes === datos.mes_actual)) { estado.month = datos.mes_actual; $('df-month').value = datos.mes_actual; }
  $('df-clear').addEventListener('click', () => { Object.keys(estado).forEach(k => { estado[k] = ''; const s = $('df-' + k); if (s) s.value = ''; }); render(); });

  new MutationObserver(render).observe(document.body, {attributes: true, attributeFilter: ['class']});
  render();
}());
