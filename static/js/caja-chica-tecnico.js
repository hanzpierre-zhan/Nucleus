/* Caja Chica · portal del técnico: solicitar por ítems y rendir cada ítem. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = '/form-pruebas/caja-chica';
  const ESTADOS = {PENDIENTE: 'En validación', VALIDADO: 'Por depositar', DEPOSITADO: 'Por rendir',
                   POR_DEVOLVER: 'Falta la devolución', ARCHIVADO: 'Archivado', RECHAZADO: 'Rechazado: corrige y reenvía', ANULADO: 'Anulado'};
  const ITEM = {POR_RENDIR: 'Por rendir', EN_REVISION: 'En revisión', APROBADO: 'Aprobado', RECHAZADO: 'Rechazado', DEVUELTO: 'Se devuelve'};
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const numero = v => { const t = String(v || '').replace(/\s/g, '').replace(/,(?=\d{3}(\D|$))/g, '').replace(',', '.'); return /^\d+(\.\d{1,2})?$/.test(t) ? Number(t) : NaN; };
  let datos = null, corrigiendo = null;  // corrigiendo = solicitud rechazada que se está reenviando

  async function api(ruta, opciones = {}, prefijo = base) {
    const r = await fetch(prefijo + ruta, {credentials: 'same-origin', ...opciones, headers: {'X-CSRF-Token': $('csrf').value, ...(opciones.headers || {})}});
    let j; try { j = await r.json(); } catch { throw Error('No se pudo leer la respuesta. Revisa tu conexión.'); }
    if (r.status === 401 || (r.status === 403 && j.codigo === 'CAMBIAR_CLAVE')) { location.href = '/form-pruebas/'; throw Error(j.error); }
    if (!r.ok) throw Error(j.error || 'No se pudo completar el envío.');
    return j;
  }
  function ver(id) { document.querySelectorAll('.view').forEach(v => { v.hidden = v.id !== id; }); window.scrollTo({top: 0, behavior: 'smooth'}); }
  async function enviando(boton, caja, fn) {
    const texto = boton.textContent; boton.disabled = true; boton.textContent = 'Enviando…'; caja.hidden = true;
    try { await fn(); } catch (e) { caja.textContent = e.message; caja.hidden = false; caja.focus(); }
    finally { boton.disabled = false; boton.textContent = texto; }
  }

  // ── Lista de solicitudes ──
  function foto(sid, nombre, texto) { const a = el('a', 'cc-foto', texto); a.href = base + '/foto/' + sid + '/' + nombre; a.target = '_blank'; a.rel = 'noopener'; return a; }
  // Casilla de foto: toca para elegir o tomar la foto, con vista previa.
  function casillaFoto(nombre, titulo, ayuda, varias = false) {
    const casilla = el('label', 'cc-slot');
    const input = el('input');
    Object.assign(input, {type: 'file', name: nombre, accept: 'image/*', multiple: varias});
    const vista = el('img'); vista.alt = ''; vista.hidden = true;
    const texto = el('span', 'cc-slot-texto');
    texto.append(el('span', 'cc-slot-icono', '📷'), el('strong', null, titulo), el('small', null, ayuda));
    casilla.append(input, vista, texto);
    input.addEventListener('change', () => {
      const archivo = input.files[0];
      casilla.classList.toggle('lleno', !!archivo);
      vista.hidden = !archivo;
      if (vista.src) URL.revokeObjectURL(vista.src);
      if (archivo) vista.src = URL.createObjectURL(archivo);
      texto.querySelector('small').textContent = archivo
        ? (input.files.length > 1 ? input.files.length + ' fotos' : 'Toca para cambiarla') : ayuda;
    });
    return {casilla, input};
  }
  function formRendir(sol, item) {
    const form = el('form', 'cc-rendir'); form.noValidate = true;
    const campo = (nombre, titulo, modo, ejemplo, largo) => {
      const id = 'r' + item.id + '-' + nombre, label = el('label', null, titulo), input = el('input');
      label.htmlFor = id; Object.assign(input, {id, name: nombre, inputMode: modo, placeholder: ejemplo, required: true, maxLength: largo});
      form.append(label, input);
      return input;
    };
    const ruc = campo('ruc', 'RUC del comprobante', 'numeric', '20123456789', 11);
    // Al escribir los 11 dígitos se completa la razón social (openruc / padrón).
    const razon = el('p', 'cc-razon'); razon.hidden = true; razon.setAttribute('aria-live', 'polite');
    const razonOculta = Object.assign(el('input'), {type: 'hidden', name: 'razon_social'});
    form.append(razon, razonOculta);
    let consulta;
    ruc.addEventListener('input', async () => {
      consulta?.abort(); razonOculta.value = '';
      razon.hidden = !/^[0-9]{11}$/.test(ruc.value); razon.className = 'cc-razon';
      if (razon.hidden) return;
      const actual = consulta = new AbortController();
      razon.textContent = 'Consultando RUC…';
      try {
        const r = await api('/ruc/' + ruc.value, {signal: actual.signal}, '/form-pruebas');
        if (actual.signal.aborted) return;
        if (r.resultado === 'encontrado') {
          razonOculta.value = r.razon_social;
          razon.textContent = r.razon_social + (r.activo ? ' · Activo' : ' · No activo');
          razon.classList.add(r.activo ? 'ok' : 'alerta');
        } else {
          razon.textContent = r.resultado === 'no_encontrado' ? 'RUC no encontrado. Revisa los dígitos.' : 'Consulta de RUC no disponible ahora.';
          razon.classList.add('alerta');
        }
      } catch { if (!actual.signal.aborted) { razon.textContent = 'No se pudo consultar el RUC.'; razon.classList.add('alerta'); } }
    });
    campo('comprobante', 'N.º de boleta o factura', 'text', 'F001-000123', 40);
    const gastado = campo('monto_gastado', 'Monto gastado (S/)', 'decimal', item.monto, 12);
    // Si gasta menos de lo solicitado, el saldo se acumula solo en la devolución.
    const saldo = el('p', 'cc-item-saldo'); saldo.hidden = true; saldo.setAttribute('aria-live', 'polite');
    gastado.addEventListener('input', () => {
      const valor = Number(gastado.value.replace(',', '.'));
      const resto = Math.round((Number(item.monto) - valor) * 100) / 100;
      saldo.hidden = !(gastado.value && Number.isFinite(valor) && valor >= 0 && resto > 0);
      saldo.textContent = '↩ ' + dinero(resto) + ' pasa a tu devolución';
    });
    form.append(saldo);
    const boleta = casillaFoto('fotos', 'Boleta / factura', 'Foto del comprobante', true);
    const evidencia = casillaFoto('evidencia', 'Evidencia del gasto', 'Foto del uso');
    const fotos = el('div', 'cc-slots'); fotos.append(boleta.casilla, evidencia.casilla);
    const error = el('div', 'error'); error.setAttribute('role', 'alert'); error.tabIndex = -1; error.hidden = true;
    const boton = el('button', 'primary wide', item.tipo_gasto ? 'Rendir ' + item.tipo_gasto : 'Rendir'); boton.type = 'submit';
    form.append(fotos, error, boton);
    form.addEventListener('submit', e => { e.preventDefault(); enviando(boton, error, async () => {
      if (!boleta.input.files.length) throw Error('Adjunta la foto de la boleta o factura.');
      if (boleta.input.files.length > 5) throw Error('Adjunta como máximo 5 fotos de la boleta.');
      if (!evidencia.input.files.length) throw Error('Adjunta la foto de la evidencia del gasto.');
      await api('/' + sol.id + '/item/' + item.id + '/rendir', {method: 'POST', body: new FormData(form)});
      await recargar(sol);
    }); });
    return form;
  }
  // Lo que un ítem suma a la devolución: todo si se devuelve, o lo no gastado si ya se rindió.
  function saldoItem(item) {
    if (item.estado === 'DEVUELTO') return Number(item.monto || 0);
    if (!['EN_REVISION', 'APROBADO'].includes(item.estado)) return 0;
    return Math.max(0, Math.round((Number(item.monto || 0) - Number(item.monto_gastado || 0)) * 100) / 100);
  }
  function formDevolucion(sol) {
    const form = el('form', 'cc-rendir'); form.noValidate = true;
    const enRevision = sol.items.some(i => i.estado === 'EN_REVISION');
    const aprobado = sol.items.filter(i => ['APROBADO', 'EN_REVISION'].includes(i.estado)).reduce((t, i) => t + Number(i.monto_gastado || 0), 0);
    const calculo = el('dl', 'cc-calculo');
    const fila = (a, b, clase) => { const d = el('div', clase || null); d.append(el('dt', null, a), el('dd', null, b)); calculo.append(d); };
    fila('Depositado', dinero(sol.deposito_monto || sol.total));
    fila(enRevision ? 'Gastado (rendido)' : 'Gastado y aprobado', '− ' + dinero(aprobado));
    // Qué suma la devolución, ítem por ítem.
    for (const item of sol.items.filter(i => saldoItem(i) > 0)) {
      fila('↩ ' + item.tipo_gasto + (item.estado === 'DEVUELTO' ? ' (completo)' : ' (saldo)'), dinero(saldoItem(item)), 'detalle');
    }
    fila('Debes devolver', dinero(sol.diferencia), 'total');
    const ultimo = sol.historial?.at(-1);
    form.append(el('h3', 'cc-devolucion-titulo', 'Devolución del saldo'));
    if (ultimo?.accion === 'rechazar devolución') {
      const motivo = el('p', 'cc-item-motivo'); motivo.append(el('strong', null, 'Devolución rechazada: '), ultimo.motivo || 'Sin motivo');
      form.append(motivo, el('p', 'hint', 'Vuelve a subir la captura correcta.'));
    }
    form.append(calculo,
      el('p', 'hint', 'Devuelve el importe indicado y adjunta el comprobante. La devolución quedará pendiente de revisión.'));
    const monto = el('input'); Object.assign(monto, {name: 'monto', value: sol.diferencia, readOnly: true, type: 'hidden'});
    const foto = casillaFoto('foto', 'Adjuntar comprobante de devolución', 'Captura de la transferencia');
    const archivo = foto.input;
    const error = el('div', 'error'); error.hidden = true; error.tabIndex = -1;
    const boton = el('button', 'primary wide', 'Enviar devolución a revisión'); boton.type = 'submit';
    form.classList.add('cc-devolucion');
    form.append(monto, foto.casilla, error, boton);
    form.addEventListener('submit', e => { e.preventDefault(); enviando(boton, error, async () => {
      if (!archivo.files.length) throw Error('Adjunta la foto del depósito de devolución.');
      await api('/' + sol.id + '/devolucion', {method: 'POST', body: new FormData(form)}); await recargar(sol);
    }); });
    return form;
  }
  const fechaLima = new Intl.DateTimeFormat('es-PE', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Lima'
  });
  // Lo que falta: ítems por rendir, o el saldo a devolver cuando ya se rindió todo.
  function montoPendiente(sol) {
    if (sol.estado === 'POR_DEVOLVER') return sol.devolucion_foto ? 0 : Math.round(Number(sol.diferencia) * 100);
    if (sol.estado !== 'DEPOSITADO') return 0;
    const porRendir = sol.items.filter(item => ['POR_RENDIR', 'RECHAZADO'].includes(item.estado))
      .reduce((suma, item) => suma + Math.round(Number(item.monto) * 100), 0);
    return porRendir || (sol.puede_devolver ? Math.round(Number(sol.diferencia) * 100) : 0);
  }
  const porDevolver = sol => sol.estado === 'POR_DEVOLVER' || (sol.estado === 'DEPOSITADO' && sol.puede_devolver);
  function rechazado(sol) {
    return sol.estado === 'RECHAZADO' || (sol.estado === 'DEPOSITADO' && sol.items.some(item => item.estado === 'RECHAZADO'))
      || (['POR_DEVOLVER', 'DEPOSITADO'].includes(sol.estado) && !sol.devolucion_foto && sol.historial?.at(-1)?.accion === 'rechazar devolución');
  }
  function actualizarAntiguedad() {
    document.querySelectorAll('[data-cc-solicitada]').forEach(indicador => {
      const horas = Math.max(0, Math.floor((Date.now() - Date.parse(indicador.dataset.ccSolicitada)) / 3600000));
      const dias = Math.floor(horas / 24), resto = horas % 24;
      indicador.dataset.nivel = horas >= 24 ? 'rojo' : horas >= 12 ? 'amarillo' : 'normal';
      indicador.textContent = (dias ? dias + ' d ' : '') + resto + ' h desde la solicitud';
    });
  }
  setInterval(actualizarAntiguedad, 60000);
  function fichaDeposito(sol) {
    const descripcion = el('span');
    descripcion.append(el('strong', null, sol.codigo),
      el('span', 'cc-estado cc-' + sol.estado.toLowerCase(), rechazado(sol) ? 'Rechazado' : sol.devolucion_aceptada && sol.estado === 'DEPOSITADO' ? 'Devolución aprobada'
        : sol.devolucion_foto && ['DEPOSITADO', 'POR_DEVOLVER'].includes(sol.estado) ? 'Devolución en revisión'
        : sol.puede_devolver && sol.estado === 'DEPOSITADO' ? ESTADOS.POR_DEVOLVER : ESTADOS[sol.estado]),
      el('small', null, 'Motivo: ' + (sol.motivo || 'Sin motivo registrado')));
    const ultimo = sol.historial?.at(-1);
    const rechazo = sol.motivo_rechazo || sol.items.find(item => item.estado === 'RECHAZADO')?.motivo_rechazo
      || (ultimo?.accion === 'rechazar devolución' ? ultimo.motivo : '');
    if (rechazo) descripcion.append(el('small', null, 'Motivo del rechazo: ' + rechazo));
    const fecha = sol.creado ? sol.creado + 'Z' : '';
    if (Number.isFinite(Date.parse(fecha))) {
      const momento = el('time', 'solicitud-fecha', 'Solicitado el ' + fechaLima.format(new Date(fecha)));
      momento.dateTime = fecha;
      const antiguedad = el('span', 'solicitud-antiguedad');
      antiguedad.dataset.ccSolicitada = fecha;
      descripcion.append(momento, antiguedad);
    }
    const montos = el('span', 'cc-rendir-importes');
    const pendiente = montoPendiente(sol);
    montos.append(el('strong', 'cc-rendir-monto', dinero(pendiente ? pendiente / 100 : sol.total)),
      el('small', null, porDevolver(sol) ? 'Por devolver' : pendiente ? 'Por rendir'
        : sol.estado === 'DEPOSITADO' ? 'En revisión' : 'Solicitado'));
    if (pendiente > 0 && pendiente !== Math.round(Number(sol.total) * 100)) {
      montos.append(el('small', null, 'Total solicitado: ' + dinero(sol.total)));
    }
    return [descripcion, montos];
  }
  // Mientras falten ítems: muestra cuánto va a devolución y se actualiza al escribir el monto o activar Devolver.
  function previaDevolucion(sol, detalle) {
    const aviso = el('section', 'cc-devolucion cc-devolucion-previa');
    const calculo = el('dl', 'cc-calculo');
    const ayuda = el('p', 'hint');
    aviso.append(el('h3', 'cc-devolucion-titulo', 'Devolución'), calculo, ayuda);
    const resumenDev = detalle.querySelector('.cc-resumen-rendir .dev strong');
    const actualizar = () => {
      const lineas = sol.items.filter(i => saldoItem(i) > 0)
        .map(i => [i.tipo_gasto + (i.estado === 'DEVUELTO' ? ' (completo)' : ' (saldo)'), saldoItem(i)]);
      let pendientes = 0;
      detalle.querySelectorAll('.cc-rindiendo').forEach(fila => {
        pendientes++;
        const monto = Number(fila.dataset.monto);
        if (fila.querySelector('.cc-check-devolver input')?.checked) { lineas.push([fila.dataset.tipo + ' (completo)', monto]); return; }
        const texto = (fila.querySelector('input[name=monto_gastado]')?.value || '').replace(',', '.').trim();
        const gastado = Number(texto);
        if (texto && Number.isFinite(gastado) && gastado >= 0 && gastado < monto) {
          lineas.push([fila.dataset.tipo + ' (saldo)', Math.round((monto - gastado) * 100) / 100]);
        }
      });
      const total = Math.round(lineas.reduce((t, [, m]) => t + m, 0) * 100) / 100;
      const filas = lineas.map(([texto, monto]) => {
        const d = el('div', 'detalle'); d.append(el('dt', null, '↩ ' + texto), el('dd', null, dinero(monto))); return d;
      });
      const pie = el('div', 'total'); pie.append(el('dt', null, 'Debes devolver'), el('dd', null, dinero(total)));
      calculo.replaceChildren(...filas, pie);
      ayuda.textContent = pendientes
        ? 'Te ' + (pendientes === 1 ? 'falta rendir 1 ítem' : 'faltan rendir ' + pendientes + ' ítems') + '. Al terminar, aquí mismo subes la captura de la devolución.'
        : 'Al terminar la revisión, aquí mismo subes la captura de la devolución.';
      aviso.hidden = total <= 0;
      if (resumenDev) resumenDev.textContent = dinero(total);
    };
    detalle.oninput = detalle.onchange = actualizar;
    queueMicrotask(actualizar);
    return aviso;
  }
  function abrirRendicion(sol, previos = new Map()) {
    const detalle = $('cc-detalle-contenido');
    const resumen = el('div', 'deposit');
    resumen.append(...fichaDeposito(sol));
    detalle.replaceChildren(resumen);
    $('cc-titulo-rendir').textContent = sol.estado === 'RECHAZADO' ? 'Solicitud rechazada' : 'Rendir depósito';
    if (['DEPOSITADO', 'POR_DEVOLVER'].includes(sol.estado)) {
      // Resumen: depositado, aprobado y lo que falta sustentar.
      const aprobado = sol.items.filter(i => i.estado === 'APROBADO').reduce((t, i) => t + Number(i.monto_gastado || 0), 0);
      const porSustentar = sol.items.filter(i => ['POR_RENDIR', 'RECHAZADO', 'EN_REVISION'].includes(i.estado))
        .reduce((t, i) => t + Number(i.monto || 0), 0);
      const aDevolver = sol.items.reduce((t, i) => t + saldoItem(i), 0);
      const resumen = el('div', 'cc-resumen-rendir');
      for (const [titulo, valor, clase] of [['Depositado', sol.deposito_monto || sol.total], ['Aprobado', aprobado, 'ok'],
        ['Por sustentar', porSustentar, 'pend'], ['A devolver', aDevolver, 'dev']]) {
        const caja = el('div', clase || null); caja.append(el('small', null, titulo), el('strong', null, dinero(valor))); resumen.append(caja);
      }
      detalle.append(resumen);
    }
    for (const item of sol.items) {
      const fila = el('section', 'card cc-item-fila cc-item-' + item.estado.toLowerCase());
      const cab = el('div', 'cc-item-cabecera');
      cab.append(el('strong', null, item.numero + ' · ' + item.tipo_gasto), el('span', 'cc-chip cc-' + item.estado.toLowerCase(), ITEM[item.estado]));
      fila.append(cab, el('small', null, (item.descripcion ? item.descripcion + ' · ' : '') + 'Solicitado ' + dinero(item.monto)));
      if (item.estado === 'APROBADO' || item.estado === 'EN_REVISION') {
        fila.append(el('p', 'cc-item-ok', (item.estado === 'APROBADO' ? '✓ Rendiste ' : 'Enviado · ') + dinero(item.monto_gastado)
          + (item.comprobante ? ' · ' + item.comprobante : '')));
      }
      const saldo = saldoItem(item);
      if (saldo > 0 && item.estado !== 'DEVUELTO') fila.append(el('p', 'cc-item-saldo', '↩ ' + dinero(saldo) + ' pasa a tu devolución'));
      if (item.estado === 'DEVUELTO') {
        const nota = el('p', 'cc-item-saldo', '↩ Devuelves ' + dinero(saldo));
        // Mientras no se envíe la devolución, se puede desmarcar.
        if (sol.estado === 'DEPOSITADO' || (sol.estado === 'POR_DEVOLVER' && !sol.devolucion_foto)) {
          const deshacer = el('button', 'cc-deshacer', 'Deshacer'); deshacer.type = 'button';
          const error = el('div', 'error'); error.hidden = true; error.tabIndex = -1;
          deshacer.addEventListener('click', () => enviando(deshacer, error, async () => {
            await api('/' + sol.id + '/item/' + item.id + '/deshacer', {method: 'POST'});
            await recargar(sol);
          }));
          nota.append(deshacer);
          fila.append(nota, error);
        } else fila.append(nota);
      }
      const rindiendo = sol.estado === 'DEPOSITADO' && ['POR_RENDIR', 'RECHAZADO'].includes(item.estado);
      if (rindiendo) {
        fila.classList.add('cc-rindiendo');
        Object.assign(fila.dataset, {id: String(item.id), monto: item.monto, tipo: item.tipo_gasto});
        const previo = previos.get(String(item.id));
        if (item.estado === 'RECHAZADO') {
          const motivo = el('p', 'cc-item-motivo'); motivo.append(el('strong', null, 'Motivo: '), item.motivo_rechazo || 'Sin motivo');
          fila.append(motivo);
        }
        // Check de devolución: al marcarlo se oculta la rendición y queda el botón para devolver todo el ítem.
        const check = el('label', 'cc-check-devolver');
        const marca = Object.assign(el('input'), {type: 'checkbox'}); marca.setAttribute('role', 'switch');
        check.append(marca, el('span', null, 'Devolver'));
        check.title = 'Devolver todo el ítem (' + dinero(item.monto) + ')';
        cab.querySelector('.cc-chip').before(check);
        const form = previo?.form || formRendir(sol, item);
        const devolverBtn = el('button', 'primary wide cc-btn-devolver', '↩ Devolver ' + dinero(item.monto)); devolverBtn.type = 'button';
        devolverBtn.hidden = true;
        const error = el('div', 'error'); error.hidden = true; error.tabIndex = -1;
        marca.addEventListener('change', () => {
          fila.classList.toggle('cc-marcado-devolver', marca.checked);
          form.hidden = marca.checked; devolverBtn.hidden = !marca.checked; error.hidden = true;
        });
        devolverBtn.addEventListener('click', () => enviando(devolverBtn, error, async () => {
          await api('/' + sol.id + '/item/' + item.id + '/devolver', {method: 'POST'});
          await recargar(sol);
        }));
        fila.append(form, devolverBtn, error);
        if (previo?.marcado) { marca.checked = true; marca.dispatchEvent(new Event('change')); }
      }
      detalle.append(fila);
    }
    detalle.oninput = detalle.onchange = null;
    if (sol.estado === 'DEPOSITADO' && !sol.puede_devolver && !sol.devolucion_foto) detalle.append(previaDevolucion(sol, detalle));
    if (sol.estado === 'POR_DEVOLVER' || (sol.estado === 'DEPOSITADO' && (sol.puede_devolver || sol.devolucion_foto))) {
      detalle.append(sol.devolucion_foto
        ? el('p', 'notice', 'Devolución de ' + dinero(sol.devolucion_monto || sol.diferencia)
          + (sol.devolucion_aceptada ? ' aprobada. ✓' : ' enviada. Está pendiente de revisión.'))
        : formDevolucion(sol));
    }
    if (sol.estado === 'RECHAZADO') {
      const corregir = el('button', 'primary wide', 'Corregir y reenviar');
      corregir.type = 'button';
      corregir.addEventListener('click', () => abrirFormulario(sol));
      detalle.append(corregir);
    }
    actualizarAntiguedad();
    ver('cc-detalle-rendicion');
    $('cc-titulo-rendir').focus({preventScroll: true});
  }
  let filtro = 'rendir';
  function pintar() {
    const total = datos.solicitudes.reduce((suma, sol) => suma + montoPendiente(sol), 0);
    $('cc-pendiente').textContent = dinero(total / 100);
    const lista = $('cc-lista');
    lista.replaceChildren();
    const grupos = [
      ['validar', 'Por validar', datos.solicitudes.filter(sol => ['PENDIENTE', 'RECHAZADO'].includes(sol.estado))],
      ['depositar', 'Por depositar', datos.solicitudes.filter(sol => sol.estado === 'VALIDADO')],
      ['rendir', 'Por rendir', datos.solicitudes.filter(sol => ['DEPOSITADO', 'POR_DEVOLVER'].includes(sol.estado))],
    ];
    const filtros = $('cc-filtros');
    filtros.replaceChildren();
    for (const [clave, etiqueta, registros] of grupos) {
      const boton = el('button', 'filtro-rendicion', etiqueta);
      boton.type = 'button';
      boton.dataset.filtro = clave;
      boton.setAttribute('aria-pressed', String(filtro === clave));
      boton.append(el('span', null, String(registros.length)));
      boton.onclick = () => {
        filtro = clave;
        pintar();
        filtros.querySelector('[aria-pressed="true"]').focus();
      };
      filtros.append(boton);
    }
    const solicitudes = grupos.find(([clave]) => clave === filtro)[2];
    if (!solicitudes.length) lista.append(el('p', 'empty', 'No tienes solicitudes en esta etapa.'));
    for (const sol of solicitudes) {
      const ficha = el('button', 'deposit');
      ficha.type = 'button';
      ficha.append(...fichaDeposito(sol));
      ficha.addEventListener('click', () => abrirRendicion(sol));
      lista.append(ficha);
    }
    actualizarAntiguedad();
  }
  async function cargar() { datos = await api('/datos'); pintar(); $('cargando').hidden = true; ver('cc-inicio'); }
  // Tras rendir, devolver o deshacer: se queda en la misma solicitud y en la misma posición.
  async function recargar(sol) {
    const y = window.scrollY;
    const previos = new Map([...$('cc-detalle-contenido').querySelectorAll('.cc-rindiendo')].map(fila => [fila.dataset.id,
      {form: fila.querySelector('form.cc-rendir'), marcado: !!fila.querySelector('.cc-check-devolver input')?.checked}]));
    datos = await api('/datos'); pintar(); $('cargando').hidden = true;
    const actual = datos.solicitudes.find(s => s.id === sol.id);
    if (!actual) { ver('cc-inicio'); return; }
    abrirRendicion(actual, previos);
    window.scrollTo(0, y);
  }

  // ── Nueva solicitud ──
  function itemsSeleccionados() {
    return [...$('cc-items').querySelectorAll('.expense-card')]
      .filter(card => card.querySelector('[type=checkbox]').checked)
      .map(card => ({
        ...Object.fromEntries([...card.querySelectorAll('[data-campo]')]
          .map(control => [control.dataset.campo, control.value.trim()])),
        descripcion: card.dataset.descripcion
      }));
  }
  function total() {
    const items = itemsSeleccionados();
    const suma = items.reduce((centimos, item) => centimos + Math.round((numero(item.monto) || 0) * 100), 0);
    $('cc-cantidad').textContent = items.length + (items.length === 1 ? ' gasto' : ' gastos');
    $('cc-subtotal').textContent = $('cc-total').textContent = dinero(suma / 100);
  }
  function mostrarConceptos(seleccionados = [], mostrarAnteriores = false) {
    const proyecto = $('cc-proyecto').value;
    const catalogo = datos.catalogo.filter(concepto => concepto.proyectos[proyecto]);
    const porNombre = new Map(catalogo.map(concepto => [concepto.nombre, concepto]));
    const nombresSeleccionados = new Set(seleccionados.map(item => item.tipo_gasto));
    const filas = seleccionados.filter(item => mostrarAnteriores || porNombre.has(item.tipo_gasto))
      .map(item => [porNombre.get(item.tipo_gasto) || {
        nombre: item.tipo_gasto, descripcion: 'Este concepto ya no está disponible para el proyecto.',
        proyectos: {}, correo: {[proyecto]: item.requiere_correo}
      }, item]);
    const pideCorreo = concepto => typeof concepto.correo === 'object' ? Boolean(concepto.correo?.[proyecto]) : Boolean(concepto.correo);
    catalogo.filter(concepto => !nombresSeleccionados.has(concepto.nombre))
      .forEach(concepto => filas.push([concepto]));
    $('cc-items').replaceChildren(...filas.map(([concepto, valores], indice) => {
      const card = $('cc-item-plantilla').content.firstElementChild.cloneNode(true);
      const checkbox = card.querySelector('[type=checkbox]');
      const detalle = card.querySelector('.expense-amount');
      const correo = card.querySelector('[data-correo]');
      card.dataset.descripcion = valores?.descripcion || '';
      card.querySelector('[data-nombre]').textContent = concepto.nombre;
      card.querySelector('.expense-criterion').textContent = concepto.descripcion || '';
      card.querySelector('.expense-classification').textContent = concepto.proyectos[proyecto] || valores?.tipo_presupuesto || '';
      checkbox.value = concepto.nombre;
      checkbox.checked = Boolean(valores);
      correo.hidden = !pideCorreo(concepto);
      detalle.querySelectorAll('[data-campo]').forEach(control => {
        control.id = 'cc-' + control.dataset.campo + '-' + indice;
        control.previousElementSibling.htmlFor = control.id;
        if (control.type === 'email') control.disabled = !pideCorreo(concepto);
        if (valores && !control.disabled) control.value = valores[control.dataset.campo] ?? '';
      });
      detalle.hidden = !checkbox.checked;
      checkbox.addEventListener('change', () => {
        detalle.hidden = !checkbox.checked;
        total();
      });
      card.querySelector('[data-campo=monto]').addEventListener('input', total);
      return card;
    }));
    total();
  }
  // Nueva solicitud (sol vacío) o corrección de una rechazada (precargada con sus datos).
  function actualizarResponsables(valor = '') {
    const control = $('cc-responsable');
    control.replaceChildren(new Option('Selecciona un responsable', ''));
    Object.entries(datos.responsables[$('cc-proyecto').value] || {}).forEach(([id, nombre]) => control.add(new Option(nombre, id)));
    control.value = [...control.options].some(o => o.value === valor) ? valor : '';
  }
  function actualizarBilletera() {
    $('cc-billetera-numero').hidden = $('cc-numero-billetera').disabled = $('cc-billetera').value === 'No aplica';
  }
  function abrirFormulario(sol) {
    corrigiendo = sol || null;
    const form = $('cc-form'); form.reset();
    // El proyecto es el del técnico en Dataper: se muestra, pero no se puede cambiar.
    const selectorProyecto = $('cc-proyecto');
    for (const opcion of [...selectorProyecto.options]) if (opcion.value !== datos.proyecto) opcion.remove();
    if (!selectorProyecto.options.length) selectorProyecto.add(new Option('Sin proyecto en Dataper', ''));
    selectorProyecto.disabled = true;
    form.querySelector('.error').hidden = true;
    $('cc-rechazo').hidden = !sol;
    $('cc-volver-solicitud').hidden = !sol;
    $('cc-volver-portal').hidden = Boolean(sol);
    form.querySelector('[type=submit]').textContent = sol ? 'Reenviar solicitud' : 'Enviar solicitud';
    $('cc-dni').value = datos.personal.documento || '';
    $('cc-tecnico').value = datos.personal.nombre || '';
    $('cc-supervisor').value = datos.personal.supervisor || '';
    if (sol) {
      $('cc-rechazo').textContent = 'Rechazada: ' + sol.motivo_rechazo;
      $('cc-motivo').value = sol.motivo;
      $('cc-banco').value = sol.banco; $('cc-cuenta').value = sol.cuenta;
    }
    mostrarConceptos(sol?.items, Boolean(sol));
    const extra = sol?.formulario || {};
    $('cc-site').value = extra.site === 'SITE PENDIENTE' ? '' : extra.site || '';
    $('cc-wo').value = extra.wo === 'CM PENDIENTE' ? '' : extra.wo || '';
    $('cc-titular').value = extra.titular || '';
    $('cc-billetera').value = extra.tipo_billetera || 'No aplica';
    $('cc-numero-billetera').value = extra.numero_billetera || '';
    actualizarResponsables(extra.responsable_validacion_id);
    actualizarBilletera();
    ver('cc-solicitud');
  }
  $('cc-proyecto').addEventListener('change', () => {
    actualizarResponsables();
    mostrarConceptos(itemsSeleccionados());
  });
  $('cc-billetera').addEventListener('change', actualizarBilletera);
  $('cc-cuenta').addEventListener('input', ({target}) => {
    target.value = target.value.replace(/[^0-9]/g, '').slice(0, 20);
  });
  for (const campo of ['site', 'wo']) {
    const input = $('cc-' + campo);
    const lista = $('cc-sugerencias-' + campo);
    let espera, consulta;
    function limpiar() {
      clearTimeout(espera);
      consulta?.abort();
      lista.replaceChildren();
    }
    $('cc-form').addEventListener('reset', limpiar);
    $('cc-proyecto').addEventListener('change', () => {
      input.value = '';
      limpiar();
    });
    input.addEventListener('input', () => {
      limpiar();
      const q = input.value.trim(), proyecto = $('cc-proyecto').value;
      if (q.length < 2 || !proyecto) return;
      espera = setTimeout(async () => {
        const actual = new AbortController();
        consulta = actual;
        try {
          const parametros = new URLSearchParams({campo, q, proyecto});
          const {opciones} = await api('/sugerencias?' + parametros, {signal: actual.signal}, '/form-pruebas');
          if (actual.signal.aborted) return;
          const botones = opciones.map(valor => {
            const boton = el('button', null, valor);
            boton.type = 'button';
            boton.addEventListener('click', () => { input.value = valor; limpiar(); });
            return boton;
          });
          lista.replaceChildren(...botones);
          if (!botones.length) lista.textContent = 'Sin coincidencias para este proyecto.';
        } catch {
          if (!actual.signal.aborted) lista.textContent = 'No se pudieron cargar las sugerencias.';
        }
      }, 250);
    });
  }
  $('cc-exito-volver').addEventListener('click', () => { filtro = 'validar'; pintar(); ver('cc-inicio'); });
  document.querySelectorAll('[data-cc-volver]').forEach(b => b.addEventListener('click', () => ver('cc-inicio')));
  $('cc-form').addEventListener('submit', e => {
    e.preventDefault(); const form = e.currentTarget, error = form.querySelector('.error');
    enviando(form.querySelector('[type=submit]'), error, async () => {
      if (!/^[0-9]{20}$/.test($('cc-cuenta').value)) throw Error('Ingresa el CCI de 20 dígitos.');
      const items = itemsSeleccionados();
      if (!items.length) throw Error('Selecciona al menos un concepto.');
      items.forEach(item => {
        if (!(numero(item.monto) > 0)) throw Error(item.tipo_gasto + ': escribe un monto mayor a cero.');
      });
      const cuerpo = {...Object.fromEntries(new FormData(form)), items};
      const ruta = corrigiendo ? '/' + corrigiendo.id + '/reenviar' : '/solicitar';
      const r = await api(ruta, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo)});
      $('cc-exito-titulo').textContent = corrigiendo ? '¡Solicitud reenviada!' : '¡Solicitud enviada!';
      $('codigo-exito').textContent = r.solicitud.codigo;
      $('total-exito').textContent = dinero(r.solicitud.total);
      datos.solicitudes = [r.solicitud, ...datos.solicitudes.filter(sol => sol.id !== r.solicitud.id)];
      pintar();
      corrigiendo = null;
      ver('cc-exito');
      $('cc-exito-titulo').focus();
    });
  });

  cargar().then(() => {
    // "Solicitar" del inicio del portal llega con #nueva: abre directo el formulario.
    if (location.hash === '#nueva') { history.replaceState(null, '', location.pathname); abrirFormulario(); }
  }).catch(e => { const c = $('cargando'); c.setAttribute('role', 'alert'); c.textContent = e.message; });
})();
