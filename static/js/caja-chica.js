/* Caja Chica · gestión en Nucleus: validar, depositar y revisar cada ítem. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ESTADOS = {PENDIENTE: 'Pendiente', VALIDADO: 'Validado', DEPOSITADO: 'Depositado', POR_DEVOLVER: 'Por devolver',
                   SUSTENTO: 'Sustentada', ARCHIVADO: 'Archivado', RECHAZADO: 'Rechazado · con el técnico', ANULADO: 'Anulado'};
  // Una solicitud que volvió a una etapa anterior se marca con su motivo de retorno.
  const RETORNO = {desde_deposito: ['Rechazado en depósito', 'cc-retorno'], reenviada: ['Corregida y reenviada', 'cc-reenviada']};
  const ITEM = {POR_RENDIR: 'Por rendir', EN_REVISION: 'En revisión', APROBADO: 'Aprobado', RECHAZADO: 'Rechazado', DEVUELTO: 'Se devuelve'};
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const avisar = m => (window.nucleusAlert || alert)(m);
  const confirmar = async (mensaje, titulo, opciones) => window.nucleusConfirm ? window.nucleusConfirm(mensaje, titulo, opciones) : confirm(mensaje);
  const permisos = document.querySelector('[data-gestionar]').dataset;
  const puedeGestionar = permisos.gestionar === 'si';
  const puedeEliminar = permisos.eliminar === 'si';
  const esAdmin = permisos.admin === 'si';
  const seleccionadas = new Set();
  const eliminar = $('cc-eliminar');
  let eliminando = false;
  const dialogo = $('cc-solicitud-dialogo');
  const configuracion = JSON.parse($('cc-revision-config').textContent);
  let solicitudes = [], tab = 'validacion', solicitudAbierta = null;
  try { tab = localStorage.getItem('cc-tab') || tab; } catch (_) {}
  if (!document.querySelector('.cc-tab[data-tab="' + tab + '"]')) tab = 'validacion';  // p. ej. la antigua pestaña "cerradas"

  async function accion(sol, nombre, cuerpo) {
    const opciones = cuerpo instanceof FormData ? {method: 'POST', body: cuerpo}
      : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo || {})};
    if (['editar', 'documentos', 'cm_site', 'tecnico'].includes(nombre)) opciones.headers = {...opciones.headers, 'X-CSRF-Token': $('cc-excel').dataset.csrf};
    const r = await fetch('/api/caja-chica/' + sol.id + '/' + nombre, opciones);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(j.error || 'No se pudo completar la acción.');
    const i = solicitudes.findIndex(s => s.id === sol.id);
    if (i >= 0) solicitudes[i] = j.solicitud;
    if (nombre === 'rechazar' && sol.estado === 'VALIDADO' && j.solicitud?.estado === 'PENDIENTE') {
      tab = 'validacion';
      filtros = {};
      busquedas = {};
      seleccionadas.clear();
      try { localStorage.setItem('cc-tab', tab); } catch (_) {}
    }
    pintar();
    if (dialogo.open && solicitudAbierta === sol.id && j.solicitud) {
      if (nombre === 'depositar') dialogo.close();
      else verDetalle(j.solicitud);
    }
  }
  const estadosPorEtapa = {
    por_rendir: ['POR_RENDIR', 'RECHAZADO'],
    revision: ['EN_REVISION'],
    sustento: ['APROBADO', 'DEVUELTO'],
    archivado: ['APROBADO', 'DEVUELTO'],
  };
  function itemsEtapa(sol, etapa = tab) {
    const estados = estadosPorEtapa[etapa];
    return estados ? sol.items.filter(item =>
      estados.includes(item.estado) && (item.estado !== 'DEVUELTO' || ['SUSTENTO', 'ARCHIVADO'].includes(sol.estado))) : sol.items;
  }
  const importeEtapa = (sol, etapa = tab) => sol.montos_etapa?.[etapa] ?? sol.total;

  const intentar = fn => async (...a) => { try { await fn(...a); } catch (e) { avisar(e.message); } };
  function boton(texto, clase, fn) { const b = el('button', 'cc-btn ' + clase, texto); b.type = 'button'; b.addEventListener('click', async () => { b.disabled = true; try { await fn(); } finally { b.disabled = false; } }); return b; }
  // Ventana para escribir un motivo: título, datos de contexto, motivos rápidos y texto libre.
  // Devuelve el texto o null si se cancela.
  const SUGERENCIAS = {
    item: ['La boleta no se lee', 'El RUC no coincide', 'El monto no coincide con la boleta', 'Falta la foto de evidencia', 'El comprobante no es válido'],
    rechazar: ['Falta la cotización', 'El monto no corresponde', 'Falta el correo de validación', 'Datos bancarios incorrectos'],
    anular: ['Solicitud duplicada', 'Ya no se necesita', 'Registrada por error'],
  };
  function pedirMotivo({titulo, subtitulo = '', datos = [], sugerencias = [], ayuda = '', okText = 'Rechazar', iconoNombre = 'fa-rotate-left'}) {
    return new Promise(resolve => {
      const dialogo = el('dialog', 'cc-motivo');
      const form = el('form', 'cc-motivo-form'); form.method = 'dialog';
      const cabeza = el('header', 'cc-motivo-cabeza');
      const marca = el('span', 'cc-motivo-icono'); marca.append(icono(iconoNombre));
      const textos = el('div'); textos.append(el('h3', null, titulo));
      if (subtitulo) textos.append(el('p', null, subtitulo));
      cabeza.append(marca, textos);
      form.append(cabeza);
      if (datos.length) {
        const lista = el('dl', 'cc-motivo-datos');
        for (const [k, v, clase] of datos.filter(d => d[1])) { const d = el('div', clase || null); d.append(el('dt', null, k), el('dd', null, v)); lista.append(d); }
        form.append(lista);
      }
      const texto = Object.assign(el('textarea'), {rows: 3, maxLength: 300, required: true, placeholder: 'Escribe el motivo…'});
      texto.setAttribute('aria-label', titulo);
      if (sugerencias.length) {
        // En <nav> para que el decorador de botones del sitio no les cambie el estilo.
        const chips = el('nav', 'cc-motivo-chips'); chips.setAttribute('aria-label', 'Motivos frecuentes');
        for (const sugerencia of sugerencias) {
          const chip = el('button', 'cc-motivo-chip', sugerencia); chip.type = 'button';
          chip.addEventListener('click', () => {
            texto.value = texto.value.trim() ? texto.value.trim().replace(/[.;,]?$/, '; ') + sugerencia.toLowerCase() : sugerencia;
            chip.classList.add('usado'); texto.focus(); validar();
          });
          chips.append(chip);
        }
        form.append(el('span', 'cc-motivo-etiqueta', 'Motivos frecuentes'), chips);
      }
      form.append(el('span', 'cc-motivo-etiqueta', 'Motivo'), texto);
      if (ayuda) form.append(el('p', 'cc-motivo-ayuda', ayuda));
      const pie = el('nav', 'cc-motivo-pie');
      const cancelar = el('button', 'cc-motivo-cancelar', 'Cancelar'); cancelar.type = 'button'; cancelar.value = '';
      const ok = el('button', 'cc-motivo-ok'); ok.type = 'submit'; ok.value = 'ok';
      ok.append(icono(iconoNombre), el('span', null, okText));
      pie.append(cancelar, ok);
      form.append(pie);
      dialogo.append(form);
      const validar = () => { ok.disabled = !texto.value.trim(); };
      texto.addEventListener('input', validar); validar();
      texto.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && texto.value.trim()) form.requestSubmit(ok); });
      cancelar.addEventListener('click', () => dialogo.close(''));
      dialogo.addEventListener('close', () => {
        resolve(dialogo.returnValue === 'ok' && texto.value.trim() ? texto.value.trim() : null);
        dialogo.remove();
      });
      document.body.append(dialogo);
      dialogo.showModal();
      texto.focus();
    });
  }
  function conMotivo(sol, nombre, opciones, extra = {}) {
    if (typeof opciones === 'string') opciones = {titulo: opciones};
    return intentar(async () => {
      const motivo = await pedirMotivo(opciones);
      if (motivo === null) return;
      await accion(sol, nombre, {...extra, motivo});
    });
  }
  const MOTIVO_DEVOLUCION = sol => ({titulo: 'Rechazar devolución', subtitulo: sol.codigo + ' · ' + (sol.tecnico || ''),
    datos: [['Monto', dinero(sol.devolucion_monto || sol.diferencia)]],
    sugerencias: ['La transferencia no llegó', 'El monto no coincide', 'La captura no se lee', 'No se ve la operación'],
    ayuda: 'El técnico deberá volver a subir la captura.'});
  function motivoItem(sol, item) {
    const sobrante = Number(item.monto) - Number(item.monto_gastado || 0);
    return {
      titulo: 'Rechazar ' + item.tipo_gasto, subtitulo: sol.codigo + ' · ' + (sol.tecnico || ''),
      datos: [['Comprobante', (item.comprobantes || []).map(c => c.comprobante).join(' / ') || item.comprobante], ['Solicitado', dinero(item.monto)],
        ['Gastó', item.monto_gastado && dinero(item.monto_gastado)], ['Sobrante', sobrante > 0 && item.monto_gastado ? dinero(sobrante) : '', 'naranja']],
      sugerencias: SUGERENCIAS.item, ayuda: 'El técnico verá este motivo y podrá corregir el ítem o devolverlo.',
    };
  }
  function foto(sol, nombre, etiqueta) {
    const enlace = el('a', 'cc-foto');
    enlace.href = '/form-pruebas/caja-chica/foto/' + sol.id + '/' + nombre;
    enlace.target = '_blank';
    enlace.rel = 'noopener';
    enlace.title = etiqueta;
    enlace.setAttribute('aria-label', etiqueta);
    const icono = el('i', 'fa-solid fa-camera');
    icono.setAttribute('aria-hidden', 'true');
    enlace.append(icono);
    return enlace;
  }

  function botonRapido(sol, etiqueta, clase, simbolo, ejecutar) {
    const b = boton('', 'cc-rapida ' + clase, ejecutar);
    b.title = etiqueta;
    b.setAttribute('aria-label', etiqueta + ' ' + sol.codigo);
    b.append(icono(simbolo));
    b.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); });
    return b;
  }
  // SLA de "Por rendir": tiempo desde que se confirmó el depósito (depositado_en viene en UTC).
  // Plazo para rendir: 24 h. Semáforo: azul < 6 h, verde < 12 h, amarillo < 18 h, ámbar < 24 h, rojo vencido.
  const NIVELES_SLA = [[6, 'cc-sla-azul'], [12, 'cc-sla-verde'], [18, 'cc-sla-amarillo'], [24, 'cc-sla-ambar'], [Infinity, 'cc-sla-rojo']];
  function pintarSla(nodo) {
    const horas = Math.max(0, Math.floor((Date.now() - new Date(nodo.dataset.sla + 'Z')) / 3600000));
    const dias = Math.floor(horas / 24);
    nodo.querySelector('.cc-sla-tiempo').textContent = dias ? dias + 'd ' + (horas % 24) + 'h' : horas + 'h';
    const nivel = NIVELES_SLA.find(([limite]) => horas < limite)[1];
    NIVELES_SLA.forEach(([, clase]) => nodo.classList.toggle(clase, clase === nivel));
  }
  const fechaDeposito = sol => new Date(sol.depositado_en + 'Z').toLocaleString('es-PE', {dateStyle: 'short', timeStyle: 'short'});
  function sla(sol) {
    if (!sol.depositado_en) return el('span', 'cc-sla', '—');
    const chip = boton('', 'cc-sla', () => verDetalle(sol));
    chip.dataset.sla = sol.depositado_en;
    chip.title = 'Depositado el ' + fechaDeposito(sol) + ' · ver solicitud';
    chip.setAttribute('aria-label', 'Ver solicitud ' + sol.codigo);
    chip.append(icono('fa-clock'), el('span', 'cc-sla-tiempo'));
    chip.addEventListener('click', e => e.stopPropagation());
    pintarSla(chip); return chip;
  }
  setInterval(() => document.querySelectorAll('[data-sla]').forEach(pintarSla), 60000);
  // Archivado: SLA desde el depósito hasta que terminó de rendir (último ítem rendido).
  const horasEntre = (a, b) => Math.max(0, Math.floor((new Date(b + 'Z') - new Date(a + 'Z')) / 3600000));
  const duracion = horas => { const d = Math.floor(horas / 24); return d ? d + 'd ' + (horas % 24) + 'h' : horas + 'h'; };
  const fechaCorta = f => new Date(f + 'Z').toLocaleString('es-PE', {dateStyle: 'short', timeStyle: 'short'});
  function slaArchivo(sol) {
    const rendidos = sol.items.map(i => i.rendido_en).filter(Boolean).sort();
    const fin = rendidos.at(-1) || sol.archivado_en;
    if (!sol.depositado_en || !fin) return el('span', 'cc-sla', '—');
    const total = horasEntre(sol.depositado_en, fin);
    const chip = boton('', 'cc-sla cc-sla-cerrado ' + NIVELES_SLA.find(([limite]) => total < limite)[1], () => verDetalle(sol));
    chip.title = ['Depositado: ' + fechaCorta(sol.depositado_en), 'Rindió: ' + fechaCorta(fin),
      'Tiempo de rendición: ' + duracion(total) + (total <= 24 ? ' · dentro de plazo' : ' · fuera de plazo')].join('\n');
    chip.setAttribute('aria-label', 'Tiempo de rendición ' + duracion(total) + ' · ver solicitud ' + sol.codigo);
    chip.append(icono('fa-stopwatch'), el('span', 'cc-sla-tiempo', duracion(total)));
    chip.addEventListener('click', e => e.stopPropagation());
    return chip;
  }
  // Ventana para que el gestor complete el CM y/o el site que faltan.
  function completarDatos(sol) {
    const f = sol.formulario || {};
    const dialogo = el('dialog', 'cc-motivo cc-completar');
    const form = el('form', 'cc-motivo-form'); form.method = 'dialog';
    const cabeza = el('header', 'cc-motivo-cabeza');
    const marca = el('span', 'cc-motivo-icono'); marca.append(icono('fa-triangle-exclamation'));
    const textos = el('div'); textos.append(el('h3', null, 'Completar CM / Site'), el('p', null, sol.codigo + ' · ' + (sol.tecnico || '')));
    cabeza.append(marca, textos);
    const limpio = (v, pendiente) => (v || '').trim().toUpperCase() === pendiente ? '' : (v || '');
    const cm = Object.assign(el('input'), {maxLength: 100, value: limpio(f.wo, 'CM PENDIENTE'), placeholder: 'CM-AAAAMMDD-NNNNNNNN'});
    const site = Object.assign(el('input'), {maxLength: 150, value: limpio(f.site, 'SITE PENDIENTE'), placeholder: 'Nombre del site'});
    cm.setAttribute('aria-label', 'N.º CM / PM / PLM'); site.setAttribute('aria-label', 'Nombre del site');
    const error = el('p', 'cc-alerta'); error.hidden = true;
    const pie = el('nav', 'cc-motivo-pie');
    const cancelar = el('button', 'cc-motivo-cancelar', 'Cancelar'); cancelar.type = 'button';
    const ok = el('button', 'cc-motivo-ok'); ok.type = 'submit';
    ok.append(icono('fa-check'), el('span', null, 'Guardar'));
    pie.append(cancelar, ok);
    form.append(cabeza, el('span', 'cc-motivo-etiqueta', 'N.º CM / PM / PLM (vacío = CM PENDIENTE)'), cm,
                el('span', 'cc-motivo-etiqueta', 'Nombre del site (vacío = SITE PENDIENTE)'), site, error, pie);
    dialogo.append(form);
    cancelar.addEventListener('click', () => dialogo.close());
    dialogo.addEventListener('close', () => dialogo.remove());
    form.addEventListener('submit', async e => {
      e.preventDefault();
      ok.disabled = true; error.hidden = true;
      try { await accion(sol, 'cm_site', {wo: cm.value, site: site.value}); dialogo.close(); }
      catch (err) { error.textContent = err.message; error.hidden = false; }
      finally { ok.disabled = false; }
    });
    document.body.append(dialogo);
    dialogo.showModal();
    (sol.faltan?.includes('CM') ? cm : site).focus();
  }
  // Sustentado ⇄ Archivado: un solo botón en cada pestaña (fila y ventana de detalle).
  async function pasarEtapa(sol, nombre) {
    const archivar = nombre === 'archivar';
    if (!await confirmar('La solicitud ' + sol.codigo + (archivar ? ' pasará a Archivado.' : ' volverá a Sustentado.'),
      archivar ? 'Archivar solicitud' : 'Volver a Sustentado', {okText: archivar ? 'Archivar' : 'Volver', circular: true})) return;
    await accion(sol, nombre);
    if (dialogo.open && solicitudAbierta === sol.id) dialogo.close();
  }
  // Corrige un DNI mal escrito: el nombre se toma de Dataper (solo administradores).
  function corregirTecnico(sol) {
    const dialogo = el('dialog', 'cc-motivo cc-completar');
    const form = el('form', 'cc-motivo-form'); form.method = 'dialog';
    const cabeza = el('header', 'cc-motivo-cabeza');
    const marca = el('span', 'cc-motivo-icono'); marca.append(icono('fa-id-card'));
    const textos = el('div'); textos.append(el('h3', null, 'Corregir DNI del técnico'), el('p', null, sol.codigo + ' · ahora: ' + sol.documento + ' · ' + (sol.tecnico || '')));
    cabeza.append(marca, textos);
    const dni = Object.assign(el('input'), {maxLength: 15, inputMode: 'numeric', placeholder: 'DNI correcto'});
    dni.setAttribute('aria-label', 'DNI correcto');
    const error = el('p', 'cc-alerta'); error.hidden = true;
    const pie = el('nav', 'cc-motivo-pie');
    const cancelar = el('button', 'cc-motivo-cancelar', 'Cancelar'); cancelar.type = 'button';
    const ok = el('button', 'cc-motivo-ok'); ok.type = 'submit';
    ok.append(icono('fa-check'), el('span', null, 'Corregir'));
    pie.append(cancelar, ok);
    form.append(cabeza, el('span', 'cc-motivo-etiqueta', 'DNI correcto (debe estar ACTIVO en Dataper)'), dni,
                el('p', 'cc-motivo-ayuda', 'El nombre del técnico se toma de Dataper y el cambio queda en el historial.'), error, pie);
    dialogo.append(form);
    cancelar.addEventListener('click', () => dialogo.close());
    dialogo.addEventListener('close', () => dialogo.remove());
    form.addEventListener('submit', async e => {
      e.preventDefault();
      ok.disabled = true; error.hidden = true;
      try { await accion(sol, 'tecnico', {documento: dni.value}); dialogo.close(); }
      catch (err) { error.textContent = err.message; error.hidden = false; }
      finally { ok.disabled = false; }
    });
    document.body.append(dialogo);
    dialogo.showModal();
    dni.focus();
  }
  function accionesRapidas(sol) {
    const caja = el('span', 'cc-acciones-rapidas');
    if (tab === 'pendientes') {
      if (puedeGestionar) caja.append(botonRapido(sol, 'Completar CM / Site', 'cc-ok', 'fa-pen', () => completarDatos(sol)));
      return caja;
    }
    // En "Por rendir" no hay acciones: solo el tiempo transcurrido desde el depósito.
    if (tab === 'por_rendir') { caja.append(sla(sol)); return caja; }
    if (tab === 'sustento') {
      if (sol.estado === 'SUSTENTO') {
        caja.append(slaArchivo(sol));
        if (puedeGestionar) caja.append(botonRapido(sol, 'Archivar', 'cc-ok', 'fa-box-archive', () => pasarEtapa(sol, 'archivar')));
      }
      return caja;
    }
    if (tab === 'archivado') {
      if (sol.estado === 'ARCHIVADO') {
        caja.append(slaArchivo(sol));
        if (puedeGestionar) caja.append(botonRapido(sol, 'Volver a Sustentado', 'cc-no', 'fa-rotate-left', () => pasarEtapa(sol, 'sustento')));
      }
      return caja;
    }
    if (tab === 'revision') {
      caja.append(botonRapido(sol, 'Revisar', 'cc-ok', 'fa-magnifying-glass-dollar', () => verDetalle(sol)));
      return caja;
    }
    if (tab === 'deposito') {
      if (puedeGestionar && sol.estado === 'VALIDADO') {
        caja.append(botonRapido(sol, 'Depositar', 'cc-ok', 'fa-money-bill-transfer', () => verDetalle(sol)));
      }
      return caja;
    }
    if (puedeGestionar && sol.estado === 'PENDIENTE') {
      caja.append(botonRapido(sol, 'Validar', 'cc-ok', 'fa-check', () => verDetalle(sol)));
    }
    if (puedeGestionar && ['PENDIENTE', 'VALIDADO', 'RECHAZADO'].includes(sol.estado)) {
      caja.append(botonRapido(sol, 'Anular', 'cc-no', 'fa-ban', () => verDetalle(sol)));
    }
    return caja;
  }

  function acciones(sol) {
    const caja = el('div', 'cc-acciones');
    if (sol.estado === 'RECHAZADO') caja.append(el('span', 'cc-nota', 'Devuelta al técnico: cuando la corrija y reenvíe vuelve a esta etapa.'));
    if (sol.estado === 'POR_DEVOLVER' && sol.devolucion_foto) {
      caja.append(el('span', 'cc-nota', 'Devolución de ' + dinero(sol.diferencia) + ':'), foto(sol, sol.devolucion_foto, 'Ver foto de la devolución'),
                  boton('Aceptar devolución y archivar', 'cc-ok', intentar(() => accion(sol, 'devolucion', {aceptar: true}))),
                  boton('Rechazar devolución', 'cc-no', conMotivo(sol, 'devolucion', MOTIVO_DEVOLUCION(sol), {aceptar: false})));
    }
    return caja;
  }
  function detalle(sol) {
    const d = el('div', 'cc-detalle');
    if (sol.depositado_en) d.append(el('p', 'cc-nota', 'Depositado el ' + new Date(sol.depositado_en + 'Z').toLocaleString('es-PE', {dateStyle: 'medium', timeStyle: 'short'})));
    else if (sol.deposito_fecha) d.append(el('p', 'cc-nota', 'Depositado el ' + sol.deposito_fecha));
    if (sol.motivo_rechazo) d.append(el('p', 'cc-alerta', 'Motivo: ' + sol.motivo_rechazo));
    const tabla = el('table', 'cc-items'), cab = el('tr');
    ['Ítem', 'Tipo de gasto', 'Monto', 'Comprobante', 'Gastado', 'Fotos', 'Estado', ''].forEach(t => cab.append(el('th', null, t)));
    tabla.append(cab);
    for (const item of sol.items) {
      const tr = el('tr');
      const fotos = el('td'); item.fotos.forEach((n, i) => fotos.append(foto(sol, n, 'Foto ' + (i + 1)), ' '));
      const estado = el('td'); estado.append(el('span', 'cc-chip cc-' + item.estado.toLowerCase(), ITEM[item.estado]));
      if (item.motivo_rechazo) estado.append(el('small', 'cc-alerta', item.motivo_rechazo));
      const botones = el('td');
      if (sol.estado === 'DEPOSITADO' && item.estado === 'EN_REVISION') {
        botones.append(boton('Aprobar', 'cc-ok', intentar(() => accion(sol, 'revisar_item', {item: item.id, aprobar: true}))),
                       boton('Rechazar', 'cc-no', conMotivo(sol, 'revisar_item', motivoItem(sol, item), {item: item.id, aprobar: false})));
      }
      const concepto = el('td', null, [item.tipo_gasto, item.tipo_presupuesto, item.descripcion].filter(Boolean).join(' · '));
      if (item.correo_validador) concepto.append(el('div', null, 'Correo de validación: ' + item.correo_validador));
      tr.append(el('td', null, String(item.numero)), concepto,
                el('td', 'cc-num', dinero(item.monto)), el('td', null, (item.comprobantes || []).length > 1 ? item.comprobantes.map(c => c.comprobante).join(' / ') : item.comprobante ? item.comprobante + ' · RUC ' + item.ruc : '—'),
                el('td', 'cc-num', item.monto_gastado ? dinero(item.monto_gastado) : '—'), fotos, estado, botones);
      tabla.append(tr);
    }
    if (['DEPOSITADO', 'POR_DEVOLVER', 'SUSTENTO', 'ARCHIVADO'].includes(sol.estado)) d.append(tabla);
    if (sol.deposito_foto) { const p = el('p', 'cc-nota', 'Depósito: '); p.append(foto(sol, sol.deposito_foto, 'Ver foto del depósito')); d.append(p); }
    if (sol.devolucion_foto && ['SUSTENTO', 'ARCHIVADO'].includes(sol.estado)) { const p = el('p', 'cc-nota', 'Devolución: '); p.append(foto(sol, sol.devolucion_foto, 'Ver foto de la devolución')); d.append(p); }
    const controles = acciones(sol);
    if (controles.hasChildNodes()) d.append(controles);
    return d;
  }

  // Edición en el mismo formato de la ventana: las fichas de la columna izquierda pasan a ser
  // editables (misma cabecera, mismos bordes). Cotización y correo siguen en la columna derecha.
  function editorSolicitud(sol, documentos) {
    const form = el('form', 'cc-editar-solicitud cc-editor');
    form.id = 'cc-solicitud-editor';
    function seccion(iconoNombre, titulo) {
      const caja = el('section', 'cc-ficha cc-editor-ficha');
      const cabeza = el('h4', 'cc-ficha-titulo');
      cabeza.append(icono(iconoNombre), el('span', null, titulo));
      caja.append(cabeza);
      form.append(caja);
      return caja;
    }
    // Fila etiqueta / control, igual que las filas de solo lectura.
    function campo(titulo, control, contenedor) {
      const fila = el('label', 'cc-editor-fila');
      fila.append(el('span', null, titulo), control);
      contenedor.append(fila);
      return control;
    }
    function texto(valor, maxLength, required = false) {
      return Object.assign(el('input'), {value: valor || '', maxLength, required});
    }
    function selector(valores, seleccionado) {
      const control = el('select');
      [...new Set([seleccionado, ...valores])].forEach(v => control.add(new Option(v, v)));
      control.value = seleccionado;
      return control;
    }
    const justificacion = seccion('fa-file-lines', 'Justificación de la solicitud');
    const motivo = campo('Justificación', Object.assign(el('textarea'), {value: sol.motivo || '', rows: 3, maxLength: 500, required: true}), justificacion);
    // Conceptos: concepto y monto por fila, con el total al pie.
    const conceptos = seccion('fa-list-check', 'Datos de la solicitud');
    const proyecto = selector(configuracion.proyectos, sol.proyecto);
    const controles = sol.items.map(item => {
      const fila = el('div', 'cc-editor-concepto');
      const tipo = selector([], item.tipo_gasto);
      tipo.setAttribute('aria-label', 'Concepto ' + item.numero);
      function actualizar() {
        const seleccionado = tipo.value;
        const disponibles = configuracion.catalogo.filter(c => c.proyectos[proyecto.value]).map(c => c.nombre);
        tipo.replaceChildren(new Option('Selecciona', ''), ...disponibles.map(v => new Option(v, v)));
        if (proyecto.value === sol.proyecto && seleccionado === item.tipo_gasto && !disponibles.includes(seleccionado)) {
          tipo.add(new Option(seleccionado, seleccionado));
        }
        tipo.value = [...tipo.options].some(o => o.value === seleccionado) ? seleccionado : '';
      }
      tipo.required = true;
      actualizar();
      proyecto.addEventListener('change', actualizar);
      const montoCaja = el('span', 'cc-editor-monto');
      const monto = Object.assign(texto(item.monto, 16, true), {inputMode: 'decimal'});
      monto.setAttribute('aria-label', 'Monto del concepto ' + item.numero);
      monto.dataset.monto = '';
      montoCaja.append(el('span', null, 'S/'), monto);
      fila.append(tipo, montoCaja);
      conceptos.append(fila);
      return () => ({tipo_gasto: tipo.value, descripcion: item.descripcion || '', monto: monto.value, correo_validador: item.correo_validador || ''});
    });
    const total = el('output', 'cc-num');
    const filaTotal = el('div', 'cc-ficha-concepto cc-ficha-total');
    filaTotal.append(el('strong', null, 'Total solicitado'), total);
    conceptos.append(filaTotal);
    const cotizacion = documentos.elements.namedItem('cotizacion');
    const actualizarTotal = () => {
      const centimos = controles.reduce((suma, leer) => {
        const valor = leer().monto.replace('S/', '').replace(/ /g, '');
        const decimal = valor.includes('.') ? valor.replace(/,/g, '') : valor.replace(',', '.');
        return suma + (/^\d+(?:\.\d{0,2})?$/.test(decimal) ? Math.round(Number(decimal) * 100) : 0);
      }, 0);
      total.textContent = dinero(centimos / 100);
      cotizacion.dataset.totalCentimos = String(centimos);
      cotizacion.dispatchEvent(new Event('input'));
    };
    conceptos.addEventListener('input', e => { if (e.target.hasAttribute('data-monto')) actualizarTotal(); });

    const detalleFicha = seccion('fa-file-lines', 'Detalle de la solicitud');
    campo('Técnico', Object.assign(texto([sol.tecnico, sol.documento].filter(Boolean).join(' · '), 200), {readOnly: true, tabIndex: -1}), detalleFicha);
    campo('Proyecto', proyecto, detalleFicha);

    const deposito = seccion('fa-building-columns', 'Datos del depósito');
    const banco = campo('Banco', selector(configuracion.bancos, sol.banco), deposito);
    const cuenta = campo('CCI', Object.assign(texto(sol.cuenta, 40, true), {inputMode: 'numeric'}), deposito);
    cuenta.classList.add('cc-mono');
    actualizarTotal();

    const adjunto = documentos.elements.namedItem('correo');
    const guardar = $('cc-solicitud-guardar');
    const error = el('p', 'cc-alerta');
    error.setAttribute('role', 'alert');
    error.hidden = true;
    form.append(error);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (guardar.disabled) return;
      error.hidden = true;
      const datos = new FormData();
      datos.set('datos', JSON.stringify({proyecto: proyecto.value, motivo: motivo.value, banco: banco.value,
        cuenta: cuenta.value, items: controles.map(leer => leer()), cotizacion: cotizacion.value}));
      if (adjunto?.files.length) datos.set('correo', adjunto.files[0]);
      guardar.disabled = true;
      try {
        await accion(sol, 'editar', datos);
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
      } finally {
        if (form.isConnected) guardar.disabled = false;
      }
    });
    return form;
  }

  function totalSolicitud(valor) {
    const total = el('div', 'cc-total-solicitud cc-campo-ancho');
    total.append(el('span', null, 'Total solicitado'), valor);
    return total;
  }

  function datosEnviados(datos, titulo) {
    const panel = el('section', 'cc-datos-enviados');
    if (titulo) panel.append(el('h3', null, titulo));
    const extra = datos.formulario || {};
    function campos(datosCampos) {
      const lista = el('dl', 'cc-datos-solicitud');
      for (const [etiqueta, valor, ancho] of datosCampos) {
        const campo = el('div', ancho ? 'cc-campo-ancho' : null);
        campo.append(el('dt', null, etiqueta), el('dd', null, valor || 'Sin registrar'));
        lista.append(campo);
      }
      return lista;
    }
    function grupo(titulo, valores = []) {
      const seccion = el('fieldset', 'cc-grupo-solicitud');
      seccion.append(el('legend', null, titulo));
      if (valores.length) seccion.append(campos(valores));
      panel.append(seccion);
      return seccion;
    }
    const solicitud = el('div', 'cc-solicitud-contenido');
    panel.append(solicitud);
    solicitud.append(el('h4', null, 'Datos de la solicitud'));
    for (const item of datos.items) {
      const fila = el('div', 'cc-concepto-enviado');
      const nombre = el('strong', 'cc-concepto-marcado');
      nombre.append(icono('fa-square-check'), document.createTextNode(item.tipo_gasto));
      fila.append(nombre,
        el('strong', 'cc-num', dinero(item.monto)));
      const detalle = el('div', 'cc-campo-ancho');
      for (const texto of [item.descripcion, item.tipo_presupuesto,
        item.correo_validador && 'Correo de quien valida: ' + item.correo_validador].filter(Boolean)) {
        detalle.append(el('p', 'cc-nota', texto));
      }
      if (detalle.childNodes.length) fila.append(detalle);
      solicitud.append(fila);
    }
    solicitud.append(totalSolicitud(el('strong', 'cc-num', dinero(datos.total))));
    solicitud.append(campos([['Nombre de site', extra.site], ['Número CM / PM / PLM', extra.wo],
      ['Responsable de la validación', extra.responsable_validacion], ['Justificar la solicitud', datos.motivo, true]]));
    grupo('Datos del depósito', [['CCI o número de cuenta', datos.cuenta], ['Banco', datos.banco],
      ['Titular de la cuenta', extra.titular]]);
    const billetera = [['Tipo de billetera', extra.tipo_billetera]];
    if (extra.numero_billetera) billetera.push(['Número de Yape / Plin', extra.numero_billetera]);
    grupo('Billetera digital', billetera);
    return panel;
  }

  // Tarjeta compacta (formato de ventanas): título con ícono y filas etiqueta / valor.
  // filas: [etiqueta, valor, clase?]; las vacías se omiten. copiable agrega "copiar".
  function ficha(iconoNombre, titulo, filas, copiable = false) {
    const caja = el('section', 'cc-ficha');
    const cabeza = el('h4', 'cc-ficha-titulo');
    cabeza.append(icono(iconoNombre), el('span', null, titulo));
    const lista = el('dl', 'cc-ficha-datos' + (copiable ? ' cc-ficha-copiable' : ''));
    for (const [nombre, valor, clase] of filas) {
      if (!valor) continue;
      const fila = el('div', 'cc-ficha-fila');
      fila.append(el('dt', null, nombre), el('dd', clase || null, valor));
      if (copiable) {
        const copiar = el('button', 'cc-ficha-copiar');
        copiar.type = 'button';
        copiar.title = 'Copiar ' + nombre.toLowerCase();
        copiar.setAttribute('aria-label', copiar.title);
        copiar.append(icono('fa-copy'));
        copiar.addEventListener('click', async () => {
          try { await navigator.clipboard.writeText(valor); copiar.replaceChildren(icono('fa-check')); }
          catch (_) { copiar.replaceChildren(icono('fa-xmark')); }
          setTimeout(() => copiar.replaceChildren(icono('fa-copy')), 1500);
        });
        fila.append(copiar);
      }
      lista.append(fila);
    }
    caja.append(cabeza, lista);
    return caja;
  }
  function datosBancarios(sol) {
    const f = sol.formulario || {};
    const filas = [['Banco', sol.banco], ['CCI', sol.cuenta, 'cc-mono'], ['Titular', f.titular || sol.tecnico]];
    if (f.tipo_billetera && f.tipo_billetera !== 'No aplica') filas.push([f.tipo_billetera, f.numero_billetera, 'cc-mono']);
    return filas;
  }
  // Gastos seleccionados con su importe individual y el total.
  function datosSolicitud(sol) {
    const conceptos = el('section', 'cc-ficha');
    const cabeza = el('h4', 'cc-ficha-titulo');
    cabeza.append(icono('fa-list-check'), el('span', null, 'Conceptos solicitados'));
    conceptos.append(cabeza);
    for (const item of sol.items) {
      const fila = el('div', 'cc-ficha-concepto');
      const nombre = el('span');
      nombre.append(item.tipo_gasto);
      if (item.tipo_presupuesto) nombre.append(el('span', 'cc-ficha-suave', ' · ' + item.tipo_presupuesto));
      fila.append(nombre, el('strong', 'cc-num', dinero(item.monto)));
      conceptos.append(fila);
    }
    const total = el('div', 'cc-ficha-concepto cc-ficha-total');
    total.append(el('strong', null, 'Total solicitado'), el('strong', 'cc-num', dinero(sol.total)));
    conceptos.append(total);
    return conceptos;
  }

  function resumenSolicitud(sol) {
    const f = sol.formulario || {};
    return [datosSolicitud(sol),
      ficha('fa-file-lines', 'Detalle de la solicitud', [
        ['Técnico', [sol.tecnico, sol.documento].filter(Boolean).join(' · ')], ['Supervisor', f.supervisor],
        ['Site', f.site], ['CM / PM / PLM', f.wo], ['Responsable', f.responsable_validacion || sol.validado_por],
        ['Justificación', sol.motivo || 'Sin registrar', 'cc-justificacion-texto']]),
      ficha('fa-building-columns', 'Datos del depósito', datosBancarios(sol))];
  }

  function formularioDocumentos(sol) {
    const form = el('form', 'cc-editar-solicitud cc-documentos-validacion');
    form.id = 'cc-solicitud-documentos';
    const grupo = el('section', 'cc-ficha cc-ficha-cotizacion');
    const cabeza = el('h4', 'cc-ficha-titulo');
    cabeza.append(icono('fa-file-invoice'), el('span', null, 'Cotización'));
    grupo.append(cabeza);
    const cotizacion = el('div', 'cc-cotizacion-campo');
    const entrada = Object.assign(el('input'), {
      name: 'cotizacion', value: sol.revision?.cotizacion || '', maxLength: 80,
      autocomplete: 'off', placeholder: 'Busca por número de cotización',
    });
    entrada.setAttribute('aria-label', 'Número de cotización');
    const opciones = el('datalist');
    opciones.id = 'cc-cotizaciones-opciones';
    entrada.setAttribute('list', opciones.id);
    const estado = el('span', 'cc-nota cc-cotizacion-estado');
    estado.setAttribute('aria-live', 'polite');
    cotizacion.append(entrada, opciones, estado);
    const control = el('div', 'cc-cotizacion-control cc-campo-ancho');
    control.hidden = true;
    const actualizar = lista => {
      const numero = entrada.value.trim().toUpperCase();
      const seleccion = lista.find(c => c.numero.toUpperCase() === numero);
      control.hidden = !seleccion;
      if (!seleccion) {
        estado.textContent = numero ? 'Selecciona una cotización de la lista.' : '';
        return;
      }
      estado.textContent = [seleccion.estado || 'Sin estado', seleccion.proyecto].filter(Boolean).join(' · ');
      const actual = Number(entrada.dataset.totalCentimos ?? Math.round(Number(sol.total) * 100));
      const otras = Math.round(Number(seleccion.otras_solicitudes) * 100);
      const acumulado = otras + actual;
      const cotizado = seleccion.monto === null ? null : Math.round(Number(seleccion.monto) * 100);
      const saldo = cotizado === null ? null : cotizado - acumulado;
      const mensaje = el('p', 'cc-cotizacion-aviso', saldo === null ? 'Monto cotizado sin registrar.'
        : saldo < 0 ? 'Excede el monto cotizado en ' + dinero(-saldo / 100) + '.'
          : 'Dentro del monto cotizado. Saldo disponible: ' + dinero(saldo / 100) + '.');
      mensaje.dataset.resultado = saldo === null ? '' : saldo < 0 ? 'excede' : 'dentro';
      const tarjetas = el('dl', 'cc-cotizacion-montos');
      for (const [etiqueta, monto] of [['Cotizado', cotizado], ['Otras solicitudes', otras],
        ['Esta solicitud', actual], ['Acumulado', acumulado]]) {
        const fila = el('div');
        fila.append(el('dt', null, etiqueta), el('dd', 'cc-num', monto === null ? '—' : dinero(monto / 100)));
        tarjetas.append(fila);
      }
      control.replaceChildren(mensaje, tarjetas);
    };
    fetch('/api/caja-chica/cotizaciones?' + new URLSearchParams({solicitud: sol.id})).then(async respuesta => {
      if (!respuesta.ok) throw Error('No se pudieron cargar las cotizaciones.');
      const {cotizaciones} = await respuesta.json();
      const lista = [...cotizaciones.filter(c => c.proyecto === sol.proyecto),
        ...cotizaciones.filter(c => c.proyecto !== sol.proyecto)];
      const sugerencias = document.createDocumentFragment();
      for (const c of lista) {
        sugerencias.append(new Option([c.estado || 'Sin estado', c.proyecto].filter(Boolean).join(' · '), c.numero));
      }
      opciones.replaceChildren(sugerencias);
      entrada.addEventListener('input', () => actualizar(lista));
      actualizar(lista);
    }).catch(() => { estado.textContent = 'No se pudieron cargar las cotizaciones.'; });
    // Correo de validación como zona para tocar (el input se oculta solo dentro de la zona:
    // el editor de la solicitud lo reutiliza y ahí debe verse).
    const correo = el('label', 'cc-validacion-zona');
    const archivoCorreo = Object.assign(el('input'), {
      type: 'file', name: 'correo', accept: '.pdf,.eml,.msg,.jpg,.jpeg,.png,.webp',
    });
    const ayudaCorreo = el('small', null, 'Toca para adjuntar .msg, PDF o imagen');
    correo.append(archivoCorreo, icono('fa-envelope'), el('strong', null, 'Correo de validación'), ayudaCorreo);
    archivoCorreo.addEventListener('change', () => {
      const elegido = archivoCorreo.files[0];
      ayudaCorreo.textContent = elegido ? elegido.name + ' · toca para cambiarlo' : 'Toca para adjuntar .msg, PDF o imagen';
      correo.classList.toggle('con-archivo', Boolean(elegido));
    });
    const guardar = $('cc-solicitud-guardar');
    const editar = $('cc-solicitud-editar');
    const error = el('p', 'cc-alerta cc-campo-ancho');
    error.hidden = true;
    error.setAttribute('role', 'alert');
    grupo.append(cotizacion, control);
    form.append(grupo, correo, error);
    // Cotización y correo solo se piden si algún concepto de gasto lo exige (o ya se cargaron).
    form.pideCotizacion = sol.items.some(i => i.requiere_cotizacion) || Boolean(sol.revision?.cotizacion);
    form.pideCorreo = sol.items.some(i => i.requiere_correo) || Boolean(sol.revision?.archivo);
    grupo.hidden = !form.pideCotizacion;
    correo.hidden = !form.pideCorreo;
    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (guardar.disabled) return;
      guardar.disabled = true;
      editar.disabled = true;
      error.hidden = true;
      try {
        await accion(sol, 'documentos', new FormData(form));
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
      } finally {
        if (form.isConnected) {
          guardar.disabled = false;
          editar.disabled = false;
        }
      }
    });
    return form;
  }

  // Depósito: detalle a la izquierda, foto vertical a la derecha. Se confirma con
  // el botón redondo de la cabecera (#cc-solicitud-depositar, junto a la X).
  function formularioDeposito(sol) {
    const form = el('form', 'cc-deposito-panel');
    form.id = 'cc-deposito-form';
    const izquierda = el('div', 'cc-deposito-izquierda');
    izquierda.append(...resumenSolicitud(sol));

    const monto = el('div', 'cc-deposito-cabecera');
    const bolsa = el('span', 'cc-deposito-bolsa');
    bolsa.append(icono('fa-sack-dollar'));
    const textos = el('div');
    textos.append(el('small', null, 'Monto a depositar'), el('strong', 'cc-deposito-monto', dinero(sol.total)));
    monto.append(bolsa, textos);

    // Foto: tocar, arrastrar o pegar (Ctrl+V), con vista previa.
    const archivo = Object.assign(el('input'), {type: 'file', name: 'foto', accept: 'image/*', required: true, hidden: true});
    const zona = el('label', 'cc-deposito-zona');
    zona.tabIndex = 0;
    const vista = el('img');
    vista.alt = 'Vista previa del comprobante';
    vista.hidden = true;
    const ayuda = el('span', 'cc-deposito-ayuda');
    ayuda.append(icono('fa-camera'), el('strong', null, 'Foto del comprobante'),
      el('small', null, 'Toca para elegir, arrástrala aquí o pégala con Ctrl+V'));
    zona.append(archivo, vista, ayuda);
    let previa = '';
    function usar(lista) {
      const imagen = [...(lista || [])].find(f => f.type.startsWith('image/'));
      if (!imagen) return;
      const transferencia = new DataTransfer();
      transferencia.items.add(imagen);
      archivo.files = transferencia.files;
      if (previa) URL.revokeObjectURL(previa);
      previa = URL.createObjectURL(imagen);
      vista.src = previa;
      vista.hidden = false;
      zona.classList.add('con-foto');
      ayuda.querySelector('small').textContent = imagen.name + ' · toca para cambiarla';
    }
    archivo.addEventListener('change', () => usar(archivo.files));
    zona.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); archivo.click(); } });
    zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('arrastrando'); });
    zona.addEventListener('dragleave', () => zona.classList.remove('arrastrando'));
    zona.addEventListener('drop', e => { e.preventDefault(); zona.classList.remove('arrastrando'); usar(e.dataTransfer.files); });
    form.addEventListener('paste', e => usar(e.clipboardData?.files));
    dialogo.addEventListener('paste', e => { if (form.isConnected && !form.contains(e.target)) usar(e.clipboardData?.files); });

    const error = el('p', 'cc-alerta cc-deposito-error');
    error.setAttribute('role', 'alert');
    error.hidden = true;
    const montoOculto = Object.assign(el('input'), {type: 'hidden', name: 'monto', value: sol.total});
    const derecha = el('div', 'cc-deposito-derecha');
    derecha.append(monto, zona);
    form.append(error, izquierda, derecha, montoOculto);

    const enviar = $('cc-solicitud-depositar');
    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (enviar.disabled) return;
      error.hidden = true;
      if (!archivo.files.length) {
        error.textContent = 'Adjunta la foto del comprobante del depósito.';
        error.hidden = false;
        zona.focus();
        return;
      }
      enviar.disabled = true;
      enviar.replaceChildren(icono('fa-spinner fa-spin'));
      try {
        await accion(sol, 'depositar', new FormData(form));
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
      } finally {
        enviar.disabled = false;
        enviar.replaceChildren(icono('fa-sack-dollar'));
      }
    });
    return form;
  }

  // Ventana de "Revisión": detalle arriba y una tarjeta por concepto con sus 2 fotos.
  // Se valida o rechaza cada concepto; la devolución aparece cuando ya no queda nada pendiente.
  function fotoRevision(sol, nombre, titulo) {
    const figura = el('figure', 'cc-rev-foto');
    if (nombre) {
      const enlace = el('a'); enlace.href = '/form-pruebas/caja-chica/foto/' + sol.id + '/' + nombre;
      enlace.target = '_blank'; enlace.rel = 'noopener'; enlace.title = 'Abrir ' + titulo.toLowerCase();
      const img = el('img'); img.src = enlace.href; img.alt = titulo; img.loading = 'lazy';
      enlace.append(img); figura.append(enlace);
    } else {
      const vacio = el('div', 'cc-rev-sin-foto'); vacio.append(icono('fa-image')); figura.append(vacio);
    }
    figura.append(el('figcaption', null, titulo));
    return figura;
  }
  // Primera foto en grande y el resto en miniaturas (varios comprobantes o evidencias).
  function galeriaRevision(sol, nombres, titulo) {
    const figura = fotoRevision(sol, nombres[0], titulo + (nombres.length > 1 ? ' (' + nombres.length + ')' : ''));
    if (nombres.length > 1) {
      const tira = el('div', 'cc-rev-miniaturas');
      nombres.slice(1).forEach((n, i) => {
        const a = el('a'); a.href = '/form-pruebas/caja-chica/foto/' + sol.id + '/' + n; a.target = '_blank'; a.rel = 'noopener';
        a.title = titulo + ' ' + (i + 2);
        const img = el('img'); img.src = a.href; img.alt = a.title; img.loading = 'lazy'; a.append(img); tira.append(a);
      });
      figura.insertBefore(tira, figura.querySelector('figcaption'));
    }
    return figura;
  }
  // ID de un archivo de Google Drive (open?id=ID, /file/d/ID/view, uc?id=ID).
  const driveId = u => (String(u || '').match(/[?&]id=([A-Za-z0-9_-]{8,})/) || String(u || '').match(/\/d\/([A-Za-z0-9_-]{8,})/) || [])[1] || null;
  const cacheOrigen = new Map();
  function fotosOrigen(sol) {
    if (!cacheOrigen.has(sol.id)) {
      cacheOrigen.set(sol.id, fetch('/api/caja-chica/' + sol.id + '/fotos-origen', {credentials: 'same-origin'})
        .then(r => r.ok ? r.json() : {fotos: []}).then(j => j.fotos || []).catch(() => []));
    }
    return cacheOrigen.get(sol.id);
  }
  function tarjetaConcepto(sol, item) {
    const caja = el('section', 'cc-ficha cc-rev-item cc-rev-' + item.estado.toLowerCase());
    const cabeza = el('h4', 'cc-ficha-titulo');
    const iconos = {EN_REVISION: 'fa-magnifying-glass-dollar', RECHAZADO: 'fa-rotate-left', POR_RENDIR: 'fa-hourglass-half'};
    const nombre = el('span', 'cc-rev-nombre', item.numero + ' · ' + item.tipo_gasto);
    if (item.tipo_presupuesto) nombre.append(el('span', 'cc-ficha-suave', ' · ' + item.tipo_presupuesto));
    cabeza.append(icono(iconos[item.estado] || 'fa-receipt'), nombre, el('span', 'cc-chip cc-' + item.estado.toLowerCase(), ITEM[item.estado]));
    if (puedeGestionar && sol.estado === 'DEPOSITADO' && item.estado === 'EN_REVISION') {
      const acciones = el('span', 'cc-dialogo-acciones');
      const validar = boton('', 'cc-dialogo-icono cc-dialogo-guardar', intentar(() => accion(sol, 'revisar_item', {item: item.id, aprobar: true})));
      validar.title = 'Validar ' + item.tipo_gasto; validar.setAttribute('aria-label', validar.title); validar.append(icono('fa-check'));
      const rechazar = boton('', 'cc-dialogo-icono cc-dialogo-cerrar',
        conMotivo(sol, 'revisar_item', motivoItem(sol, item), {item: item.id, aprobar: false}));
      rechazar.title = 'Rechazar ' + item.tipo_gasto; rechazar.setAttribute('aria-label', rechazar.title); rechazar.append(icono('fa-xmark'));
      acciones.append(validar, rechazar);
      cabeza.append(acciones);
    }
    caja.append(cabeza);
    if (item.estado === 'POR_RENDIR') {
      caja.append(el('p', 'cc-rev-espera', 'El técnico aún no rinde este concepto · solicitado ' + dinero(item.monto)));
      return caja;
    }
    const cuerpo = el('div', 'cc-rev-cuerpo');
    const sobrante = Number(item.monto) - Number(item.monto_gastado || 0);
    const razon = item.razon_social || (item.ruc ? 'Sin consultar' : '');
    const comps = item.comprobantes || [];
    const filasComp = comps.length > 1
      ? comps.map((c, i) => ['Comprobante ' + (i + 1), [c.comprobante, dinero(c.monto), 'RUC ' + c.ruc, c.razon_social].filter(Boolean).join(' · ')])
      : [['RUC', item.ruc, 'cc-mono'], ['Razón social', razon], ['Comprobante', item.comprobante]];
    cuerpo.append(ficha('fa-receipt', '', [
      ...filasComp,
      ['Solicitado', dinero(item.monto)], ['Gastó', item.monto_gastado && dinero(item.monto_gastado)],
      ['Sobrante', sobrante > 0 && item.monto_gastado ? dinero(sobrante) + ' · va a devolución' : '', 'cc-rev-sobrante']]).querySelector('dl'));
    const evidencias = item.evidencias?.length ? item.evidencias : [item.evidencia].filter(Boolean);
    if (!item.fotos.length && !evidencias.length) {
      // Solicitud migrada desde Rendición: las fotos quedaron en el registro original.
      const origen = el('div', 'cc-rev-origen');
      origen.append(el('p', 'cc-nota', 'Buscando fotos en Rendición…'));
      cuerpo.append(origen);
      fotosOrigen(sol).then(fotos => {
        origen.replaceChildren();
        if (!fotos.length) { origen.append(fotoRevision(sol, '', 'Sin fotos en el registro de Rendición')); return; }
        for (const f of fotos) {
          const figura = el('figure', 'cc-rev-foto'), enlace = el('a');
          const id = driveId(f.url);
          enlace.href = id ? 'https://drive.google.com/file/d/' + id + '/view' : f.url;
          enlace.target = '_blank'; enlace.rel = 'noopener'; enlace.title = 'Abrir ' + f.etiqueta.toLowerCase();
          // Fotos del formulario (Drive): se prueban las miniaturas de Google, como en Rendición.
          const opciones = id ? ['https://lh3.googleusercontent.com/d/' + id + '=w600',
            'https://drive.google.com/thumbnail?id=' + id + '&sz=w600', f.url] : [f.url];
          const img = el('img'); img.alt = f.etiqueta; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
          img.src = opciones.shift();
          img.addEventListener('error', () => {
            if (opciones.length) img.src = opciones.shift();
            else img.replaceWith(el('span', 'cc-rev-sin-foto', 'Abrir foto'));
          });
          enlace.append(img); figura.append(enlace, el('figcaption', null, f.etiqueta)); origen.append(figura);
        }
      });
    } else cuerpo.append(galeriaRevision(sol, item.fotos, 'Boleta / factura'), galeriaRevision(sol, evidencias, 'Evidencia del gasto'));
    caja.append(cuerpo);
    if (item.estado === 'RECHAZADO') {
      const motivo = el('div', 'cc-rev-motivo');
      const texto = el('span'); texto.append(el('strong', null, 'Motivo: '), item.motivo_rechazo || '');
      motivo.append(texto, el('span', null, 'El técnico corrige o devuelve ' + dinero(item.monto)));
      caja.append(motivo);
    }
    return caja;
  }
  function panelRevision(sol) {
    const f = sol.formulario || {};
    const columna = el('div', 'cc-rev');
    const detalleFicha = ficha('fa-file-lines', 'Detalle de la solicitud', [
      ['Técnico', [sol.tecnico, sol.documento].filter(Boolean).join(' · ')], ['Supervisor', f.supervisor], ['Site', f.site],
      ['CM / PM / PLM', f.wo], ['Cotización', sol.revision?.cotizacion],
      ['Banco', sol.banco], ['Depositado', sol.depositado_en ? fechaDeposito(sol) : sol.deposito_fecha], ['Por', sol.depositado_por]]);
    detalleFicha.classList.add('cc-rev-detalle');
    // Totales: depositado, aprobado, en revisión, rechazado y la devolución estimada.
    const suma = (estados, campo) => sol.items.filter(i => estados.includes(i.estado)).reduce((t, i) => t + Number(i[campo] || 0), 0);
    const depositado = Number(sol.deposito_monto || sol.total);
    const aprobado = suma(['APROBADO'], 'monto_gastado');
    const enRevision = suma(['EN_REVISION'], 'monto_gastado');
    const porDevolver = sol.estado === 'POR_DEVOLVER' ? Number(sol.diferencia)
      : depositado - aprobado - enRevision - suma(['RECHAZADO', 'POR_RENDIR'], 'monto');
    const totales = el('div', 'cc-rev-totales');
    for (const [titulo, valor, clase] of [['Depositado', depositado], ['Aprobado', aprobado, 'ok'], ['En revisión', enRevision, 'rev'],
      ['Rechazado', suma(['RECHAZADO'], 'monto'), 'no'], [sol.estado === 'POR_DEVOLVER' ? 'Por devolver' : 'Por devolver (estimado)', Math.max(0, porDevolver), 'dev']]) {
      const caja = el('div', clase ? 'cc-rev-' + clase : null); caja.append(el('small', null, titulo), el('strong', null, dinero(valor))); totales.append(caja);
    }
    detalleFicha.append(totales);
    columna.append(detalleFicha);
    const porRevisar = itemsEtapa(sol, 'revision');
    if (porRevisar.length) {
      columna.append(el('h5', 'cc-rev-seccion', 'Por revisar · ' + porRevisar.length),
        ...porRevisar.map(item => tarjetaConcepto(sol, item)));
    }
    const devolucion = el('section', 'cc-ficha cc-rev-devolucion');
    const cabeza = el('h4', 'cc-ficha-titulo'); cabeza.append(icono('fa-hand-holding-dollar'), el('span', 'cc-rev-nombre', 'Devolución'));
    devolucion.append(cabeza);
    if (sol.estado === 'POR_DEVOLVER' && sol.devolucion_foto) {
      if (puedeGestionar) {
        const acciones = el('span', 'cc-dialogo-acciones');
        const aceptar = boton('', 'cc-dialogo-icono cc-dialogo-guardar', intentar(() => accion(sol, 'devolucion', {aceptar: true})));
        aceptar.title = 'Aceptar devolución y archivar'; aceptar.setAttribute('aria-label', aceptar.title); aceptar.append(icono('fa-check'));
        const rechazar = boton('', 'cc-dialogo-icono cc-dialogo-cerrar', conMotivo(sol, 'devolucion', MOTIVO_DEVOLUCION(sol), {aceptar: false}));
        rechazar.title = 'Rechazar la captura'; rechazar.setAttribute('aria-label', rechazar.title); rechazar.append(icono('fa-xmark'));
        acciones.append(aceptar, rechazar); cabeza.append(acciones);
      }
      const cuerpo = el('div', 'cc-rev-cuerpo');
      cuerpo.append(ficha('fa-receipt', '', [['Monto devuelto', dinero(sol.diferencia)]]).querySelector('dl'),
        fotoRevision(sol, sol.devolucion_foto, 'Captura de la devolución'));
      devolucion.append(cuerpo);
    } else if (sol.estado === 'DEPOSITADO' && sol.devolucion_foto) {
      // La captura llegó antes de revisar todos los ítems: se aprueba o rechaza ya.
      const aprobada = sol.devolucion_aceptada;
      cabeza.append(el('span', 'cc-chip ' + (aprobada ? 'cc-aprobado' : 'cc-en_revision'), aprobada ? 'Aprobada' : 'Por revisar'));
      if (puedeGestionar && !aprobada) {
        const acciones = el('span', 'cc-dialogo-acciones');
        const aceptar = boton('', 'cc-dialogo-icono cc-dialogo-guardar', intentar(() => accion(sol, 'devolucion', {aceptar: true})));
        aceptar.title = 'Aprobar devolución'; aceptar.setAttribute('aria-label', aceptar.title); aceptar.append(icono('fa-check'));
        const rechazar = boton('', 'cc-dialogo-icono cc-dialogo-cerrar', conMotivo(sol, 'devolucion', MOTIVO_DEVOLUCION(sol), {aceptar: false}));
        rechazar.title = 'Rechazar devolución'; rechazar.setAttribute('aria-label', rechazar.title); rechazar.append(icono('fa-xmark'));
        acciones.append(aceptar, rechazar); cabeza.append(acciones);
      }
      const cuerpo = el('div', 'cc-rev-cuerpo');
      cuerpo.append(ficha('fa-receipt', '', [['Monto devuelto', dinero(sol.devolucion_monto)],
        ['Estado', aprobada ? 'Aprobada · se archiva al validar todos los ítems' : 'Revisa que la transferencia haya llegado']]).querySelector('dl'),
        fotoRevision(sol, sol.devolucion_foto, 'Captura de la devolución'));
      devolucion.append(cuerpo);
    } else {
      const aviso = el('div', 'cc-cotizacion-aviso');
      aviso.dataset.resultado = '';
      aviso.textContent = sol.estado === 'POR_DEVOLVER'
        ? 'Esperando que el técnico devuelva ' + dinero(sol.diferencia) + ' y suba la captura.'
        : 'Aparece cuando no quede nada por revisar ni corregir. El técnico verá el monto a devolver y subirá la captura; aquí se acepta o se rechaza.';
      devolucion.append(aviso);
    }
    columna.append(devolucion);
    return columna;
  }

  // Ventana de "Por rendir" (solo lectura): timer y datos a la izquierda, foto del depósito a la derecha.
  function panelPorRendir(sol) {
    const panel = el('div', 'cc-rendir-panel');
    const izquierda = el('div', 'cc-deposito-izquierda');
    const timer = el('div', 'cc-sla-timer');
    timer.dataset.sla = sol.depositado_en;
    const textos = el('div');
    textos.append(el('small', null, 'Tiempo desde el depósito'), el('strong', 'cc-sla-tiempo'));
    const cuando = el('div', 'cc-sla-cuando');
    cuando.append(el('small', null, 'Depositado'), el('strong', null, fechaDeposito(sol)));
    timer.append(icono('fa-clock'), textos, cuando);
    pintarSla(timer);
    const pendientes = itemsEtapa(sol, 'por_rendir');
    if (sol.estado === 'POR_DEVOLVER') {
      izquierda.append(ficha('fa-hand-holding-dollar', 'Devolución pendiente', [['Por devolver', dinero(sol.diferencia)]]));
    }
    const fichas = resumenSolicitud({...sol, items: pendientes, total: sol.pendiente});
    izquierda.append(...(pendientes.length ? fichas : fichas.slice(1)));
    for (const item of pendientes.filter(i => i.estado === 'RECHAZADO')) {
      izquierda.append(el('p', 'cc-alerta', item.tipo_gasto + ' · ' + item.motivo_rechazo));
    }
    const derecha = el('figure', 'cc-rendir-foto');
    if (sol.deposito_foto) {
      const enlace = el('a');
      enlace.href = '/form-pruebas/caja-chica/foto/' + sol.id + '/' + sol.deposito_foto;
      enlace.target = '_blank'; enlace.rel = 'noopener'; enlace.title = 'Abrir la foto en otra pestaña';
      const imagen = el('img'); imagen.src = enlace.href; imagen.alt = 'Comprobante del depósito de ' + sol.codigo;
      enlace.append(imagen);
      derecha.append(enlace, el('figcaption', null, 'Comprobante del depósito · clic para ampliar'));
    } else {
      derecha.append(el('p', 'cc-nota', 'Sin foto del depósito.'));
    }
    const columnaFoto = el('div', 'cc-rendir-derecha');
    columnaFoto.append(timer, derecha);
    panel.append(izquierda, columnaFoto);
    return panel;
  }

  function justificacionSolicitud(sol) {
    const tarjeta = el('section', 'cc-ficha cc-justificacion');
    const titulo = el('h4', 'cc-ficha-titulo');
    titulo.append(icono('fa-file-lines'), el('span', null, 'Justificación de la solicitud'));
    tarjeta.append(titulo, el('p', 'cc-justificacion-texto', sol.motivo || 'Sin registrar'));
    return tarjeta;
  }

  function mostrarDetalle() {
    if (!dialogo.open) dialogo.showModal();
    $('cc-solicitud-contenido').scrollTop = 0;
    dialogo.scrollTop = 0;
  }

  function verDetalle(sol) {
    solicitudAbierta = sol.id;
    $('cc-solicitud-editar').classList.remove('activo');
    $('cc-solicitud-titulo').textContent = [sol.codigo, sol.tecnico, sol.proyecto].join(' · ');
    const contenido = $('cc-solicitud-contenido');
    const editar = $('cc-solicitud-editar');
    const guardar = $('cc-solicitud-guardar');
    const validar = $('cc-solicitud-validar');
    const anular = $('cc-solicitud-anular');
    const rechazar = $('cc-solicitud-rechazar');
    validar.hidden = !puedeGestionar || sol.estado !== 'PENDIENTE';
    anular.hidden = !puedeGestionar || !['PENDIENTE', 'RECHAZADO'].includes(sol.estado);
    rechazar.hidden = !puedeGestionar || sol.estado !== 'VALIDADO';
    rechazar.disabled = false;
    rechazar.onclick = intentar(async () => {
      const motivo = await pedirMotivo({titulo: 'Rechazar solicitud', subtitulo: sol.codigo + ' · ' + (sol.tecnico || ''),
        datos: [['Proyecto', sol.proyecto], ['Total', dinero(sol.total)]], sugerencias: SUGERENCIAS.rechazar,
        ayuda: 'La solicitud volverá a Validación.'});
      if (motivo === null) return;
      rechazar.disabled = true;
      try { await accion(sol, 'rechazar', {motivo}); }
      finally { rechazar.disabled = false; }
    });
    validar.disabled = anular.disabled = false;
    validar.onclick = intentar(async () => {
      if (!await confirmar('La solicitud ' + sol.codigo + ' por ' + dinero(sol.total) + ' pasará a Por depositar.', 'Validar solicitud', {okText: 'Validar', circular: true})) return;
      validar.disabled = true;
      try { await accion(sol, 'validar'); }
      finally { validar.disabled = false; }
    });
    anular.onclick = intentar(async () => {
      const motivo = await pedirMotivo({titulo: 'Anular solicitud', subtitulo: sol.codigo + ' · ' + (sol.tecnico || ''),
        datos: [['Proyecto', sol.proyecto], ['Total', dinero(sol.total)]], sugerencias: SUGERENCIAS.anular,
        ayuda: 'La solicitud pasará a Anuladas.', okText: 'Anular', iconoNombre: 'fa-ban'});
      if (motivo === null) return;
      anular.disabled = true;
      try { await accion(sol, 'anular', {motivo}); }
      finally { anular.disabled = false; }
    });
    const enDeposito = tab === 'deposito' && sol.estado === 'VALIDADO';
    editar.hidden = guardar.hidden = enDeposito;
    // El botón redondo de depósito (junto a la X) solo se ve al depositar.
    $('cc-solicitud-depositar').hidden = !(enDeposito && puedeGestionar);
    const botonTecnico = $('cc-solicitud-tecnico');
    botonTecnico.hidden = !esAdmin;
    botonTecnico.onclick = () => corregirTecnico(sol);
    const botonArchivar = $('cc-solicitud-archivar'), botonSustento = $('cc-solicitud-sustento');
    botonArchivar.hidden = !(puedeGestionar && tab === 'sustento' && sol.estado === 'SUSTENTO');
    botonSustento.hidden = !(puedeGestionar && tab === 'archivado' && sol.estado === 'ARCHIVADO');
    botonArchivar.onclick = intentar(() => pasarEtapa(sol, 'archivar'));
    botonSustento.onclick = intentar(() => pasarEtapa(sol, 'sustento'));
    if (tab === 'pendientes') {
      // CM / Site pendiente: solo se edita el site y el N.º CM / PM / PLM; nada más de la solicitud.
      [editar, validar, anular, rechazar, botonTecnico, botonArchivar, botonSustento, $('cc-solicitud-depositar')]
        .forEach(b => { b.hidden = true; });
      const f = sol.formulario || {};
      const limpio = (v, pendiente) => (v || '').trim().toUpperCase() === pendiente ? '' : (v || '');
      const form = el('form', 'cc-ficha cc-pendiente-form'); form.id = 'cc-pendiente-form'; form.noValidate = true;
      const titulo = el('h4', 'cc-ficha-titulo'); titulo.append(icono('fa-triangle-exclamation'), el('span', null, 'Completar ' + (sol.faltan || []).join(' y ')));
      const cm = Object.assign(el('input'), {maxLength: 100, value: limpio(f.wo, 'CM PENDIENTE'), placeholder: 'CM-AAAAMMDD-NNNNNNNN'});
      const site = Object.assign(el('input'), {maxLength: 150, value: limpio(f.site, 'SITE PENDIENTE'), placeholder: 'Nombre del site'});
      const etiqueta = (texto, control) => { const l = el('label', 'cc-pendiente-campo'); l.append(el('span', null, texto), control); return l; };
      const error = el('p', 'cc-alerta'); error.hidden = true;
      form.append(titulo, etiqueta('N.º CM / PM / PLM (vacío = CM PENDIENTE)', cm), etiqueta('Nombre del site (vacío = SITE PENDIENTE)', site), error);
      form.addEventListener('submit', async e => {
        e.preventDefault();
        guardar.disabled = true; error.hidden = true;
        try { await accion(sol, 'cm_site', {wo: cm.value, site: site.value}); dialogo.close(); }
        catch (err) { error.textContent = err.message; error.hidden = false; }
        finally { guardar.disabled = false; }
      });
      const resumen = ficha('fa-file-lines', 'Solicitud', [
        ['Técnico', [sol.tecnico, sol.documento].filter(Boolean).join(' · ')], ['Proyecto', sol.proyecto],
        ['Responsable', f.responsable_validacion], ['Total', dinero(sol.total)]]);
      guardar.hidden = !puedeGestionar; guardar.disabled = !puedeGestionar;
      guardar.setAttribute('form', form.id);
      contenido.replaceChildren(resumen, form);
      mostrarDetalle();
      (sol.faltan?.includes('CM') ? cm : site).focus();
      return;
    }
    if (tab === 'archivado' || tab === 'sustento') {
      editar.hidden = guardar.hidden = true;
      const fichaArchivada = ficha('fa-file-lines', 'Gastos conformes', [
        ['Estado de la solicitud', sol.estado === 'ARCHIVADO' ? 'Cerrada' : sol.estado === 'SUSTENTO' ? 'Lista para archivar' : 'Faltan ítems por rendir o revisar'],
        ['Gasto aprobado', dinero(importeEtapa(sol, tab))],
        ['Justificación', sol.motivo || 'Sin registrar', 'cc-justificacion-texto'],
      ]);
      contenido.replaceChildren(fichaArchivada, ...itemsEtapa(sol, tab).map(item => tarjetaConcepto(sol, item)));
      mostrarDetalle();
      return;
    }
    if (tab === 'revision' && ['DEPOSITADO', 'POR_DEVOLVER'].includes(sol.estado)) {
      editar.hidden = guardar.hidden = true;
      contenido.replaceChildren(justificacionSolicitud(sol), panelRevision(sol));
      mostrarDetalle();
      return;
    }
    if (tab === 'por_rendir' && sol.depositado_en) {
      editar.hidden = guardar.hidden = true;
      contenido.replaceChildren(panelPorRendir(sol));
      mostrarDetalle();
      return;
    }
    if (enDeposito) {
      contenido.replaceChildren(...(puedeGestionar
        ? [formularioDeposito(sol)]
        : [justificacionSolicitud(sol), datosEnviados(sol, 'Datos de la solicitud')]));
      mostrarDetalle();
      return;
    }
    // Dos columnas: detalle a la izquierda; cotización, revisión y adjunto a la derecha.
    const izquierda = el('div', 'cc-validacion-izquierda');
    const derecha = el('div', 'cc-validacion-derecha');
    izquierda.append(...resumenSolicitud(sol));
    if (sol.envio_tecnico) {
      const original = el('details', 'cc-ficha cc-ficha-original');
      original.append(el('summary', null, 'Ver lo que envió el técnico'), datosEnviados(sol.envio_tecnico));
      izquierda.append(original);
    }
    const revision = sol.revision || {};
    if (revision.cotizacion) derecha.append(el('p', 'cc-validacion-dato', 'Cotización: ' + revision.cotizacion));
    if (revision.archivo) {
      const enlace = el('a', 'cc-foto', 'Descargar correo de validación');
      enlace.href = '/api/caja-chica/' + sol.id + '/correo-validacion';
      derecha.append(enlace);
    }
    if (sol.items.some(i => i.requiere_correo) && !revision.archivo) derecha.append(el('p', 'cc-alerta', 'Falta adjuntar el correo de validación.'));
    if (sol.items.some(i => i.requiere_cotizacion) && !revision.cotizacion) derecha.append(el('p', 'cc-alerta', 'Falta el número de cotización.'));
    const columnas = el('div', 'cc-validacion-columnas');
    columnas.append(izquierda, derecha);
    contenido.replaceChildren(columnas);
    editar.disabled = !puedeGestionar || sol.estado !== 'PENDIENTE';
    const documentos = editar.disabled ? null : formularioDocumentos(sol);
    guardar.setAttribute('form', 'cc-solicitud-documentos');
    guardar.disabled = !documentos;
    editar.onclick = () => {
      // La columna izquierda se vuelve editable; la derecha (cotización y correo) no cambia.
      const form = editorSolicitud(sol, documentos);
      izquierda.replaceChildren(form);
      editar.disabled = true;
      editar.classList.add('activo');
      validar.disabled = anular.disabled = true;
      guardar.setAttribute('form', form.id);
      guardar.disabled = false;
      form.querySelector('select').focus();
    };
    const seguimiento = detalle(sol);
    if (seguimiento.hasChildNodes()) izquierda.append(seguimiento);
    if (documentos && (documentos.pideCotizacion || documentos.pideCorreo)) derecha.prepend(documentos);
    else if (documentos) { documentos.hidden = true; derecha.append(documentos); }  // el botón Guardar sigue apuntando al formulario
    columnas.classList.toggle('cc-una-columna', ![...derecha.children].some(n => !n.hidden));
    mostrarDetalle();
  }
  // ── Tabla: columnas que se filtran y se mueven arrastrando ──
  // Columna "Estado": dice qué falta en lenguaje simple, con el color de la pestaña.
  function estadoDe(s) {
    const items = s.items || [];
    const hay = estado => items.some(i => i.estado === estado);
    const devolucionPorRevisar = s.devolucion_foto && !s.devolucion_aceptada;
    if (s.estado === 'ANULADO') return ['Anulada', 'cc-e-anulada'];
    if (s.estado === 'RECHAZADO') return ['Observada · la corrige el técnico', 'cc-e-observada'];
    if (s.estado === 'PENDIENTE') {
      if (s.retorno === 'desde_deposito') return ['Devuelta desde Depósito · por validar', 'cc-e-observada'];
      if (s.retorno === 'reenviada') return ['Corregida · por validar', 'cc-e-reenviada'];
      return ['Por validar', 'cc-e-validar'];
    }
    if (s.estado === 'VALIDADO') return ['Por depositar', 'cc-e-depositar'];
    if (s.estado === 'ARCHIVADO') return ['Archivada · cerrada', 'cc-e-archivada'];
    if (s.estado === 'SUSTENTO') return ['Por archivar', 'cc-e-sustento'];
    // Depositada: el texto depende de la pestaña donde se mira.
    if (tab === 'sustento') return ['Aprobada en parte · ítems pendientes', 'cc-e-archivada'];
    if (tab === 'revision') {
      if (hay('EN_REVISION')) return [devolucionPorRevisar ? 'Ítems y devolución por revisar' : 'Ítems por revisar', 'cc-e-revisar'];
      return ['Devolución por revisar', 'cc-e-revisar'];
    }
    if (hay('RECHAZADO')) return ['Ítem observado · lo corrige el técnico', 'cc-e-observada'];
    if (hay('POR_RENDIR')) return ['Por rendir', 'cc-e-rendir'];
    if (Number(s.diferencia) > 0 && !s.devolucion_foto) return ['Falta la devolución', 'cc-e-rendir'];
    if (devolucionPorRevisar) return ['Devolución por revisar', 'cc-e-revisar'];
    if (hay('EN_REVISION')) return ['Rendida · por revisar', 'cc-e-revisar'];
    return [ESTADOS[s.estado] || s.estado, 'cc-e-rendir'];
  }
  const creado = s => new Date(s.creado + 'Z');
  const NOMBRES_PROYECTO = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};
  // Desplegable de proyecto: filtra cantidades, montos y la tabla. Vacío = todos.
  const selectorProyecto = $('cc-proyecto');
  configuracion.proyectos.forEach(p => selectorProyecto.add(new Option(NOMBRES_PROYECTO[p] || p, p)));
  const botonProyecto = $('cc-proyecto-btn'), menuProyecto = $('cc-proyecto-menu');
  const cerrarProyecto = () => { menuProyecto.hidden = true; botonProyecto.setAttribute('aria-expanded', 'false'); };
  const opcionesProyecto = [...selectorProyecto.options].map(o => {
    const b = el('button', 'cc-proyecto-opcion'); b.type = 'button'; b.setAttribute('role', 'option'); b.dataset.valor = o.value;
    const punto = el('span', 'cc-proyecto-punto ' + (o.value ? 'project-badge--' + o.value.toLowerCase() : 'cc-proyecto-todos'));
    const check = el('i', 'fa-solid fa-check cc-proyecto-check'); check.setAttribute('aria-hidden', 'true');
    b.append(check, punto, el('span', null, o.text), el('span', 'cc-proyecto-cuenta', '0'));
    b.addEventListener('click', () => {
      cerrarProyecto(); botonProyecto.focus();
      if (selectorProyecto.value === o.value) return;
      selectorProyecto.value = o.value; selectorProyecto.dispatchEvent(new Event('change'));
    });
    menuProyecto.append(b); return b;
  });
  botonProyecto.addEventListener('click', e => {
    e.stopPropagation();
    const abrir = menuProyecto.hidden; menuProyecto.hidden = !abrir; botonProyecto.setAttribute('aria-expanded', String(abrir));
    if (abrir) (menuProyecto.querySelector('[aria-selected="true"]') || opcionesProyecto[0]).focus();
  });
  menuProyecto.addEventListener('keydown', e => {
    const i = opcionesProyecto.indexOf(document.activeElement), n = opcionesProyecto.length;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); opcionesProyecto[(i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n].focus(); }
    else if (e.key === 'Escape') { cerrarProyecto(); botonProyecto.focus(); }
  });
  document.addEventListener('click', e => { if (!menuProyecto.hidden && !menuProyecto.contains(e.target)) cerrarProyecto(); });
  // Texto del botón, opción marcada y cantidad de solicitudes por proyecto.
  function pintarProyecto() {
    const elegido = selectorProyecto.selectedOptions[0];
    $('cc-proyecto-texto').textContent = elegido ? elegido.text : 'Todos los proyectos';
    $('cc-proyecto-btn').title = 'Proyecto: ' + (elegido ? elegido.text : 'Todos los proyectos');
    botonProyecto.closest('.cc-proyecto-pill').classList.toggle('activo', !!selectorProyecto.value);
    opcionesProyecto.forEach(b => {
      b.setAttribute('aria-selected', String(b.dataset.valor === selectorProyecto.value));
      b.lastChild.textContent = solicitudes.filter(s => !b.dataset.valor || s.proyecto === b.dataset.valor).length;
    });
  }
  const delProyecto = () => solicitudes.filter(s => !selectorProyecto.value || s.proyecto === selectorProyecto.value);
  const COLUMNAS = {
    codigo:   {titulo: 'Código depósito', ancho: 'minmax(145px, 1fr)', texto: s => s.codigo, celda: s => {
      const enlace = el('a', 'cc-codigo-link', s.codigo);
      enlace.href = '#solicitud-' + s.id;
      enlace.addEventListener('click', e => { e.preventDefault(); verDetalle(s); });
      return enlace;
    }},
    tecnico:  {titulo: 'Técnico · Documento', ancho: 'minmax(180px, 2.4fr)', texto: s => s.tecnico + ' · ' + s.documento},
    proyecto: {titulo: 'Proyecto', ancho: 'minmax(100px, .8fr)', texto: s => s.proyecto, celda: s => {
      const nombre = NOMBRES_PROYECTO[s.proyecto];
      return el('span', nombre ? 'project-badge project-badge--' + s.proyecto.toLowerCase() : null, nombre || s.proyecto);
    }},
    site: {titulo: 'Nombre del site', ancho: 'minmax(150px, 1fr)', texto: s => s.formulario?.site || '—',
           celda: s => el('span', s.faltan?.includes('Site') ? 'cc-falta' : null, s.formulario?.site || '—')},
    wo: {titulo: 'N.º CM / PM / PLM', ancho: 'minmax(145px, 1fr)', texto: s => s.formulario?.wo || '—',
         celda: s => el('span', s.faltan?.includes('CM') ? 'cc-falta' : null, s.formulario?.wo || '—')},
    // Gasto Cobra / Refacturable según los conceptos de la solicitud (pueden ser ambos).
    presupuesto: {titulo: 'Gasto Cobra / Refacturable', ancho: 'minmax(150px, 1fr)',
                  texto: s => [...new Set(itemsEtapa(s).map(i => i.tipo_presupuesto).filter(Boolean))].join(' · ') || '—',
                  celda: s => {
                    const tipos = [...new Set(itemsEtapa(s).map(i => i.tipo_presupuesto).filter(Boolean))];
                    if (!tipos.length) return el('span', null, '—');
                    const caja = el('span', 'cc-presupuestos');
                    tipos.forEach(t => caja.append(el('span', 'cc-chip ' + (/refact/i.test(t) ? 'cc-refacturable' : 'cc-gasto-cobra'), t)));
                    return caja;
                  }},
    justificacion: {titulo: 'Justificación', ancho: 'minmax(220px, 1.8fr)', texto: s => s.motivo || '—', clase: 'cc-justificacion-celda'},
    gasto: {titulo: 'Tipo de gasto', ancho: 'minmax(190px, 1.4fr)',
            texto: s => [...new Set(itemsEtapa(s).map(item => item.tipo_gasto))].join(' · ') || '—'},
    dataper: {titulo: 'Dataper', ancho: 'minmax(150px, .9fr)', texto: s => s.dataper ? 'Registrado' : 'No registrado',
              celda: s => el('span', 'cc-chip ' + (s.dataper ? 'cc-dataper-si' : 'cc-dataper-no'), s.dataper ? 'Registrado' : 'No registrado')},
    responsable: {titulo: 'Responsable de validación', ancho: 'minmax(190px, 1.3fr)',
                  texto: s => s.formulario?.responsable_validacion || '—'},
    estado:   {titulo: 'Estado', ancho: 'minmax(180px, 1.3fr)', texto: s => estadoDe(s)[0],
               celda: s => { const [t, c] = estadoDe(s); return el('span', 'cc-chip ' + c, t); }},
    fecha:    {titulo: 'Fecha / Avance', ancho: 'minmax(140px, 1.1fr)', clase: 'cc-avance', orden: s => creado(s).getTime(),
               texto: s => s.estado === 'DEPOSITADO' ? s.avance : creado(s).toLocaleDateString('es-PE')},
    total:    {titulo: 'Importe de etapa', ancho: 'minmax(110px, .8fr)', num: true, orden: s => Number(importeEtapa(s)) || 0, texto: s => dinero(importeEtapa(s)),
               celda: s => el('strong', 'cc-num', dinero(importeEtapa(s)))},
  };
  // El orden y ancho de las columnas se recuerdan en este navegador.
  let columnas = Object.keys(COLUMNAS), filtros = {}, busquedas = {}, anchos = {};
  // Orden de la tabla: columna y sentido (1 = menor a mayor, -1 = mayor a menor).
  let orden = null;
  // Búsqueda sin distinguir mayúsculas ni tildes ("peru" encuentra "Perú").
  const plano = t => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  try {
    const p = JSON.parse(localStorage.getItem('cc-tabla') || '{}');
    if (Array.isArray(p.columnas) && p.columnas.length === columnas.length && columnas.every(c => p.columnas.includes(c))) columnas = p.columnas;
    if (p.anchos && typeof p.anchos === 'object') for (const [c, w] of Object.entries(p.anchos)) if (COLUMNAS[c] && w >= 60) anchos[c] = w;
  } catch (_) {}
  const guardar = () => { try { localStorage.setItem('cc-tabla', JSON.stringify({columnas, anchos})); } catch (_) {} };
  // Ancho de cada columna: el que el usuario fijó arrastrando o, si no, el automático.
  const plantilla = () => {
    // Ancho mínimo de la tabla = suma de columnas + espacios; si no cabe, se desplaza a lo ancho.
    const minimo = columnas.reduce((s, c) => s + (anchos[c] || parseInt(COLUMNAS[c].ancho.slice(7), 10)), 0)
      + 12 * columnas.length + 140 + (puedeEliminar ? 52 : 0);
    $('cc-tabla').style.setProperty('--cc-min', minimo + 'px');
    const medidas = columnas.map(c => anchos[c] ? anchos[c] + 'px' : COLUMNAS[c].ancho);
    return [...(puedeEliminar ? ['40px'] : []), '108px', ...medidas].join(' ');
  };
  // Nucleus aplica zoom al área principal: factor para pasar px de pantalla a px CSS.
  const escala = () => { const t = $('cc-tabla'); return t.getBoundingClientRect().width / t.offsetWidth || 1; };

  // Ajustar ancho: arrastrar el borde derecho de la cabecera. Doble clic vuelve al automático.
  function asa(id, th) {
    const a = el('span', 'cc-th-asa'); a.title = 'Arrastra para ajustar el ancho · doble clic: automático';
    a.addEventListener('pointerdown', e => {
      e.preventDefault(); e.stopPropagation(); a.setPointerCapture(e.pointerId);
      const inicio = e.clientX, base = th.getBoundingClientRect().width, z = escala();
      document.body.classList.add('cc-redimensionando');
      const mover = ev => { anchos[id] = Math.max(60, Math.round((base + ev.clientX - inicio) / z)); $('cc-tabla').style.setProperty('--cc-cols', plantilla()); };
      const soltar = () => { a.removeEventListener('pointermove', mover); document.body.classList.remove('cc-redimensionando'); guardar(); };
      a.addEventListener('pointermove', mover);
      a.addEventListener('pointerup', soltar, {once: true});
      a.addEventListener('pointercancel', soltar, {once: true});
    });
    a.addEventListener('dblclick', e => { e.stopPropagation(); delete anchos[id]; guardar(); pintarEncabezado(); });
    return a;
  }

  function icono(nombre) { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; }
  function pintarEncabezado() {
    $('cc-tabla').style.setProperty('--cc-cols', plantilla());
    const cab = $('cc-encabezado');
    // El encabezado se redibuja al filtrar: se conserva el cuadro de búsqueda donde se está escribiendo.
    const activo = document.activeElement, foco = activo && cab.contains(activo) && activo.dataset.buscar
      ? {col: activo.dataset.buscar, ini: activo.selectionStart, fin: activo.selectionEnd} : null;
    cab.replaceChildren();
    if (puedeEliminar) cab.append(el('div', 'cc-th cc-th-nombre cc-acciones-cab cc-seleccion', 'Sel.'));
    cab.append(el('div', 'cc-th cc-th-nombre cc-acciones-cab cc-col-acciones', 'Acciones'));
    for (const id of columnas) {
      const col = COLUMNAS[id], th = el('div', 'cc-th' + (col.num ? ' cc-th-num' : ''));
      th.dataset.col = id;
      const fila = el('div', 'cc-th-fila'); fila.draggable = true; fila.title = 'Arrastra para mover la columna';
      const buscar = el('input', 'cc-th-buscar'); buscar.dataset.buscar = id;
      Object.assign(buscar, {type: 'search', value: busquedas[id] || '', placeholder: 'Buscar…', ariaLabel: 'Buscar en ' + col.titulo});
      buscar.addEventListener('input', () => { if (buscar.value.trim()) busquedas[id] = buscar.value; else delete busquedas[id]; pintar(); });
      const filtrar = el('button', 'cc-th-btn' + (filtros[id] ? ' activo' : '')); filtrar.type = 'button';
      filtrar.append(icono('fa-filter')); filtrar.title = filtrar.ariaLabel = 'Filtrar ' + col.titulo;
      filtrar.addEventListener('click', e => { e.stopPropagation(); abrirFiltro(id, filtrar); });
      // Ordenar: 1.er clic de menor a mayor, 2.º de mayor a menor, 3.º quita el orden.
      const sentido = orden?.col === id ? orden.dir : 0;
      const ordenar = el('button', 'cc-th-btn' + (sentido ? ' activo' : '')); ordenar.type = 'button';
      ordenar.append(icono(sentido === 1 ? 'fa-arrow-up-short-wide' : sentido === -1 ? 'fa-arrow-down-wide-short' : 'fa-sort'));
      ordenar.title = ordenar.ariaLabel = sentido === 1 ? 'Ordenado de menor a mayor · clic: de mayor a menor'
        : sentido === -1 ? 'Ordenado de mayor a menor · clic: quitar orden' : 'Ordenar ' + col.titulo + ' de menor a mayor';
      ordenar.addEventListener('click', e => {
        e.stopPropagation();
        orden = sentido === 1 ? {col: id, dir: -1} : sentido === -1 ? null : {col: id, dir: 1};
        pintar();
      });
      fila.append(el('span', 'cc-th-nombre', col.titulo), ordenar, filtrar);
      th.append(fila, buscar, asa(id, th));
      fila.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', id); e.dataTransfer.effectAllowed = 'move'; th.classList.add('arrastrando'); });
      th.addEventListener('dragend', () => cab.querySelectorAll('.cc-th').forEach(t => t.classList.remove('arrastrando', 'soltar-antes', 'soltar-despues')));
      th.addEventListener('dragover', e => {
        e.preventDefault();
        const r = th.getBoundingClientRect(), antes = e.clientX < r.left + r.width / 2;
        th.classList.toggle('soltar-antes', antes); th.classList.toggle('soltar-despues', !antes);
      });
      th.addEventListener('dragleave', () => th.classList.remove('soltar-antes', 'soltar-despues'));
      th.addEventListener('drop', e => {
        e.preventDefault();
        const origen = e.dataTransfer.getData('text/plain');
        if (!COLUMNAS[origen] || origen === id) return pintarEncabezado();
        const antes = th.classList.contains('soltar-antes');
        columnas = columnas.filter(c => c !== origen);
        columnas.splice(columnas.indexOf(id) + (antes ? 0 : 1), 0, origen);
        guardar(); pintar();
      });
      cab.append(th);
    }
    if (foco) { const i = cab.querySelector('[data-buscar="' + foco.col + '"]'); if (i) { i.focus(); i.setSelectionRange(foco.ini, foco.fin); } }
  }

  // Filtro por columna: lista de valores de la etapa actual, como en Excel.
  function abrirFiltro(id, boton) {
    const caja = $('cc-filtro');
    if (!caja.hidden && caja.dataset.col === id) { caja.hidden = true; return; }
    const col = COLUMNAS[id], valores = [...new Set(base(id).map(col.texto))].sort((a, b) => a.localeCompare(b, 'es', {numeric: true}));
    const marcados = new Set(filtros[id] || valores);
    caja.dataset.col = id; caja.replaceChildren();
    const buscar = el('input'); Object.assign(buscar, {type: 'search', placeholder: 'Buscar en ' + col.titulo.toLowerCase()});
    const lista = el('div', 'cc-filtro-valores');
    const todos = el('label', 'cc-todos'), todosCheck = el('input'); todosCheck.type = 'checkbox'; todos.append(todosCheck, 'Seleccionar todo');
    const checks = valores.map(v => { const l = el('label'), c = el('input'); c.type = 'checkbox'; c.value = v; c.checked = marcados.has(v); l.append(c, v || '(vacío)'); return l; });
    const sincronizar = () => { const v = checks.filter(l => !l.hidden); todosCheck.checked = v.length > 0 && v.every(l => l.firstChild.checked); };
    todosCheck.addEventListener('change', () => { checks.filter(l => !l.hidden).forEach(l => { l.firstChild.checked = todosCheck.checked; }); });
    checks.forEach(l => l.firstChild.addEventListener('change', sincronizar));
    buscar.addEventListener('input', () => { const t = buscar.value.trim().toLowerCase(); checks.forEach(l => { l.hidden = t && !l.textContent.toLowerCase().includes(t); }); sincronizar(); });
    lista.append(todos, ...checks);
    if (!valores.length) lista.append(el('p', 'cc-nota', 'Sin valores en esta etapa.'));
    const limpiar = el('button', 'cc-btn', 'Limpiar'), aplicar = el('button', 'cc-btn cc-ok', 'Aplicar');
    limpiar.type = aplicar.type = 'button';
    limpiar.addEventListener('click', () => { delete filtros[id]; caja.hidden = true; pintar(); });
    aplicar.addEventListener('click', () => {
      const elegidos = checks.filter(l => l.firstChild.checked).map(l => l.firstChild.value);
      if (elegidos.length === valores.length) delete filtros[id]; else filtros[id] = elegidos;
      caja.hidden = true; pintar();
    });
    const pie = el('div', 'cc-filtro-pie'); pie.append(limpiar, aplicar);
    caja.append(buscar, lista, pie); sincronizar();
    caja.hidden = false;
    const z = escala(), r = boton.getBoundingClientRect(), alto = innerHeight / z, ancho = innerWidth / z;
    caja.style.top = Math.min(r.bottom / z + 6, alto - caja.offsetHeight - 8) + 'px';
    caja.style.left = Math.max(8, Math.min(r.left / z - 8, ancho - caja.offsetWidth - 8)) + 'px';
    buscar.focus();
  }
  document.addEventListener('click', e => { const c = $('cc-filtro'); if (!c.hidden && !c.contains(e.target)) c.hidden = true; });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') $('cc-filtro').hidden = true; });

  // Solicitudes de la etapa con el buscador general y los filtros de columna (menos `excepto`).
  function base(excepto) {
    const filas = filtrar(excepto);
    if (orden && COLUMNAS[orden.col]) {
      const col = COLUMNAS[orden.col];
      filas.sort((a, b) => (col.orden ? col.orden(a) - col.orden(b)
        : String(col.texto(a)).localeCompare(String(col.texto(b)), 'es', {numeric: true, sensitivity: 'base'})) * orden.dir || b.id - a.id);
    } else if (tab === 'pendientes') filas.sort((a, b) => COLUMNAS.responsable.texto(a).localeCompare(COLUMNAS.responsable.texto(b), 'es') || b.id - a.id);
    return filas;
  }
  // Buscador general: busca en todas las pestañas (no solo en la que se ve).
  const coincideBusqueda = s => {
    const texto = plano($('cc-buscar').value.trim());
    return !texto || plano([s.codigo, s.tecnico, s.documento, s.proyecto, s.formulario?.site, s.formulario?.wo].join(' ')).includes(texto);
  };
  function filtrar(excepto) {
    return delProyecto().filter(s => s.etapas.includes(tab)
      && coincideBusqueda(s)
      && Object.entries(filtros).every(([id, vals]) => id === excepto || vals.includes(COLUMNAS[id].texto(s)))
      && Object.entries(busquedas).every(([id, t]) => plano(COLUMNAS[id].texto(s)).includes(plano(t.trim()))));
  }
  const excel = $('cc-excel');
  function estadoEliminar() {
    if (eliminar) eliminar.disabled = eliminando || !seleccionadas.size;
  }
  eliminar?.addEventListener('click', intentar(async () => {
    const ids = [...seleccionadas];
    if (!ids.length || eliminando) return;
    eliminando = true;
    estadoEliminar();
    try {
      if (!await confirmar(ids.length === 1 ? '¿Eliminar la solicitud seleccionada?' : '¿Eliminar las ' + ids.length + ' solicitudes seleccionadas?')) return;
      const r = await fetch(eliminar.dataset.url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': excel.dataset.csrf},
        body: JSON.stringify(ids),
      });
      if (!r.ok) throw Error('No se pudieron eliminar las solicitudes. Actualiza la lista e inténtalo de nuevo.');
      const borradas = new Set(ids);
      solicitudes = solicitudes.filter(sol => !borradas.has(sol.id));
      seleccionadas.clear();
      pintar();
    } finally {
      eliminando = false;
      estadoEliminar();
    }
  }));
  let exportando = false;
  // El botón de Excel despliega dos opciones: la pestaña actual (con filtros) o todo el historial.
  const menuExportar = $('cc-exportar-menu');
  const NOMBRE_TAB = {validacion: 'Validación', deposito: 'Depósito', por_rendir: 'Por rendir', revision: 'Revisión', sustento: 'Sustentado', archivado: 'Archivado', anuladas: 'Anuladas', pendientes: 'CM-Site pendiente'};
  const cerrarExportar = () => { menuExportar.hidden = true; excel.setAttribute('aria-expanded', 'false'); };
  excel.addEventListener('click', e => {
    e.stopPropagation();
    if (!menuExportar.hidden) { cerrarExportar(); return; }
    const visibles = base().length;
    const opcionPestana = menuExportar.querySelector('[data-alcance="pestana"]');
    opcionPestana.disabled = !visibles;
    $('cc-exportar-pestana').textContent = NOMBRE_TAB[tab] + ' · ' + visibles + (visibles === 1 ? ' solicitud' : ' solicitudes');
    const todas = delProyecto().length;
    $('cc-exportar-todo').textContent = 'Todas las pestañas' + (selectorProyecto.value ? ' · ' + selectorProyecto.value : '') + ' · ' + todas + (todas === 1 ? ' solicitud' : ' solicitudes');
    menuExportar.hidden = false; excel.setAttribute('aria-expanded', 'true');
    menuExportar.querySelector('button:not(:disabled)')?.focus();
  });
  document.addEventListener('click', e => { if (!menuExportar.hidden && !menuExportar.contains(e.target)) cerrarExportar(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menuExportar.hidden) { cerrarExportar(); excel.focus(); } });
  menuExportar.querySelectorAll('.cc-exportar-opcion').forEach(opcion => opcion.addEventListener('click', () => {
    const todo = opcion.dataset.alcance === 'todo';
    cerrarExportar();
    exportar(todo ? delProyecto().map(s => s.id) : base().map(s => s.id),
      todo ? 'Caja-Chica-historial.xlsx' : 'Caja-Chica-' + NOMBRE_TAB[tab].replace(/\s+/g, '-') + '.xlsx');
  }));
  async function exportar(ids, nombre) {
    if (!ids.length) return;
    exportando = excel.disabled = true;
    try {
      const respuesta = await fetch(excel.dataset.url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': excel.dataset.csrf},
        body: JSON.stringify(ids),
      });
      if (!respuesta.ok || !respuesta.headers.get('Content-Type')?.includes('spreadsheetml')) {
        throw Error('No se pudo exportar. Vuelve a cargar Caja Chica e inténtalo de nuevo.');
      }
      const url = URL.createObjectURL(await respuesta.blob());
      const descarga = el('a');
      descarga.href = url;
      descarga.download = nombre;
      descarga.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (error) {
      alert(error.message);
    } finally {
      exportando = false;
      excel.disabled = !solicitudes.length;
    }
  }
  function pintar() {
    pintarProyecto();
    document.querySelectorAll('.cc-tab').forEach(b => { b.classList.toggle('activa', b.dataset.tab === tab); b.setAttribute('aria-selected', b.dataset.tab === tab); });
    // Con el buscador lleno, cada pestaña cuenta solo lo que coincide: así se ve dónde está el registro.
    const buscados = delProyecto().filter(coincideBusqueda);
    document.querySelectorAll('[data-cuenta]').forEach(c => { c.textContent = buscados.filter(s => s.etapas.includes(c.dataset.cuenta)).length; });
    // Plata acumulada de cada etapa: suma del total solicitado de sus solicitudes.
    document.querySelectorAll('[data-plata]').forEach(p => {
      const suma = delProyecto().filter(s => s.etapas.includes(p.dataset.plata)).reduce((t, s) => t + Number(importeEtapa(s, p.dataset.plata)), 0);
      p.textContent = 'S/ ' + suma.toLocaleString('es-PE', {minimumFractionDigits: suma >= 1000 || !suma ? 0 : 2, maximumFractionDigits: suma >= 1000 ? 0 : 2});
      p.title = 'Total acumulado: ' + dinero(suma);
    });
    pintarEncabezado();
    const lista = $('cc-lista'); lista.replaceChildren();
    const visibles = base();
    const idsVisibles = new Set(visibles.map(sol => sol.id));
    for (const id of seleccionadas) if (!idsVisibles.has(id)) seleccionadas.delete(id);
    estadoEliminar();
    excel.disabled = exportando || !solicitudes.length;
    if (!visibles.length) {
      const hayFiltros = Object.keys(filtros).length || Object.keys(busquedas).length || $('cc-buscar').value.trim();
      lista.append(el('p', 'cc-vacio', hayFiltros && solicitudes.some(s => s.etapas.includes(tab)) ? 'Ninguna solicitud coincide con los filtros.' : 'No hay solicitudes en esta etapa.'));
      return;
    }
    for (const sol of visibles) {
      const s = el('div', 'cc-card cc-resumen cc-fila-solicitud');
      if (puedeEliminar) {
        const celda = el('span', 'cc-seleccion');
        const check = Object.assign(el('input'), {type: 'checkbox', checked: seleccionadas.has(sol.id)});
        check.setAttribute('aria-label', 'Seleccionar ' + sol.codigo);
        check.addEventListener('change', () => {
          if (check.checked) seleccionadas.add(sol.id);
          else seleccionadas.delete(sol.id);
          estadoEliminar();
        });
        celda.append(check);
        s.append(celda);
      }
      const controles = accionesRapidas(sol);
      controles.classList.add('cc-col-acciones');
      s.append(controles);
      for (const id of columnas) { const col = COLUMNAS[id]; s.append(col.celda ? col.celda(sol) : el('span', col.clase || null, col.texto(sol))); }
      lista.append(s);
    }
  }
  async function cargar() {
    const r = await fetch('/api/caja-chica/solicitudes'); const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('cc-lista').replaceChildren(el('p', 'cc-alerta', j.error || 'No se pudo cargar Caja Chica.')); return; }
    solicitudes = j.solicitudes; pintar();
  }
  // Los filtros de columna se aplican a la etapa elegida: al cambiar de etapa se limpian.
  document.querySelectorAll('.cc-tab').forEach(b => b.addEventListener('click', () => { tab = b.dataset.tab; filtros = {}; busquedas = {}; seleccionadas.clear(); try { localStorage.setItem('cc-tab', tab); } catch (_) {} pintar(); }));
  $('cc-buscar').addEventListener('input', () => {
    // Si en la pestaña actual no hay coincidencias, salta a la primera pestaña donde está el registro.
    if ($('cc-buscar').value.trim()) {
      const buscados = delProyecto().filter(coincideBusqueda);
      if (!buscados.some(s => s.etapas.includes(tab))) {
        const destino = [...document.querySelectorAll('.cc-tab')].map(b => b.dataset.tab).find(t => buscados.some(s => s.etapas.includes(t)));
        if (destino) { tab = destino; filtros = {}; busquedas = {}; seleccionadas.clear(); }
      }
    }
    pintar();
  });
  selectorProyecto.addEventListener('change', () => { seleccionadas.clear(); pintar(); });

  // Engranaje: menú de opciones. Para agregar una opción, un botón con data-accion en la
  // plantilla y su caso aquí.
  const ajustes = $('cc-ajustes-btn'), menu = $('cc-ajustes-menu');
  const cerrarMenu = () => { menu.hidden = true; ajustes.setAttribute('aria-expanded', 'false'); };
  ajustes.addEventListener('click', e => {
    e.stopPropagation();
    const abrir = menu.hidden; menu.hidden = !abrir; ajustes.setAttribute('aria-expanded', String(abrir));
    if (abrir) menu.querySelector('button:not(:disabled)')?.focus();
  });
  menu.addEventListener('click', e => {
    const opcion = e.target.closest('[data-accion]'); if (!opcion) return;
    e.stopPropagation(); cerrarMenu();
    if (opcion.dataset.accion === 'catalogo') {
      location.assign(opcion.dataset.url);
      return;
    }
    if (opcion.dataset.accion === 'limpiar') {
      filtros = {}; busquedas = {}; orden = null; $('cc-buscar').value = ''; selectorProyecto.value = ''; $('cc-filtro').hidden = true;
    } else if (opcion.dataset.accion === 'restablecer') {
      columnas = Object.keys(COLUMNAS); anchos = {}; guardar();
    }
    pintar();
  });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) cerrarMenu(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menu.hidden) { cerrarMenu(); ajustes.focus(); } });
  pintarEncabezado();
  cargar();
})();
