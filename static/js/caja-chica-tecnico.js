/* Caja Chica · portal del técnico: solicitar por ítems y rendir cada ítem. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = '/form-pruebas/caja-chica';
  const ESTADOS = {PENDIENTE: 'En validación', VALIDADO: 'Por depositar', DEPOSITADO: 'Por rendir',
                   POR_DEVOLVER: 'Falta la devolución', SUSTENTO: 'Rendido', ARCHIVADO: 'Archivado', RECHAZADO: 'Rechazado: corrige y reenvía', ANULADO: 'Anulado'};
  const ITEM = {POR_RENDIR: 'Por rendir', EN_REVISION: 'En revisión', APROBADO: 'Aprobado', RECHAZADO: 'Rechazado', DEVUELTO: 'Se devuelve'};
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const numero = v => { const t = String(v || '').replace(/\s/g, '').replace(/,(?=\d{3}(\D|$))/g, '').replace(',', '.'); return /^\d+(\.\d{1,2})?$/.test(t) ? Number(t) : NaN; };
  let datos = null, corrigiendo = null;  // corrigiendo = solicitud rechazada que se está reenviando
  // Gasto Cobra (azul) o Refacturable (naranja): la misma etiqueta en todo Nucleus.
  const tipoDe = t => !t ? '' : /refact/i.test(t) ? 'Refacturable' : 'Gasto Cobra';
  const etiquetaTipo = t => el('span', 'cc-tipo ' + (t === 'Refacturable' ? 'cc-tipo-rf' : 'cc-tipo-gc'), t);
  const conRefacturable = items => (items || []).some(i => tipoDe(i.tipo_presupuesto) === 'Refacturable');
  // Restricciones de Mobile: aviso por monto, bloqueos y refacturables pendientes.
  function restricciones(nuevo = true) {
    const r = datos.restricciones || {}, caja = el('div', 'cc-restricciones');
    for (const b of r.bloqueos || []) caja.append(el('p', 'cc-restriccion bloqueo', '🔒 ' + b));
    // Bloqueos de un solo tipo: puede seguir pidiendo el otro tipo de gasto.
    for (const b of r.bloqueos_tipo || []) caja.append(el('p', 'cc-restriccion bloqueo', '🔒 ' + b.mensaje + ' Puedes pedir ' + (b.gasto === 'refacturable' ? 'Gasto Cobra' : 'Refacturable') + '.'));
    if (r.aviso) caja.append(el('p', 'cc-restriccion aviso', '⚠️ ' + r.aviso));
    if (r.tope) {
      const avance = Math.min(100, Number(r.por_rendir_tope ?? r.por_rendir) / Number(r.tope) * 100);
      const barra = el('div', 'cc-tope'), fila = el('div', 'cc-tope-fila');
      fila.append(el('span', null, 'Por rendir' + (r.tope_gasto === 'cobra' ? ' (Gasto Cobra)' : r.tope_gasto === 'refacturable' ? ' (Refacturable)' : '')),
        el('strong', null, dinero(r.por_rendir_tope ?? r.por_rendir) + ' / ' + dinero(r.tope)));
      const pista = el('div', 'cc-tope-pista'), lleno = el('div', 'cc-tope-lleno');
      lleno.style.width = avance + '%'; lleno.dataset.nivel = avance >= 100 ? 'rojo' : r.aviso || avance >= 80 ? 'ambar' : 'verde';
      pista.append(lleno); barra.append(fila, pista); caja.append(barra);
    }
    if (r.refacturables) {
      const {pendientes, maximo} = r.refacturables, lleno = pendientes >= maximo;
      caja.append(el('p', 'cc-restriccion refact' + (lleno ? ' lleno' : ''), 'Refacturables sin rendir: ' + pendientes + ' de ' + maximo
        + (lleno && nuevo ? ' · rinde uno para pedir otro refacturable' : '')));
    }
    return caja;
  }
  function etiquetasTipo(items) {
    const tipos = [...new Set(items.map(i => tipoDe(i.tipo_presupuesto)).filter(Boolean))];
    if (!tipos.length) return null;
    const caja = el('span', 'cc-tipos'); tipos.forEach(t => caja.append(etiquetaTipo(t))); return caja;
  }

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
  const MAX_COMPROBANTES = 10;
  const aNumero = t => { const v = Number(String(t || '').replace(',', '.').trim()); return Number.isFinite(v) ? v : NaN; };
  // Rendir un ítem: uno o más comprobantes (RUC, N.º, monto y su foto) y de 1 a 3 fotos de evidencia.
  function formRendir(sol, item) {
    const form = el('form', 'cc-rendir'); form.noValidate = true;
    const lista = el('div', 'cc-comps');
    const agregar = el('button', 'cc-agregar', '+ Agregar otro comprobante'); agregar.type = 'button';
    const totales = el('dl', 'cc-comp-totales');
    let correlativo = 0;

    function campo(caja, titulo, modo, ejemplo, largo, clase) {
      const id = 'r' + item.id + '-' + (++correlativo), label = el('label', null, titulo), input = el('input');
      label.htmlFor = id; Object.assign(input, {id, inputMode: modo, placeholder: ejemplo, required: true, maxLength: largo});
      input.dataset.campo = clase;
      const envoltura = el('div'); envoltura.append(label, input); caja.append(envoltura);
      return input;
    }
    function comprobante(anterior) {
      const caja = el('div', 'cc-comp');
      const cab = el('div', 'cc-comp-cab');
      const quitar = el('button', 'cc-comp-quitar', 'Quitar'); quitar.type = 'button'; quitar.title = 'Quitar comprobante';
      quitar.addEventListener('click', () => { caja.remove(); renumerar(); });
      cab.append(el('strong'), quitar);
      caja.append(cab);
      const ruc = campo(caja, 'RUC', 'numeric', '20123456789', 11, 'ruc');
      // Al escribir los 11 dígitos se completa la razón social (openruc / padrón).
      const razon = el('p', 'cc-razon'); razon.hidden = true; razon.setAttribute('aria-live', 'polite');
      caja.append(razon);
      caja.razonSocial = '';
      let consulta;
      const consultar = async () => {
        consulta?.abort(); caja.razonSocial = '';
        razon.hidden = !/^[0-9]{11}$/.test(ruc.value); razon.className = 'cc-razon';
        if (razon.hidden) return;
        const actual = consulta = new AbortController();
        razon.textContent = 'Consultando RUC…';
        try {
          const r = await api('/ruc/' + ruc.value, {signal: actual.signal}, '/form-pruebas');
          if (actual.signal.aborted) return;
          if (r.resultado === 'encontrado') {
            caja.razonSocial = r.razon_social;
            razon.textContent = r.razon_social + (r.activo ? ' · Activo' : ' · No activo');
            razon.classList.add(r.activo ? 'ok' : 'alerta');
          } else {
            razon.textContent = r.resultado === 'no_encontrado' ? 'RUC no encontrado. Revisa los dígitos.' : 'Consulta de RUC no disponible ahora.';
            razon.classList.add('alerta');
          }
        } catch { if (!actual.signal.aborted) { razon.textContent = 'No se pudo consultar el RUC.'; razon.classList.add('alerta'); } }
      };
      ruc.addEventListener('input', consultar);
      const fila = el('div', 'cc-comp-fila');
      campo(fila, 'N.º boleta / factura', 'text', 'B001-000123', 40, 'numero');
      const monto = campo(fila, 'Monto (S/)', 'decimal', '0.00', 12, 'monto');
      caja.append(fila);
      const foto = casillaFoto('', 'Foto del comprobante', 'Tomar o elegir foto');
      foto.casilla.classList.add('cc-comp-foto');
      caja.foto = foto.input;
      caja.append(foto.casilla);
      monto.addEventListener('input', actualizar);
      // El RUC se copia del comprobante anterior: suele ser el mismo proveedor, pero se puede cambiar.
      if (anterior?.value) { ruc.value = anterior.value; consultar(); }
      lista.append(caja);
      renumerar();
      return caja;
    }
    function renumerar() {
      const cajas = [...lista.children];
      cajas.forEach((c, i) => {
        c.querySelector('.cc-comp-cab strong').textContent = 'Comprobante ' + (i + 1);
        c.querySelector('.cc-comp-quitar').hidden = cajas.length === 1;
      });
      agregar.hidden = cajas.length >= MAX_COMPROBANTES;
      actualizar();
    }
    function actualizar() {
      const montos = [...lista.querySelectorAll('[data-campo=monto]')].map(i => aNumero(i.value));
      const gastado = Math.round(montos.reduce((t, m) => t + (m > 0 ? m : 0), 0) * 100) / 100;
      const resto = Math.round((Number(item.monto) - gastado) * 100) / 100;
      const fila = (a, b, clase) => { const d = el('div', clase || null); d.append(el('dt', null, a), el('dd', null, b)); return d; };
      totales.replaceChildren(fila('Total gastado', dinero(gastado) + ' de ' + dinero(item.monto)),
        ...(resto > 0 && gastado > 0 ? [fila('Pasa a tu devolución', dinero(resto), 'dev')] : []),
        ...(resto < 0 ? [fila('Excede lo depositado', dinero(-resto), 'alerta')] : []));
      totales.hidden = gastado <= 0;
      form.dataset.gastado = String(gastado);
      form.closest('.cc-rindiendo')?.dispatchEvent(new Event('input', {bubbles: true}));
    }
    agregar.addEventListener('click', () => {
      const ultimo = lista.lastElementChild;
      comprobante(ultimo?.querySelector('[data-campo=ruc]')).querySelector('[data-campo=numero]').focus();
    });

    // Evidencia: una foto obligatoria y las adicionales que haga falta (sin tope).
    const evidencias = el('div', 'cc-slots cc-evidencias');
    const otraEvidencia = el('button', 'cc-slot cc-slot-agregar'); otraEvidencia.type = 'button';
    otraEvidencia.append(el('span', 'cc-slot-texto', '+ Foto adicional'));
    const estadoEvidencias = () => {};
    const slotEvidencia = opcional => {
      const f = casillaFoto('', opcional ? 'Evidencia adicional' : 'Evidencia del gasto', opcional ? 'Opcional' : 'Foto del uso');
      f.casilla.classList.add('cc-evidencia');
      if (opcional) {
        const quitar = el('button', 'cc-slot-quitar', '×'); quitar.type = 'button'; quitar.title = 'Quitar foto';
        quitar.setAttribute('aria-label', 'Quitar foto');
        quitar.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); f.casilla.remove(); estadoEvidencias(); });
        f.casilla.append(quitar);
      }
      evidencias.insertBefore(f.casilla, otraEvidencia);
      estadoEvidencias();
      return f;
    };
    evidencias.append(otraEvidencia);
    otraEvidencia.addEventListener('click', () => slotEvidencia(true).input.click());
    slotEvidencia(false);

    comprobante(null);
    const error = el('div', 'error'); error.setAttribute('role', 'alert'); error.tabIndex = -1; error.hidden = true;
    const boton = el('button', 'primary wide', item.tipo_gasto ? 'Rendir ' + item.tipo_gasto : 'Rendir'); boton.type = 'submit';
    form.append(lista, agregar, totales, el('p', 'cc-subtitulo-evidencia', 'Evidencia del gasto'), evidencias,
      el('p', 'hint', 'Obligatorio: al menos 1 foto de evidencia; puedes agregar las que necesites.'), error, boton);
    form.addEventListener('submit', e => { e.preventDefault(); enviando(boton, error, async () => {
      const cajas = [...lista.children], datos = new FormData();
      cajas.forEach((c, i) => {
        const pre = cajas.length > 1 ? 'Comprobante ' + (i + 1) + ': ' : '';
        const v = k => c.querySelector('[data-campo=' + k + ']').value.trim();
        if (!/^[0-9]{11}$/.test(v('ruc'))) throw Error(pre + 'escribe el RUC de 11 dígitos.');
        if (!v('numero')) throw Error(pre + 'escribe el número de la boleta o factura.');
        if (!(aNumero(v('monto')) > 0)) throw Error(pre + 'escribe el monto de la boleta.');
        if (!c.foto.files.length) throw Error(pre + 'adjunta la foto de la boleta o factura.');
        datos.append('comp_ruc', v('ruc')); datos.append('comp_numero', v('numero'));
        datos.append('comp_monto', v('monto')); datos.append('comp_razon', c.razonSocial || '');
        datos.append('comp_foto_' + i, c.foto.files[0]);
      });
      if (Number(form.dataset.gastado) > Number(item.monto)) throw Error('El total gastado no puede superar ' + dinero(item.monto) + '.');
      const fotos = [...evidencias.querySelectorAll('.cc-evidencia input')].filter(i => i.files.length);
      if (!fotos.length) throw Error('Adjunta la foto de la evidencia del gasto.');
      fotos.forEach(i => datos.append('evidencia', i.files[0]));
      await api('/' + sol.id + '/item/' + item.id + '/rendir', {method: 'POST', body: datos});
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
  // Dónde devolver: la cuenta que define Nucleus (con botón para copiar el número).
  function cuentaDevolucion() {
    const c = datos?.cuenta_devolucion;
    if (!c?.numero) return document.createTextNode('');
    const caja = el('div', 'cc-cuenta-devolucion');
    const info = el('div');
    info.append(el('small', null, 'Devuelve a este ' + c.tipo), el('strong', null, c.numero), el('span', null, c.titular));
    const copiar = el('button', 'cc-copiar', 'Copiar'); copiar.type = 'button';
    copiar.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(c.numero); copiar.textContent = '¡Copiado!'; } catch (_) { copiar.textContent = c.numero; }
      setTimeout(() => { copiar.textContent = 'Copiar'; }, 1800);
    });
    caja.append(el('span', 'cc-cuenta-tipo', c.tipo), info, copiar);
    return caja;
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
    form.append(calculo, cuentaDevolucion(),
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
    const tipos = etiquetasTipo(sol.items || []);
    if (tipos) descripcion.append(tipos);
    const ultimo = sol.historial?.at(-1);
    const rechazo = sol.motivo_rechazo || sol.items.find(item => item.estado === 'RECHAZADO')?.motivo_rechazo
      || (ultimo?.accion === 'rechazar devolución' ? ultimo.motivo : '');
    if (rechazo) descripcion.append(el('small', null, 'Motivo del rechazo: ' + rechazo));
    if (sol.deposito_comentario) descripcion.append(el('small', null, 'Comentario del depósito: ' + sol.deposito_comentario));
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
    aviso.append(el('h3', 'cc-devolucion-titulo', 'Devolución'), calculo, cuentaDevolucion(), ayuda);
    const resumenDev = detalle.querySelector('.cc-resumen-rendir .dev strong');
    const actualizar = () => {
      const lineas = sol.items.filter(i => saldoItem(i) > 0)
        .map(i => [i.tipo_gasto + (i.estado === 'DEVUELTO' ? ' (completo)' : ' (saldo)'), saldoItem(i)]);
      let pendientes = 0;
      detalle.querySelectorAll('.cc-rindiendo').forEach(fila => {
        pendientes++;
        const monto = Number(fila.dataset.monto);
        if (fila.querySelector('.cc-check-devolver input')?.checked) { lineas.push([fila.dataset.tipo + ' (completo)', monto]); return; }
        const gastado = Number(fila.querySelector('form.cc-rendir')?.dataset.gastado || 0);
        if (gastado > 0 && gastado < monto) {
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
      // Resumen: Gasto Cobra a rendir y lo Refacturable aparte (no se rinde).
      const refact = sol.items.filter(i => i.refacturable_auto).reduce((t, i) => t + Number(i.monto || 0), 0);
      const porSustentar = sol.items.filter(i => ['POR_RENDIR', 'RECHAZADO', 'EN_REVISION'].includes(i.estado))
        .reduce((t, i) => t + Number(i.monto || 0), 0);
      const aDevolver = sol.items.reduce((t, i) => t + saldoItem(i), 0);
      const resumen = el('div', 'cc-resumen-rendir');
      for (const [titulo, valor, clase] of [['Depositado', sol.deposito_monto || sol.total], ['Gasto Cobra a rendir', porSustentar, 'pend'],
        ...(refact ? [['Refacturable', refact, 'rf']] : []), ['A devolver', aDevolver, 'dev']]) {
        const caja = el('div', clase || null); caja.append(el('small', null, titulo), el('strong', null, dinero(valor))); resumen.append(caja);
      }
      detalle.append(resumen);
    }
    for (const item of sol.items) {
      const fila = el('section', 'card cc-item-fila cc-item-' + item.estado.toLowerCase() + (conRefacturable([item]) ? ' cc-con-refacturable' : ''));
      if (item.refacturable_auto) {
        // Refacturable: solo se muestra (no se rinde ni se devuelve).
        const cabRf = el('div', 'cc-item-cabecera'); cabRf.append(el('strong', null, item.numero + ' · ' + item.tipo_gasto), etiquetaTipo('Refacturable'));
        fila.append(cabRf, el('small', null, (item.descripcion ? item.descripcion + ' · ' : '') + dinero(item.monto)));
        detalle.append(fila);
        continue;
      }
      const cab = el('div', 'cc-item-cabecera');
      cab.append(el('strong', null, item.numero + ' · ' + item.tipo_gasto), el('span', 'cc-chip cc-' + item.estado.toLowerCase(), ITEM[item.estado]));
      fila.append(cab);
      if (tipoDe(item.tipo_presupuesto)) { const t = el('div', 'cc-tipos'); t.append(etiquetaTipo(tipoDe(item.tipo_presupuesto))); fila.append(t); }
      fila.append(el('small', null, (item.descripcion ? item.descripcion + ' · ' : '') + 'Solicitado ' + dinero(item.monto)));
      if (item.estado === 'APROBADO' || item.estado === 'EN_REVISION') {
        fila.append(el('p', 'cc-item-ok', (item.estado === 'APROBADO' ? '✓ Rendiste ' : 'Enviado · ') + dinero(item.monto_gastado)
          + ((item.comprobantes || []).length > 1 ? ' · ' + item.comprobantes.length + ' comprobantes' : item.comprobante ? ' · ' + item.comprobante : '')));
      }
      if (item.correccion) { const aviso = el('p', 'cc-item-motivo'); aviso.append(el('strong', null, 'Monto corregido: '), item.correccion); fila.append(aviso); }
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
  function pintar() {
    const total = datos.solicitudes.reduce((suma, sol) => suma + montoPendiente(sol), 0);
    $('cc-pendiente').textContent = dinero(total / 100);
    const refact = datos.solicitudes.filter(sol => ['DEPOSITADO', 'POR_DEVOLVER'].includes(sol.estado))
      .flatMap(sol => sol.items).filter(i => i.refacturable_auto).reduce((t, i) => t + Number(i.monto || 0), 0);
    $('cc-refacturable').hidden = !refact;
    $('cc-refacturable').replaceChildren(el('span', null, 'Refacturable'), el('strong', null, dinero(refact)));
    $('cc-restricciones').replaceChildren(restricciones());
    const lista = $('cc-lista');
    lista.replaceChildren();
    // Sin pestañas: el técnico solo ve lo que tiene por rendir.
    $('cc-filtros').replaceChildren();
    $('cc-filtros').hidden = true;
    const solicitudes = datos.solicitudes.filter(sol => ['DEPOSITADO', 'POR_DEVOLVER'].includes(sol.estado));
    if (!solicitudes.length) lista.append(el('p', 'empty', 'No tienes depósitos por rendir.'));
    for (const sol of solicitudes) {
      const ficha = el('button', 'deposit' + (conRefacturable(sol.items) ? ' cc-con-refacturable' : ''));
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
    catalogo.filter(concepto => !nombresSeleccionados.has(concepto.nombre))
      .forEach(concepto => filas.push([concepto]));
    $('cc-items').replaceChildren(...filas.map(([concepto, valores], indice) => {
      const card = $('cc-item-plantilla').content.firstElementChild.cloneNode(true);
      const checkbox = card.querySelector('[type=checkbox]');
      const detalle = card.querySelector('.expense-amount');
      card.dataset.descripcion = valores?.descripcion || '';
      card.querySelector('[data-nombre]').textContent = concepto.nombre;
      card.querySelector('.expense-criterion').textContent = concepto.descripcion || '';
      // Etiqueta de color: Gasto Cobra o Refacturable.
      const clasificacion = card.querySelector('.expense-classification');
      const tipo = tipoDe(concepto.proyectos[proyecto] || valores?.tipo_presupuesto);
      clasificacion.replaceChildren(...(tipo ? [etiquetaTipo(tipo)] : []));
      checkbox.value = concepto.nombre;
      checkbox.checked = Boolean(valores);
      detalle.querySelectorAll('[data-campo]').forEach(control => {
        control.id = 'cc-' + control.dataset.campo + '-' + indice;
        control.previousElementSibling.htmlFor = control.id;
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
    const form = $('cc-form'); form.reset(); pintarCci();
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
    const bloqueado = !sol && (datos.restricciones?.bloqueos || []).length > 0;
    form.querySelector('[type=submit]').disabled = bloqueado;
    form.classList.toggle('cc-bloqueado', bloqueado);
    $('cc-restricciones-form').replaceChildren(...(sol ? [] : [restricciones()]));
    $('cc-dni').value = datos.personal.documento || '';
    $('cc-tecnico').value = datos.personal.nombre || '';
    $('cc-supervisor').value = datos.personal.supervisor || '';
    if (sol) {
      $('cc-rechazo').textContent = 'Rechazada: ' + sol.motivo_rechazo;
      $('cc-motivo').value = sol.motivo;
      $('cc-banco').value = sol.banco; $('cc-cuenta').value = sol.cuenta;
      pintarCci();
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
  // CCI: exactamente 20 dígitos (ni más ni menos); el contador avisa cuántos faltan.
  function pintarCci() {
    const input = $('cc-cuenta'), n = input.value.length, ayuda = $('cc-cuenta-ayuda');
    ayuda.textContent = !n ? 'Debe tener exactamente 20 dígitos.' : n === 20 ? '✓ 20 de 20 dígitos' : n + ' de 20 dígitos · faltan ' + (20 - n);
    ayuda.dataset.estado = !n ? '' : n === 20 ? 'ok' : 'falta';
    input.setCustomValidity(n && n !== 20 ? 'El CCI debe tener exactamente 20 dígitos.' : '');
  }
  $('cc-cuenta').addEventListener('input', ({target}) => {
    target.value = target.value.replace(/[^0-9]/g, '').slice(0, 20);
    pintarCci();
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
  $('cc-exito-volver').addEventListener('click', () => { pintar(); ver('cc-inicio'); });
  document.querySelectorAll('[data-cc-volver]').forEach(b => b.addEventListener('click', () => ver('cc-inicio')));
  $('cc-form').addEventListener('submit', e => {
    e.preventDefault(); const form = e.currentTarget, error = form.querySelector('.error');
    enviando(form.querySelector('[type=submit]'), error, async () => {
      if (!/^[0-9]{20}$/.test($('cc-cuenta').value)) { $('cc-cuenta').focus(); throw Error('El CCI debe tener exactamente 20 dígitos (tienes ' + $('cc-cuenta').value.length + ').'); }
      // Un concepto marcado sin monto (vacío o 0) no se considera.
      const items = itemsSeleccionados().filter(item => numero(item.monto) > 0);
      if (!items.length) throw Error('Marca al menos un concepto y escribe su monto.');
      const cuerpo = {...Object.fromEntries(new FormData(form)), items};
      const ruta = corrigiendo ? '/' + corrigiendo.id + '/reenviar' : '/solicitar';
      const r = await api(ruta, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo)});
      $('cc-exito-titulo').textContent = corrigiendo ? '¡Solicitud reenviada!' : '¡Solicitud enviada!';
      $('codigo-exito').textContent = r.solicitud.codigo;
      $('total-exito').textContent = dinero(r.solicitud.total);
      datos.solicitudes = [r.solicitud, ...datos.solicitudes.filter(sol => sol.id !== r.solicitud.id)];
      try { datos.restricciones = (await api('/datos')).restricciones; } catch (_) {}
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
