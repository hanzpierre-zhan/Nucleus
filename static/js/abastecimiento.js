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

for (const campos of document.querySelectorAll('.ab-campos')) {
  const unidad = campos.querySelector('[name="tipo"]');
  const combustible = campos.querySelector('[name="combustible"]');
  const actualizar = () => {
    for (const campo of campos.querySelectorAll('[data-unidad], [data-combustible-otro]')) {
      campo.hidden = campo.hasAttribute('data-unidad')
        ? campo.dataset.unidad !== unidad.value : combustible.value !== 'otro';
      campo.querySelector('input').disabled = campo.hidden;
    }
    campos.querySelector('[name="otro_combustible"]').required = combustible.value === 'otro';
  };
  unidad.addEventListener('change', actualizar);
  combustible.addEventListener('change', actualizar);
  actualizar();
}

for (const formulario of document.querySelectorAll('.ab-form')) {
  formulario.addEventListener('submit', async evento => {
    evento.preventDefault();
    const boton = evento.submitter;
    const aviso = formulario.querySelector('[data-error]');
    const datos = new FormData(formulario);
    aviso.hidden = true;
    const botones = [...formulario.querySelectorAll('button[type="submit"]')];
    botones.forEach(b => { b.disabled = true; });
    try {
      const respuesta = await fetch(boton?.getAttribute('formaction') || formulario.action, {method: 'POST', body: datos});
      const resultado = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok || !resultado.ok) throw Error(resultado.error || 'No se pudo guardar. Actualiza la página y vuelve a intentar.');
      if (window.parent !== window) window.parent.postMessage('abastecimiento-prueba-guardada', location.origin);
      window.location.reload();
    } catch (error) {
      aviso.textContent = error.message;
      aviso.hidden = false;
      botones.forEach(b => { b.disabled = false; });
    }
  });
}
