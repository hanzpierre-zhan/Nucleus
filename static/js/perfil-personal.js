(() => {
  'use strict';
  const campos = [['primer_nombre', 'Primer nombre'], ['segundo_nombre', 'Segundo nombre'], ['apellido_paterno', 'Apellido paterno'], ['apellido_materno', 'Apellido materno'], ['fecha_nacimiento', 'Fecha de nacimiento']];
  function prepararCampos(grid, perfil = {}) {
    grid.replaceChildren();
    for (const [key, nombre] of campos) {
      const label = document.createElement('label'), input = document.createElement('input'); label.textContent = nombre;
      input.name = key; input.required = key !== 'segundo_nombre'; input.type = key === 'fecha_nacimiento' ? 'date' : 'text';
      if (input.type === 'date') {input.min = '1900-01-01'; input.max = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Lima',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());} else input.maxLength = 60;
      input.value = perfil[key] || '';
      label.append(input); grid.append(label);
    }
  }
  async function guardarPerfil(form) {
    const respuesta = await fetch('/api/perfil-personal', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error || 'No se pudo guardar.');
    return datos;
  }
  async function aviso(personas) {
    if (personas.length) {
      const panel = document.createElement('aside'); panel.className = 'cumple-aviso'; panel.setAttribute('role', 'status');
      const titulo = document.createElement('strong'); titulo.textContent = '🎂 Hoy es el cumpleaños de';
      const nombres = document.createElement('p'); nombres.textContent = personas.map(p => p.nombre.toLocaleUpperCase('es-PE')).join(', ') + '. ¡Feliz cumpleaños!';
      const cerrar = document.createElement('button'); cerrar.className = 'cumple-cerrar'; cerrar.textContent = '×'; cerrar.setAttribute('aria-label', 'Cerrar aviso'); cerrar.onclick = () => panel.remove();
      panel.append(titulo, nombres, cerrar); document.body.append(panel);
    }
    await fetch('/api/cumpleanos/visto', {method: 'POST'});
  }
  async function iniciar() {
    const respuesta = await fetch('/api/perfil-personal'); if (!respuesta.ok) return;
    const datos = await respuesta.json();
    if (datos.perfil.fecha_nacimiento) { await aviso(datos.cumpleanos); return; }
    const dialogo = document.createElement('dialog'); dialogo.className = 'perfil-dialog';
    const titulo = document.createElement('h2'); titulo.textContent = 'Completa tus datos personales';
    const form = document.createElement('form'), grid = document.createElement('div'); grid.className = 'perfil-grid';
    prepararCampos(grid);
    const error = document.createElement('p'); error.className = 'perfil-error'; error.setAttribute('role', 'alert');
    const guardar = document.createElement('button'); guardar.type = 'submit'; guardar.className = 'perfil-guardar'; guardar.textContent = 'Guardar mis datos';
    form.append(grid, error, guardar); dialogo.append(titulo, form); document.body.append(dialogo);
    dialogo.addEventListener('cancel', e => e.preventDefault()); dialogo.showModal();
    form.addEventListener('submit', async e => {
      e.preventDefault(); guardar.disabled = true; error.textContent = '';
      try {
        const j = await guardarPerfil(form);
        dialogo.close(); dialogo.remove(); await aviso(j.cumpleanos);
      } catch (err) { error.textContent = err.message; } finally { guardar.disabled = false; }
    });
  }
  const enlace = document.getElementById('abrir-mi-perfil');
  if (enlace) {
    const dialogo = document.getElementById('mi-perfil');
    const lista = document.getElementById('mi-perfil-datos');
    const estado = document.getElementById('mi-perfil-estado');
    const botonCuenta = document.getElementById('sb-usuario-btn');
    const edicion = document.getElementById('mi-perfil-edicion');
    const acciones = document.getElementById('mi-perfil-acciones');
    const editar = document.getElementById('mi-perfil-editar');
    const cancelar = document.getElementById('mi-perfil-cancelar');
    const guardar = edicion.querySelector('[type="submit"]');
    const error = edicion.querySelector('.perfil-error');
    let perfil = {};
    function mostrarDatos() {
      lista.replaceChildren();
      for (const [campo, etiqueta] of campos) {
        const fila = document.createElement('div');
        const nombre = document.createElement('dt');
        const valor = document.createElement('dd');
        nombre.textContent = etiqueta;
        valor.textContent = campo === 'fecha_nacimiento' && perfil[campo]
          ? perfil[campo].split('-').reverse().join('/')
          : perfil[campo] || '—';
        fila.append(nombre, valor);
        lista.append(fila);
      }
    }
    function cambiarModo(editando) {
      edicion.hidden = !editando;
      lista.hidden = acciones.hidden = editando;
      estado.hidden = error.hidden = true;
    }
    editar.addEventListener('click', () => {
      prepararCampos(edicion.querySelector('.perfil-grid'), perfil);
      cambiarModo(true);
      edicion.querySelector('input').focus();
    });
    cancelar.addEventListener('click', () => {
      cambiarModo(false);
      editar.focus();
    });
    dialogo.addEventListener('cancel', event => {
      if (edicion.hidden) return;
      event.preventDefault();
      if (!guardar.disabled) cancelar.click();
    });
    edicion.addEventListener('submit', async event => {
      event.preventDefault();
      guardar.disabled = cancelar.disabled = true;
      error.hidden = true;
      try {
        ({perfil} = await guardarPerfil(edicion));
        mostrarDatos();
        const nombre = campos.slice(0, 4).map(([campo]) => perfil[campo]).filter(Boolean).join(' ');
        document.getElementById('mi-perfil-nombre').textContent = nombre;
        botonCuenta.querySelector('strong').textContent = nombre;
        botonCuenta.querySelector('.sb-avatar').textContent = nombre[0].toUpperCase();
        botonCuenta.title = nombre;
        cambiarModo(false);
        estado.textContent = 'Cambios guardados.';
        estado.hidden = false;
        editar.focus();
      } catch (err) {
        error.textContent = err.message;
        error.hidden = false;
      } finally {
        guardar.disabled = cancelar.disabled = false;
      }
    });
    dialogo.addEventListener('close', () => botonCuenta.focus());
    enlace.addEventListener('click', async event => {
      event.preventDefault();
      cambiarModo(false);
      editar.disabled = true;
      lista.replaceChildren();
      estado.textContent = 'Cargando datos…';
      estado.hidden = false;
      dialogo.showModal();
      if (botonCuenta.getAttribute('aria-expanded') === 'true') botonCuenta.click();
      try {
        const respuesta = await fetch('/api/perfil-personal', {cache: 'no-store'});
        if (!respuesta.ok) throw new Error();
        ({perfil} = await respuesta.json());
        mostrarDatos();
        editar.disabled = false;
        estado.hidden = true;
      } catch {
        estado.textContent = 'No se pudieron cargar los datos del perfil.';
      }
    });
  }
  iniciar().catch(() => {});
})();
