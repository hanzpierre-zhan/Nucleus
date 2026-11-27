// Pulido visual común: estilo de gráficos (tipo Mono Charts), conteo animado de KPIs y brillo en tarjetas.
// Solo acabado visual: no cambia datos, colores elegidos por cada gráfico ni la distribución. No se carga en el dashboard de Claro.
(() => {
  const reducido = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 1) Gráficos: valores por defecto (cada gráfico conserva lo que ya define).
  if (window.Chart) {
    const d = Chart.defaults;
    const mono = 'ui-monospace, SFMono-Regular, Consolas, monospace';
    d.font.family = getComputedStyle(document.documentElement).fontFamily || d.font.family;
    d.animation.duration = reducido ? 0 : 700;
    d.animation.easing = 'easeOutQuart';
    Object.assign(d.elements.bar, {borderRadius: 6, borderSkipped: 'start'});
    Object.assign(d.elements.line, {tension: 0.35, borderWidth: 2.5, borderCapStyle: 'round', borderJoinStyle: 'round'});
    Object.assign(d.elements.point, {radius: 3, hoverRadius: 5, borderWidth: 2, hitRadius: 8});
    Object.assign(d.elements.arc, {borderWidth: 2, borderRadius: 4});
    d.scale.grid.drawTicks = false;
    d.scale.border.display = false;
    d.scale.border.dash = [2, 4];
    d.scale.ticks.padding = 6;
    d.scale.ticks.font = {family: mono, size: 10};
    Object.assign(d.plugins.legend.labels, {usePointStyle: true, pointStyle: 'circle', boxWidth: 8, boxHeight: 8, padding: 14});
    Object.assign(d.plugins.tooltip, {backgroundColor: 'rgba(17, 24, 39, .92)', cornerRadius: 10, padding: 10, boxPadding: 4,
      usePointStyle: true, titleFont: {weight: '600'}, bodyFont: {family: mono, size: 11}, caretSize: 5});
  }

  // 2) KPIs: el número sube desde cero la primera vez que aparece (Count Up). Mantiene el mismo formato.
  const KPI = '.kpi-card-val, .di-kpis strong, .df-kpis strong, .dg-kpis strong, .dg2-kpi strong, .dr-viz-kpis strong, .sla-kpi strong, .kpi-card b';
  const NUM = /-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?/;
  const vistos = new WeakSet();
  function contar(el) {
    if (reducido || vistos.has(el) || el.children.length) return;
    const texto = el.textContent, m = texto.match(NUM);
    if (!m) return;
    const fin = parseFloat(m[0].replace(/,/g, ''));
    if (!isFinite(fin) || Math.abs(fin) < 2) return;
    vistos.add(el);
    const dec = (m[0].split('.')[1] || '').length, miles = m[0].includes(',');
    const fmt = v => miles ? v.toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec}) : v.toFixed(dec);
    const antes = texto.slice(0, m.index), despues = texto.slice(m.index + m[0].length), t0 = performance.now();
    let ultimo = antes + fmt(0) + despues;
    el.textContent = ultimo;
    const paso = t => {
      if (el.textContent !== ultimo) return; // otro código cambió el valor: se respeta
      const p = Math.min(1, (t - t0) / 800);
      ultimo = p < 1 ? antes + fmt(fin * (1 - Math.pow(1 - p, 3))) + despues : texto;
      el.textContent = ultimo;
      if (p < 1) requestAnimationFrame(paso);
    };
    requestAnimationFrame(paso);
  }

  // 3) Tarjetas: brillo suave que sigue al mouse (Spotlight).
  const TARJETA = '.di-card, .dor-card, .dg2-card, .kpi-card, .expense-card, .df-analysis-card, .dv-sla-card, .up-stat, .data-stat, .inicio-tarjeta';
  function preparar(card) {
    if (card.classList.contains('nx-spot')) return;
    if (getComputedStyle(card).position === 'static' && [...card.querySelectorAll('*')].some(x => getComputedStyle(x).position === 'absolute')) return;
    card.classList.add('nx-spot');
  }
  document.addEventListener('pointermove', e => {
    const card = e.target.closest && e.target.closest('.nx-spot');
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty('--nx-x', (e.clientX - r.left) + 'px');
    card.style.setProperty('--nx-y', (e.clientY - r.top) + 'px');
  }, {passive: true});

  function revisar(raiz) {
    if (!raiz.querySelectorAll) return;
    raiz.querySelectorAll(TARJETA).forEach(preparar);
    raiz.querySelectorAll(KPI).forEach(contar);
  }
  function iniciar() {
    revisar(document);
    new MutationObserver(cambios => {
      for (const c of cambios) {
        if (c.type === 'characterData') { const p = c.target.parentElement; if (p && p.matches(KPI)) contar(p); continue; }
        c.addedNodes.forEach(n => {
          if (n.nodeType === 3) { const p = n.parentElement; if (p && p.matches(KPI)) contar(p); return; }
          if (n.nodeType !== 1) return;
          if (n.matches(TARJETA)) preparar(n);
          if (n.matches(KPI)) contar(n);
          revisar(n);
        });
      }
    }).observe(document.body, {childList: true, subtree: true, characterData: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
