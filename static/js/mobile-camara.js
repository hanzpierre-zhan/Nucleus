const fotosCapturadas = new WeakMap();
const camara = document.getElementById('ab-camara');
if (camara) {
  const video = camara.querySelector('video');
  const disparar = camara.querySelector('[data-ab-disparar]');
  const aviso = camara.querySelector('[role="alert"]');
  const captura = camara.querySelector('[data-ab-captura]');
  const revision = camara.querySelector('.ab-camara-revision');
  const confirmar = camara.querySelector('[data-ab-confirmar]');
  const rechazar = camara.querySelector('[data-ab-rechazar]');
  let flujo, objetivo, fotoPendiente, turno = 0;

  function limpiarCaptura() {
    fotoPendiente = null;
    if (captura.hasAttribute('src')) URL.revokeObjectURL(captura.src);
    captura.removeAttribute('src');
    captura.hidden = true;
    revision.hidden = true;
    video.hidden = false;
    disparar.hidden = false;
  }

  function apagar() {
    turno++;
    limpiarCaptura();
    flujo?.getTracks().forEach(pista => pista.stop());
    flujo = null;
    video.srcObject = null;
    disparar.disabled = true;
  }

  function errorCamara(mensaje) {
    aviso.textContent = mensaje;
    aviso.hidden = false;
  }

  for (const boton of document.querySelectorAll('[data-ab-foto]')) {
    const previa = boton.parentElement.querySelector('img');
    const quitar = boton.parentElement.querySelector('[data-ab-quitar-foto]');
    const archivo = boton.parentElement.querySelector('input[type="file"]');
    if (archivo?.hasAttribute('data-foto-requerida')) {
      archivo.form.addEventListener('submit', evento => {
        if (archivo.files.length) return;
        evento.preventDefault();
        boton.click();
      });
    }
    quitar.addEventListener('click', () => {
      fotosCapturadas.delete(boton);
      if (archivo) archivo.value = "";
      URL.revokeObjectURL(previa.src);
      previa.removeAttribute('src');
      previa.hidden = true;
      quitar.hidden = true;
      boton.querySelector('span').textContent = 'Tomar foto';
      boton.focus();
    });
    boton.addEventListener('click', async () => {
      apagar();
      objetivo = boton;
      const intento = turno;
      aviso.hidden = true;
      camara.querySelector('h2').textContent = boton.dataset.etiqueta;
      camara.showModal();
      if (!navigator.mediaDevices?.getUserMedia) {
        errorCamara('La cámara requiere abrir Nucleus en un navegador compatible y con conexión segura.');
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {facingMode: {ideal: boton.dataset.camara || 'environment'}, width: {ideal: 1920}, height: {ideal: 1080}},
          audio: false,
        });
        if (!camara.open || intento !== turno) {
          stream.getTracks().forEach(pista => pista.stop());
          return;
        }
        flujo = stream;
        video.srcObject = flujo;
      } catch {
        if (camara.open && intento === turno) errorCamara('No se pudo abrir la cámara. Revisa los permisos del navegador y vuelve a intentar.');
      }
    });
  }

  video.addEventListener('loadeddata', () => { if (camara.open && flujo) disparar.disabled = false; });
  disparar.addEventListener('click', () => {
    if (!video.videoWidth || !flujo) return;
    disparar.disabled = true;
    const intento = turno;
    const lienzo = document.createElement('canvas');
    lienzo.width = video.videoWidth;
    lienzo.height = video.videoHeight;
    lienzo.getContext('2d').drawImage(video, 0, 0);
    lienzo.toBlob(foto => {
      if (!camara.open || intento !== turno) return;
      if (!foto) {
        errorCamara('No se pudo tomar la foto. Vuelve a intentar.');
        disparar.disabled = false;
        return;
      }
      fotoPendiente = foto;
      captura.src = URL.createObjectURL(foto);
      captura.hidden = false;
      video.hidden = true;
      disparar.hidden = true;
      revision.hidden = false;
      confirmar.focus();
    }, 'image/jpeg', .9);
  });
  rechazar.addEventListener('click', () => {
    limpiarCaptura();
    disparar.disabled = false;
    disparar.focus();
  });
  confirmar.addEventListener('click', () => {
    if (!fotoPendiente) return;
    const archivo = objetivo.parentElement.querySelector('input[type="file"]');
    if (archivo) {
      const seleccion = new DataTransfer();
      seleccion.items.add(new File([fotoPendiente], 'perfil.jpg', {type: fotoPendiente.type}));
      archivo.files = seleccion.files;
    }
    fotosCapturadas.set(objetivo, fotoPendiente);
    const previa = objetivo.parentElement.querySelector('img');
    if (previa.hasAttribute('src')) URL.revokeObjectURL(previa.src);
    previa.src = URL.createObjectURL(fotoPendiente);
    previa.hidden = false;
    objetivo.parentElement.querySelector('[data-ab-quitar-foto]').hidden = false;
    objetivo.querySelector('span').textContent = 'Volver a tomar foto';
    camara.close();
    apagar();
  });
  camara.addEventListener('close', () => { if (!camara.open) apagar(); });
  window.addEventListener('pagehide', apagar);
}
