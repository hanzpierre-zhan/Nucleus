/* Caja Chica en el celular del depositante: lista Por depositar y depósito con captura.
   Usa el mismo flujo y las mismas reglas de la gestión: /api/caja-chica/<id>/depositar. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const plano = t => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const PROYECTOS = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};
  // Vistas del menú: Por depositar (se deposita aquí) y, solo para consultar, Revisión, Sustentado y Archivado.
  const ETAPAS = {
    deposito: {titulo: 'Por depositar', total: 'TOTAL POR DEPOSITAR', vacio: 'No hay solicitudes por depositar. 🎉'},
    revision: {titulo: 'Revisión', total: 'TOTAL EN REVISIÓN', vacio: 'No hay solicitudes en revisión.'},
    sustento: {titulo: 'Sustentado', total: 'TOTAL SUSTENTADO', vacio: 'No hay solicitudes sustentadas.'},
    archivado: {titulo: 'Archivado', total: 'TOTAL ARCHIVADO', vacio: 'No hay solicitudes archivadas.'},
  };
  const ESTADO_ITEM = {POR_RENDIR: 'Por rendir', RECHAZADO: 'Observado', EN_REVISION: 'En revisión', APROBADO: 'Aprobado', DEVUELTO: 'Devuelto'};
  let todas = [], solicitudes = [], abierta = null, etapa = 'deposito';
  try { etapa = ETAPAS[localStorage.getItem('cm-etapa')] ? localStorage.getItem('cm-etapa') : etapa; } catch (_) {}
  const importe = s => etapa === 'deposito' ? s.total : (s.montos_etapa?.[etapa] ?? s.total);

  // ── Gasto Cobra / Refacturable: etiqueta clara en cada concepto ──
  const tipoDe = t => !t ? '' : /refact/i.test(t) ? 'Refacturable' : 'Gasto Cobra';
  const etiquetaTipo = t => el('span', 'cm-tipo ' + (t === 'Refacturable' ? 'cm-tipo-rf' : 'cm-tipo-gc'), t);
  const tiposDe = s => [...new Set(s.items.map(i => tipoDe(i.tipo_presupuesto)).filter(Boolean))];
  const conceptosDe = s => [...new Set(s.items.map(i => i.tipo_gasto).filter(Boolean))];

  // ── Filtros: atajos de un toque y hoja de "Filtros" ──
  const filtroVacio = () => ({tipos: new Set(), conceptos: new Set(), proyectos: new Set(), fecha: '', desde: '', hasta: '', orden: ''});
  let filtro = filtroVacio();
  // Fecha en hora de Perú como 'AAAA-MM-DD' (se compara como texto).
  const diaLima = d => d.toLocaleDateString('en-CA', {timeZone: 'America/Lima'});
  function rangoFecha(f) {
    const hoy = new Date(), dia = diaLima(hoy);
    if (f.fecha === 'hoy') return [dia, dia];
    if (f.fecha === 'ayer') { const a = diaLima(new Date(hoy - 864e5)); return [a, a]; }
    if (f.fecha === 'semana') {  // desde el lunes
      const n = (new Date(dia + 'T12:00:00').getDay() + 6) % 7;
      return [diaLima(new Date(hoy - n * 864e5)), dia];
    }
    if (f.fecha === 'mes') return [dia.slice(0, 8) + '01', dia];
    if (f.fecha === 'rango') return [f.desde || '0000-00-00', f.hasta || '9999-99-99'];
    return null;
  }
  function cumple(s, f) {
    if (f.tipos.size && !tiposDe(s).some(t => f.tipos.has(t))) return false;
    if (f.conceptos.size && !conceptosDe(s).some(c => f.conceptos.has(c))) return false;
    if (f.proyectos.size && !f.proyectos.has(s.proyecto)) return false;
    const rango = rangoFecha(f);
    if (rango) { const d = diaLima(new Date(s.creado + 'Z')); if (d < rango[0] || d > rango[1]) return false; }
    return true;
  }
  const activos = f => [f.tipos.size, f.conceptos.size, f.proyectos.size, f.fecha, f.orden].filter(Boolean).length;
  function ordenar(lista, f) {
    if (f.orden === 'reciente') return lista.sort((a, b) => b.id - a.id);
    if (f.orden === 'antiguo') return lista.sort((a, b) => a.id - b.id);
    if (f.orden === 'monto') return lista.sort((a, b) => Number(importe(b)) - Number(importe(a)) || a.id - b.id);
    return lista;
  }
  const visibles = (f = filtro) => {
    const texto = plano($('cm-buscar').value.trim());
    return ordenar(solicitudes.filter(s => cumple(s, f)
      && (!texto || plano([s.codigo, s.tecnico, s.documento, s.proyecto, ...conceptosDe(s)].join(' ')).includes(texto))), f);
  };
  function chip(texto, activo, alTocar) {
    const b = el('button', 'cm-atajo', texto); b.type = 'button'; b.setAttribute('aria-pressed', String(!!activo));
    b.addEventListener('click', alTocar); return b;
  }
  function pintarAtajos() {
    const alternar = (conjunto, valor) => { conjunto.has(valor) ? conjunto.delete(valor) : conjunto.add(valor); pintarLista(); };
    const fecha = valor => { filtro.fecha = filtro.fecha === valor ? '' : valor; filtro.desde = filtro.hasta = ''; pintarLista(); };
    $('cm-atajos').replaceChildren(
      chip('Todos', !activos(filtro), () => { filtro = filtroVacio(); pintarLista(); }),
      chip('Gasto Cobra', filtro.tipos.has('Gasto Cobra'), () => alternar(filtro.tipos, 'Gasto Cobra')),
      chip('Refacturable', filtro.tipos.has('Refacturable'), () => alternar(filtro.tipos, 'Refacturable')),
      chip('Hoy', filtro.fecha === 'hoy', () => fecha('hoy')),
      chip('Esta semana', filtro.fecha === 'semana', () => fecha('semana')));
    const n = activos(filtro);
    $('cm-filtros-cuenta').hidden = !n; $('cm-filtros-cuenta').textContent = n;
    $('cm-filtros-btn').classList.toggle('activo', !!n);
  }

  // Hoja de filtros: se edita una copia y se aplica con "Ver resultados".
  let borrador = null;
  const copia = f => ({...f, tipos: new Set(f.tipos), conceptos: new Set(f.conceptos), proyectos: new Set(f.proyectos)});
  function grupo(titulo, opciones, activo, alTocar) {
    const g = el('div', 'cm-hoja-grupo'); g.append(el('h4', null, titulo));
    const fila = el('div', 'cm-hoja-chips');
    for (const [valor, texto] of opciones) fila.append(chip(texto, activo(valor), () => { alTocar(valor); pintarHoja(); }));
    g.append(fila); return g;
  }
  function pintarHoja() {
    const f = borrador;
    const alternar = conjunto => valor => { conjunto.has(valor) ? conjunto.delete(valor) : conjunto.add(valor); };
    // Conceptos de esta vista, del más usado al menos usado.
    const cuenta = new Map();
    solicitudes.forEach(s => conceptosDe(s).forEach(c => cuenta.set(c, (cuenta.get(c) || 0) + 1)));
    const conceptos = [...cuenta.keys()].sort((a, b) => cuenta.get(b) - cuenta.get(a) || a.localeCompare(b, 'es'));
    const proyectos = [...new Set(solicitudes.map(s => s.proyecto))].sort();
    const fechas = el('div', 'cm-hoja-fechas');
    for (const [campo, texto] of [['desde', 'Desde'], ['hasta', 'Hasta']]) {
      const l = el('label'); const i = Object.assign(el('input'), {type: 'date', value: f[campo]});
      i.addEventListener('change', () => { f[campo] = i.value; f.fecha = f.desde || f.hasta ? 'rango' : ''; pintarHoja(); });
      l.append(el('span', null, texto), i); fechas.append(l);
    }
    const fecha = grupo('Fecha', [['hoy', 'Hoy'], ['ayer', 'Ayer'], ['semana', 'Esta semana'], ['mes', 'Este mes']], v => f.fecha === v,
      v => { f.fecha = f.fecha === v ? '' : v; f.desde = f.hasta = ''; });
    fecha.append(fechas);
    $('cm-hoja-cuerpo').replaceChildren(
      grupo('Tipo', [['Gasto Cobra', 'Gasto Cobra'], ['Refacturable', 'Refacturable']], v => f.tipos.has(v), alternar(f.tipos)),
      ...(conceptos.length ? [grupo('Concepto', conceptos.map(c => [c, c]), v => f.conceptos.has(v), alternar(f.conceptos))] : []),
      fecha,
      ...(proyectos.length > 1 ? [grupo('Proyecto', proyectos.map(p => [p, PROYECTOS[p] || p]), v => f.proyectos.has(v), alternar(f.proyectos))] : []),
      grupo('Ordenar', [['antiguo', 'Más antiguo'], ['reciente', 'Más reciente'], ['monto', 'Mayor monto']], v => f.orden === v,
        v => { f.orden = f.orden === v ? '' : v; }));
    const n = visibles(f).length;
    $('cm-hoja-ver').textContent = n === 1 ? 'Ver 1 resultado' : 'Ver ' + n + ' resultados';
  }
  function abrirHoja() {
    borrador = copia(filtro); pintarHoja();
    $('cm-hoja').hidden = $('cm-hoja-velo').hidden = false;
    document.body.classList.add('cm-sin-scroll');
    $('cm-hoja-ver').focus();
  }
  function cerrarHoja(aplicar) {
    if (aplicar) { filtro = borrador; pintarLista(); }
    $('cm-hoja').hidden = $('cm-hoja-velo').hidden = true;
    document.body.classList.remove('cm-sin-scroll');
    $('cm-filtros-btn').focus();
  }

  function ver(id) { ['cm-lista-vista', 'cm-detalle-vista', 'cm-exito'].forEach(v => { $(v).hidden = v !== id; }); window.scrollTo({top: 0}); }

  async function cargar() {
    const r = await fetch('/api/caja-chica/solicitudes', {credentials: 'same-origin'});
    if (r.status === 401 || r.redirected) { location.href = '/login'; return; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('cm-lista').replaceChildren(el('p', 'error', j.error || 'No se pudo cargar.')); return; }
    todas = j.solicitudes;
    pintarLista();
  }

  function pintarLista() {
    // Por depositar: solicitudes ya validadas (pestaña Depósito de la gestión); las demás, según su etapa.
    solicitudes = todas.filter(s => etapa === 'deposito' ? s.estado === 'VALIDADO' : (s.etapas || []).includes(etapa))
      .sort((a, b) => etapa === 'deposito' ? a.id - b.id : b.id - a.id);
    const datos = ETAPAS[etapa];
    $('cm-titulo').textContent = $('cm-volver-texto').textContent = datos.titulo;
    $('cm-total-titulo').textContent = datos.total;
    $('cm-total').closest('.balance').className = 'balance compact cm-b-' + etapa;
    menu.querySelectorAll('[data-etapa]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.etapa === etapa)));
    pintarAtajos();
    // El total y la cantidad siguen a lo filtrado.
    const lista = visibles();
    $('cm-total').textContent = dinero(lista.reduce((t, s) => t + Number(importe(s)), 0));
    const filtrando = lista.length !== solicitudes.length;
    $('cm-cantidad').textContent = (filtrando ? lista.length + ' de ' : '') + solicitudes.length + (solicitudes.length === 1 ? ' solicitud' : ' solicitudes');
    const cont = $('cm-lista'); cont.replaceChildren();
    if (!lista.length) { cont.append(el('p', 'hint cm-vacio', solicitudes.length ? 'Ninguna solicitud coincide.' : datos.vacio)); return; }
    for (const s of lista) {
      const b = el('button', 'card cm-item'); b.type = 'button';
      const izq = el('span', 'cm-item-izq');
      const linea = el('span', 'cm-item-codigo'); linea.append(el('strong', null, s.codigo), el('span', 'cm-chip cm-' + s.proyecto.toLowerCase(), PROYECTOS[s.proyecto] || s.proyecto));
      izq.append(linea);
      // Conceptos de gasto y si son Gasto Cobra o Refacturable.
      const conceptos = conceptosDe(s);
      if (conceptos.length) { const c = el('span', 'cm-conceptos'); conceptos.forEach(n => c.append(el('span', null, n))); izq.append(c); }
      const tipos = tiposDe(s);
      if (tipos.length) { const t = el('span', 'cm-tipos'); tipos.forEach(n => t.append(etiquetaTipo(n))); izq.append(t); }
      izq.append(el('small', null, s.tecnico + ' · ' + (s.formulario?.tipo_billetera && s.formulario.tipo_billetera !== 'No aplica' ? s.formulario.tipo_billetera : s.banco)),
        el('small', 'cm-fecha', '🕒 ' + new Date(s.creado + 'Z').toLocaleString('es-PE', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Lima'})));
      b.append(izq, el('strong', 'cm-item-monto', dinero(importe(s))));
      b.addEventListener('click', () => abrir(s));
      cont.append(b);
    }
  }

  function fila(lista, nombre, valor, copiable) {
    if (!valor) return;
    const d = el('div', 'cm-fila'); d.append(el('dt', null, nombre));
    const dd = el('dd', null, valor);
    if (copiable) {
      const c = el('button', 'cm-copiar', 'Copiar'); c.type = 'button';
      c.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(String(copiable)); c.textContent = '¡Copiado!'; } catch (_) { c.textContent = String(copiable); }
        setTimeout(() => { c.textContent = 'Copiar'; }, 1600);
      });
      dd.append(c);
    }
    d.append(dd); lista.append(d);
  }
  function tarjeta(titulo, filas) {
    const c = el('section', 'card cm-tarjeta'); c.append(el('h2', 'cm-subtitulo', titulo));
    const dl = el('dl', 'cm-datos'); filas(dl); c.append(dl); return c;
  }

  // ── Evidencias y acciones de Revisión / Sustentado (mismas acciones de la gestión) ──
  const ITEMS_ETAPA = {revision: ['EN_REVISION'], sustento: ['APROBADO', 'DEVUELTO'], archivado: ['APROBADO', 'DEVUELTO']};
  const urlFoto = (s, nombre) => '/form-pruebas/caja-chica/foto/' + s.id + '/' + nombre;
  function fotos(s, nombres, titulo) {
    const caja = el('div', 'cm-fotos');
    caja.append(el('small', 'cm-fotos-titulo', titulo + (nombres.length > 1 ? ' (' + nombres.length + ')' : '')));
    if (!nombres.length) { caja.append(el('span', 'cm-sin-foto', 'Sin foto')); return caja; }
    const tira = el('div', 'cm-fotos-tira');
    for (const n of nombres) {
      const a = el('a'); a.href = urlFoto(s, n); a.target = '_blank'; a.rel = 'noopener'; a.title = 'Abrir ' + titulo.toLowerCase();
      const img = el('img'); img.src = a.href; img.alt = titulo; img.loading = 'lazy'; a.append(img); tira.append(a);
    }
    caja.append(tira); return caja;
  }
  // Solicitudes migradas desde Rendición: sus fotos quedaron en el registro original.
  function fotosOrigen(s) {
    const caja = el('div', 'cm-fotos'); caja.append(el('small', 'cm-fotos-titulo', 'Fotos en Rendición'), el('span', 'cm-sin-foto', 'Buscando…'));
    fetch('/api/caja-chica/' + s.id + '/fotos-origen', {credentials: 'same-origin'}).then(r => r.ok ? r.json() : {}).catch(() => ({})).then(j => {
      const lista = j.fotos || [];
      caja.lastChild.remove();
      if (!lista.length) { caja.append(el('span', 'cm-sin-foto', 'Sin fotos')); return; }
      const tira = el('div', 'cm-fotos-enlaces');
      for (const f of lista) { const a = el('a', 'cm-copiar', f.etiqueta || 'Foto'); a.href = f.url; a.target = '_blank'; a.rel = 'noopener'; tira.append(a); }
      caja.append(tira);
    });
    return caja;
  }
  async function accion(s, nombre, cuerpo) {
    const r = await fetch('/api/caja-chica/' + s.id + '/' + nombre, {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo || {})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(j.error || 'No se pudo completar la acción.');
    const i = todas.findIndex(x => x.id === s.id);
    if (i >= 0 && j.solicitud) todas[i] = j.solicitud;
    pintarLista();
    // Si la solicitud sigue en esta vista se vuelve a mostrar; si no, se regresa a la lista.
    if (j.solicitud && solicitudes.some(x => x.id === s.id)) abrir(j.solicitud);
    else ver('cm-lista-vista');
  }
  // Íconos de línea (mismo trazo que el encabezado) en vez de emojis.
  const SVG = {
    ok: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    no: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    archivar: '<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8M10 12h4"/>',
  };
  function svg(nombre) {
    const ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg');
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.innerHTML = SVG[nombre]; return s;
  }
  function botonAccion(texto, clase, fn, simbolo) {
    const b = el('button', 'cm-accion ' + clase); b.type = 'button';
    if (simbolo) b.append(svg(simbolo));
    b.append(texto);
    b.addEventListener('click', async () => {
      b.disabled = true;
      try { await fn(); } catch (e) { alert(e.message); } finally { b.disabled = false; }
    });
    return b;
  }
  const pedirMotivo = titulo => { const m = prompt(titulo); return m === null ? null : m.trim(); };
  function conceptos(s) {
    const items = s.items.filter(i => (ITEMS_ETAPA[etapa] || []).includes(i.estado));
    return items.map(i => {
      const c = el('section', 'card cm-tarjeta cm-concepto');
      const cab = el('div', 'cm-concepto-cab');
      cab.append(el('h2', 'cm-subtitulo', (i.numero ? i.numero + ' · ' : '') + i.tipo_gasto), el('span', 'cm-estado cm-e-' + i.estado.toLowerCase(), ESTADO_ITEM[i.estado] || i.estado));
      c.append(cab);
      if (tipoDe(i.tipo_presupuesto)) { const t = el('div', 'cm-tipos'); t.append(etiquetaTipo(tipoDe(i.tipo_presupuesto))); c.append(t); }
      const dl = el('dl', 'cm-datos');
      const comps = i.comprobantes || [];
      if (comps.length > 1) comps.forEach((x, n) => fila(dl, 'Comprobante ' + (n + 1), [x.comprobante, dinero(x.monto), x.ruc && 'RUC ' + x.ruc].filter(Boolean).join(' · ')));
      else { fila(dl, 'Comprobante', i.comprobante); fila(dl, 'RUC', i.ruc); fila(dl, 'Razón social', i.razon_social); }
      fila(dl, 'Solicitado', dinero(i.monto));
      fila(dl, 'Gastó', i.monto_gastado && dinero(i.monto_gastado));
      const sobrante = Number(i.monto) - Number(i.monto_gastado || 0);
      if (sobrante > 0 && i.monto_gastado) fila(dl, 'Sobrante', dinero(sobrante) + ' · va a devolución');
      c.append(dl);
      const evidencias = i.evidencias?.length ? i.evidencias : [i.evidencia].filter(Boolean);
      if (!(i.fotos || []).length && !evidencias.length) c.append(fotosOrigen(s));
      else c.append(fotos(s, i.fotos || [], 'Boleta / factura'), fotos(s, evidencias, 'Evidencia del gasto'));
      if (etapa === 'revision' && s.estado === 'DEPOSITADO' && i.estado === 'EN_REVISION') {
        const pie = el('div', 'cm-acciones');
        pie.append(
          botonAccion('Aprobar', 'cm-ok', () => accion(s, 'revisar_item', {item: i.id, aprobar: true}), 'ok'),
          botonAccion('Rechazar', 'cm-no', async () => {
            const motivo = pedirMotivo('Motivo del rechazo de ' + i.tipo_gasto + ' (lo verá el técnico):');
            if (motivo === null) return;
            if (!motivo) throw Error('Escribe el motivo del rechazo.');
            await accion(s, 'revisar_item', {item: i.id, aprobar: false, motivo});
          }, 'no'));
        c.append(pie);
      }
      return c;
    });
  }
  // Devolución del técnico (Revisión): captura y aceptar o rechazar.
  function devolucion(s) {
    if (etapa !== 'revision' || !s.devolucion_foto) return null;
    const pendiente = s.estado === 'POR_DEVOLVER' || (s.estado === 'DEPOSITADO' && !s.devolucion_aceptada);
    const c = el('section', 'card cm-tarjeta cm-concepto');
    const cab = el('div', 'cm-concepto-cab');
    cab.append(el('h2', 'cm-subtitulo', 'Devolución'), el('span', 'cm-estado ' + (pendiente ? 'cm-e-en_revision' : 'cm-e-aprobado'), pendiente ? 'Por revisar' : 'Aprobada'));
    const dl = el('dl', 'cm-datos'); fila(dl, 'Monto devuelto', dinero(s.estado === 'POR_DEVOLVER' ? s.diferencia : s.devolucion_monto));
    c.append(cab, dl, fotos(s, [s.devolucion_foto], 'Captura de la devolución'));
    if (pendiente) {
      const pie = el('div', 'cm-acciones');
      pie.append(
        botonAccion('Aceptar', 'cm-ok', () => accion(s, 'devolucion', {aceptar: true}), 'ok'),
        botonAccion('Rechazar', 'cm-no', async () => {
          const motivo = pedirMotivo('Motivo del rechazo de la devolución (el técnico subirá otra captura):');
          if (motivo === null) return;
          if (!motivo) throw Error('Escribe el motivo del rechazo.');
          await accion(s, 'devolucion', {aceptar: false, motivo});
        }, 'no'));
      c.append(pie);
    }
    return c;
  }
  function botonArchivar(s) {
    return botonAccion('Archivar solicitud', 'primary wide cm-archivar', async () => {
      if (!confirm('La solicitud ' + s.codigo + ' pasará a Archivado.')) return;
      await accion(s, 'archivar');
    }, 'archivar');
  }

  function abrir(s) {
    abierta = s;
    const f = s.formulario || {};
    $('cm-codigo').textContent = s.codigo + ' · ' + dinero(importe(s));
    const billetera = f.tipo_billetera && f.tipo_billetera !== 'No aplica';
    const depositar = etapa === 'deposito';
    $('cm-detalle').replaceChildren(
      // Depositar a: lo que se copia al banco (solo en Por depositar).
      ...(depositar ? [tarjeta('Depositar a', dl => {
        fila(dl, 'Titular', f.titular || s.tecnico);
        fila(dl, 'Banco', s.banco);
        fila(dl, 'CCI', s.cuenta, s.cuenta);
        if (billetera) fila(dl, f.tipo_billetera, f.numero_billetera, f.numero_billetera);
        fila(dl, 'Monto', dinero(s.total), Number(s.total).toFixed(2));
      })] : []),
      // Datos del técnico que solicitó.
      tarjeta('Técnico que solicita', dl => {
        fila(dl, 'Técnico', s.tecnico);
        fila(dl, 'DNI', s.documento);
        fila(dl, 'Proyecto', PROYECTOS[s.proyecto] || s.proyecto);
        fila(dl, 'Supervisor', s.supervisor || f.supervisor);
        fila(dl, 'Registrado en Dataper', s.dataper === undefined ? '' : s.dataper ? 'Sí' : 'No');
      }),
      tarjeta('Solicitud', dl => {
        fila(dl, 'Fecha', new Date(s.creado + 'Z').toLocaleString('es-PE', {dateStyle: 'medium', timeStyle: 'short'}));
        fila(dl, 'Site', f.site);
        fila(dl, 'CM / PM / PLM', f.wo);
        fila(dl, 'Justificación', s.motivo);
        fila(dl, 'Cotización', s.revision?.cotizacion);
        fila(dl, 'Responsable', f.responsable_validacion);
        fila(dl, 'Validado por', s.validado_por);
        if (!depositar) { fila(dl, 'Depositado', dinero(s.total)); fila(dl, 'Depositado por', s.depositado_por); }
        if (depositar) for (const i of s.items) fila(dl, i.tipo_gasto + (tipoDe(i.tipo_presupuesto) ? ' · ' + tipoDe(i.tipo_presupuesto) : ''), dinero(i.monto));
      }),
      // Revisión, Sustentado y Archivado: cada gasto con su boleta y evidencia.
      ...(depositar ? [] : conceptos(s)),
      ...(depositar ? [] : [devolucion(s)].filter(Boolean)),
      ...(etapa === 'sustento' && s.estado === 'SUSTENTO' ? [botonArchivar(s)] : []));
    // Solo Por depositar lleva captura y botón de depósito.
    $('cm-form').hidden = !depositar;
    $('cm-monto').value = s.total;
    limpiarCaptura();
    ver('cm-detalle-vista');
    $('cm-codigo').focus();
  }

  const captura = $('cm-captura'), archivo = $('cm-foto'), vista = captura.querySelector('img');
  function limpiarCaptura() {
    archivo.value = ''; vista.hidden = true; captura.classList.remove('lleno');
    if (vista.src) URL.revokeObjectURL(vista.src);
    captura.querySelector('small').textContent = 'La fecha y hora se registran solas';
  }
  archivo.addEventListener('change', () => {
    const a = archivo.files[0];
    captura.classList.toggle('lleno', !!a); vista.hidden = !a;
    if (vista.src) URL.revokeObjectURL(vista.src);
    if (a) { vista.src = URL.createObjectURL(a); captura.querySelector('small').textContent = 'Toca para cambiarla'; }
  });

  $('cm-form').addEventListener('submit', async e => {
    e.preventDefault();
    const form = e.currentTarget, error = form.querySelector('.error'), boton = form.querySelector('.cm-depositar');
    error.hidden = true;
    if (!archivo.files.length) { error.textContent = 'Toma o elige la captura del depósito.'; error.hidden = false; error.focus(); return; }
    const texto = boton.textContent; boton.disabled = true; boton.textContent = 'Registrando…';
    try {
      const r = await fetch('/api/caja-chica/' + abierta.id + '/depositar', {method: 'POST', body: new FormData(form), credentials: 'same-origin'});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(j.error || 'No se pudo registrar el depósito.');
      $('cm-exito-texto').textContent = abierta.codigo + ' · ' + dinero(abierta.total) + ' para ' + abierta.tecnico + '. Ya pasó a Por rendir.';
      ver('cm-exito');
      await cargar();
    } catch (err) { error.textContent = err.message; error.hidden = false; error.focus(); }
    finally { boton.disabled = false; boton.textContent = texto; }
  });

  const menu = $('cm-menu'), menuBtn = $('cm-menu-btn');
  const cerrarMenu = () => { menu.hidden = true; menuBtn.setAttribute('aria-expanded', 'false'); };
  menuBtn.addEventListener('click', e => { e.stopPropagation(); const abrir = menu.hidden; menu.hidden = !abrir; menuBtn.setAttribute('aria-expanded', String(abrir)); });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) cerrarMenu(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarMenu(); });
  menu.addEventListener('click', e => {
    const b = e.target.closest('[data-etapa]'); if (!b) return;
    etapa = b.dataset.etapa; cerrarMenu();
    filtro.conceptos.clear(); filtro.proyectos.clear();  // los conceptos cambian según la vista
    try { localStorage.setItem('cm-etapa', etapa); } catch (_) {}
    $('cm-buscar').value = ''; pintarLista(); ver('cm-lista-vista');
  });
  $('cm-volver').addEventListener('click', () => ver('cm-lista-vista'));
  $('cm-exito-volver').addEventListener('click', () => ver('cm-lista-vista'));
  $('cm-buscar').addEventListener('input', pintarLista);
  $('cm-filtros-btn').addEventListener('click', abrirHoja);
  $('cm-hoja-velo').addEventListener('click', () => cerrarHoja(false));
  $('cm-hoja-cancelar').addEventListener('click', () => cerrarHoja(false));
  $('cm-hoja-ver').addEventListener('click', () => cerrarHoja(true));
  $('cm-hoja-limpiar').addEventListener('click', () => { borrador = filtroVacio(); pintarHoja(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('cm-hoja').hidden) cerrarHoja(false); });
  cargar();
})();
