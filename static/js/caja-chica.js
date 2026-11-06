/* Caja Chica · gestión en Nucleus: validar, depositar y revisar cada ítem. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ESTADOS = {PENDIENTE: 'Pendiente', VALIDADO: 'Validado', DEPOSITADO: 'Depositado', POR_DEVOLVER: 'Por devolver',
                   ARCHIVADO: 'Archivado', RECHAZADO: 'Rechazado · con el técnico', ANULADO: 'Anulado'};
  // Una solicitud que volvió a una etapa anterior se marca con su motivo de retorno.
  const RETORNO = {desde_deposito: ['Rechazado en depósito', 'cc-retorno'], reenviada: ['Corregida y reenviada', 'cc-reenviada']};
  const ITEM = {POR_RENDIR: 'Por rendir', EN_REVISION: 'En revisión', APROBADO: 'Aprobado', RECHAZADO: 'Rechazado'};
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const avisar = m => (window.nucleusAlert || alert)(m);
  const confirmar = async m => window.nucleusConfirm ? window.nucleusConfirm(m) : confirm(m);
  const permisos = document.querySelector('[data-gestionar]').dataset;
  const puedeGestionar = permisos.gestionar === 'si';
  const puedeEliminar = permisos.eliminar === 'si';
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
    if (['editar', 'documentos'].includes(nombre)) opciones.headers = {...opciones.headers, 'X-CSRF-Token': $('cc-excel').dataset.csrf};
    const r = await fetch('/api/caja-chica/' + sol.id + '/' + nombre, opciones);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(j.error || 'No se pudo completar la acción.');
    const i = solicitudes.findIndex(s => s.id === sol.id);
    if (i >= 0) solicitudes[i] = j.solicitud;
    pintar();
    if (dialogo.open && solicitudAbierta === sol.id && j.solicitud) {
      if (nombre === 'depositar') dialogo.close();
      else verDetalle(j.solicitud);
    }
  }
  const intentar = fn => async (...a) => { try { await fn(...a); } catch (e) { avisar(e.message); } };
  function boton(texto, clase, fn) { const b = el('button', 'cc-btn ' + clase, texto); b.type = 'button'; b.addEventListener('click', async () => { b.disabled = true; try { await fn(); } finally { b.disabled = false; } }); return b; }
  function conMotivo(sol, nombre, pregunta, extra = {}) {
    return intentar(async () => { const motivo = prompt(pregunta); if (motivo === null) return; await accion(sol, nombre, {...extra, motivo}); });
  }
  function foto(sol, nombre, texto) { const a = el('a', 'cc-foto', texto); a.href = '/form-pruebas/caja-chica/foto/' + sol.id + '/' + nombre; a.target = '_blank'; a.rel = 'noopener'; return a; }

  function botonRapido(sol, etiqueta, clase, simbolo, ejecutar) {
    const b = boton('', 'cc-rapida ' + clase, ejecutar);
    b.title = etiqueta;
    b.setAttribute('aria-label', etiqueta + ' ' + sol.codigo);
    b.append(icono(simbolo));
    b.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); });
    return b;
  }
  function accionesRapidas(sol) {
    const caja = el('span', 'cc-acciones-rapidas');
    if (tab === 'deposito') {
      if (puedeGestionar && sol.estado === 'VALIDADO') {
        caja.append(botonRapido(sol, 'Depositar', 'cc-ok', 'fa-money-bill-transfer', () => verDetalle(sol)));
      }
      return caja;
    }
    if (puedeGestionar && sol.estado === 'PENDIENTE') {
      caja.append(botonRapido(sol, 'Validar', 'cc-ok', 'fa-check', intentar(async () => {
        if (await confirmar('¿Validar ' + sol.codigo + ' por ' + dinero(sol.total) + '?')) await accion(sol, 'validar');
      })));
    }
    if (puedeGestionar && ['PENDIENTE', 'VALIDADO'].includes(sol.estado)) {
      const destino = sol.estado === 'VALIDADO' ? 'Validación' : 'el técnico';
      caja.append(botonRapido(sol, 'Rechazar', 'cc-rechazar', 'fa-xmark',
        conMotivo(sol, 'rechazar', 'Motivo del rechazo (vuelve a ' + destino + '):')));
    }
    if (puedeGestionar && ['PENDIENTE', 'VALIDADO', 'RECHAZADO'].includes(sol.estado)) {
      caja.append(botonRapido(sol, 'Anular', 'cc-no', 'fa-ban', conMotivo(sol, 'anular', 'Motivo de la anulación:')));
    }
    return caja;
  }

  function acciones(sol) {
    const caja = el('div', 'cc-acciones');
    if (sol.estado === 'RECHAZADO') caja.append(el('span', 'cc-nota', 'Devuelta al técnico: cuando la corrija y reenvíe vuelve a esta etapa.'));
    if (sol.estado === 'POR_DEVOLVER' && sol.devolucion_foto) {
      caja.append(el('span', 'cc-nota', 'Devolución de ' + dinero(sol.diferencia) + ':'), foto(sol, sol.devolucion_foto, 'ver foto'),
                  boton('Aceptar devolución y archivar', 'cc-ok', intentar(() => accion(sol, 'devolucion', {aceptar: true}))),
                  boton('Rechazar devolución', 'cc-no', conMotivo(sol, 'devolucion', 'Motivo del rechazo de la devolución:', {aceptar: false})));
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
                       boton('Rechazar', 'cc-no', conMotivo(sol, 'revisar_item', 'Ítem ' + item.numero + ': ¿qué debe corregir el técnico?', {item: item.id, aprobar: false})));
      }
      const concepto = el('td', null, [item.tipo_gasto, item.tipo_presupuesto, item.descripcion].filter(Boolean).join(' · '));
      if (item.correo_validador) concepto.append(el('div', null, 'Correo de validación: ' + item.correo_validador));
      tr.append(el('td', null, String(item.numero)), concepto,
                el('td', 'cc-num', dinero(item.monto)), el('td', null, item.comprobante ? item.comprobante + ' · RUC ' + item.ruc : '—'),
                el('td', 'cc-num', item.monto_gastado ? dinero(item.monto_gastado) : '—'), fotos, estado, botones);
      tabla.append(tr);
    }
    if (['DEPOSITADO', 'POR_DEVOLVER', 'ARCHIVADO'].includes(sol.estado)) d.append(tabla);
    if (sol.deposito_foto) { const p = el('p', 'cc-nota', 'Depósito: '); p.append(foto(sol, sol.deposito_foto, 'ver foto')); d.append(p); }
    if (sol.devolucion_foto && sol.estado === 'ARCHIVADO') { const p = el('p', 'cc-nota', 'Devolución: '); p.append(foto(sol, sol.devolucion_foto, 'ver foto')); d.append(p); }
    const controles = acciones(sol);
    if (controles.hasChildNodes()) d.append(controles);
    return d;
  }

  function editorSolicitud(sol, documentos) {
    const form = el('form', 'cc-editar-solicitud');
    form.id = 'cc-solicitud-editor';
    function seccion(titulo) {
      const grupo = el('fieldset');
      grupo.append(el('legend', null, titulo));
      form.append(grupo);
      return grupo;
    }
    const tecnico = seccion('Datos del técnico');
    const datosSolicitud = seccion('Datos de la solicitud');
    function campo(titulo, control, contenedor) {
      const etiqueta = el('label', null, titulo);
      etiqueta.append(control);
      contenedor.append(etiqueta);
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
    campo('Técnico', Object.assign(texto(sol.tecnico, 150), {readOnly: true}), tecnico);
    campo('Documento', Object.assign(texto(sol.documento, 20), {readOnly: true}), tecnico);
    const proyecto = campo('Proyecto', selector(configuracion.proyectos, sol.proyecto), tecnico);
    const motivo = campo('Motivo de la solicitud', Object.assign(el('textarea'), {value: sol.motivo, rows: 3, maxLength: 500, required: true}), datosSolicitud);
    motivo.parentElement.classList.add('cc-campo-ancho');
    const controles = sol.items.map(item => {
      const grupo = el('fieldset', 'cc-campo-ancho cc-concepto-editar');
      grupo.append(el('legend', null, 'Concepto ' + item.numero));
      datosSolicitud.append(grupo);
      const tipo = campo('Concepto', selector([], item.tipo_gasto), grupo);
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
      const descripcion = campo('Descripción', texto(item.descripcion, 300), grupo);
      const monto = campo('Monto (S/)', Object.assign(texto(item.monto, 16, true), {inputMode: 'decimal'}), grupo);
      monto.dataset.monto = '';
      const correo = campo('Correo de quien valida', Object.assign(texto(item.correo_validador, 254), {type: 'email'}), grupo);
      return () => ({tipo_gasto: tipo.value, descripcion: descripcion.value, monto: monto.value, correo_validador: correo.value});
    });
    const total = el('output', 'cc-num');
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
    datosSolicitud.append(totalSolicitud(total));
    datosSolicitud.addEventListener('input', e => { if (e.target.hasAttribute('data-monto')) actualizarTotal(); });
    const deposito = seccion('Datos del depósito');
    const banco = campo('Banco', selector(configuracion.bancos, sol.banco), deposito);
    const cuenta = campo('Número de cuenta', texto(sol.cuenta, 40, true), deposito);
    const validacion = seccion('Documentos de validación');
    const cotizacion = documentos.elements.namedItem('cotizacion');
    validacion.append(cotizacion.closest('label'), documentos.querySelector('.cc-cotizacion-control'));
    actualizarTotal();
    const adjunto = campo('Adjuntar correo de validación', documentos.elements.namedItem('correo'), validacion);
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
      if (adjunto.files.length) datos.set('correo', adjunto.files[0]);
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
    solicitud.append(el('h4', null, 'Conceptos solicitados'));
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

  function formularioDocumentos(sol) {
    const form = el('form', 'cc-editar-solicitud cc-documentos-validacion');
    form.id = 'cc-solicitud-documentos';
    const grupo = el('fieldset');
    grupo.append(el('legend', null, 'Documentos de validación'));
    const cotizacion = el('label', null, 'Número de cotización');
    const entrada = Object.assign(el('input'), {
      name: 'cotizacion', value: sol.revision?.cotizacion || '', maxLength: 80,
      autocomplete: 'off', placeholder: 'Busca por número de cotización',
    });
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
      const tarjetas = el('dl', 'cc-cotizacion-importes');
      const montos = [
        ['Cotizado · suma de valores unitarios (' + seleccion.items + (seleccion.items === 1 ? ' ítem)' : ' ítems)'), cotizado],
        ['Otras solicitudes activas', otras],
        ['Esta solicitud', actual],
        ['Total solicitado acumulado', acumulado],
        ['Saldo / exceso', saldo],
      ];
      for (const [etiqueta, monto] of montos) {
        const tarjeta = el('div');
        tarjeta.append(el('dt', null, etiqueta), el('dd', null, monto === null ? '—' : dinero(monto / 100)));
        tarjetas.append(tarjeta);
      }
      control.replaceChildren(mensaje, tarjetas, el('p', 'cc-nota',
        'El cotizado suma los valores unitarios sin cantidad ni FEE. El acumulado considera las solicitudes activas de Caja Chica vinculadas a esta cotización. El resultado es informativo.'));
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
    const correo = el('label', null, 'Adjuntar correo de validación');
    correo.append(Object.assign(el('input'), {
      type: 'file', name: 'correo', accept: '.pdf,.eml,.msg,.jpg,.jpeg,.png,.webp',
    }));
    const guardar = $('cc-solicitud-guardar');
    const editar = $('cc-solicitud-editar');
    const error = el('p', 'cc-alerta cc-campo-ancho');
    error.hidden = true;
    error.setAttribute('role', 'alert');
    grupo.append(cotizacion, correo, control, error);
    form.append(grupo);
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

  // Panel de depósito: va arriba del detalle, con el botón de confirmar en su cabecera.
  function formularioDeposito(sol) {
    const form = el('form', 'cc-deposito-panel');
    const formulario = sol.formulario || {};
    const cabecera = el('div', 'cc-deposito-cabecera');
    const titulo = el('div', 'cc-deposito-titulo');
    const bolsa = el('span', 'cc-deposito-bolsa');
    bolsa.append(icono('fa-sack-dollar'));
    const textos = el('div');
    textos.append(el('small', null, 'Monto a depositar'), el('strong', 'cc-deposito-monto', dinero(sol.total)));
    titulo.append(bolsa, textos);
    // Botón redondo solo con ícono; el texto va en la ayuda y para lectores de pantalla.
    const enviar = el('button', 'cc-deposito-enviar');
    enviar.type = 'submit';
    enviar.title = 'Confirmar depósito';
    enviar.setAttribute('aria-label', enviar.title);
    enviar.append(icono('fa-sack-dollar'));
    cabecera.append(titulo, enviar);

    // Datos para depositar, con copiar al portapapeles.
    const tarjeta = el('div', 'cc-deposito-tarjeta');
    const subtitulo = el('h4', 'cc-deposito-subtitulo');
    subtitulo.append(icono('fa-building-columns'), ' Datos para el depósito');
    const datos = el('dl', 'cc-deposito-datos');
    const filas = [['Banco', sol.banco], ['CCI / cuenta', sol.cuenta], ['Titular', formulario.titular || sol.tecnico]];
    if (formulario.tipo_billetera && formulario.tipo_billetera !== 'No aplica') filas.push([formulario.tipo_billetera, formulario.numero_billetera]);
    for (const [nombre, valor] of filas) {
      if (!valor) continue;
      const fila = el('div', 'cc-deposito-fila');
      const dd = el('dd');
      dd.append(el('span', nombre === 'CCI / cuenta' ? 'cc-deposito-cci' : null, valor));
      const copiar = el('button', 'cc-deposito-copiar');
      copiar.type = 'button';
      copiar.title = 'Copiar ' + nombre.toLowerCase();
      copiar.setAttribute('aria-label', copiar.title);
      copiar.append(icono('fa-copy'));
      copiar.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(valor); copiar.replaceChildren(icono('fa-check')); }
        catch (_) { copiar.replaceChildren(icono('fa-xmark')); }
        setTimeout(() => copiar.replaceChildren(icono('fa-copy')), 1500);
      });
      fila.append(el('dt', null, nombre), dd, copiar);
      datos.append(fila);
    }
    const nota = el('p', 'cc-deposito-nota');
    nota.append(icono('fa-clock'), ' La fecha y hora se registran solas al confirmar.');
    tarjeta.append(subtitulo, datos, nota);

    const monto = Object.assign(el('input'), {type: 'hidden', name: 'monto', value: sol.total});

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

    const error = el('p', 'cc-alerta');
    error.setAttribute('role', 'alert');
    error.hidden = true;
    const cuerpo = el('div', 'cc-deposito-cuerpo');
    const lateral = el('div', 'cc-deposito-lateral');
    lateral.append(tarjeta);
    cuerpo.append(lateral, zona);
    form.append(cabecera, error, cuerpo, monto);
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

  function verDetalle(sol) {
    solicitudAbierta = sol.id;
    $('cc-solicitud-titulo').textContent = [sol.codigo, sol.tecnico, sol.proyecto].join(' · ');
    const contenido = $('cc-solicitud-contenido');
    const editar = $('cc-solicitud-editar');
    const guardar = $('cc-solicitud-guardar');
    const enDeposito = tab === 'deposito' && sol.estado === 'VALIDADO';
    editar.hidden = guardar.hidden = enDeposito;
    if (enDeposito) {
      contenido.replaceChildren(datosEnviados(sol, 'Datos de la solicitud'));
      if (puedeGestionar) contenido.prepend(formularioDeposito(sol));
      if (!dialogo.open) dialogo.showModal();
      return;
    }
    contenido.replaceChildren(datosEnviados(sol.envio_tecnico || sol, sol.envio_tecnico && 'Datos enviados por el técnico'));
    if (sol.envio_tecnico) contenido.append(datosEnviados(sol, 'Datos revisados por gestión'));
    const revision = sol.revision || {};
    if (revision.cotizacion) contenido.append(el('p', null, 'Cotización: ' + revision.cotizacion));
    if (revision.archivo) {
      const enlace = el('a', 'cc-foto', 'Descargar correo de validación');
      enlace.href = '/api/caja-chica/' + sol.id + '/correo-validacion';
      contenido.append(enlace);
    }
    if (sol.items.some(i => i.requiere_correo) && !revision.archivo) contenido.append(el('p', 'cc-alerta', 'Falta adjuntar el correo de validación.'));
    if (sol.items.some(i => i.requiere_cotizacion) && !revision.cotizacion) contenido.append(el('p', 'cc-alerta', 'Falta el número de cotización.'));
    editar.disabled = !puedeGestionar || sol.estado !== 'PENDIENTE';
    const documentos = editar.disabled ? null : formularioDocumentos(sol);
    guardar.setAttribute('form', 'cc-solicitud-documentos');
    guardar.disabled = !documentos;
    editar.onclick = () => {
      const form = editorSolicitud(sol, documentos);
      documentos?.remove();
      contenido.prepend(form);
      editar.disabled = true;
      guardar.setAttribute('form', form.id);
      guardar.disabled = false;
      form.querySelector('select').focus();
    };
    const seguimiento = detalle(sol);
    if (seguimiento.hasChildNodes()) contenido.append(seguimiento);
    if (documentos) contenido.append(documentos);
    if (!dialogo.open) dialogo.showModal();
  }
  // ── Tabla: columnas que se filtran y se mueven arrastrando ──
  const estadoDe = s => RETORNO[s.retorno] || [ESTADOS[s.estado] || s.estado, 'cc-' + s.estado.toLowerCase()];
  const creado = s => new Date(s.creado + 'Z');
  const COLUMNAS = {
    codigo:   {titulo: 'Código depósito', ancho: 'minmax(145px, 1fr)', texto: s => s.codigo, celda: s => {
      const enlace = el('a', 'cc-codigo-link', s.codigo);
      enlace.href = '#solicitud-' + s.id;
      enlace.addEventListener('click', e => { e.preventDefault(); verDetalle(s); });
      return enlace;
    }},
    tecnico:  {titulo: 'Técnico · Documento', ancho: 'minmax(180px, 2.4fr)', texto: s => s.tecnico + ' · ' + s.documento},
    proyecto: {titulo: 'Proyecto', ancho: 'minmax(100px, .8fr)', texto: s => s.proyecto, celda: s => {
      const nombres = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};
      const nombre = nombres[s.proyecto];
      return el('span', nombre ? 'project-badge project-badge--' + s.proyecto.toLowerCase() : null, nombre || s.proyecto);
    }},
    site: {titulo: 'Nombre del site', ancho: 'minmax(150px, 1fr)', texto: s => s.formulario?.site || '—'},
    wo: {titulo: 'N.º CM / PM / PLM', ancho: 'minmax(145px, 1fr)', texto: s => s.formulario?.wo || '—'},
    gasto: {titulo: 'Tipo de gasto', ancho: 'minmax(190px, 1.4fr)',
            texto: s => [...new Set(s.items.map(item => item.tipo_gasto))].join(' · ') || '—'},
    responsable: {titulo: 'Responsable de validación', ancho: 'minmax(190px, 1.3fr)',
                  texto: s => s.formulario?.responsable_validacion || '—'},
    estado:   {titulo: 'Estado', ancho: 'minmax(180px, 1.3fr)', texto: s => estadoDe(s)[0],
               celda: s => { const [t, c] = estadoDe(s); return el('span', 'cc-chip ' + c, t); }},
    fecha:    {titulo: 'Fecha / Avance', ancho: 'minmax(140px, 1.1fr)', clase: 'cc-avance',
               texto: s => s.estado === 'DEPOSITADO' ? s.avance : creado(s).toLocaleDateString('es-PE')},
    total:    {titulo: 'Total', ancho: 'minmax(110px, .8fr)', num: true, texto: s => dinero(s.total),
               celda: s => el('strong', 'cc-num', dinero(s.total))},
  };
  // El orden y ancho de las columnas se recuerdan en este navegador.
  let columnas = Object.keys(COLUMNAS), filtros = {}, busquedas = {}, anchos = {};
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
      fila.append(el('span', 'cc-th-nombre', col.titulo), filtrar);
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
    const texto = $('cc-buscar').value.trim().toLowerCase();
    return solicitudes.filter(s => s.etapas.includes(tab)
      && (!texto || [s.codigo, s.tecnico, s.documento, s.proyecto].join(' ').toLowerCase().includes(texto))
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
  excel.addEventListener('click', async () => {
    const ids = base().map(s => s.id);
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
      descarga.download = 'Caja-Chica.xlsx';
      descarga.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (error) {
      alert(error.message);
    } finally {
      exportando = false;
      excel.disabled = !base().length;
    }
  });
  function pintar() {
    document.querySelectorAll('.cc-tab').forEach(b => { b.classList.toggle('activa', b.dataset.tab === tab); b.setAttribute('aria-selected', b.dataset.tab === tab); });
    document.querySelectorAll('[data-cuenta]').forEach(c => { c.textContent = solicitudes.filter(s => s.etapas.includes(c.dataset.cuenta)).length; });
    // Plata acumulada de cada etapa: suma del total solicitado de sus solicitudes.
    document.querySelectorAll('[data-plata]').forEach(p => {
      const suma = solicitudes.filter(s => s.etapas.includes(p.dataset.plata)).reduce((t, s) => t + Number(s.total || 0), 0);
      p.textContent = 'S/ ' + suma.toLocaleString('es-PE', {minimumFractionDigits: suma >= 1000 || !suma ? 0 : 2, maximumFractionDigits: suma >= 1000 ? 0 : 2});
      p.title = 'Total acumulado: ' + dinero(suma);
    });
    pintarEncabezado();
    const lista = $('cc-lista'); lista.replaceChildren();
    const visibles = base();
    const idsVisibles = new Set(visibles.map(sol => sol.id));
    for (const id of seleccionadas) if (!idsVisibles.has(id)) seleccionadas.delete(id);
    estadoEliminar();
    excel.disabled = exportando || !visibles.length;
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
  $('cc-buscar').addEventListener('input', pintar);

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
      filtros = {}; busquedas = {}; $('cc-buscar').value = ''; $('cc-filtro').hidden = true;
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
