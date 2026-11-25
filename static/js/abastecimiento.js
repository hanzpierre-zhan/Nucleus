const enlacePrueba = document.getElementById('ab-abrir-prueba');
const ventanaPrueba = document.getElementById('ab-prueba');
const pantallaPrueba = document.getElementById('ab-prueba-pantalla');

if (enlacePrueba && ventanaPrueba && pantallaPrueba) {
  let actualizarGestion = false;
  enlacePrueba.addEventListener('click', evento => {
    if (evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
    evento.preventDefault();
    pantallaPrueba.src = enlacePrueba.href;
    ventanaPrueba.showModal();
  });
  window.addEventListener('message', evento => {
    if (evento.origin === location.origin && evento.source === pantallaPrueba.contentWindow
        && evento.data === 'abastecimiento-prueba-guardada') actualizarGestion = true;
  });
  ventanaPrueba.addEventListener('close', () => {
    pantallaPrueba.removeAttribute('src');
    if (actualizarGestion) window.location.reload();
  });
}

const dialogoQr = document.getElementById('ab-qr-completo');
if (dialogoQr) {
  for (const enlace of document.querySelectorAll('[data-ver-qr]')) {
    enlace.addEventListener('click', evento => {
      evento.preventDefault();
      dialogoQr.querySelector('img').src = enlace.href;
      dialogoQr.showModal();
      dialogoQr.requestFullscreen?.().catch(() => {});
    });
  }
  dialogoQr.addEventListener('close', () => {
    if (document.fullscreenElement === dialogoQr) document.exitFullscreen().catch(() => {});
  });
}

for (const ticket of document.querySelectorAll('[data-ab-ticket]')) {
  ticket.addEventListener('input', () => { ticket.value = ticket.value.toUpperCase(); });
}

for (const boton of document.querySelectorAll('[data-ab-detalle]')) {
  const dialogo = document.getElementById(boton.dataset.abDetalle);
  boton.addEventListener('click', () => {
    dialogo.showModal();
    dialogo.dispatchEvent(new Event('ab-abrir'));
  });
}

for (const campos of document.querySelectorAll('[data-pedido]')) {
  const unidad = campos.querySelector('[name="tipo"]');
  const actualizar = () => {
    for (const campo of campos.querySelectorAll('[data-unidad]')) {
      campo.hidden = campo.dataset.unidad !== unidad.value;
      campo.querySelector('input, select').disabled = campo.hidden;
    }
  };
  unidad.addEventListener('change', actualizar);
  actualizar();

  const grifo = campos.querySelector('[name="grifo"]');
  const otroGrifo = campos.querySelector('[data-otro-grifo]');
  if (grifo && otroGrifo) {
    const nombre = otroGrifo.querySelector('input');
    const actualizarGrifo = () => {
      otroGrifo.hidden = grifo.value !== 'otro';
      nombre.disabled = otroGrifo.hidden;
      nombre.required = !otroGrifo.hidden;
    };
    grifo.addEventListener('change', actualizarGrifo);
    actualizarGrifo();
  }

  if (!campos.dataset.catalogo) continue;
  const proyecto = campos.closest('form')?.querySelector('[name="proyecto"]');
  const site = campos.querySelector('[name="site"]');
  const codigo = campos.querySelector('[name="codigo"]');
  const generador = campos.querySelector('[name="generador"]');
  let sugerencias = [], espera, consultaSites, consultaCatalogo, codigoAutomatico;

  async function consultar(q, signal) {
    const url = new URL(campos.dataset.catalogo, location.origin);
    url.searchParams.set('proyecto', proyecto?.value || campos.dataset.proyecto);
    url.searchParams.set('q', q);
    const respuesta = await fetch(url, {signal});
    if (!respuesta.ok) throw Error('Catálogo no disponible.');
    return respuesta.json();
  }

  function mostrarSites(sites) {
    sugerencias = sites;
    site.list.replaceChildren(...sites.map(s => new Option(s.codigo, s.nombre)));
  }

  async function cargarCatalogo(cambioProyecto = false) {
    consultaCatalogo?.abort();
    consultaSites?.abort();
    clearTimeout(espera);
    consultaCatalogo = new AbortController();
    const signal = consultaCatalogo.signal;
    if (cambioProyecto) {
      site.value = '';
      codigo.value = '';
      codigoAutomatico = '';
      mostrarSites([]);
      generador.options.length = 1;
    }
    try {
      const catalogo = await consultar('', signal);
      if (signal.aborted) return;
      if (!site.value) mostrarSites(catalogo.sites);
      const anterior = generador.value;
      const etiquetaAnterior = generador.selectedOptions[0]?.textContent || anterior;
      generador.options.length = 1;
      for (const g of catalogo.generadores) {
        generador.add(new Option(g.qr, g.qr));
      }
      if (anterior && ![...generador.options].some(o => o.value === anterior)) generador.add(new Option(etiquetaAnterior, anterior));
      generador.value = anterior;
    } catch (_) { /* Si falla el catálogo de Sites, se puede ingresar el site manualmente. */ }
  }

  const normal = s => s.trim().toLocaleUpperCase('es-PE');
  function completarSite(q) {
    const exactos = sugerencias.filter(s => normal(s.nombre) === normal(q) || normal(s.codigo) === normal(q));
    if (exactos.length !== 1) return false;
    site.value = exactos[0].nombre;
    codigo.value = codigoAutomatico = exactos[0].codigo;
    return true;
  }
  site.addEventListener('input', () => {
    clearTimeout(espera);
    consultaSites?.abort();
    const q = site.value.trim();
    if (codigo.value === codigoAutomatico) codigo.value = '';
    codigoAutomatico = '';
    if (completarSite(q)) return;
    consultaSites = new AbortController();
    const signal = consultaSites.signal;
    espera = setTimeout(async () => {
      try {
        const resultado = await consultar(q, signal);
        if (!signal.aborted) {
          mostrarSites(resultado.sites);
          if (q && !codigo.value) completarSite(q);
        }
      } catch (_) { /* Conserva la entrada manual. */ }
    }, 180);
  });
  proyecto?.addEventListener('change', () => cargarCatalogo(true));
  const detalle = campos.closest('details');
  const dialogo = campos.closest('.ab-dialogo-pedido');
  if (dialogo) dialogo.addEventListener('ab-abrir', () => cargarCatalogo(), {once: true});
  else if (!detalle || detalle.open) cargarCatalogo();
  else detalle.addEventListener('toggle', function abrirCatalogo() {
    if (!detalle.open) return;
    detalle.removeEventListener('toggle', abrirCatalogo);
    cargarCatalogo();
  });
}

for (const formulario of document.querySelectorAll('.ab-form')) {
  formulario.addEventListener('submit', async evento => {
    evento.preventDefault();
    const boton = evento.submitter;
    const aviso = formulario.querySelector('[data-error]');
    const datos = new FormData(formulario);
    aviso.hidden = true;
    const botones = [...formulario.elements].filter(control => control instanceof HTMLButtonElement && control.type === 'submit');
    botones.forEach(b => { b.disabled = true; });
    try {
      const respuesta = await fetch(boton?.getAttribute('formaction') || formulario.action, {method: 'POST', body: datos});
      const resultado = await respuesta.json().catch(() => ({}));
      if (resultado.codigo === 'ASISTENCIA_REQUERIDA') {
        location.href = resultado.destino;
        return;
      }
      if (!respuesta.ok || !resultado.ok) throw Error(resultado.error || 'No se pudo guardar. Actualiza la página y vuelve a intentar.');
      if (window.parent !== window) window.parent.postMessage('abastecimiento-prueba-guardada', location.origin);
      if (resultado.destino) window.location.assign(resultado.destino);
      else window.location.reload();
    } catch (error) {
      aviso.textContent = error.message;
      aviso.hidden = false;
      botones.forEach(b => { b.disabled = false; });
    }
  });
}
