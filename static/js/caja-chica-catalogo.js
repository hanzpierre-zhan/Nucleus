(() => {
  'use strict';
  const form = document.getElementById('cc-catalogo');
  const filas = document.getElementById('cc-catalogo-filas');
  const mensaje = document.getElementById('cc-catalogo-mensaje');
  const agregar = document.getElementById('cc-catalogo-agregar');
  const dialogo = document.getElementById('cc-comentario-dialogo');
  const editor = dialogo.querySelector('textarea');
  let comentarioActivo;

  function mostrarComentario(fila) {
    const texto = fila.querySelector('[name=descripcion]').value;
    const boton = fila.querySelector('[data-comentario]');
    boton.textContent = texto || 'Agregar comentario…';
    boton.title = texto || 'Agregar comentario';
  }

  dialogo.addEventListener('close', () => {
    if (dialogo.returnValue === 'aplicar' && comentarioActivo) {
      comentarioActivo.querySelector('[name=descripcion]').value = editor.value;
      mostrarComentario(comentarioActivo);
    }
    comentarioActivo = null;
  });

  // Color por clasificación; sin asignar apaga correo y cotización de ese proyecto.
  function pintarCelda(campo) {
    const celda = campo.closest('.cc-celda-proyecto');
    celda.dataset.tipo = campo.value === 'Refacturable' ? 'refa' : campo.value ? 'cobra' : 'sin';
    celda.querySelectorAll('input[type=checkbox]').forEach(c => { c.disabled = !campo.value; if (!campo.value) c.checked = false; });
  }

  function agregarFila(concepto) {
    const fila = document.getElementById('cc-catalogo-fila').content.firstElementChild.cloneNode(true);
    const nombre = fila.querySelector('[name=nombre]');
    nombre.value = concepto?.nombre || '';
    fila.querySelector('[name=descripcion]').value = concepto?.descripcion || '';
    mostrarComentario(fila);
    fila.querySelector('[data-comentario]').addEventListener('click', () => {
      comentarioActivo = fila;
      editor.value = fila.querySelector('[name=descripcion]').value;
      dialogo.returnValue = '';
      dialogo.showModal();
    });
    const pide = (valor, proyecto) => typeof valor === 'object' && valor ? Boolean(valor[proyecto]) : Boolean(valor);
    fila.querySelectorAll('[data-correo]').forEach(c => { c.checked = pide(concepto?.correo, c.dataset.correo); });
    fila.querySelectorAll('[data-cotizacion]').forEach(c => { c.checked = pide(concepto?.cotizacion, c.dataset.cotizacion); });
    fila.querySelectorAll('[data-proyecto]').forEach(campo => {
      campo.value = concepto?.proyectos[campo.dataset.proyecto] ?? 'Gasto Cobra';
      pintarCelda(campo);
      campo.addEventListener('change', () => pintarCelda(campo));
    });
    fila.querySelector('[data-quitar]').addEventListener('click', () => {
      fila.remove();
      mensaje.textContent = 'Concepto retirado del editor. Guarda para aplicar el cambio.';
      agregar.focus();
    });
    filas.append(fila);
    if (!concepto) nombre.focus();
  }

  JSON.parse(document.getElementById('cc-catalogo-datos').textContent).forEach(agregarFila);
  agregar.addEventListener('click', () => agregarFila());
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const catalogo = Array.from(filas.children, fila => ({
      nombre: fila.querySelector('[name=nombre]').value,
      descripcion: fila.querySelector('[name=descripcion]').value,
      correo: Object.fromEntries(Array.from(fila.querySelectorAll('[data-correo]'), c => [c.dataset.correo, c.checked])),
      cotizacion: Object.fromEntries(Array.from(fila.querySelectorAll('[data-cotizacion]'), c => [c.dataset.cotizacion, c.checked])),
      proyectos: Object.fromEntries(Array.from(fila.querySelectorAll('[data-proyecto]'),
        campo => [campo.dataset.proyecto, campo.value])),
    }));
    const boton = form.querySelector('[type=submit]');
    boton.disabled = true;
    mensaje.textContent = 'Guardando…';
    try {
      const respuesta = await fetch(location.pathname, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': form.dataset.csrf},
        body: JSON.stringify(catalogo),
      });
      const datos = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok || !datos.success) throw Error(datos.error || 'No se pudo guardar el catálogo.');
      mensaje.textContent = 'Cambios guardados.';
    } catch (error) {
      mensaje.textContent = error.message;
    } finally {
      boton.disabled = false;
    }
  });
})();
