/* FLM con el diseño de Caja Chica (mismas clases cc-*): barra con buscador, pestañas por estado y botones redondos.
   Solo diseño: reutiliza Nuevo WO, Menú, Excel y la paginación de la tabla clásica; no cambia datos ni funciones. */
(() => {
  'use strict';
  const main = document.querySelector('.excel-main.vista-flm');
  if (!main) return;
  const $ = id => document.getElementById(id);
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const icono = nombre => { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; };
  const plano = t => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  // Estados de "Task Status" agrupados como las pestañas de Caja Chica.
  const GRUPOS = [
    ['', 'Todos', '#3b82f6', 'fa-list'],
    ['pendiente', 'Pendiente', '#f59e0b', 'fa-clock'],
    ['proceso', 'En proceso', '#2563eb', 'fa-screwdriver-wrench'],
    ['completado', 'Completado', '#16a34a', 'fa-circle-check'],
    ['cancelado', 'Cancelado', '#94a3b8', 'fa-ban'],
  ];
  const grupoDe = estado => {
    const e = plano(estado);
    if (/cancel/.test(e)) return 'cancelado';
    if (/complet|closed|cerrad|culmin/.test(e)) return 'completado';
    if (/inprocess|process|arrive|depart|ejecuc/.test(e)) return 'proceso';
    return e ? 'pendiente' : '';
  };
  const CHIP = {pendiente: 'fv-chip-pendiente', proceso: 'fv-chip-proceso', completado: 'fv-chip-completado', cancelado: 'fv-chip-cancelado'};

  // ── SLA por proyecto ──
  // Claro (mismas reglas que la página SLA): CM desde Dispatch Time; PM y PLM desde Arrive Time. Objetivo: SLA Hour (min).
  //   Cerrado (completed/closed): termina en Complete Time y cumple según SLA Status.
  // Entel: desde dispatch_time hasta SubmitTime(complete), menos Total SLA Pause Duration (segundos).
  //   Objetivo según Fault Level (KPI OM Sitios): Crítica/Critical 4 h · Alta/Major 4 h · Media 6 h · Baja/Minor 48 h.
  //   "SLA Cobra" es nuestro cálculo, para contrastarlo con el SLA Status que trae la data.
  const esClaro = main.dataset.proyecto === 'FLM - CLARO';
  const esEntel = main.dataset.proyecto === 'FLM - ENTEL';
  const esIntegratel = main.dataset.proyecto === 'FLM - INTEGRATEL';
  const conSla = esClaro || esEntel || esIntegratel;
  // Integratel trae su estado de SLA en "Sla Status" (la otra columna, "SLA Status", es vieja).
  const CAMPO_ESTADO = esIntegratel ? 'Sla Status' : 'SLA Status';
  const PAUSAS = ['First', 'Second', 'Third', 'Fourth', 'Fifth'];
  const COLUMNAS_SLA = esEntel
    ? ['Ticket Status', 'Fault Level(create)', 'dispatch_time', 'SubmitTime(complete)', 'Total SLA Pause Duration', 'SLA Status']
    : esIntegratel
      ? ['Task Type', 'Task Status', 'Dispatch Time', 'First Complete Time', 'Require Finish Time', 'Sla', 'Sla Status', 'Reject Counter',
         ...PAUSAS.flatMap(n => [n + ' Pause Time', n + ' Resume Time'])]
      : ['Task Type', 'Task Status', 'Dispatch Time', 'Arrive Time', 'SLA Hour', 'Complete Time', 'SLA Status', 'Schedule Operator'];
  const estadoDe = f => f['Task Status'] ?? f['Ticket Status'];
  const POR_VENCER = [0.25, 60];
  const fecha = v => { const m = String(v || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/); return m ? new Date(m[1], m[2] - 1, m[3], m[4], m[5], m[6] || 0) : null; };
  const duracion = min => { min = Math.max(0, Math.round(min)); const d = Math.floor(min / 1440), h = Math.floor(min % 1440 / 60), m = min % 60; return d ? d + 'd ' + h + 'h' : h ? h + 'h ' + m + 'm' : m + 'm'; };
  // Abierto: azul en plazo, ámbar por vencer, rojo vencido.
  function abierto(pasado, objetivo, extra = '') {
    if (!objetivo) return {clase: 'fv-sla-gris', icono: 'fa-clock', texto: duracion(pasado), ayuda: 'Abierto hace ' + duracion(pasado) + ' · sin objetivo' + extra};
    const meta = ' · objetivo ' + duracion(objetivo) + extra;
    const resto = objetivo - pasado;
    if (resto < 0) return {clase: 'fv-sla-rojo', icono: 'fa-triangle-exclamation', texto: '+' + duracion(-resto), ayuda: 'Vencido hace ' + duracion(-resto) + meta};
    const urgente = resto <= objetivo * POR_VENCER[0] || resto <= POR_VENCER[1];
    return {clase: urgente ? 'fv-sla-ambar' : 'fv-sla-azul', icono: 'fa-hourglass-half', texto: duracion(resto),
      ayuda: (urgente ? 'Por vencer: quedan ' : 'En plazo: quedan ') + duracion(resto) + meta};
  }
  function cerrado(cumple, falla, usado, ayudaExtra) {
    return {clase: cumple ? 'fv-sla-verde' : falla ? 'fv-sla-rojo' : 'fv-sla-gris', icono: cumple ? 'fa-circle-check' : falla ? 'fa-circle-xmark' : 'fa-stopwatch',
      texto: usado === null ? (cumple ? 'Cumplió' : falla ? 'No cumplió' : 'Cerrado') : duracion(usado),
      ayuda: (cumple ? 'Cumplió el SLA' : falla ? 'No cumplió el SLA' : 'Cerrado') + (usado === null ? '' : ' en ' + duracion(usado)) + ayudaExtra};
  }
  function slaClaro(f) {
    const estado = plano(f['Task Status']);
    if (/cancel/.test(estado)) return null;
    let tipo = String(f['Task Type'] || '').trim().toUpperCase();
    if (!['CM', 'PM', 'PLM'].includes(tipo)) tipo = (String(f._key || '').toUpperCase().match(/^(CM|PLM|PM)\b/) || [])[1] || '';
    if (!tipo) return null;
    const inicio = fecha(tipo === 'CM' ? f['Dispatch Time'] : f['Arrive Time']);
    const objetivo = Number(f['SLA Hour']) > 0 ? Number(f['SLA Hour']) : null;
    if (!inicio) return {clase: 'fv-sla-gris', icono: 'fa-hourglass-start', texto: 'Sin inicio', ayuda: (tipo === 'CM' ? 'Falta Dispatch Time' : 'Falta Arrive Time')};
    if (/complet|closed/.test(estado)) {
      const fin = fecha(f['Complete Time'] || f['FECHA CAMBIO ESTADO']);
      const st = plano(f['SLA Status']), m = medidaClaro(f);
      return cerrado(st === 'normal', st.includes('violation'), m ? m.neto : fin ? (fin - inicio) / 60000 : null,
        (objetivo ? ' · objetivo ' + duracion(objetivo) : '') + (m && m.pausa ? ' · parada de reloj ' + duracion(m.pausa) : ''));
    }
    const m = medidaClaro(f);
    return abierto(m ? m.neto : (Date.now() - inicio) / 60000, objetivo, m && m.pausa ? ' · parada de reloj ' + duracion(m.pausa) : '');
  }

  const OBJETIVO_ENTEL = {critica: 4, critical: 4, alta: 4, major: 4, media: 6, baja: 48, minor: 48, calidad: 720};  // calidad = 30 días
  const nivelEntel = f => String(f['Fault Level(create)'] || f['Fault Level'] || '').trim();
  const objetivoEntel = f => OBJETIVO_ENTEL[plano(nivelEntel(f))] ?? null;
  const pausaEntel = f => { const s = Number(String(f['Total SLA Pause Duration'] ?? '').trim()); return s > 0 ? s / 60 : 0; };  // segundos → minutos
  // Minutos netos de SLA (sin la parada de reloj); fin = null si sigue abierto.
  function medidaEntel(f) {
    const inicio = fecha(f['dispatch_time']);
    if (!inicio) return null;
    const fin = fecha(f['SubmitTime(complete)'] || f['complete_time']);
    return {fin, neto: Math.max(0, ((fin || Date.now()) - inicio) / 60000 - pausaEntel(f))};
  }
  // SLA Cobra: "normal" si el tiempo neto no pasó el objetivo; "sla_violation" si lo pasó.
  // Claro: CM desde Dispatch Time, PM/PLM desde Arrive Time, hasta Complete Time; objetivo SLA Hour (min).
  function medidaClaro(f) {
    if (/cancel/.test(plano(f['Task Status']))) return null;
    let tipo = String(f['Task Type'] || '').trim().toUpperCase();
    if (!['CM', 'PM', 'PLM'].includes(tipo)) tipo = (String(f._key || '').toUpperCase().match(/^(CM|PLM|PM)/) || [])[1] || '';
    const inicio = fecha(tipo === 'CM' ? f['Dispatch Time'] : f['Arrive Time']);
    const objetivo = Number(f['SLA Hour']) > 0 ? Number(f['SLA Hour']) : null;
    if (!tipo || !inicio || !objetivo) return null;
    const cerrado = /complet|closed/.test(plano(f['Task Status']));
    const fin = cerrado ? fecha(f['Complete Time'] || f['FECHA CAMBIO ESTADO']) : null;
    if (cerrado && !fin) return null;
    // Parada de reloj: Require Finish Time = inicio + SLA Hour + pausa (así lo calcula Claro; coincide con su SLA Status).
    const limite = fecha(f['Require Finish Time']);
    const pausa = limite ? Math.max(0, (limite - inicio) / 60000 - objetivo) : 0;
    return {fin, neto: ((fin || Date.now()) - inicio) / 60000 - pausa, objetivo, pausa};
  }
  // Integratel (coincide con su Sla Status en el 99 % de los CM):
  //   CM: Dispatch Time → First Complete Time (el primer cierre; si lo rechazan y se reabre, eso no cuenta) − pausas
  //       (First…Fifth Pause → Resume Time), contra Sla (minutos).
  //   PM / PLM no traen Sla: el límite es Require Finish Time (objetivo = Require Finish Time − Dispatch Time).
  const rechazosIntegratel = f => { const n = Number(String(f['Reject Counter'] ?? '').trim()); return n > 0 ? n : 0; };
  function medidaIntegratel(f) {
    if (/cancel/.test(plano(f['Task Status']))) return null;
    const inicio = fecha(f['Dispatch Time']);
    if (!inicio) return null;
    const cerrado = /complet|closed/.test(plano(f['Task Status']));
    const fin = cerrado ? fecha(f['First Complete Time'] || f['Complete Time']) : null;
    if (cerrado && !fin) return null;
    const hasta = fin || new Date();
    if (tipoDe(f) === 'CM') {
      const objetivo = Number(f['Sla']) > 0 ? Number(f['Sla']) : null;
      let pausa = 0;
      PAUSAS.forEach(n => {
        const p = fecha(f[n + ' Pause Time']);
        if (!p || p >= hasta) return;
        const r = fecha(f[n + ' Resume Time']), cierre = r && r < hasta ? r : hasta;
        pausa += Math.max(0, (cierre - p) / 60000);
      });
      return {fin, neto: Math.max(0, (hasta - inicio) / 60000 - pausa), objetivo, pausa};
    }
    const limite = fecha(f['Require Finish Time']);
    const objetivo = limite && limite > inicio ? (limite - inicio) / 60000 : null;
    return {fin, neto: (hasta - inicio) / 60000, objetivo, pausa: 0};
  }
  function slaIntegratel(f) {
    if (/cancel/.test(plano(f['Task Status']))) return null;
    const m = medidaIntegratel(f);
    if (!m) return {clase: 'fv-sla-gris', icono: 'fa-hourglass-start', texto: 'Sin inicio', ayuda: 'Falta Dispatch Time'};
    const pausa = m.pausa ? ' · parada de reloj ' + duracion(m.pausa) : '';
    const meta = m.objetivo ? ' · objetivo ' + duracion(m.objetivo) : tipoDe(f) === 'CM' ? ' · sin Sla' : ' · sin Require Finish Time';
    const rech = rechazosIntegratel(f) ? ' · rechazado ' + rechazosIntegratel(f) + ' vez/veces (cuenta hasta el primer cierre)' : '';
    if (!m.fin) {
      const estado = abierto(m.neto, m.objetivo, pausa);
      return {...estado, icono: 'fa-stopwatch', texto: duracion(m.neto), ayuda: 'Transcurrido ' + duracion(m.neto) + ' · ' + estado.ayuda};
    }
    const cobra = slaCobra(f), data = plano(f[CAMPO_ESTADO]);
    const contraste = data && cobra && data !== cobra ? ' · ⚠ la data dice ' + f[CAMPO_ESTADO] : '';
    return cerrado(cobra === 'normal', cobra === 'sla_violation', m.neto, meta + pausa + rech + contraste);
  }
  // SLA Cobra: "normal" si el tiempo neto no pasó el objetivo; "sla_violation" si lo pasó (abiertos: solo si ya venció).
  function slaCobra(f) {
    if (esIntegratel) {
      if (/cancel/.test(plano(f['Task Status']))) return '';
      if (tipoDe(f) === 'CM' && !(Number(f['Sla']) > 0)) return 'sin_sla';
      const m = medidaIntegratel(f);
      if (!m || !m.objetivo) return '';
      if (m.neto > m.objetivo) return 'sla_violation';
      return m.fin ? 'normal' : '';
    }
    if (esClaro) {
      // SLA Hour vacío o en 0: se marcan para tenerlos ubicados (no se puede medir sin objetivo).
      const hora = String(f['SLA Hour'] ?? '').trim();
      if (!hora) return 'sin_sla_hour';
      if (Number(hora) === 0) return 'sla_hour_0';
      const m = medidaClaro(f);
      if (!m) return '';
      if (m.neto > m.objetivo) return 'sla_violation';
      return m.fin ? 'normal' : '';
    }
    const m = medidaEntel(f), horas = objetivoEntel(f);
    if (!m || horas === null) return '';
    if (m.neto > horas * 60) return 'sla_violation';
    return m.fin ? 'normal' : '';
  }
  function slaEntel(f) {
    if (/cancel/.test(plano(estadoDe(f)))) return null;
    const m = medidaEntel(f), horas = objetivoEntel(f);
    if (!m) return {clase: 'fv-sla-gris', icono: 'fa-hourglass-start', texto: 'Sin inicio', ayuda: 'Falta dispatch_time'};
    const pausa = pausaEntel(f) ? ' · parada de reloj ' + duracion(pausaEntel(f)) : '';
    if (!m.fin) {
      // Abierto: muestra el tiempo que va transcurriendo (sin la parada de reloj); el color dice cómo va.
      const estado = abierto(m.neto, horas === null ? null : horas * 60, pausa);
      return {...estado, icono: 'fa-stopwatch', texto: duracion(m.neto), ayuda: 'Transcurrido ' + duracion(m.neto) + ' · ' + estado.ayuda};
    }
    const cobra = slaCobra(f), data = plano(f['SLA Status']);
    const contraste = data && cobra && data !== cobra ? ' · ⚠ la data dice ' + f['SLA Status'] : '';
    return cerrado(cobra === 'normal', cobra === 'sla_violation', m.neto,
      (horas === null ? ' · sin objetivo (Fault Level ' + (nivelEntel(f) || 'vacío') + ')' : ' · objetivo ' + horas + ' h') + pausa + contraste);
  }
  const sla = f => (esEntel ? slaEntel(f) : esIntegratel ? slaIntegratel(f) : slaClaro(f));
  function chipSla(f) {
    const s = sla(f);
    if (!s) return el('span', 'fv-sla fv-sla-vacio', '—');
    const chip = el('span', 'fv-sla ' + s.clase);
    chip.title = s.ayuda; chip.setAttribute('aria-label', 'SLA: ' + s.ayuda);
    chip.append(icono(s.icono), el('span', null, s.texto));
    return chip;
  }

  let tabla = null, grupo = '', texto = '', filtro = null, tipo = '';
  try { grupo = localStorage.getItem('fv-grupo') || ''; tipo = localStorage.getItem('fv-tipo') || ''; } catch (_) {}
  // Tipo de ticket: Task Type (CM, PM o PLM); si no lo trae, el prefijo del N.º de ticket (CM-…, PM-…, PLM-…).
  const tipoDe = f => {
    const t = String(f['Task Type'] || '').trim().toUpperCase();
    if (['CM', 'PM', 'PLM'].includes(t)) return t;
    return (String(f._key || f['Ticket ID'] || '').toUpperCase().match(/^(CM|PLM|PM)/) || [])[1] || '';
  };

  // ── Barra (mismo marcado que Caja Chica) ──
  const gestion = el('section', 'cc-gestion fv-gestion');
  const barra = el('div', 'cc-barra');
  const buscar = Object.assign(el('input'), {type: 'search', id: 'cc-buscar', placeholder: 'Buscar ticket, site, operador o WO'});
  buscar.setAttribute('aria-label', 'Buscar en la tabla');
  const pestanas = el('nav', 'cc-tabs'); pestanas.setAttribute('role', 'tablist'); pestanas.setAttribute('aria-label', 'Estado del ticket');
  const acciones = el('div', 'fv-acciones');
  // Todos · CM · PM · PLM (igual que en la página SLA).
  const tipos = el('nav', 'sla-tipos fv-tipos'); tipos.setAttribute('aria-label', 'Tipo de ticket');
  ['', 'CM', 'PM', 'PLM'].forEach(t => {
    const b = el('button', 'sla-tipo' + (tipo === t ? ' activo' : ''), t || 'Todos'); b.type = 'button'; b.dataset.tipo = t;
    b.setAttribute('aria-pressed', String(tipo === t));
    b.addEventListener('click', () => {
      tipo = t; try { localStorage.setItem('fv-tipo', tipo); } catch (_) {}
      tipos.querySelectorAll('.sla-tipo').forEach(x => { x.classList.toggle('activo', x.dataset.tipo === tipo); x.setAttribute('aria-pressed', String(x.dataset.tipo === tipo)); });
      aplicar();
    });
    tipos.append(b);
  });
  barra.append(buscar, pestanas, tipos, acciones);
  gestion.append(barra);
  let espera;
  buscar.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => { texto = buscar.value; aplicar(); }, 200); });

  function aplicar() {
    if (filtro) tabla.removeFilter(filtro);
    const campos = tabla.getColumns().filter(c => c.isVisible() && c.getField()).map(c => c.getField());
    const q = plano(texto.trim());
    filtro = fila => (!tipo || tipoDe(fila) === tipo) && (!grupo || grupoDe(estadoDe(fila)) === grupo) && (!q || campos.some(c => plano(fila[c]).includes(q)));
    tabla.addFilter(filtro);
    pintarPestanas();
  }

  function pintarPestanas() {
    // Las pestañas cuentan solo el tipo elegido (CM, PM o PLM).
    const datos = tabla.getData().filter(f => !tipo || tipoDe(f) === tipo), cuenta = {};
    datos.forEach(f => { const g = grupoDe(estadoDe(f)); cuenta[g] = (cuenta[g] || 0) + 1; });
    pestanas.replaceChildren(...GRUPOS.map(([clave, nombre, color, simbolo]) => {
      const b = el('button', 'cc-tab' + (grupo === clave ? ' activa' : '')); b.type = 'button'; b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(grupo === clave)); b.style.setProperty('--cc-color', color);
      const fila = el('span', 'cc-tab-fila');
      const n = clave ? cuenta[clave] || 0 : datos.length;
      fila.append(icono(simbolo), el('span', null, nombre), el('span', 'cc-cuenta', n.toLocaleString('es-PE')));
      // Segunda línea como en Caja Chica: en vez del monto, la parte del total.
      const parte = datos.length ? Math.round(n * 100 / datos.length) : 0;
      b.append(fila, el('span', 'cc-plata', clave ? parte + '% del total' : 'tickets'));
      b.addEventListener('click', () => { grupo = clave; try { localStorage.setItem('fv-grupo', grupo); } catch (_) {} aplicar(); });
      return b;
    }));
  }

  // Botones redondos al final: Nuevo WO, Excel y Menú (los mismos de la vista clásica).
  function moverBotones() {
    const nuevo = document.querySelector('.topbar-row .coti-new-record');
    if (nuevo) { nuevo.classList.add('fv-redondo', 'fv-verde'); acciones.append(nuevo); }
    if (typeof window.descargarExcel === 'function' || $('btn-top-export')) {
      const excel = el('button', 'cc-excel fv-excel'); excel.type = 'button'; excel.id = 'cc-excel';
      excel.title = 'Exportar a Excel'; excel.setAttribute('aria-label', 'Exportar a Excel'); excel.append(icono('fa-file-excel'));
      excel.addEventListener('click', () => ($('btn-top-export') ? $('btn-top-export').click() : window.descargarExcel()));
      acciones.append(excel);
    }
    const menu = $('module-settings-wrap');
    if (menu) { menu.classList.add('cc-ajustes'); $('btn-module-settings')?.classList.add('cc-ajustes-btn'); acciones.append(menu); }
  }

  // Contador y paginación debajo de la tabla (la barra queda como en Caja Chica).
  function moverPaginacion() {
    const pie = el('div', 'fv-pie');
    const cuenta = $('status-record-count'), paginas = $('pagination-container');
    if (cuenta) pie.append(cuenta);
    if (paginas) pie.append(paginas);
    $('data-grid').after(pie);
  }

  // Encabezado como Caja Chica: TÍTULO · ordenar · filtrar en una línea y "Buscar…" debajo.
  function ajustarEncabezado() {
    document.querySelectorAll('#data-grid .tabulator-col').forEach(col => {
      const holder = col.querySelector('.tabulator-col-title-holder');
      const filtroCol = col.querySelector('.tabulator-col-title .tabulator-header-popup-button');
      if (holder && filtroCol) holder.append(filtroCol);
      const input = col.querySelector('.tabulator-header-filter input');
      if (input && !input.placeholder) input.placeholder = 'Buscar…';
    });
  }

  // Ajusta las columnas de la tabla (chips, Acciones, SLA) sobre sus definiciones, en un solo paso.
  // table-controller la llama ANTES de crear la tabla: así no se redibuja la tabla una vez por cada columna.
  function ajustarColumnas(defs) {
    const col = campo => defs.find(d => d && d.field === campo);
    const poner = (campo, props) => { const d = col(campo); if (d) Object.assign(d, props); return d; };
    const indice = campo => defs.findIndex(d => d && d.field === campo);
    if (col('_fv_acciones')) return defs;
    // El N.º de ticket completo, sin cortarse.
    const clave = col('_key');
    if (clave) Object.assign(clave, {minWidth: 200, width: Math.max(200, Number(clave.width) || 0)});
    // Estado como chip de color (solo cómo se ve).
    ['Task Status', 'Ticket Status'].forEach(c => poner(c, {formatter: celda => {
      const v = celda.getValue(); return v ? el('span', 'fv-chip ' + (CHIP[grupoDe(v)] || ''), v) : '';
    }}));
    // SLA Status: normal en verde, sla_violation en rojo.
    poner(CAMPO_ESTADO, {formatter: celda => {
      const v = String(celda.getValue() ?? '').trim(), e = plano(v);
      if (!v) return '';
      const clase = e === 'normal' ? 'fv-chip-sla-ok' : e.includes('violation') ? 'fv-chip-sla-mal' : '';
      return clase ? el('span', 'fv-chip ' + clase, v) : v;
    }});
    // Acciones: botón redondo que abre el mismo detalle que el clic en el ticket (antes del N.º de ticket).
    if (clave) {
      const ancho = conSla ? 168 : 92;
      defs.splice(indice('_key'), 0, {title: 'Acciones', field: '_fv_acciones', headerSort: false, headerFilter: false, width: ancho, minWidth: ancho, hozAlign: 'center', download: false,
        formatter: celda => {
          const b = el('button', 'fv-accion'); b.type = 'button'; b.title = 'Ver / editar';
          b.setAttribute('aria-label', 'Ver o editar ' + (celda.getRow().getData()._key || ''));
          b.append(icono('fa-pen'));
          b.addEventListener('click', e => {
            e.stopPropagation();
            const destino = celda.getRow().getCell('_key')?.getElement();
            (destino?.querySelector('.wo-link') || destino)?.click();
          });
          if (!conSla) return b;
          const caja = el('div', 'fv-acciones-celda');
          caja.append(b, chipSla(celda.getRow().getData()));
          return caja;
        }});
    }
    if (esEntel) {
      // Fault Level y su objetivo de SLA en un solo chip ("Media · 6 h"), así no se suma otra columna.
      const colNivel = ['Fault Level(create)', 'Fault Level'].find(col);
      if (colNivel) poner(colNivel, {hozAlign: 'left', headerTooltip: 'Objetivo SLA según Fault Level: Crítica/Critical 4 h · Alta/Major 4 h · Media 6 h · Baja/Minor 48 h · Calidad 30 días',
        sorter: (a, b, filaA, filaB) => (objetivoEntel(filaA.getData()) ?? 1e9) - (objetivoEntel(filaB.getData()) ?? 1e9),
        formatter: celda => {
          const f = celda.getRow().getData(), nivel = nivelEntel(f), horas = objetivoEntel(f);
          if (!nivel) return '';
          const clase = {critica: 'critica', critical: 'critica', alta: 'alta', major: 'alta', media: 'media', baja: 'baja', minor: 'baja', calidad: 'calidad'}[plano(nivel)];
          const chip = el('span', 'fv-nivel ' + (clase ? 'fv-nivel-' + clase : 'fv-nivel-otro'));
          chip.title = horas === null ? nivel + ': sin objetivo de SLA' : nivel + ': SLA ' + horas + ' horas';
          chip.append(el('span', null, nivel), el('span', 'fv-nivel-horas', horas === null ? '· sin regla' : horas >= 720 ? '· ' + horas / 24 + ' días' : '· ' + horas + ' h'));
          return chip;
        }});
    }
    if (conSla) {
      // SLA Cobra: nuestro cálculo con los mismos estados que SLA Status, para contrastar. ⚠ si no coinciden.
      const tras = indice(CAMPO_ESTADO);
      // Se guarda el cálculo en la fila (mutator) para poder filtrar y buscar como cualquier columna, con el mismo embudo que SLA Status.
      const filtroDe = col(CAMPO_ESTADO) || {};
      defs.splice(tras >= 0 ? tras + 1 : indice('_key') + 1, 0, {title: 'SLA Cobra', field: '_fv_sla_cobra', headerSort: true, width: 150, minWidth: 140, hozAlign: 'left', download: true,
        mutator: (valor, fila) => slaCobra(fila),
        headerFilter: filtroDe.headerFilter ?? 'input', headerFilterFunc: filtroDe.headerFilterFunc ?? 'like', headerFilterParams: filtroDe.headerFilterParams,
        headerFilterPlaceholder: filtroDe.headerFilterPlaceholder, headerPopup: filtroDe.headerPopup, headerPopupIcon: filtroDe.headerPopupIcon,
        cssClass: 'fv-col-sla', headerTooltip: esEntel ? 'Cálculo Cobra: dispatch_time → SubmitTime(complete) − parada de reloj, contra el objetivo por Fault Level'
          : esIntegratel ? 'Cálculo Cobra: CM Dispatch Time → First Complete Time − pausas, contra Sla (min) · PM/PLM: cierre antes de Require Finish Time'
          : 'Cálculo Cobra: CM desde Dispatch Time, PM/PLM desde Arrive Time, hasta Complete Time, contra SLA Hour',
        sorter: (a, b, filaA, filaB) => slaCobra(filaA.getData()).localeCompare(slaCobra(filaB.getData())),
        formatter: celda => {
          const f = celda.getRow().getData(), v = slaCobra(f);
          if (!v) return '';
          const medible = v === 'normal' || v === 'sla_violation';
          const chip = el('span', 'fv-chip ' + (v === 'normal' ? 'fv-chip-sla-ok' : v === 'sla_violation' ? 'fv-chip-sla-mal' : 'fv-chip-sla-sin'), v);
          if (!medible) { chip.title = v === 'sla_hour_0' ? 'SLA Hour = 0: sin objetivo para medir' : v === 'sin_sla' ? 'Sla vacío: sin objetivo para medir' : 'SLA Hour vacío: sin objetivo para medir'; return chip; }
          const data = plano(f[CAMPO_ESTADO]);
          const caja = el('span', 'fv-sla-contraste');
          caja.append(chip);
          if (data && data !== v) {
            caja.title = 'No coincide: la data dice ' + f[CAMPO_ESTADO] + ' y el cálculo Cobra dice ' + v;
            caja.append(icono('fa-triangle-exclamation'));
          }
          // Integratel: aviso de rechazo aparte (el SLA se mide hasta el primer cierre).
          const rech = esIntegratel ? rechazosIntegratel(f) : 0;
          if (rech) {
            const r = el('span', 'fv-rechazo'); r.title = 'Rechazado ' + rech + (rech === 1 ? ' vez' : ' veces') + ': el SLA se mide hasta el primer cierre';
            r.append(icono('fa-rotate-left'), el('span', null, String(rech))); caja.append(r);
          }
          return caja.childNodes.length > 1 ? caja : chip;
        }});
    }
    if (esEntel) {
      // Viene en segundos: se muestra en horas y minutos (el número original queda al pasar el mouse).
      poner('Total SLA Pause Duration', {formatter: celda => {
        const s = Number(String(celda.getValue() ?? '').trim());
        if (!(s > 0)) return '';
        const t = el('span', null, duracion(s / 60)); t.title = s + ' segundos'; return t;
      }});
    }
    if (conSla) {
      // Columnas que usa el SLA: cabecera y celdas con color.
      COLUMNAS_SLA.forEach(campo => {
        const d = col(campo);
        if (!d) return;
        const clases = new Set(String(d.cssClass || '').split(' ').filter(Boolean)).add('fv-col-sla');
        Object.assign(d, {cssClass: [...clases].join(' '), headerTooltip: 'Se usa para calcular el SLA'});
      });
    }
    return defs;
  }
  window.FlmVista = {columnas: ajustarColumnas};

  function preparar(t) {
    tabla = t;
    const fila = document.querySelector('.topbar-row');
    if (fila && !document.querySelector('.fv-gestion')) {
      fila.before(gestion);
      moverBotones();
      moverPaginacion();
      fila.classList.add('fv-oculta');
    }
    ajustarEncabezado();
    // Con la cabecera ya ordenada, la tabla recalcula su alto para no tapar los buscadores.
    setTimeout(() => tabla.redraw(), 0);
    // Las columnas ya vienen ajustadas (FlmVista.columnas, antes de crear la tabla). Si no, se ajustan aquí en un solo paso.
    if (!tabla.getColumn('_fv_acciones') && tabla.getColumn('_key')) tabla.setColumns(ajustarColumnas(tabla.getColumnDefinitions()));
    const cab = document.querySelector('#data-grid .tabulator-header');
    if (cab) new MutationObserver(() => { clearTimeout(ajustarEncabezado.t); ajustarEncabezado.t = setTimeout(ajustarEncabezado, 50); }).observe(cab, {childList: true, subtree: true});
    if (conSla) {
      // El cronómetro del SLA se actualiza cada minuto: solo el chip de las filas en pantalla, sin redibujar la fila.
      setInterval(() => {
        try {
          tabla.getRows('visible').forEach(r => {
            const viejo = r.getElement().querySelector('.fv-acciones-celda .fv-sla');
            if (viejo) viejo.replaceWith(chipSla(r.getData()));
          });
        } catch (_) {}
      }, 60000);
    }
    main.classList.add('fv-lista');  // ya con el diseño nuevo: se muestra
    tabla.on('dataLoaded', () => setTimeout(pintarPestanas, 0));
    tabla.on('dataChanged', () => setTimeout(pintarPestanas, 0));
    if (grupo || tipo) aplicar(); else pintarPestanas();
  }

  // La tabla clásica se crea en otro script: se espera a que exista y tenga datos.
  let intentos = 0;
  const esperar = setInterval(() => {
    const t = window.Tabulator?.findTable?.('#data-grid')?.[0];
    // Con datos, o tras 5 s aunque el proyecto esté vacío, se arma el diseño nuevo.
    if (t && t.initialized !== false && (t.getData().length || intentos > 25)) { clearInterval(esperar); preparar(t); }
    else if (++intentos > 150) { clearInterval(esperar); main.classList.add('fv-lista'); }
  }, 200);
})();
