// Nucleus Mobile · Asistencia: junior, placa y foto de la cuadrilla con coordenadas.
(() => {
  const $ = id => document.getElementById(id);
  const csrf = $('csrf').value;
  let ubicacion = null, foto = null, flujo = null, frontal = false;

  const dato = (titulo, valor) => { const d = document.createElement('div'); const s = document.createElement('span'); s.textContent = titulo; d.append(s, valor || '—'); return d; };
  function error(texto) { const e = document.querySelector('#asis-form .error'); e.textContent = texto || ''; e.hidden = !texto; if (texto) e.focus(); }
  function gps(texto, clase) { const g = $('asis-gps'); g.textContent = texto; g.className = 'asis-gps ' + (clase || ''); g.hidden = false; }

  function mostrarHecho(r) {
    $('asis-form-vista').hidden = true; $('asis-hecho-vista').hidden = false;
    $('asis-hecho-texto').textContent = 'Registraste tu asistencia hoy a las ' + r.hora + '.';
    $('asis-hecho-foto').src = '/form-pruebas/asistencia/foto/' + r.id;
    $('asis-hecho-datos').replaceChildren(dato('Junior', r.junior), dato('Placa', r.placa),
      dato('Ubicación', r.latitud.toFixed(6) + ', ' + r.longitud.toFixed(6)), dato('Precisión', r.precision != null ? '±' + Math.round(r.precision) + ' m' : ''));
    $('asis-hecho-titulo').focus();
  }

  async function cargar() {
    try {
      const r = await fetch('/form-pruebas/asistencia/datos', {credentials: 'same-origin'});
      const j = await r.json();
      if (r.status === 401) { location.href = '/form-pruebas/'; return; }
      if (!r.ok) throw Error(j.error || 'No se pudo cargar tu información.');
      $('cargando').hidden = true;
      if (j.hoy) { mostrarHecho(j.hoy); return; }
      const p = j.personal;
      $('asis-nombre').textContent = p.nombre;
      $('asis-doc').textContent = 'Documento ' + p.documento + (p.cargo ? ' · ' + p.cargo : '');
      $('asis-datos').replaceChildren(dato('Proyecto', p.proyecto), dato('Departamento', p.departamento), dato('Supervisor', p.supervisor), dato('Celular', p.celular));
      const sel = $('asis-junior');
      const grupos = [['Junior', j.juniors.filter(x => x.junior)], ['Otros del proyecto', j.juniors.filter(x => !x.junior)]];
      for (const [titulo, lista] of grupos) {
        if (!lista.length) continue;
        const g = document.createElement('optgroup'); g.label = titulo;
        lista.forEach(x => g.append(new Option(x.nombre + (x.cargo ? ' · ' + x.cargo : ''), x.id)));
        sel.append(g);
      }
      $('asis-form-vista').hidden = false;
    } catch (e) { $('cargando').textContent = e.message; }
  }

  function pedirUbicacion() {
    ubicacion = null;
    if (!navigator.geolocation) { gps('Tu celular no permite obtener la ubicación.', 'mal'); return; }
    gps('Obteniendo tu ubicación…');
    navigator.geolocation.getCurrentPosition(p => {
      ubicacion = {latitud: p.coords.latitude, longitud: p.coords.longitude, precision: p.coords.accuracy};
      gps('Ubicación: ' + ubicacion.latitud.toFixed(6) + ', ' + ubicacion.longitud.toFixed(6) + ' · ±' + Math.round(ubicacion.precision) + ' m', 'ok');
    }, () => gps('No se obtuvo tu ubicación. Activa el GPS, da permiso de ubicación y vuelve a tomar la foto.', 'mal'),
    {enableHighAccuracy: true, timeout: 20000, maximumAge: 0});
  }

  // Cámara dentro de Nucleus: no hay galería ni archivos; la foto solo sale de este visor.
  function apagarCamara() { if (flujo) flujo.getTracks().forEach(t => t.stop()); flujo = null; $('asis-camara').hidden = true; }
  async function abrirCamara() {
    error(''); apagarCamara();
    if (!navigator.mediaDevices?.getUserMedia) return error('Tu navegador no permite usar la cámara. Abre Nucleus en Chrome o Safari.');
    try {
      flujo = await navigator.mediaDevices.getUserMedia({video: {facingMode: frontal ? 'user' : {ideal: 'environment'}, width: {ideal: 1920}, height: {ideal: 1080}}, audio: false});
    } catch (_) { return error('Nucleus no tiene permiso para usar la cámara. Actívalo en los permisos del navegador y vuelve a intentar.'); }
    $('asis-video').srcObject = flujo;
    $('asis-camara').hidden = false; $('asis-camara-abrir').hidden = true; $('asis-previa').hidden = true; $('asis-repetir').hidden = true;
    pedirUbicacion();
  }
  $('asis-camara-abrir').addEventListener('click', abrirCamara);
  $('asis-repetir').addEventListener('click', () => { foto = null; abrirCamara(); });
  $('asis-girar').addEventListener('click', () => { frontal = !frontal; abrirCamara(); });
  $('asis-disparar').addEventListener('click', () => {
    const v = $('asis-video');
    if (!v.videoWidth) return;
    const lienzo = document.createElement('canvas'); lienzo.width = v.videoWidth; lienzo.height = v.videoHeight;
    lienzo.getContext('2d').drawImage(v, 0, 0);
    lienzo.toBlob(b => {
      foto = b; apagarCamara();
      $('asis-previa').src = URL.createObjectURL(b); $('asis-previa').hidden = false; $('asis-repetir').hidden = false;
      pedirUbicacion();
    }, 'image/jpeg', 0.9);
  });
  window.addEventListener('pagehide', apagarCamara);
  $('asis-placa').addEventListener('input', e => { e.target.value = e.target.value.toUpperCase(); });

  $('asis-form').addEventListener('submit', async e => {
    e.preventDefault(); error('');
    if (!$('asis-junior').value) return error('Elige a tu junior.');
    if (!$('asis-placa').value.trim()) return error('Escribe la placa del vehículo.');
    if (!foto) return error('Toma la foto de la cuadrilla.');
    if (!ubicacion) return error('Falta tu ubicación. Activa el GPS y vuelve a tomar la foto.');
    const boton = e.target.querySelector('button[type=submit]'); boton.disabled = true;
    try {
      const datos = new FormData();
      datos.append('junior', $('asis-junior').value); datos.append('placa', $('asis-placa').value.trim());
      datos.append('latitud', ubicacion.latitud); datos.append('longitud', ubicacion.longitud); datos.append('precision', ubicacion.precision);
      datos.append('foto', foto, 'cuadrilla.jpg');
      const r = await fetch('/form-pruebas/asistencia', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': csrf}, body: datos});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw Error(j.error || 'No se pudo registrar tu asistencia.');
      mostrarHecho(j.registro);
    } catch (err) { error(err.message); } finally { boton.disabled = false; }
  });

  cargar();
})();
