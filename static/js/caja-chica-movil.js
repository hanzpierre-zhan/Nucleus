/* Caja Chica en el celular del depositante: lista Por depositar y depósito con captura.
   Usa el mismo flujo y las mismas reglas de la gestión: /api/caja-chica/<id>/depositar. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const dinero = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const plano = t => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const PROYECTOS = {CLARO: 'Claro', ENTEL: 'Entel', INTEGRATEL: 'Integratel', PEXT: 'PEXT'};
  let solicitudes = [], abierta = null;

  function ver(id) { ['cm-lista-vista', 'cm-detalle-vista', 'cm-exito'].forEach(v => { $(v).hidden = v !== id; }); window.scrollTo({top: 0}); }

  async function cargar() {
    const r = await fetch('/api/caja-chica/solicitudes', {credentials: 'same-origin'});
    if (r.status === 401 || r.redirected) { location.href = '/login'; return; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { $('cm-lista').replaceChildren(el('p', 'error', j.error || 'No se pudo cargar.')); return; }
    // Por depositar: solicitudes ya validadas (pestaña Depósito de la gestión).
    solicitudes = j.solicitudes.filter(s => s.estado === 'VALIDADO').sort((a, b) => a.id - b.id);
    pintarLista();
  }

  function pintarLista() {
    const total = solicitudes.reduce((t, s) => t + Number(s.total), 0);
    $('cm-total').textContent = dinero(total);
    $('cm-cantidad').textContent = solicitudes.length === 1 ? '1 solicitud' : solicitudes.length + ' solicitudes';
    const texto = plano($('cm-buscar').value.trim());
    const lista = solicitudes.filter(s => !texto || plano([s.codigo, s.tecnico, s.documento, s.proyecto].join(' ')).includes(texto));
    const cont = $('cm-lista'); cont.replaceChildren();
    if (!lista.length) { cont.append(el('p', 'hint cm-vacio', solicitudes.length ? 'Ninguna solicitud coincide.' : 'No hay solicitudes por depositar. 🎉')); return; }
    for (const s of lista) {
      const b = el('button', 'card cm-item'); b.type = 'button';
      const izq = el('span', 'cm-item-izq');
      const linea = el('span', 'cm-item-codigo'); linea.append(el('strong', null, s.codigo), el('span', 'cm-chip cm-' + s.proyecto.toLowerCase(), PROYECTOS[s.proyecto] || s.proyecto));
      izq.append(linea, el('small', null, s.tecnico + ' · ' + (s.formulario?.tipo_billetera && s.formulario.tipo_billetera !== 'No aplica' ? s.formulario.tipo_billetera : s.banco)));
      b.append(izq, el('strong', 'cm-item-monto', dinero(s.total)));
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

  function abrir(s) {
    abierta = s;
    const f = s.formulario || {};
    $('cm-codigo').textContent = s.codigo + ' · ' + dinero(s.total);
    const billetera = f.tipo_billetera && f.tipo_billetera !== 'No aplica';
    $('cm-detalle').replaceChildren(
      // Depositar a: lo que se copia al banco.
      tarjeta('Depositar a', dl => {
        fila(dl, 'Titular', f.titular || s.tecnico);
        fila(dl, 'Banco', s.banco);
        fila(dl, 'CCI', s.cuenta, s.cuenta);
        if (billetera) fila(dl, f.tipo_billetera, f.numero_billetera, f.numero_billetera);
        fila(dl, 'Monto', dinero(s.total), Number(s.total).toFixed(2));
      }),
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
        for (const i of s.items) fila(dl, i.tipo_gasto + (i.tipo_presupuesto ? ' · ' + i.tipo_presupuesto : ''), dinero(i.monto));
      }));
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

  $('cm-volver').addEventListener('click', () => ver('cm-lista-vista'));
  $('cm-exito-volver').addEventListener('click', () => ver('cm-lista-vista'));
  $('cm-buscar').addEventListener('input', pintarLista);
  cargar();
})();
