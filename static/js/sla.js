/* SLA · cumplimiento por proyecto FLM: indicadores, casos abiertos con cuenta regresiva y ranking por técnico. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const icono = nombre => { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; };
  const plano = t => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const CFG = JSON.parse($('sla-config').textContent);
  const ESTADOS = {
    vencido: ['Vencido', 'fa-alarm-clock', 'sla-rojo'], por_vencer: ['Por vencer', 'fa-hourglass-half', 'sla-ambar'],
    en_plazo: ['En plazo', 'fa-circle-check', 'sla-verde'], sin_objetivo: ['Sin objetivo', 'fa-circle-question', 'sla-gris'],
    sla_cero: ['SLA en 0', 'fa-circle-exclamation', 'sla-gris'], sin_inicio: ['Sin inicio', 'fa-hourglass-start', 'sla-gris'],
    cumple: ['Cerrado · cumplió', 'fa-circle-check', 'sla-verde'], no_cumple: ['Cerrado · no cumplió', 'fa-circle-xmark', 'sla-rojo'],
  };

  // Al abrir, se ve por defecto la pestaña Abiertos (filtro vacío).
  // Por defecto se ve el mes actual.
  let proyecto = '', tipo = '', filtro = '', periodo = 'mes', categoria = '';
  try { proyecto = localStorage.getItem('sla-proyecto') || ''; } catch (_) {}
  const cache = {};

  // Fechas guardadas como "2026-11-02 14:47:13" (hora de Perú, la del navegador).
  const fecha = s => { const m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/); return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : null; };
  const duracion = min => { min = Math.round(Math.abs(min)); const d = Math.floor(min / 1440), h = Math.floor(min % 1440 / 60), m = min % 60; return (d ? d + ' d ' : '') + (d || h ? h + ' h ' : '') + m + ' min'; };

  // Estado de un caso abierto, calculado contra la hora actual.
  function medir(c, ahora) {
    const ini = fecha(c.inicio);
    // Sin medir: SLA en 0, sin objetivo (vacío) o sin la fecha de inicio (CM: Dispatch Time; PM/PLM: Arrive Time).
    if (/^0+(\.0+)?$/.test(String(c.sla_hour ?? '').trim())) return {estado: 'sla_cero', resto: null, uso: 0};
    if (!c.objetivo) return {estado: 'sin_objetivo', resto: null, uso: 0};
    if (!ini) return {estado: 'sin_inicio', resto: null, uso: 0};
    const transcurrido = (ahora - ini) / 60000 - (c.pausa || 0), resto = c.objetivo - transcurrido, uso = Math.max(0, transcurrido / c.objetivo * 100);
    const estado = resto < 0 ? 'vencido' : (resto <= c.objetivo * CFG.porcentaje || resto <= CFG.minutos) ? 'por_vencer' : 'en_plazo';
    return {estado, resto, uso};
  }
  // Cerrado: cumple si SLA Status es "normal" (si no lo trae, se compara la duración con el objetivo).
  function cumple(c) {
    if (c.sla_status) return c.sla_status === 'normal';
    const ini = fecha(c.inicio), fin = fecha(c.fin);
    return !(ini && fin && c.objetivo) || (fin - ini) / 60000 - (c.pausa || 0) <= c.objetivo;
  }
  function enPeriodo(c) {
    if (!periodo) return true;
    const fin = fecha(c.fin || c.inicio); if (!fin) return false;
    const hoy = new Date();
    if (periodo === 'hoy') return fin.toDateString() === hoy.toDateString();
    if (periodo === 'ayer') { const ayer = new Date(hoy); ayer.setDate(hoy.getDate() - 1); return fin.toDateString() === ayer.toDateString(); }
    if (periodo === '7') return hoy - fin <= 7 * 864e5;
    const mes = periodo === 'mes' ? new Date(hoy.getFullYear(), hoy.getMonth(), 1) : new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
    const hasta = new Date(mes.getFullYear(), mes.getMonth() + 1, 1);
    return fin >= mes && fin < hasta;
  }
  // SLA Status: "normal" = Cumplimiento; "sla_violation" (u otro valor) = Incumplimiento. El valor original queda en el tooltip.
  const resultadoSla = c => !c.sla_status ? '' : c.sla_status === 'normal' ? 'Cumplimiento' : 'Incumplimiento';
  function estadoSla(c) {
    const texto = resultadoSla(c);
    // Se muestra el valor tal cual viene (normal / sla_violation); el color y el tooltip dicen si cumplió.
    const s = el('span', 'sla-status ' + (!texto ? '' : texto === 'Cumplimiento' ? 'sla-status-normal' : 'sla-status-sla_violation'), c.sla_status_original || '—');
    if (texto) s.title = texto;
    // Entel: contraste con el cálculo Cobra (⚠ si no coinciden).
    if (c.sla_cobra && c.sla_status && c.sla_cobra !== c.sla_status) {
      const caja = el('span', 'sla-contraste'); caja.title = 'La data dice ' + c.sla_status_original + ' y el cálculo Cobra dice ' + c.sla_cobra;
      caja.append(s, icono('fa-triangle-exclamation')); return caja;
    }
    return s;
  }
  // ── Ordenar y filtrar por columna (como en Caja Chica) ──
  // valor: lo que se compara al ordenar; texto: lo que se elige en el filtro.
  const COLS = {
    ticket: {valor: c => c.ticket, texto: c => c.ticket},
    tipo: {valor: c => c.tipo, texto: c => c.tipo},
    categoria: {valor: c => c.categoria || '', texto: c => c.categoria || '(vacío)'},
    fm_office: {valor: c => c.fm_office || '', texto: c => c.fm_office || '(vacío)'},
    tecnico: {valor: c => c.tecnico_nombre || c.tecnico || '', texto: c => nombreTec(c)},
    dispatch: {valor: c => c.dispatch || '', texto: c => (c.dispatch || '').slice(0, 10) || '(vacío)'},
    arrive: {valor: c => c.arrive || '', texto: c => (c.arrive || '').slice(0, 10) || '(vacío)'},
    fin: {valor: c => c.fin || '', texto: c => (c.fin || '').slice(0, 10) || '(vacío)'},
    objetivo: {valor: c => Number(c.objetivo) || 0, texto: c => c.sla_hour || '(vacío)'},
    sla_status: {valor: c => c.sla_status_original || '', texto: c => c.sla_status_original || '(vacío)'},
    uso: {valor: c => Number(c.uso) || 0, texto: c => !c.uso ? '0 %' : c.uso > 100 ? 'Más del 100 %' : c.uso >= 75 ? '75 a 100 %' : c.uso >= 50 ? '50 a 75 %' : 'Menos del 50 %'},
    estado: {valor: c => c.resto ?? (c.estado === 'cumple' ? 1e9 : -1e9), texto: c => (ESTADOS[c.estado] || [c.estado])[0]},
  };
  let ordenCol = null;            // {col, dir: 1 | -1}
  const filtrosCol = {};          // col -> Set de textos elegidos
  let baseFiltro = [];            // filas antes de los filtros por columna (para armar las opciones)
  function prepararEncabezado() {
    document.querySelectorAll('.sla-encabezado [data-col]').forEach(h => {
      if (h.querySelector('.sla-th-txt')) return;
      const col = h.dataset.col, txt = el('span', 'sla-th-txt', h.textContent.trim());
      const ordenar = el('button', 'sla-th-btn sla-th-orden'); ordenar.type = 'button'; ordenar.title = 'Ordenar'; ordenar.append(icono('fa-sort'));
      const filtrar = el('button', 'sla-th-btn sla-th-filtro'); filtrar.type = 'button'; filtrar.title = 'Filtrar'; filtrar.append(icono('fa-filter'));
      ordenar.addEventListener('click', () => {
        ordenCol = ordenCol?.col !== col ? {col, dir: 1} : ordenCol.dir === 1 ? {col, dir: -1} : null; pintar();
      });
      filtrar.addEventListener('click', e => { e.stopPropagation(); abrirFiltro(col, filtrar); });
      h.replaceChildren(txt, ordenar, filtrar);
    });
  }
  function pintarEncabezado() {
    document.querySelectorAll('.sla-encabezado [data-col]').forEach(h => {
      const col = h.dataset.col, o = h.querySelector('.sla-th-orden'), f = h.querySelector('.sla-th-filtro');
      if (!o) return;
      const sentido = ordenCol?.col === col ? ordenCol.dir : 0;
      o.classList.toggle('activo', !!sentido); o.replaceChildren(icono(sentido === 1 ? 'fa-arrow-up-short-wide' : sentido === -1 ? 'fa-arrow-down-wide-short' : 'fa-sort'));
      o.title = sentido === 1 ? 'De menor a mayor · clic: de mayor a menor' : sentido === -1 ? 'De mayor a menor · clic: quitar orden' : 'Ordenar de menor a mayor';
      f.classList.toggle('activo', !!filtrosCol[col]?.size);
    });
  }
  let popFiltro = null;
  function cerrarFiltro() { popFiltro?.remove(); popFiltro = null; }
  document.addEventListener('click', e => { if (popFiltro && !popFiltro.contains(e.target)) cerrarFiltro(); });
  function abrirFiltro(col, boton) {
    cerrarFiltro();
    const conteo = new Map();
    for (const c of baseFiltro) { const t = COLS[col].texto(c); conteo.set(t, (conteo.get(t) || 0) + 1); }
    const valores = [...conteo.keys()].sort((a, b) => String(a).localeCompare(String(b), 'es', {numeric: true}));
    const elegidos = filtrosCol[col] || new Set();
    const pop = el('div', 'sla-pop'); pop.setAttribute('role', 'dialog'); pop.addEventListener('click', e => e.stopPropagation());
    const buscar = Object.assign(el('input', 'sla-pop-buscar'), {type: 'search', placeholder: 'Buscar…'});
    const lista = el('div', 'sla-pop-lista');
    const pintarLista = () => {
      const q = plano(buscar.value);
      lista.replaceChildren(...valores.filter(v => plano(v).includes(q)).slice(0, 300).map(v => {
        const l = el('label', 'sla-pop-op'), ch = Object.assign(el('input'), {type: 'checkbox', checked: elegidos.has(v)});
        ch.addEventListener('change', () => { ch.checked ? elegidos.add(v) : elegidos.delete(v); filtrosCol[col] = elegidos; if (!elegidos.size) delete filtrosCol[col]; pintar(); });
        l.append(ch, el('span', null, v), el('small', null, String(conteo.get(v)))); return l;
      }));
    };
    buscar.addEventListener('input', pintarLista); pintarLista();
    const limpiar = el('button', 'sla-pop-limpiar', 'Limpiar filtro'); limpiar.type = 'button';
    limpiar.addEventListener('click', () => { delete filtrosCol[col]; cerrarFiltro(); pintar(); });
    pop.append(buscar, lista, limpiar);
    document.body.append(pop);
    const r = boton.getBoundingClientRect();
    pop.style.top = Math.min(innerHeight - 340, r.bottom + 6) + 'px';
    pop.style.left = Math.max(8, Math.min(innerWidth - 268, r.left - 120)) + 'px';
    popFiltro = pop; buscar.focus();
  }

  const nombreTec = c => c.tecnico ? c.tecnico + (c.tecnico_nombre ? ' · ' + c.tecnico_nombre : '') : 'Sin técnico';

  function pintar() {
    const lista = cache[proyecto];
    document.querySelectorAll('.sla-proyecto').forEach(b => { b.classList.toggle('activa', b.dataset.proyecto === proyecto); b.setAttribute('aria-selected', String(b.dataset.proyecto === proyecto)); });
    document.querySelectorAll('.sla-tipo').forEach(b => b.classList.toggle('activo', b.dataset.tipo === tipo));
    if (!lista) { $('sla-lista').replaceChildren(el('p', 'cc-vacio', 'Cargando…')); return; }
    // Proyecto sin criterios aún: se avisa en vez de calcular con reglas que no le corresponden.
    const pendiente = !(CFG.con_criterios || []).includes(proyecto);
    document.querySelector('.sla-gestion').classList.toggle('sla-sin-criterios', pendiente);
    if (pendiente) {
      const nombre = document.querySelector('.sla-proyecto[data-proyecto="' + proyecto + '"]')?.textContent.trim().split(/\s/)[0] || proyecto;
      const aviso = el('div', 'sla-pendiente'); aviso.append(icono('fa-screwdriver-wrench'), el('strong', null, 'Criterios de SLA de ' + nombre + ' por definir'),
        el('span', null, 'Cuando estén definidos (desde qué fecha cuenta, objetivo y cumplimiento) se activa esta pestaña.'));
      $('sla-kpis').replaceChildren(aviso); $('sla-filtros').replaceChildren(); $('sla-tecnicos').replaceChildren();
      $('sla-lista').replaceChildren(el('p', 'cc-vacio', 'Sin criterios definidos para este proyecto.'));
      return;
    }
    const ahora = new Date(), q = plano($('cc-buscar').value.trim());
    // Nombres de las columnas según el proyecto (Entel trae otras columnas).
    const entel = proyecto === 'ENTEL';
    const integratel = proyecto === 'INTEGRATEL';
    const CABECERAS = entel
      ? {tecnico: 'assign_to_fme', dispatch: 'dispatch_time', arrive: 'arrive_time', fin: 'SubmitTime(complete)', objetivo: 'Fault Level · objetivo', categoria: 'Task Category', fm_office: 'fm_office'}
      : integratel
      ? {tecnico: 'Assign To Fme', dispatch: 'Dispatch Time', arrive: 'Arrive Time', fin: 'First Complete Time', objetivo: 'Sla (min) / Require Finish', categoria: 'Task Category', fm_office: 'Fm Office'}
      : {tecnico: 'Schedule Operator', dispatch: 'Dispatch Time', arrive: 'Arrive Time', fin: 'Complete Time', objetivo: 'SLA Hour', categoria: 'Task Category', fm_office: proyecto === 'PEXT' ? 'Departamento' : 'FM Office'};
    prepararEncabezado();
    document.querySelectorAll('[data-cabecera]').forEach(h => { const t = h.querySelector('.sla-th-txt') || h; t.textContent = CABECERAS[h.dataset.cabecera] || t.textContent; });
    // Categorías del proyecto (Task Category) para el filtro.
    const sel = $('sla-categoria'), cats = [...new Set(lista.map(c => c.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
    if (sel.dataset.proyecto !== proyecto) {
      sel.replaceChildren(new Option('Todas las categorías', ''), ...cats.map(c => new Option(c, c)));
      sel.dataset.proyecto = proyecto; if (!cats.includes(categoria)) categoria = ''; sel.value = categoria;
    }
    const delTipo = lista.filter(c => (!tipo || c.tipo === tipo) && (!categoria || c.categoria === categoria) && (!q || plano(c.ticket + ' ' + c.site + ' ' + c.tecnico + ' ' + c.tecnico_nombre + ' ' + (c.fme || '') + ' ' + (c.fm_office || '')).includes(q)));
    const abiertos = delTipo.filter(c => !c.cerrado).map(c => ({...c, ...medir(c, ahora)}));
    const cerrados = delTipo.filter(c => c.cerrado && enPeriodo(c));
    const cumplidos = cerrados.filter(cumple).length;
    const porcentaje = cerrados.length ? cumplidos / cerrados.length * 100 : null;
    const cuenta = e => abiertos.filter(c => c.estado === e).length;

    // Indicadores
    const kpis = $('sla-kpis'); kpis.replaceChildren();
    const tarjeta = (cls, simbolo, titulo, valor, detalle, clave) => {
      const t = el(clave ? 'button' : 'div', 'sla-kpi ' + cls + (clave && filtro === clave ? ' activo' : ''));
      if (clave) { t.type = 'button'; t.addEventListener('click', () => { filtro = filtro === clave ? '' : clave; pintar(); }); t.title = 'Ver solo ' + titulo.toLowerCase(); }
      t.append(el('small', null), el('strong', null, valor), el('span', null, detalle)); t.firstChild.append(icono(simbolo), ' ' + titulo);
      kpis.append(t);
    };
    const barra = el('div', 'sla-kpi sla-kpi-cumple');
    barra.append(el('small', null, 'Cumplimiento (cerrados)'), el('strong', null, porcentaje === null ? '—' : porcentaje.toFixed(1) + ' %'));
    const pista = el('div', 'sla-pista'), lleno = el('span'); lleno.style.width = (porcentaje || 0) + '%';
    lleno.dataset.nivel = porcentaje === null ? '' : porcentaje >= 90 ? 'ok' : porcentaje >= 80 ? 'medio' : 'bajo';
    pista.append(lleno); barra.append(pista, el('span', null, cumplidos.toLocaleString('es-PE') + ' cumplidos · ' + (cerrados.length - cumplidos).toLocaleString('es-PE') + ' incumplidos'));
    // Entel: el mismo cumplimiento con el cálculo Cobra, para contrastar con SLA Status.
    const conCobra = cerrados.filter(c => c.sla_cobra);
    if (conCobra.length) {
      const okCobra = conCobra.filter(c => c.sla_cobra === 'normal').length, distintos = conCobra.filter(c => c.sla_status && c.sla_cobra !== c.sla_status).length;
      const nota = el('span', 'sla-cobra-nota', 'Cálculo Cobra: ' + (okCobra / conCobra.length * 100).toFixed(1) + ' % · ' + distintos + ' no coinciden con SLA Status');
      nota.title = integratel ? 'CM: Dispatch Time → First Complete Time − pausas, contra Sla · PM/PLM: cierre antes de Require Finish Time'
        : 'dispatch_time → SubmitTime(complete) − parada de reloj, contra el objetivo del Fault Level';
      barra.append(nota);
    }
    kpis.append(barra);
    tarjeta('sla-rojo', 'fa-alarm-clock', 'Vencidos abiertos', cuenta('vencido'), entel ? 'pasaron su objetivo' : 'pasaron su SLA Hour', 'vencido');
    tarjeta('sla-ambar', 'fa-hourglass-half', 'Por vencer', cuenta('por_vencer'), 'queda ≤ ' + Math.round(CFG.porcentaje * 100) + ' % o ≤ ' + CFG.minutos + ' min', 'por_vencer');
    tarjeta('sla-verde', 'fa-circle-check', 'En plazo', cuenta('en_plazo'), 'con tiempo de sobra', 'en_plazo');
    const sinMedir = cuenta('sin_objetivo') + cuenta('sla_cero') + cuenta('sin_inicio');
    tarjeta('sla-gris', 'fa-circle-question', 'Sin medir', sinMedir, [cuenta('sin_inicio') + ' sin inicio', cuenta('sla_cero') + ' con SLA en 0', cuenta('sin_objetivo') + (entel ? ' sin regla' : ' sin SLA')].join(' · '), 'sin_medir');

    // Cumplimiento por técnico (cerrados del periodo), de menor a mayor para ver primero a quién apoyar.
    // Por técnico: el técnico asignado (nombre) con su backlog abierto y su SLA de los cerrados del periodo.
    const fmeDe = c => String(c.fme || '').trim() || 'Sin técnico asignado';
    const porTec = {};
    const tecDe = k => porTec[k] ||= {nombre: k, abiertos: 0, vencido: 0, por_vencer: 0, en_plazo: 0, sin: 0, cerrados: 0, ok: 0};
    for (const c of abiertos) { const x = tecDe(fmeDe(c)); x.abiertos++; if (['vencido', 'por_vencer', 'en_plazo'].includes(c.estado)) x[c.estado]++; else x.sin++; }
    for (const c of cerrados) { const x = tecDe(fmeDe(c)); x.cerrados++; if (cumple(c)) x.ok++; }
    const tecs = Object.values(porTec).map(x => ({...x, pct: x.cerrados ? x.ok / x.cerrados * 100 : null}))
      .sort((a, b) => b.vencido - a.vencido || b.por_vencer - a.por_vencer || b.abiertos - a.abiertos || (a.pct ?? 101) - (b.pct ?? 101));

    // Filtros rápidos de la lista
    const filtros = $('sla-filtros'); filtros.replaceChildren();
    for (const [clave, texto] of [['', 'Abiertos'], ['vencido', 'Vencidos'], ['por_vencer', 'Por vencer'], ['en_plazo', 'En plazo'], ['sin_inicio', 'Sin inicio'], ['sla_cero', 'SLA en 0'], ['sin_objetivo', 'Sin objetivo'], ['cerrados', 'Cerrados'], ['tecnicos', 'Por técnico']]) {
      const b = el('button', 'sla-chip' + (filtro === clave ? ' activo' : '')); b.type = 'button';
      b.append(el('span', null, texto), el('strong', null, String(clave === 'tecnicos' ? tecs.length : clave === 'cerrados' ? cerrados.length : clave ? cuenta(clave) : abiertos.length)));
      b.addEventListener('click', () => { filtro = clave; pintar(); }); filtros.append(b);
    }

    // "Por técnico" usa el mismo panel: se oculta la tabla de casos y se muestra la lista de técnicos.
    const verTecnicos = filtro === 'tecnicos';
    document.querySelector('.sla-tabla').hidden = verTecnicos;
    $('sla-tecnicos').hidden = !verTecnicos;
    // Casos abiertos, más urgentes primero: por vencer y en plazo según lo que les queda; luego vencidos (los más recientes arriba).
    const orden = {por_vencer: 0, vencido: 1, en_plazo: 2, sin_inicio: 3, sla_cero: 4, sin_objetivo: 5};
    const SIN_MEDIR = ['sin_inicio', 'sla_cero', 'sin_objetivo'];
    // "Cerrados": los del periodo, del más reciente al más antiguo, con su resultado según SLA Status.
    const usoCerrado = c => { const i = fecha(c.inicio), f = fecha(c.fin); return i && f && c.objetivo ? Math.max(0, (f - i) / 60000 - (c.pausa || 0)) / c.objetivo * 100 : 0; };
    baseFiltro = verTecnicos ? [] : filtro === 'cerrados'
      ? cerrados.map(c => ({...c, estado: cumple(c) ? 'cumple' : 'no_cumple', uso: usoCerrado(c)})).sort((a, b) => String(b.fin).localeCompare(String(a.fin)))
      : abiertos.filter(c => !filtro || c.estado === filtro || (filtro === 'sin_medir' && SIN_MEDIR.includes(c.estado)))
        .sort((a, b) => orden[a.estado] - orden[b.estado] || (a.estado === 'vencido' ? b.resto - a.resto : (a.resto ?? 1e9) - (b.resto ?? 1e9)));
    // Filtros y orden elegidos en los encabezados.
    let visibles = baseFiltro.filter(c => Object.entries(filtrosCol).every(([col, set]) => set.has(COLS[col].texto(c))));
    if (ordenCol) {
      const v = COLS[ordenCol.col].valor;
      visibles = [...visibles].sort((a, b) => { const x = v(a), y = v(b); return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es', {numeric: true})) * ordenCol.dir; });
    }
    pintarEncabezado();
    const cuerpo = $('sla-lista'); cuerpo.replaceChildren();
    if (!visibles.length && !verTecnicos) cuerpo.append(el('p', 'cc-vacio', filtro === 'cerrados' ? 'No hay casos cerrados en el periodo.' : abiertos.length ? 'No hay casos con este filtro.' : 'No hay casos abiertos. 🎉'));
    for (const c of visibles.slice(0, 400)) {
      const [nombre, simbolo, cls] = ESTADOS[c.estado];
      const fila = el('div', 'sla-fila ' + cls); fila.setAttribute('role', 'row');
      const t = el('span', 'sla-dos'); t.append(el('strong', 'sla-ticket', c.ticket), el('small', null, c.site || '—'));
      const tec = el('span', 'sla-dos'); tec.append(el('span', null, c.tecnico || '—'), el('small', null, c.tecnico_nombre || ''));
      // Columnas reales; la fecha con la que empieza el SLA va resaltada (CM: Dispatch; PM/PLM: Arrive).
      const celdaFecha = (valor, usada) => { const s = el('span', 'sla-fecha' + (usada ? ' sla-fecha-inicio' : ''), valor || '—'); if (usada) s.title = 'Desde aquí cuenta el SLA'; return s; };
      const reales = [celdaFecha(c.dispatch, c.tipo === 'CM'), celdaFecha(c.arrive, c.tipo !== 'CM'), celdaFecha(c.fin, false),
        el('span', 'sla-num', c.sla_hour ? (/^\d+(\.\d+)?$/.test(c.sla_hour) ? c.sla_hour + ' min' : c.sla_hour) : '—'),
        estadoSla(c)];
      const tiempo = el('span', 'sla-tiempo');
      if (c.estado === 'cumple' || c.estado === 'no_cumple') {
        const cab = el('span', 'sla-tiempo-cab'); cab.append(el('small', null, c.uso ? 'Usó ' + Math.round(c.uso) + ' % del objetivo' + (c.pausa ? ' · pausa ' + duracion(c.pausa) : '') : '—'));
        const p = el('span', 'sla-pista'), f = el('span'); f.style.width = Math.min(100, c.uso) + '%'; p.append(f); tiempo.append(cab, p);
      } else if (SIN_MEDIR.includes(c.estado)) tiempo.append(el('small', null, c.estado === 'sin_inicio' ? 'Falta ' + (c.tipo === 'CM' || entel || integratel ? 'Dispatch Time' : 'Arrive Time')
        : c.estado === 'sla_cero' ? 'SLA en 0: no se puede medir' : entel ? 'Sin regla de Fault Level' : integratel && c.tipo === 'CM' ? 'Sla vacío' : integratel ? 'Sin Require Finish Time' : 'SLA Hour vacío'));
      else {
        const cab = el('span', 'sla-tiempo-cab'); cab.append(el('small', null, 'Objetivo ' + duracion(c.objetivo) + (c.pausa ? ' · pausa ' + duracion(c.pausa) : '')), el('small', null, Math.round(c.uso) + ' %'));
        const p = el('span', 'sla-pista'), f = el('span'); f.style.width = Math.min(100, c.uso) + '%'; p.append(f);
        tiempo.append(cab, p);
      }
      const estado = el('span', 'sla-estado');
      estado.append(icono(simbolo), el('span', null, c.estado === 'vencido' ? 'Vencido · hace ' + duracion(-c.resto)
        : [...SIN_MEDIR, 'cumple', 'no_cumple'].includes(c.estado) ? nombre : nombre + ' · quedan ' + duracion(c.resto)));
      fila.append(t, el('span', 'sla-tipo-chip', c.tipo), el('span', 'sla-categoria', c.categoria || '—'), el('span', 'sla-categoria', c.fm_office || '—'), tec, ...reales, tiempo, estado);
      cuerpo.append(fila);
    }
    if (visibles.length > 400) cuerpo.append(el('p', 'cc-vacio', 'Se muestran 400 de ' + visibles.length + '. Usa la búsqueda o los filtros.'));

    const caja = $('sla-tecnicos'); caja.replaceChildren();
    if (!tecs.length) caja.append(el('p', 'cc-vacio', 'Sin casos abiertos ni cerrados en el periodo.'));
    else {
      const leyenda = el('p', 'sla-tec-leyenda');
      leyenda.append('Técnico asignado, ordenado por lo más urgente de su backlog.',
        ...[['vencido', 'Vencidos'], ['por_vencer', 'Por vencer'], ['en_plazo', 'En plazo'], ['sin', 'Sin medir']].map(([k, t]) => el('span', 'sla-tec-punto sla-tec-' + k, t)),
        'Clic en un técnico para ver sus casos abiertos.');
      caja.append(leyenda);
    }
    const NOMBRES_ESTADO = {vencido: 'vencidos', por_vencer: 'por vencer', en_plazo: 'en plazo', sin: 'sin medir'};
    for (const x of tecs) {
      const tarjeta = el('button', 'sla-tec' + (x.vencido ? ' con-vencidos' : x.por_vencer ? ' con-por-vencer' : '')); tarjeta.type = 'button';
      tarjeta.title = 'Ver los casos abiertos de ' + x.nombre;
      const cab = el('div', 'sla-tec-cab');
      cab.append(el('strong', null, x.nombre), el('span', 'sla-tec-backlog', x.abiertos ? x.abiertos + ' en backlog' : 'Sin backlog'));
      const barra = el('div', 'sla-tec-barra' + (x.abiertos ? '' : ' vacia'));
      const cifras = el('div', 'sla-tec-cifras');
      for (const k of Object.keys(NOMBRES_ESTADO)) {
        if (!x[k]) continue;
        const tramo = el('span', 'sla-tec-' + k); tramo.style.flex = String(x[k]); tramo.title = x[k] + ' ' + NOMBRES_ESTADO[k]; barra.append(tramo);
        cifras.append(el('span', 'sla-tec-punto sla-tec-' + k, x[k] + ' ' + NOMBRES_ESTADO[k]));
      }
      const pie = el('div', 'sla-tec-pie');
      if (x.pct === null) pie.append(el('span', null, 'Sin cierres en el periodo'));
      else {
        const nivel = x.pct >= 95 ? 'ok' : x.pct >= 85 ? 'medio' : 'bajo';
        pie.append(el('span', null, 'SLA de cerrados: '), el('strong', 'sla-tec-sla-' + nivel, x.pct.toFixed(1) + ' %'), el('span', null, ' · ' + x.ok + ' de ' + x.cerrados));
      }
      tarjeta.append(cab, barra, cifras, pie);
      tarjeta.addEventListener('click', () => { $('cc-buscar').value = x.nombre === 'Sin técnico asignado' ? '' : x.nombre; filtro = ''; pintar(); });
      caja.append(tarjeta);
    }
    $('sla-reloj').textContent = 'Actualizado ' + ahora.toLocaleTimeString('es-PE', {hour: '2-digit', minute: '2-digit'});
  }

  async function cargar(clave) {
    if (cache[clave]) return;
    const r = await fetch('/api/sla/' + clave); const j = await r.json().catch(() => ({}));
    cache[clave] = r.ok ? j.casos || [] : [];
    if (j.pendiente) {
      document.querySelector('[data-cuenta="' + clave + '"]').textContent = '—';
      document.querySelector('[data-cumple="' + clave + '"]').textContent = 'Por definir';
      return;
    }
    resumenPestana(clave);
  }
  // Cuenta de abiertos y % de cumplimiento de la pestaña (cerrados del periodo elegido).
  function resumenPestana(clave) {
    const lista = cache[clave]; if (!lista) return;
    const cerrados = lista.filter(c => c.cerrado && enPeriodo(c)), ok = cerrados.filter(cumple).length;
    document.querySelector('[data-cuenta="' + clave + '"]').textContent = lista.filter(c => !c.cerrado).length.toLocaleString('es-PE');
    document.querySelector('[data-cumple="' + clave + '"]').textContent = cerrados.length ? (ok / cerrados.length * 100).toFixed(1) + ' % cumple' : 'Sin cerrados';
  }

  // Sin casos abiertos (ej. Entel, que llega todo en Completed): se abre en "Cerrados" para no mostrar la lista vacía.
  const filtroInicial = () => { const l = cache[proyecto]; if (!filtro && l && l.length && !l.some(c => !c.cerrado)) filtro = 'cerrados'; };
  document.querySelectorAll('.sla-proyecto').forEach(b => b.addEventListener('click', async () => {
    proyecto = b.dataset.proyecto; filtro = ''; try { localStorage.setItem('sla-proyecto', proyecto); } catch (_) {} pintar(); await cargar(proyecto); filtroInicial(); pintar();
  }));
  document.querySelectorAll('.sla-tipo').forEach(b => b.addEventListener('click', () => { tipo = b.dataset.tipo; pintar(); }));
  $('sla-periodo').addEventListener('change', e => {
    periodo = e.target.value;
    // El % de cada pestaña sigue el mismo periodo.
    document.querySelectorAll('.sla-proyecto').forEach(b => { if ((CFG.con_criterios || []).includes(b.dataset.proyecto)) resumenPestana(b.dataset.proyecto); });
    pintar();
  });
  $('sla-categoria').addEventListener('change', e => { categoria = e.target.value; pintar(); });
  $('cc-buscar').addEventListener('input', pintar);
  $('cc-excel').addEventListener('click', () => {
    if (typeof XLSX === 'undefined' || !cache[proyecto]) return;
    const ahora = new Date();
    const filas = cache[proyecto].filter(c => (!tipo || c.tipo === tipo) && (!categoria || c.categoria === categoria)).map(c => {
      const m = c.cerrado ? null : medir(c, ahora);
      return {'Ticket': c.ticket, 'Tipo': c.tipo, 'Task Category': c.categoria, 'FM Office': c.fm_office || '', 'Site': c.site, 'Schedule Operator': c.tecnico, 'Nombre': c.tecnico_nombre,
        'Dispatch Time': c.dispatch, 'Arrive Time': c.arrive, 'Complete Time': c.fin, 'SLA Hour': c.sla_hour, 'SLA Status': c.sla_status_original, 'Resultado SLA': resultadoSla(c),
        'Inicio SLA usado': c.inicio, 'Objetivo (min)': c.objetivo || '', 'Task Status': c.estado_ticket, 'Estado': c.cerrado ? (cumple(c) ? 'Cerrado · cumple' : 'Cerrado · no cumple') : ESTADOS[m.estado][0],
        'Minutos restantes': m && m.resto !== null ? Math.round(m.resto) : '',
        'Pausa SLA (min)': c.pausa || '', 'SLA Cobra': c.sla_cobra || ''};
    });
    const libro = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filas), 'SLA ' + proyecto);
    XLSX.writeFile(libro, 'SLA_' + proyecto + '.xlsx');
  });

  const disponibles = [...document.querySelectorAll('.sla-proyecto')].map(b => b.dataset.proyecto);
  if (!disponibles.includes(proyecto)) proyecto = disponibles.includes('CLARO') ? 'CLARO' : disponibles[0];
  pintar();
  cargar(proyecto).then(filtroInicial).then(pintar).then(() => Promise.all(disponibles.filter(p => p !== proyecto).map(cargar)));
  // Cuenta regresiva: se recalcula cada minuto para avisar antes de que venza.
  setInterval(pintar, 60000);
})();
