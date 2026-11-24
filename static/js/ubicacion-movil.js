// Nucleus Mobile: la ubicación es obligatoria. Cada acción (POST) viaja con la ubicación del momento
// y el identificador del celular; sin ubicación se bloquea la pantalla hasta activarla.
(() => {
  const LIBRES = ['/form-pruebas/ingresar', '/form-pruebas/clave', '/form-pruebas/salir'];
  let ultima = null, velo = null;

  const dispositivo = (() => {
    try {
      let id = localStorage.getItem('nucleus_dispositivo');
      if (!id) { id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/-/g, ''); localStorage.setItem('nucleus_dispositivo', id); }
      return id;
    } catch (_) { return ''; }
  })();

  function bloquear(motivo) {
    if (velo) { velo.querySelector('[data-motivo]').textContent = motivo; velo.hidden = false; return; }
    velo = document.createElement('div');
    velo.className = 'ubi-velo'; velo.setAttribute('role', 'alertdialog'); velo.setAttribute('aria-modal', 'true');
    velo.innerHTML = '<div class="ubi-caja"><div class="ubi-icono" aria-hidden="true">📍</div><h2>Activa tu ubicación</h2>'
      + '<p data-motivo></p><ol><li><strong>Android:</strong> baja la barra de arriba y prende <em>Ubicación</em>. Luego toca el candado junto a la dirección web → Permisos → Ubicación → Permitir.</li>'
      + '<li><strong>iPhone:</strong> Ajustes → Privacidad → Localización → Safari (o tu navegador) → <em>Mientras se usa</em>.</li></ol>'
      + '<p class="ubi-nota">Nucleus registra tu ubicación cuando lo usas en horario de trabajo.</p>'
      + '<button type="button" class="primary wide">Ya la activé, reintentar <span aria-hidden="true">→</span></button></div>';
    velo.querySelector('[data-motivo]').textContent = motivo;
    velo.querySelector('button').addEventListener('click', () => { velo.hidden = true; pedir().catch(() => {}); });
    document.body.append(velo);
  }

  function pedir() {
    return new Promise((ok, mal) => {
      if (!navigator.geolocation) { bloquear('Tu navegador no permite obtener la ubicación.'); return mal(Error('Sin ubicación')); }
      navigator.geolocation.getCurrentPosition(p => {
        ultima = {lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy, t: Date.now()};
        if (velo) velo.hidden = true;
        ok(ultima);
      }, e => {
        bloquear(e.code === 1 ? 'Nucleus no tiene permiso para ver tu ubicación.' : 'No se pudo obtener tu ubicación. Revisa que el GPS esté prendido.');
        mal(Error('Activa tu ubicación (GPS) para usar Nucleus Mobile.'));
      }, {enableHighAccuracy: true, timeout: 20000, maximumAge: 0});
    });
  }

  async function actual() {
    if (ultima && Date.now() - ultima.t < 60000) return ultima;
    return pedir();
  }

  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(p => { ultima = {lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy, t: Date.now()}; if (velo) velo.hidden = true; },
      e => { if (e.code === 1) bloquear('Nucleus no tiene permiso para ver tu ubicación.'); }, {enableHighAccuracy: true, maximumAge: 30000});
  }

  const original = window.fetch.bind(window);
  window.fetch = async (recurso, opciones = {}) => {
    const url = new URL(typeof recurso === 'string' ? recurso : recurso.url, location.href);
    const metodo = String(opciones.method || (typeof recurso !== 'string' && recurso.method) || 'GET').toUpperCase();
    if (metodo !== 'POST' || url.origin !== location.origin || !url.pathname.startsWith('/form-pruebas') || LIBRES.includes(url.pathname)) return original(recurso, opciones);
    const u = await actual();
    const headers = new Headers(opciones.headers || {});
    headers.set('X-Ubicacion', [u.lat, u.lng, Math.round(u.acc)].join(','));
    if (dispositivo) headers.set('X-Dispositivo', dispositivo);
    const r = await original(recurso, {...opciones, headers});
    if (r.status === 428 && (await r.clone().json().catch(() => ({}))).codigo === 'UBICACION') {
      bloquear('Nucleus no recibió tu ubicación.');
    }
    return r;
  };

  // Punto de inicio: al abrir Nucleus Mobile (una vez por sesión del navegador).
  window.addEventListener('load', async () => {
    try {
      await actual();
      if (sessionStorage.getItem('nucleus_inicio')) return;
      const token = document.getElementById('csrf')?.value;
      if (!token) return;
      const r = await window.fetch('/form-pruebas/ubicacion', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': token}, body: JSON.stringify({evento: 'Abrió Nucleus'})});
      if (r.ok) sessionStorage.setItem('nucleus_inicio', '1');
    } catch (_) { /* el velo ya avisa */ }
  });
})();
