/* Vistas nuevas (Dataper, Material, Sites, Combustible y Usuarios) con el diseño de Caja Chica. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const icono = nombre => { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; };
  const avisar = m => (window.nucleusAlert || alert)(m);
  const confirmar = async (m, t, o) => window.nucleusConfirm ? window.nucleusConfirm(m, t, o) : confirm(m);
  const plano = t => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const cfg = JSON.parse($('vn-config').textContent);
  const esUsuarios = cfg.slug === 'usuarios';
  const dialogo = $('cc-solicitud-dialogo');
  const POR_PAGINA = 300;

  let filas = [], columnas = [], columnasBase = [], tab = '', orden = null, filtros = {}, busquedas = {}, limite = POR_PAGINA;
  const memoria = 'vn-' + cfg.slug;
  try { tab = localStorage.getItem(memoria + '-tab') || ''; } catch (_) {}

  const valor = (f, c) => { const v = f.datos[c]; return v === undefined || v === null || v === '' ? '—' : String(v); };
  const numero = v => { const n = Number(String(v ?? '').replace(',', '.')); return Number.isFinite(n) ? n : null; };

  // ── Encabezado con ordenar, filtrar y buscar por columna ──
  function plantilla() {
    const anchos = columnas.map(c => c.length > 18 ? 'minmax(170px, 1.4fr)' : 'minmax(120px, 1fr)');
    $('cn-tabla').style.setProperty('--cc-min', (columnas.length * 150 + 140) + 'px');
    return ['112px', ...anchos].join(' ');
  }
  function pintarEncabezado() {
    $('cn-tabla').style.setProperty('--cc-cols', plantilla());
    const cab = $('cn-encabezado');
    const activo = document.activeElement, foco = activo && cab.contains(activo) && activo.dataset.buscar
      ? {col: activo.dataset.buscar, ini: activo.selectionStart, fin: activo.selectionEnd} : null;
    cab.replaceChildren(el('div', 'cc-th cc-th-nombre cc-acciones-cab', 'Acciones'));
    for (const id of columnas) {
      const th = el('div', 'cc-th'), fila = el('div', 'cc-th-fila'); fila.draggable = true;
      const sentido = orden?.col === id ? orden.dir : 0;
      const ordenar = el('button', 'cc-th-btn' + (sentido ? ' activo' : '')); ordenar.type = 'button';
      ordenar.append(icono(sentido === 1 ? 'fa-arrow-up-short-wide' : sentido === -1 ? 'fa-arrow-down-wide-short' : 'fa-sort'));
      ordenar.title = sentido === 1 ? 'De menor a mayor · clic: de mayor a menor' : sentido === -1 ? 'De mayor a menor · clic: quitar orden' : 'Ordenar de menor a mayor';
      ordenar.addEventListener('click', e => { e.stopPropagation(); orden = sentido === 1 ? {col: id, dir: -1} : sentido === -1 ? null : {col: id, dir: 1}; pintar(); });
      const filtrar = el('button', 'cc-th-btn' + (filtros[id] ? ' activo' : '')); filtrar.type = 'button';
      filtrar.append(icono('fa-filter')); filtrar.title = 'Filtrar ' + id;
      filtrar.addEventListener('click', e => { e.stopPropagation(); abrirFiltro(id, filtrar); });
      fila.append(el('span', 'cc-th-nombre', id), ordenar, filtrar);
      const buscar = el('input', 'cc-th-buscar'); buscar.dataset.buscar = id;
      Object.assign(buscar, {type: 'search', value: busquedas[id] || '', placeholder: 'Buscar…'});
      buscar.addEventListener('input', () => { if (buscar.value.trim()) busquedas[id] = buscar.value; else delete busquedas[id]; limite = POR_PAGINA; pintar(); });
      th.append(fila, buscar);
      fila.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', id));
      th.addEventListener('dragover', e => { e.preventDefault(); const r = th.getBoundingClientRect(), antes = e.clientX < r.left + r.width / 2; th.classList.toggle('soltar-antes', antes); th.classList.toggle('soltar-despues', !antes); });
      th.addEventListener('dragleave', () => th.classList.remove('soltar-antes', 'soltar-despues'));
      th.addEventListener('drop', e => {
        e.preventDefault();
        const origen = e.dataTransfer.getData('text/plain'); if (!columnas.includes(origen) || origen === id) return pintarEncabezado();
        const antes = th.classList.contains('soltar-antes');
        columnas = columnas.filter(c => c !== origen); columnas.splice(columnas.indexOf(id) + (antes ? 0 : 1), 0, origen);
        try { localStorage.setItem(memoria + '-columnas', JSON.stringify(columnas)); } catch (_) {}
        pintar();
      });
      cab.append(th);
    }
    if (foco) { const i = cab.querySelector('[data-buscar="' + CSS.escape(foco.col) + '"]'); if (i) { i.focus(); i.setSelectionRange(foco.ini, foco.fin); } }
  }
  function abrirFiltro(id, boton) {
    const caja = $('cn-filtro');
    if (!caja.hidden && caja.dataset.col === id) { caja.hidden = true; return; }
    const valores = [...new Set(base(id).map(f => valor(f, id)))].sort((a, b) => a.localeCompare(b, 'es', {numeric: true})).slice(0, 2000);
    const marcados = new Set(filtros[id] || valores);
    caja.dataset.col = id; caja.replaceChildren();
    const buscar = Object.assign(el('input'), {type: 'search', placeholder: 'Buscar en ' + id.toLowerCase()});
    const lista = el('div', 'cc-filtro-valores');
    const todos = el('label', 'cc-todos'), todosCheck = Object.assign(el('input'), {type: 'checkbox'}); todos.append(todosCheck, 'Seleccionar todo');
    const checks = valores.map(v => { const l = el('label'), c = Object.assign(el('input'), {type: 'checkbox', value: v, checked: marcados.has(v)}); l.append(c, v); return l; });
    const sincronizar = () => { const v = checks.filter(l => !l.hidden); todosCheck.checked = v.length > 0 && v.every(l => l.firstChild.checked); };
    todosCheck.addEventListener('change', () => checks.filter(l => !l.hidden).forEach(l => { l.firstChild.checked = todosCheck.checked; }));
    checks.forEach(l => l.firstChild.addEventListener('change', sincronizar));
    buscar.addEventListener('input', () => { const t = plano(buscar.value.trim()); checks.forEach(l => { l.hidden = t && !plano(l.textContent).includes(t); }); sincronizar(); });
    lista.append(todos, ...checks);
    const limpiar = el('button', 'cc-btn', 'Limpiar'), aplicar = el('button', 'cc-btn cc-ok', 'Aplicar'); limpiar.type = aplicar.type = 'button';
    limpiar.addEventListener('click', () => { delete filtros[id]; caja.hidden = true; pintar(); });
    aplicar.addEventListener('click', () => {
      const elegidos = checks.filter(l => l.firstChild.checked).map(l => l.firstChild.value);
      if (elegidos.length === valores.length) delete filtros[id]; else filtros[id] = elegidos;
      caja.hidden = true; limite = POR_PAGINA; pintar();
    });
    const pie = el('div', 'cc-filtro-pie'); pie.append(limpiar, aplicar);
    caja.append(buscar, lista, pie); sincronizar(); caja.hidden = false;
    const r = boton.getBoundingClientRect();
    caja.style.top = Math.min(r.bottom + 6, innerHeight - caja.offsetHeight - 8) + 'px';
    caja.style.left = Math.max(8, Math.min(r.left - 8, innerWidth - caja.offsetWidth - 8)) + 'px';
    buscar.focus();
  }
  document.addEventListener('click', e => { const c = $('cn-filtro'); if (!c.hidden && !c.contains(e.target)) c.hidden = true; });

  function base(excepto) {
    const texto = plano($('cc-buscar').value.trim());
    const lista = filas.filter(f => (!tab || f.pestana === tab)
      && (!texto || plano(f.key + ' ' + Object.values(f.datos).join(' ')).includes(texto))
      && Object.entries(filtros).every(([id, vals]) => id === excepto || vals.includes(valor(f, id)))
      && Object.entries(busquedas).every(([id, t]) => plano(valor(f, id)).includes(plano(t.trim()))));
    if (orden) lista.sort((a, b) => {
      const x = valor(a, orden.col), y = valor(b, orden.col), nx = numero(x), ny = numero(y);
      return (nx !== null && ny !== null ? nx - ny : x.localeCompare(y, 'es', {numeric: true, sensitivity: 'base'})) * orden.dir;
    });
    return lista;
  }

  // ── Botones redondos ──
  function redondo(titulo, clase, simbolo, fn, grande) {
    const b = el('button', (grande ? 'cc-dialogo-icono cn-redondo cn-grande ' : 'cc-rapida cn-redondo ') + clase); b.type = 'button';
    b.title = titulo; b.setAttribute('aria-label', titulo); b.append(icono(simbolo));
    b.addEventListener('click', async e => { e.stopPropagation(); b.disabled = true; try { await fn(); } catch (err) { avisar(err.message); } finally { b.disabled = false; } });
    return b;
  }
  async function restablecerClave(f) {
    if (!await confirmar('La clave del portal de ' + (f.datos.TECNICO || f.key) + ' volverá a ser su documento (' + f.key + '). Deberá cambiarla al ingresar.',
      'Restablecer clave', {okText: 'Restablecer', circular: true})) return;
    const r = await fetch('/api/dataper/clave/restablecer', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: f.key})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(j.error || 'No se pudo restablecer la clave.');
    avisar('Clave restablecida: ahora es el documento ' + f.key + '.');
  }
  function acciones(f) {
    const lista = [redondo(cfg.editar ? 'Ver y editar' : 'Ver detalle', cfg.editar ? 'cn-azul' : 'cn-neutro', cfg.editar ? 'fa-pen' : 'fa-eye', () => verDetalle(f))];
    if (cfg.clave_portal) lista.push(redondo('Restablecer clave del portal (vuelve a ser el documento)', 'cn-naranja', 'fa-key', () => restablecerClave(f)));
    return lista;
  }

  // ── Detalle / edición: datos a la izquierda; tarjeta del módulo a la derecha ──
  function campoEdicion(nombre, actual, opciones) {
    const fila = el('label', 'cc-pendiente-campo');
    let control;
    if (opciones) { control = el('select'); opciones.forEach(([v, t]) => control.add(new Option(t, v))); control.value = actual; }
    else control = Object.assign(el('input'), {value: actual ?? '', maxLength: 500});
    if (!cfg.editar) control.disabled = true;
    control.dataset.campo = nombre; control.dataset.inicial = actual ?? '';
    fila.append(el('span', null, nombre), control);
    return fila;
  }
  function tarjetaDerecha(f, nuevo) {
    const caja = el('section', 'cc-ficha');
    const titulo = (t, i) => { const h = el('h4', 'cc-ficha-titulo'); h.append(icono(i), el('span', null, t)); caja.append(h); };
    if (cfg.slug === 'dataper' && !nuevo) {
      titulo('Clave del portal', 'fa-key');
      caja.append(el('p', 'cc-nota', 'El técnico entra al portal con su documento y su clave. Si la olvidó, restablécela: volverá a ser su documento ' + f.key + ' y deberá cambiarla al ingresar.'));
      if (cfg.clave_portal) { const b = redondo('Restablecer clave', 'cn-naranja', 'fa-key', () => restablecerClave(f), true); const p = el('div', 'vn-centro'); p.append(b, el('span', null, 'Restablecer clave')); caja.append(p); }
      return caja;
    }
    if (cfg.slug === 'sites' && !nuevo) {
      titulo('Ubicación', 'fa-map-location-dot');
      const lat = numero(f.datos.Latitud), lon = numero(f.datos.Longitud);
      if (lat !== null && lon !== null) {
        const a = el('a', 'vn-mapa'); a.href = 'https://www.google.com/maps?q=' + lat + ',' + lon; a.target = '_blank'; a.rel = 'noopener';
        a.append(icono('fa-map-pin'), el('span', null, lat.toFixed(5) + ', ' + lon.toFixed(5)), el('small', null, 'Abrir en Google Maps'));
        caja.append(a);
      } else caja.append(el('p', 'cc-nota', 'Sin coordenadas registradas.'));
      return caja;
    }
    if (cfg.slug === 'combustible' && !nuevo) {
      titulo('Foto del reporte', 'fa-image');
      const url = String(f.datos.FOTO || '').match(/(https?:\/\/\S+|\/(?:api|static)\/\S+)/)?.[0];
      if (url) { const a = el('a', 'vn-foto'); a.href = url; a.target = '_blank'; a.rel = 'noopener'; const img = el('img'); img.src = url; img.alt = 'Foto'; img.loading = 'lazy'; a.append(img); caja.append(a); }
      else caja.append(el('p', 'cc-nota', 'Sin foto.'));
      return caja;
    }
    return null;
  }
  function verDetalle(f, nuevo = false) {
    $('cc-solicitud-titulo').textContent = nuevo ? 'Nuevo registro · ' + cfg.titulo : [cfg.titulo, f.key, f.datos.TECNICO || f.datos.DESCRIPCION_MATERIAL || f.datos.Site || ''].filter(Boolean).join(' · ');
    const accionesCab = $('cn-dialogo-acciones');
    accionesCab.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    const form = el('form', 'cc-ficha vn-form'); form.noValidate = true;
    const cab = el('h4', 'cc-ficha-titulo'); cab.append(icono('fa-file-lines'), el('span', null, nuevo ? 'Datos del nuevo registro' : 'Datos'));
    form.append(cab);
    if (nuevo) form.append(campoEdicion(cfg.clave + ' (clave)', '', null));
    const campos = [...new Set([...columnasBase, ...Object.keys(f.datos)])].filter(c => c !== 'EDITADO POR');
    for (const c of campos) form.append(campoEdicion(c, f.datos[c] ?? ''));
    if (!nuevo && f.datos['EDITADO POR']) form.append(el('p', 'cc-nota', 'Última edición: ' + f.datos['EDITADO POR']));
    const derecha = tarjetaDerecha(f, nuevo);
    const contenedor = el('div', 'cc-validacion-columnas' + (derecha ? '' : ' cc-una-columna'));
    contenedor.append(form); if (derecha) contenedor.append(derecha);
    if (cfg.editar) accionesCab.prepend(redondo(nuevo ? 'Crear registro' : 'Guardar cambios', 'cn-verde', 'fa-floppy-disk', () => guardar(f, form, nuevo), true));
    $('cc-solicitud-contenido').replaceChildren(contenedor);
    if (!dialogo.open) dialogo.showModal();
  }
  async function guardar(f, form, nuevo) {
    const controles = [...form.querySelectorAll('[data-campo]')];
    if (nuevo) {
      const clave = controles.shift().value.trim();
      if (!clave) throw Error('Escribe ' + cfg.clave + '.');
      const datos = Object.fromEntries(controles.filter(c => c.value.trim()).map(c => [c.dataset.campo, c.value.trim()]));
      const r = await fetch('/api/vista/' + cfg.slug + '/agregar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: clave, data: datos})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error) throw Error(j.error || 'No se pudo crear el registro.');
    } else {
      const cambios = controles.filter(c => c.value !== c.dataset.inicial);
      if (!cambios.length) { dialogo.close(); return; }
      for (const c of cambios) {
        const r = await fetch('/api/vista/' + cfg.slug + '/actualizar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: f.key, field: c.dataset.campo, value: c.value})});
        const j = await r.json().catch(() => ({}));
        if (!r.ok || j.error) throw Error(c.dataset.campo + ': ' + (j.error || 'no se pudo guardar.'));
      }
    }
    dialogo.close(); await cargar();
  }

  // ── Usuarios ──
  const ROLES = cfg.pestanas.map(([v, t]) => [v, t]);
  function verUsuario(f, nuevo = false) {
    const u = f.usuario || {nombre: '', username: '', rol: 'supervisor', proyectos: []};
    $('cc-solicitud-titulo').textContent = nuevo ? 'Nuevo usuario' : 'Usuario · ' + (u.nombre || u.username);
    const accionesCab = $('cn-dialogo-acciones');
    accionesCab.querySelectorAll('.cn-redondo').forEach(b => b.remove());
    const form = el('form', 'cc-ficha vn-form'); form.noValidate = true;
    const cab = el('h4', 'cc-ficha-titulo'); cab.append(icono('fa-id-badge'), el('span', null, 'Datos')); form.append(cab);
    form.append(campoEdicion('Nombre', u.nombre), campoEdicion('Usuario', u.username), campoEdicion('Rol', u.rol, ROLES));
    const clave = campoEdicion(nuevo ? 'Clave' : 'Nueva clave (vacío = no cambia)', ''); clave.querySelector('input').type = 'password'; clave.querySelector('input').autocomplete = 'new-password';
    form.append(clave);
    const derecha = el('section', 'cc-ficha');
    const h = el('h4', 'cc-ficha-titulo'); h.append(icono('fa-layer-group'), el('span', null, 'Módulos con acceso')); derecha.append(h);
    const lista = el('div', 'vn-modulos');
    const asignados = new Set(u.proyectos);
    for (const p of cfg.proyectos) {
      const l = el('label'), c = Object.assign(el('input'), {type: 'checkbox', value: p.id, checked: asignados.has(p.id)});
      l.append(c, el('span', null, p.nombre)); lista.append(l);
    }
    derecha.append(lista);
    // Celular: el depositante de Caja Chica entra directo a "Por depositar" desde el móvil.
    const celular = el('label', 'vn-interruptor');
    const depositante = Object.assign(el('input'), {type: 'checkbox', checked: !!u.depositante});
    depositante.setAttribute('role', 'switch');
    const textoCel = el('span'); textoCel.append(el('strong', null, 'Depositante de Caja Chica'),
      el('small', null, 'En el celular entra directo a "Por depositar" y deposita con su captura. Necesita el módulo Caja Chica. En computadora sigue viendo Nucleus normal.'));
    celular.append(depositante, textoCel);
    const hCel = el('h4', 'cc-ficha-titulo'); hCel.append(icono('fa-mobile-screen'), el('span', null, 'Celular'));
    derecha.append(hCel, celular);
    const contenedor = el('div', 'cc-validacion-columnas'); contenedor.append(form, derecha);
    accionesCab.prepend(redondo(nuevo ? 'Crear usuario' : 'Guardar cambios', 'cn-verde', 'fa-floppy-disk', async () => {
      const v = n => form.querySelector('[data-campo="' + n + '"]').value.trim();
      const cuerpo = {nombre: v('Nombre'), username: v('Usuario'), rol: v('Rol'), password: clave.querySelector('input').value,
                      proyectos: [...lista.querySelectorAll('input:checked')].map(c => Number(c.value))};
      if (!nuevo) cuerpo.id = u.id;
      const r = await fetch('/api/admin/usuario', {method: nuevo ? 'POST' : 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo)});
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error) throw Error(j.error || 'No se pudo guardar el usuario.');
      const id = nuevo ? j.id : u.id;
      if (id && depositante.checked !== !!u.depositante) {
        const d = await fetch('/api/vista/usuarios/depositante', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id, activo: depositante.checked})});
        if (!d.ok) throw Error((await d.json().catch(() => ({}))).error || 'Se guardó el usuario, pero no la opción de celular.');
      }
      dialogo.close(); await cargar();
    }, true));
    $('cc-solicitud-contenido').replaceChildren(contenedor);
    if (!dialogo.open) dialogo.showModal();
  }

  // ── Pintar ──
  function pintar() {
    document.querySelectorAll('.cn-tab').forEach(b => { b.classList.toggle('activa', b.dataset.tab === tab); b.setAttribute('aria-selected', b.dataset.tab === tab); });
    document.querySelectorAll('[data-cuenta]').forEach(n => { n.textContent = filas.filter(f => !n.dataset.cuenta || f.pestana === n.dataset.cuenta).length.toLocaleString('es-PE'); });
    if (cfg.suma) document.querySelectorAll('[data-plata]').forEach(p => {
      const s = filas.filter(f => !p.dataset.plata || f.pestana === p.dataset.plata).reduce((t, f) => t + (numero(f.datos[cfg.suma]) || 0), 0);
      p.textContent = s.toLocaleString('es-PE', {maximumFractionDigits: 1}) + ' ' + cfg.unidad;
    }); else document.querySelectorAll('[data-plata]').forEach(p => { p.hidden = true; });
    pintarEncabezado();
    const lista = $('cn-lista'); lista.replaceChildren();
    const visibles = base();
    if (!visibles.length) { lista.append(el('p', 'cc-vacio', filas.length ? 'Ningún registro coincide con los filtros.' : 'No hay registros.')); return; }
    for (const f of visibles.slice(0, limite)) {
      const fila = el('div', 'cc-card cc-resumen cc-fila-solicitud');
      const controles = el('span', 'cc-acciones-rapidas cc-col-acciones');
      controles.append(...(esUsuarios ? [redondo('Ver y editar', 'cn-azul', 'fa-pen', () => verUsuario(f))] : acciones(f)));
      fila.append(controles);
      for (const c of columnas) fila.append(el('span', null, valor(f, c)));
      lista.append(fila);
    }
    if (visibles.length > limite) {
      const mas = el('button', 'cc-btn vn-mas', 'Mostrar ' + Math.min(POR_PAGINA, visibles.length - limite) + ' más · ' + visibles.length.toLocaleString('es-PE') + ' en total');
      mas.type = 'button'; mas.addEventListener('click', () => { limite += POR_PAGINA; pintar(); });
      lista.append(mas);
    }
  }

  // ── Barra ──
  document.querySelectorAll('.cn-tab').forEach(b => b.addEventListener('click', () => {
    tab = b.dataset.tab; filtros = {}; busquedas = {}; limite = POR_PAGINA;
    try { localStorage.setItem(memoria + '-tab', tab); } catch (_) {}
    pintar();
  }));
  $('cc-buscar').addEventListener('input', () => { limite = POR_PAGINA; pintar(); });
  $('vn-nuevo')?.addEventListener('click', () => esUsuarios ? verUsuario({}, true) : verDetalle({key: '', datos: {}}, true));
  $('cc-excel').addEventListener('click', async () => {
    const lista = base();
    if (!lista.length) return;
    if (esUsuarios) return copiar(lista, true);
    const r = await fetch('/api/vista/' + cfg.slug + '/exportar', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ids: lista.map(f => f.id), columnas})});
    if (!r.ok) return avisar('No se pudo exportar.');
    const a = el('a'); a.href = URL.createObjectURL(await r.blob()); a.download = cfg.titulo + '.xlsx'; document.body.append(a); a.click(); a.remove();
  });
  async function copiar(lista, comoExcel) {
    const texto = [columnas.join('\t'), ...lista.map(f => columnas.map(c => valor(f, c).replace(/\s+/g, ' ')).join('\t'))].join('\n');
    try { await navigator.clipboard.writeText(texto); avisar(lista.length + ' filas copiadas' + (comoExcel ? ': pégalas en Excel.' : '.')); }
    catch (_) { avisar('No se pudo copiar al portapapeles.'); }
  }
  const ajustes = $('cn-ajustes-btn'), menu = $('cn-ajustes-menu');
  const cerrarMenu = () => { menu.hidden = true; ajustes.setAttribute('aria-expanded', 'false'); };
  ajustes.addEventListener('click', e => { e.stopPropagation(); const abrir = menu.hidden; menu.hidden = !abrir; ajustes.setAttribute('aria-expanded', String(abrir)); });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) cerrarMenu(); });
  menu.addEventListener('click', e => {
    const opcion = e.target.closest('[data-accion]'); if (!opcion) return;
    e.stopPropagation(); cerrarMenu();
    const a = opcion.dataset.accion;
    if (a === 'clasico') return location.assign(esUsuarios ? '/usuarios' : '/switch_project/' + cfg.proyecto + '?next=/');
    if (a === 'copiar') return copiar(base());
    if (a === 'limpiar') { filtros = {}; busquedas = {}; orden = null; $('cc-buscar').value = ''; }
    if (a === 'restablecer') { columnas = [...columnasBase]; try { localStorage.removeItem(memoria + '-columnas'); } catch (_) {} }
    limite = POR_PAGINA; pintar();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { $('cn-filtro').hidden = true; cerrarMenu(); } });

  async function cargar() {
    const r = await fetch('/api/vista/' + cfg.slug + '/lista'); const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('cn-lista').replaceChildren(el('p', 'cc-alerta', j.error || 'No se pudo cargar.')); return; }
    if (esUsuarios) {
      const nombres = Object.fromEntries(cfg.proyectos.map(p => [p.id, p.nombre]));
      columnasBase = ['Nombre', 'Usuario', 'Rol', 'Módulos', 'Celular'];
      filas = j.usuarios.map(u => ({id: u.id, key: u.username, pestana: u.rol, usuario: u,
        datos: {Nombre: u.nombre, Usuario: u.username, Rol: (ROLES.find(r => r[0] === u.rol) || [0, u.rol])[1],
                'Módulos': u.proyectos.map(p => nombres[p]).filter(Boolean).join(', '),
                Celular: u.depositante ? 'Depositante Caja Chica' : ''}}));
    } else { columnasBase = j.columnas; filas = j.filas; }
    let guardadas = null;
    try { guardadas = JSON.parse(localStorage.getItem(memoria + '-columnas') || 'null'); } catch (_) {}
    columnas = Array.isArray(guardadas) && guardadas.length === columnasBase.length && columnasBase.every(c => guardadas.includes(c)) ? guardadas : [...columnasBase];
    pintar();
  }
  cargar();
})();
