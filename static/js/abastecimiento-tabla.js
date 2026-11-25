(() => {
  const tabla = document.querySelector('[data-ab-tabla]');
  const panel = document.getElementById('ab-filtro-tabla');
  const cuerpo = tabla.tBodies[0];
  const vacio = cuerpo.querySelector('[data-sin-resultados]');
  const filas = [...cuerpo.querySelectorAll('[data-ab-fila]')];
  const columnas = [...tabla.querySelectorAll('[data-columna]')];
  const comparador = new Intl.Collator('es-PE', {numeric: true, sensitivity: 'base'});
  const normalizar = texto => texto.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
  const valor = (fila, columna) => fila.cells[Number(columna.dataset.columna)].textContent.trim();
  const estado = new Map(columnas.map(columna => [columna, {
    buscar: columna.querySelector('input'), ordenar: columna.querySelector('[data-ordenar]'),
    filtrar: columna.querySelector('[data-filtrar]'), valores: null,
  }]));
  let orden = null, filtroAbierto = null;

  function coincide(fila) {
    return columnas.every(columna => {
      const {buscar, valores} = estado.get(columna);
      const texto = valor(fila, columna);
      return (!valores || valores.has(texto)) && normalizar(texto).includes(normalizar(buscar.value));
    });
  }

  function pintar() {
    const ordenadas = orden ? [...filas].sort((a, b) =>
      orden.sentido * comparador.compare(valor(a, orden.columna), valor(b, orden.columna))) : filas;
    for (const fila of ordenadas) {
      fila.hidden = !coincide(fila);
      cuerpo.insertBefore(fila, vacio);
    }
    vacio.hidden = filas.some(fila => !fila.hidden);
  }

  function cerrarFiltro() {
    if (!filtroAbierto) return;
    filtroAbierto.setAttribute('aria-expanded', 'false');
    filtroAbierto = null;
    panel.hidden = true;
  }

  function abrirFiltro(columna) {
    const {filtrar, valores} = estado.get(columna);
    const estabaAbierto = filtroAbierto === filtrar;
    cerrarFiltro();
    if (estabaAbierto) return;
    const opciones = [...new Set(filas.map(fila => valor(fila, columna)))].sort(comparador.compare);
    const titulo = columna.dataset.etiqueta;
    panel.setAttribute('aria-label', 'Filtrar ' + titulo);
    panel.replaceChildren();
    const buscar = Object.assign(document.createElement('input'), {type: 'search', placeholder: 'Buscar en ' + titulo.toLowerCase()});
    buscar.setAttribute('aria-label', buscar.placeholder);
    const lista = document.createElement('div');
    lista.className = 'cc-filtro-valores';
    const controles = opciones.map(opcion => {
      const etiqueta = document.createElement('label');
      const check = Object.assign(document.createElement('input'), {type: 'checkbox', value: opcion, checked: !valores || valores.has(opcion)});
      etiqueta.append(check, opcion);
      lista.append(etiqueta);
      return {etiqueta, check};
    });
    const todos = document.createElement('label');
    todos.className = 'cc-todos';
    const seleccionarTodos = Object.assign(document.createElement('input'), {type: 'checkbox'});
    todos.append(seleccionarTodos, 'Seleccionar todo');
    lista.prepend(todos);
    const visibles = () => controles.filter(({etiqueta}) => !etiqueta.hidden);
    const sincronizar = () => {
      const items = visibles();
      seleccionarTodos.checked = items.length > 0 && items.every(({check}) => check.checked);
      seleccionarTodos.indeterminate = !seleccionarTodos.checked && items.some(({check}) => check.checked);
    };
    seleccionarTodos.addEventListener('change', () => {
      for (const {check} of visibles()) check.checked = seleccionarTodos.checked;
      sincronizar();
    });
    lista.addEventListener('change', sincronizar);
    buscar.addEventListener('input', () => {
      for (const {etiqueta, check} of controles) {
        etiqueta.hidden = !normalizar(check.value).includes(normalizar(buscar.value));
      }
      sincronizar();
    });
    const pie = document.createElement('div');
    pie.className = 'cc-filtro-pie';
    const limpiar = Object.assign(document.createElement('button'), {type: 'button', className: 'cc-btn', textContent: 'Limpiar'});
    const aplicar = Object.assign(document.createElement('button'), {type: 'button', className: 'cc-btn cc-ok', textContent: 'Aplicar'});
    const guardar = seleccion => {
      estado.get(columna).valores = seleccion;
      filtrar.classList.toggle('activo', Boolean(seleccion));
      cerrarFiltro();
      pintar();
      filtrar.focus();
    };
    limpiar.addEventListener('click', () => guardar(null));
    aplicar.addEventListener('click', () => {
      const seleccion = controles.filter(({check}) => check.checked).map(({check}) => check.value);
      guardar(seleccion.length === opciones.length ? null : new Set(seleccion));
    });
    pie.append(limpiar, aplicar);
    panel.append(buscar, lista, pie);
    sincronizar();
    panel.hidden = false;
    filtroAbierto = filtrar;
    filtrar.setAttribute('aria-expanded', 'true');
    const posicion = filtrar.getBoundingClientRect();
    panel.style.top = Math.max(8, Math.min(posicion.bottom + 6, innerHeight - panel.offsetHeight - 8)) + 'px';
    panel.style.left = Math.max(8, Math.min(posicion.left, innerWidth - panel.offsetWidth - 8)) + 'px';
    buscar.focus({preventScroll: true});
  }

  for (const columna of columnas) {
    const {buscar, ordenar, filtrar} = estado.get(columna);
    buscar.addEventListener('input', pintar);
    ordenar.addEventListener('click', () => {
      const sentido = orden?.columna === columna ? orden.sentido === 1 ? -1 : 0 : 1;
      orden = sentido ? {columna, sentido} : null;
      for (const otra of columnas) {
        otra.removeAttribute('aria-sort');
        estado.get(otra).ordenar.classList.toggle('activo', otra === columna && Boolean(sentido));
        estado.get(otra).ordenar.firstElementChild.className = 'fa-solid fa-sort';
      }
      if (sentido) {
        columna.setAttribute('aria-sort', sentido === 1 ? 'ascending' : 'descending');
        ordenar.firstElementChild.className = sentido === 1 ? 'fa-solid fa-sort-up' : 'fa-solid fa-sort-down';
      }
      pintar();
    });
    filtrar.addEventListener('click', () => abrirFiltro(columna));
  }
  document.addEventListener('click', evento => {
    if (!panel.contains(evento.target) && !evento.target.closest('[data-filtrar]')) cerrarFiltro();
  });
  document.addEventListener('keydown', evento => {
    if (evento.key !== 'Escape' || !filtroAbierto) return;
    const boton = filtroAbierto;
    cerrarFiltro();
    boton.focus();
  });
  tabla.parentElement.addEventListener('scroll', cerrarFiltro);
  window.addEventListener('resize', cerrarFiltro);
})();
