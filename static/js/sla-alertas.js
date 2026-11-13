/* Alertas de SLA en todas las pantallas: avisa cuando hay casos por vencer (para que todos se enteren).
   Revisa cada 2 minutos; muestra una tarjeta llamativa abajo a la derecha. "Ocultar" la calla 15 min,
   salvo que aparezca un caso nuevo por vencer. */
(() => {
  'use strict';
  if (window.__slaAlertas) return; window.__slaAlertas = true;
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const leer = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (_) { return d; } };
  const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} };
  const tiempo = m => m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min' : m + ' min';
  let caja = null;

  function pintar(lista) {
    caja?.remove(); caja = null;
    if (!lista.length) return;
    const silencio = leer('sla-alerta-silencio', {hasta: 0, vistos: []});
    const nuevos = lista.filter(c => !silencio.vistos.includes(c.ticket));
    if (Date.now() < silencio.hasta && !nuevos.length) return;
    caja = el('aside', 'sla-alerta'); caja.setAttribute('role', 'alert'); caja.setAttribute('aria-live', 'assertive');
    const cab = el('header', 'sla-alerta-cab');
    const titulo = el('strong'); titulo.append(el('i', 'fa-solid fa-hourglass-half'), ' ' + lista.length + (lista.length === 1 ? ' caso por vencer' : ' casos por vencer'));
    const cerrar = el('button', 'sla-alerta-x'); cerrar.type = 'button'; cerrar.title = 'Ocultar 15 min'; cerrar.setAttribute('aria-label', 'Ocultar alerta 15 minutos');
    cerrar.append(el('i', 'fa-solid fa-xmark'));
    cerrar.addEventListener('click', () => { guardar('sla-alerta-silencio', {hasta: Date.now() + 15 * 60000, vistos: lista.map(c => c.ticket)}); caja.remove(); caja = null; });
    cab.append(titulo, cerrar);
    const ul = el('ul', 'sla-alerta-lista');
    for (const c of lista.slice(0, 4)) {
      const li = el('li', c.resto <= 15 ? 'critico' : '');
      const izq = el('span'); izq.append(el('b', null, c.ticket), el('small', null, [c.proyecto, c.categoria, c.tecnico_nombre || c.tecnico].filter(Boolean).join(' · ')));
      li.append(izq, el('em', null, 'quedan ' + tiempo(c.resto)));
      ul.append(li);
    }
    const ver = el('a', 'sla-alerta-ver', lista.length > 4 ? 'Ver los ' + lista.length + ' en SLA' : 'Ver en SLA'); ver.href = '/sla/';
    caja.append(cab, ul, ver);
    document.body.append(caja);
    // Aviso del sistema operativo (si el usuario lo permitió) solo cuando aparece un caso nuevo.
    if (nuevos.length && 'Notification' in window && Notification.permission === 'granted' && document.hidden) {
      try { new Notification('SLA · ' + nuevos.length + ' caso(s) por vencer', {body: nuevos.slice(0, 3).map(c => c.ticket + ' · quedan ' + tiempo(c.resto)).join('\n'), tag: 'sla-por-vencer'}); } catch (_) {}
    }
  }

  async function revisar() {
    try {
      const r = await fetch('/api/sla/alertas', {cache: 'no-store'});
      if (!r.ok) return;
      pintar((await r.json()).alertas || []);
    } catch (_) {}
  }
  if ('Notification' in window && Notification.permission === 'default') {
    document.addEventListener('click', () => { try { Notification.requestPermission(); } catch (_) {} }, {once: true});
  }
  setTimeout(revisar, 1500);
  setInterval(revisar, 120000);
})();
