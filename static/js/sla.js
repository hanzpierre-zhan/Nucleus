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
  };

  // Al abrir, siempre se ven primero los casos por vencer.
  let proyecto = '', tipo = '', filtro = 'por_vencer', periodo = '';
  try { proyecto = localStorage.getItem('sla-proyecto') || ''; } catch (_) {}
  const cache = {};

  // Fechas guardadas como "2026-11-02 14:47:13" (hora de Perú, la del navegador).
  const fecha = s => { const m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/); return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : null; };
  const duracion = min => { min = Math.round(Math.abs(min)); const d = Math.floor(min / 1440), h = Math.floor(min % 1440 / 60), m = min % 60; return (d ? d + ' d ' : '') + (d || h ? h + ' h ' : '') + m + ' min'; };

  // Estado de un caso abierto, calculado contra la hora actual.
  function medir(c, ahora) {
    const ini = fecha(c.inicio);
    if (!c.objetivo || !ini) return {estado: 'sin_objetivo', resto: null, uso: 0};
    const transcurrido = (ahora - ini) / 60000, resto = c.objetivo - transcurrido, uso = Math.max(0, transcurrido / c.objetivo * 100);
    const estado = resto < 0 ? 'vencido' : (resto <= c.objetivo * CFG.porcentaje || resto <= CFG.minutos) ? 'por_vencer' : 'en_plazo';
    return {estado, resto, uso};
  }
  // Cerrado: cumple si SLA Status es "normal" (si no lo trae, se compara la duración con el objetivo).
  function cumple(c) {
    if (c.sla_status) return c.sla_status === 'normal';
    const ini = fecha(c.inicio), fin = fecha(c.fin);
    return !(ini && fin && c.objetivo) || (fin - ini) / 60000 <= c.objetivo;
  }
  function enPeriodo(c) {
    if (!periodo) return true;
    const fin = fecha(c.fin); if (!fin) return false;
    const hoy = new Date();
    if (periodo === '7') return hoy - fin <= 7 * 864e5;
    const mes = periodo === 'mes' ? new Date(hoy.getFullYear(), hoy.getMonth(), 1) : new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
    const hasta = new Date(mes.getFullYear(), mes.getMonth() + 1, 1);
    return fin >= mes && fin < hasta;
  }
  const nombreTec = c => c.tecnico ? c.tecnico + (c.tecnico_nombre ? ' · ' + c.tecnico_nombre : '') : 'Sin técnico';

  function pintar() {
    const lista = cache[proyecto];
    document.querySelectorAll('.sla-proyecto').forEach(b => { b.classList.toggle('activa', b.dataset.proyecto === proyecto); b.setAttribute('aria-selected', String(b.dataset.proyecto === proyecto)); });
    document.querySelectorAll('.sla-tipo').forEach(b => b.classList.toggle('activo', b.dataset.tipo === tipo));
    if (!lista) { $('sla-lista').replaceChildren(el('p', 'cc-vacio', 'Cargando…')); return; }
    const ahora = new Date(), q = plano($('cc-buscar').value.trim());
    const delTipo = lista.filter(c => (!tipo || c.tipo === tipo) && (!q || plano(c.ticket + ' ' + c.site + ' ' + c.tecnico + ' ' + c.tecnico_nombre).includes(q)));
    const abiertos = delTipo.filter(c => !c.fin).map(c => ({...c, ...medir(c, ahora)}));
    const cerrados = delTipo.filter(c => c.fin && enPeriodo(c));
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
    pista.append(lleno); barra.append(pista, el('span', null, cumplidos.toLocaleString('es-PE') + ' cumplidos · ' + (cerrados.length - cumplidos).toLocaleString('es-PE') + ' vencidos'));
    kpis.append(barra);
    tarjeta('sla-rojo', 'fa-alarm-clock', 'Vencidos abiertos', cuenta('vencido'), 'pasaron su SLA Hour', 'vencido');
    tarjeta('sla-ambar', 'fa-hourglass-half', 'Por vencer', cuenta('por_vencer'), 'queda ≤ ' + Math.round(CFG.porcentaje * 100) + ' % o ≤ ' + CFG.minutos + ' min', 'por_vencer');
    tarjeta('sla-verde', 'fa-circle-check', 'En plazo', cuenta('en_plazo'), 'con tiempo de sobra', 'en_plazo');
    tarjeta('sla-gris', 'fa-circle-question', 'Sin objetivo', cuenta('sin_objetivo'), 'sin SLA Hour o sin inicio', 'sin_objetivo');

    // Filtros rápidos de la lista
    const filtros = $('sla-filtros'); filtros.replaceChildren();
    for (const [clave, texto] of [['', 'Todos'], ['vencido', 'Vencidos'], ['por_vencer', 'Por vencer'], ['en_plazo', 'En plazo'], ['sin_objetivo', 'Sin objetivo']]) {
      const b = el('button', 'sla-chip' + (filtro === clave ? ' activo' : '')); b.type = 'button';
      b.append(el('span', null, texto), el('strong', null, String(clave ? cuenta(clave) : abiertos.length)));
      b.addEventListener('click', () => { filtro = clave; pintar(); }); filtros.append(b);
    }

    // Casos abiertos, más urgentes primero: por vencer y en plazo según lo que les queda; luego vencidos (los más recientes arriba).
    const orden = {por_vencer: 0, vencido: 1, en_plazo: 2, sin_objetivo: 3};
    const visibles = abiertos.filter(c => !filtro || c.estado === filtro)
      .sort((a, b) => orden[a.estado] - orden[b.estado] || (a.estado === 'vencido' ? b.resto - a.resto : (a.resto ?? 1e9) - (b.resto ?? 1e9)));
    const cuerpo = $('sla-lista'); cuerpo.replaceChildren();
    if (!visibles.length) cuerpo.append(el('p', 'cc-vacio', abiertos.length ? 'No hay casos con este filtro.' : 'No hay casos abiertos. 🎉'));
    for (const c of visibles.slice(0, 400)) {
      const [nombre, simbolo, cls] = ESTADOS[c.estado];
      const fila = el('div', 'sla-fila ' + cls); fila.setAttribute('role', 'row');
      const t = el('span', 'sla-dos'); t.append(el('strong', 'sla-ticket', c.ticket), el('small', null, c.site || '—'));
      const tec = el('span', 'sla-dos'); tec.append(el('span', null, c.tecnico || '—'), el('small', null, c.tecnico_nombre || ''));
      const tiempo = el('span', 'sla-tiempo');
      if (c.estado === 'sin_objetivo') tiempo.append(el('small', null, c.objetivo ? 'Sin hora de inicio' : 'Sin SLA Hour'));
      else {
        const cab = el('span', 'sla-tiempo-cab'); cab.append(el('small', null, 'Objetivo ' + c.objetivo + ' min'), el('small', null, Math.round(c.uso) + ' %'));
        const p = el('span', 'sla-pista'), f = el('span'); f.style.width = Math.min(100, c.uso) + '%'; p.append(f);
        tiempo.append(cab, p);
      }
      const estado = el('span', 'sla-estado');
      estado.append(icono(simbolo), el('span', null, c.estado === 'vencido' ? 'Vencido · hace ' + duracion(-c.resto)
        : c.estado === 'sin_objetivo' ? nombre : nombre + ' · quedan ' + duracion(c.resto)));
      fila.append(t, el('span', 'sla-tipo-chip', c.tipo), tec, tiempo, estado);
      cuerpo.append(fila);
    }
    if (visibles.length > 400) cuerpo.append(el('p', 'cc-vacio', 'Se muestran 400 de ' + visibles.length + '. Usa la búsqueda o los filtros.'));

    // Cumplimiento por técnico (cerrados del periodo), de menor a mayor para ver primero a quién apoyar.
    const porTec = {};
    for (const c of cerrados) { const k = c.tecnico || ''; const x = porTec[k] ||= {c, total: 0, ok: 0}; x.total++; if (cumple(c)) x.ok++; }
    const tecs = Object.values(porTec).map(x => ({...x, pct: x.ok / x.total * 100})).sort((a, b) => a.pct - b.pct || b.total - a.total);
    const caja = $('sla-tecnicos'); caja.replaceChildren();
    if (!tecs.length) caja.append(el('p', 'cc-vacio', 'Sin casos cerrados en el periodo.'));
    for (const x of tecs) {
      const fila = el('div', 'sla-tec'), cab = el('div', 'sla-tec-cab');
      cab.append(el('strong', null, nombreTec(x.c)), el('span', null, x.pct.toFixed(1) + ' % · ' + x.total + ' casos'));
      const p = el('div', 'sla-pista'), f = el('span'); f.style.width = x.pct + '%'; f.dataset.nivel = x.pct >= 90 ? 'ok' : x.pct >= 80 ? 'medio' : 'bajo'; p.append(f);
      const abiertosTec = abiertos.filter(c => c.tecnico === x.c.tecnico && ['vencido', 'por_vencer'].includes(c.estado)).length;
      fila.append(cab, p); if (abiertosTec) fila.append(el('small', 'sla-tec-alerta', abiertosTec + ' abierto(s) vencido(s) o por vencer'));
      caja.append(fila);
    }
    $('sla-reloj').textContent = 'Actualizado ' + ahora.toLocaleTimeString('es-PE', {hour: '2-digit', minute: '2-digit'});
  }

  async function cargar(clave) {
    if (cache[clave]) return;
    const r = await fetch('/api/sla/' + clave); const j = await r.json().catch(() => ({}));
    cache[clave] = r.ok ? j.casos || [] : [];
    const lista = cache[clave], cerrados = lista.filter(c => c.fin), ok = cerrados.filter(cumple).length;
    document.querySelector('[data-cuenta="' + clave + '"]').textContent = lista.filter(c => !c.fin).length.toLocaleString('es-PE');
    document.querySelector('[data-cumple="' + clave + '"]').textContent = cerrados.length ? (ok / cerrados.length * 100).toFixed(1) + ' % cumple' : 'Sin cerrados';
  }

  document.querySelectorAll('.sla-proyecto').forEach(b => b.addEventListener('click', async () => {
    proyecto = b.dataset.proyecto; filtro = 'por_vencer'; try { localStorage.setItem('sla-proyecto', proyecto); } catch (_) {} pintar(); await cargar(proyecto); pintar();
  }));
  document.querySelectorAll('.sla-tipo').forEach(b => b.addEventListener('click', () => { tipo = b.dataset.tipo; pintar(); }));
  $('sla-periodo').addEventListener('change', e => { periodo = e.target.value; pintar(); });
  $('cc-buscar').addEventListener('input', pintar);
  $('cc-excel').addEventListener('click', () => {
    if (typeof XLSX === 'undefined' || !cache[proyecto]) return;
    const ahora = new Date();
    const filas = cache[proyecto].filter(c => !tipo || c.tipo === tipo).map(c => {
      const m = c.fin ? null : medir(c, ahora);
      return {'Ticket': c.ticket, 'Tipo': c.tipo, 'Site': c.site, 'Técnico': c.tecnico, 'Nombre': c.tecnico_nombre, 'Inicio SLA': c.inicio, 'Fin (Complete Time)': c.fin,
        'Objetivo (min)': c.objetivo || '', 'Estado': c.fin ? (cumple(c) ? 'Cerrado · cumple' : 'Cerrado · no cumple') : ESTADOS[m.estado][0],
        'SLA Status': c.sla_status, 'Minutos restantes': m && m.resto !== null ? Math.round(m.resto) : ''};
    });
    const libro = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filas), 'SLA ' + proyecto);
    XLSX.writeFile(libro, 'SLA_' + proyecto + '.xlsx');
  });

  const disponibles = [...document.querySelectorAll('.sla-proyecto')].map(b => b.dataset.proyecto);
  if (!disponibles.includes(proyecto)) proyecto = disponibles.includes('CLARO') ? 'CLARO' : disponibles[0];
  pintar();
  cargar(proyecto).then(pintar).then(() => Promise.all(disponibles.filter(p => p !== proyecto).map(cargar)));
  // Cuenta regresiva: se recalcula cada minuto para avisar antes de que venza.
  setInterval(pintar, 60000);
})();
