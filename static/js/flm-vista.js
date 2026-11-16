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
  const conSla = esClaro || esEntel;
  const COLUMNAS_SLA = esEntel
    ? ['Ticket Status', 'Fault Level(create)', 'dispatch_time', 'SubmitTime(complete)', 'Total SLA Pause Duration', 'SLA Status']
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
      const st = plano(f['SLA Status']);
      return cerrado(st === 'normal', st.includes('violation'), fin ? (fin - inicio) / 60000 : null, objetivo ? ' · objetivo ' + duracion(objetivo) : '');
    }
    return abierto((Date.now() - inicio) / 60000, objetivo);
  }

  const OBJETIVO_ENTEL = {critica: 4, critical: 4, alta: 4, major: 4, media: 6, baja: 48, minor: 48};
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
  function slaCobra(f) {
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
  const sla = f => (esEntel ? slaEntel(f) : slaClaro(f));
  function chipSla(f) {
    const s = sla(f);
    if (!s) return el('span', 'fv-sla fv-sla-vacio', '—');
    const chip = el('span', 'fv-sla ' + s.clase);
    chip.title = s.ayuda; chip.setAttribute('aria-label', 'SLA: ' + s.ayuda);
    chip.append(icono(s.icono), el('span', null, s.texto));
    return chip;
  }

  let tabla = null, grupo = '', texto = '', filtro = null;
  try { grupo = localStorage.getItem('fv-grupo') || ''; } catch (_) {}

  // ── Barra (mismo marcado que Caja Chica) ──
  const gestion = el('section', 'cc-gestion fv-gestion');
  const barra = el('div', 'cc-barra');
  const buscar = Object.assign(el('input'), {type: 'search', id: 'cc-buscar', placeholder: 'Buscar ticket, site, operador o WO'});
  buscar.setAttribute('aria-label', 'Buscar en la tabla');
  const pestanas = el('nav', 'cc-tabs'); pestanas.setAttribute('role', 'tablist'); pestanas.setAttribute('aria-label', 'Estado del ticket');
  const acciones = el('div', 'fv-acciones');
  barra.append(buscar, pestanas, acciones);
  gestion.append(barra);
  let espera;
  buscar.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => { texto = buscar.value; aplicar(); }, 200); });

  function aplicar() {
    if (filtro) tabla.removeFilter(filtro);
    const campos = tabla.getColumns().filter(c => c.isVisible() && c.getField()).map(c => c.getField());
    const q = plano(texto.trim());
    filtro = fila => (!grupo || grupoDe(estadoDe(fila)) === grupo) && (!q || campos.some(c => plano(fila[c]).includes(q)));
    tabla.addFilter(filtro);
    pintarPestanas();
  }

  function pintarPestanas() {
    const datos = tabla.getData(), cuenta = {};
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
    // El N.º de ticket completo, sin cortarse.
    // Ancho mínimo fijo: así ni el diseño guardado ni el redibujo lo vuelven a cortar.
    if (tabla.getColumn('_key')) tabla.updateColumnDefinition('_key', {minWidth: 200, width: Math.max(200, tabla.getColumn('_key').getWidth())});
    const cab = document.querySelector('#data-grid .tabulator-header');
    if (cab) new MutationObserver(() => { clearTimeout(ajustarEncabezado.t); ajustarEncabezado.t = setTimeout(ajustarEncabezado, 50); }).observe(cab, {childList: true, subtree: true});
    // Estado como chip de color (solo cómo se ve).
    ['Task Status', 'Ticket Status'].filter(c => tabla.getColumn(c)).forEach(c => {
      tabla.updateColumnDefinition(c, {formatter: celda => {
        const v = celda.getValue(); return v ? el('span', 'fv-chip ' + (CHIP[grupoDe(v)] || ''), v) : '';
      }});
    });
    // SLA Status: normal en verde, sla_violation en rojo.
    if (tabla.getColumn('SLA Status')) {
      tabla.updateColumnDefinition('SLA Status', {formatter: celda => {
        const v = String(celda.getValue() ?? '').trim(), e = plano(v);
        if (!v) return '';
        const clase = e === 'normal' ? 'fv-chip-sla-ok' : e.includes('violation') ? 'fv-chip-sla-mal' : '';
        return clase ? el('span', 'fv-chip ' + clase, v) : v;
      }});
    }
    // Acciones: botón redondo que abre el mismo detalle que el clic en el ticket.
    if (!tabla.getColumn('_fv_acciones') && tabla.getColumn('_key')) {
      const ancho = conSla ? 168 : 92;
      tabla.addColumn({title: 'Acciones', field: '_fv_acciones', headerSort: false, headerFilter: false, width: ancho, minWidth: ancho, hozAlign: 'center', download: false,
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
        }}, true, '_key');
    }
    // Entel: Fault Level y su objetivo de SLA en un solo chip ("Media · 6 h"), así no se suma otra columna.
    const colNivel = esEntel && ['Fault Level(create)', 'Fault Level'].find(c => tabla.getColumn(c));
    if (colNivel) {
      tabla.updateColumnDefinition(colNivel, {hozAlign: 'left', headerTooltip: 'Objetivo SLA según Fault Level: Crítica/Critical 4 h · Alta/Major 4 h · Media 6 h · Baja/Minor 48 h',
        sorter: (a, b, filaA, filaB) => (objetivoEntel(filaA.getData()) ?? 1e9) - (objetivoEntel(filaB.getData()) ?? 1e9),
        formatter: celda => {
          const f = celda.getRow().getData(), nivel = nivelEntel(f), horas = objetivoEntel(f);
          if (!nivel) return '';
          const clase = {critica: 'critica', critical: 'critica', alta: 'alta', major: 'alta', media: 'media', baja: 'baja', minor: 'baja'}[plano(nivel)];
          const chip = el('span', 'fv-nivel ' + (clase ? 'fv-nivel-' + clase : 'fv-nivel-otro'));
          chip.title = horas === null ? nivel + ': sin objetivo de SLA' : nivel + ': SLA ' + horas + ' horas';
          chip.append(el('span', null, nivel), el('span', 'fv-nivel-horas', horas === null ? '· sin regla' : '· ' + horas + ' h'));
          return chip;
        }});
    }
    if (esEntel && !tabla.getColumn('_fv_sla_cobra')) {
      // SLA Cobra: nuestro cálculo con los mismos estados que SLA Status, para contrastar. ⚠ si no coinciden.
      const pos = tabla.getColumn('SLA Status') ? 'SLA Status' : '_key';
      tabla.addColumn({title: 'SLA Cobra', field: '_fv_sla_cobra', headerSort: true, headerFilter: false, width: 150, minWidth: 140, hozAlign: 'left', download: false,
        cssClass: 'fv-col-sla', headerTooltip: 'Cálculo Cobra: dispatch_time → SubmitTime(complete) − parada de reloj, contra el objetivo por Fault Level',
        sorter: (a, b, filaA, filaB) => slaCobra(filaA.getData()).localeCompare(slaCobra(filaB.getData())),
        formatter: celda => {
          const f = celda.getRow().getData(), v = slaCobra(f);
          if (!v) return '';
          const chip = el('span', 'fv-chip ' + (v === 'normal' ? 'fv-chip-sla-ok' : 'fv-chip-sla-mal'), v);
          const data = plano(f['SLA Status']);
          if (!data || data === v) return chip;
          const caja = el('span', 'fv-sla-contraste');
          const aviso = icono('fa-triangle-exclamation');
          caja.title = 'No coincide: la data dice ' + f['SLA Status'] + ' y el cálculo Cobra dice ' + v;
          caja.append(chip, aviso);
          return caja;
        }}, false, pos);
    }
    if (esEntel && tabla.getColumn('Total SLA Pause Duration')) {
      // Viene en segundos: se muestra en horas y minutos (el número original queda al pasar el mouse).
      tabla.updateColumnDefinition('Total SLA Pause Duration', {formatter: celda => {
        const s = Number(String(celda.getValue() ?? '').trim());
        if (!(s > 0)) return '';
        const t = el('span', null, duracion(s / 60)); t.title = s + ' segundos'; return t;
      }});
    }
    if (conSla) {
      // Columnas que usa el SLA: cabecera y celdas con color, y el cronómetro se actualiza cada minuto.
      COLUMNAS_SLA.forEach(campo => {
        const col = tabla.getColumn(campo);
        if (!col) return;
        const clases = new Set(String(col.getDefinition().cssClass || '').split(' ').filter(Boolean)).add('fv-col-sla');
        tabla.updateColumnDefinition(campo, {cssClass: [...clases].join(' '), headerTooltip: 'Se usa para calcular el SLA'});
      });
      setInterval(() => { try { tabla.getRows('visible').forEach(r => r.reformat()); } catch (_) {} }, 60000);
    }
    main.classList.add('fv-lista');  // ya con el diseño nuevo: se muestra
    tabla.on('dataLoaded', () => setTimeout(pintarPestanas, 0));
    tabla.on('dataChanged', () => setTimeout(pintarPestanas, 0));
    if (grupo) aplicar(); else pintarPestanas();
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
