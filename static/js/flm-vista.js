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

  // ── SLA (solo FLM - CLARO, mismas reglas que la página SLA) ──
  // CM cuenta desde Dispatch Time; PM y PLM desde Arrive Time. Objetivo: SLA Hour (min).
  // Cerrado (completed/closed): termina en Complete Time y cumple según SLA Status.
  const conSla = main.dataset.proyecto === 'FLM - CLARO';
  const COLUMNAS_SLA = ['Task Type', 'Task Status', 'Dispatch Time', 'Arrive Time', 'SLA Hour', 'Complete Time', 'SLA Status', 'Schedule Operator'];
  const POR_VENCER = [0.25, 60];
  const fecha = v => { const m = String(v || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/); return m ? new Date(m[1], m[2] - 1, m[3], m[4], m[5], m[6] || 0) : null; };
  const duracion = min => { min = Math.max(0, Math.round(min)); const d = Math.floor(min / 1440), h = Math.floor(min % 1440 / 60), m = min % 60; return d ? d + 'd ' + h + 'h' : h ? h + 'h ' + m + 'm' : m + 'm'; };
  function sla(f) {
    const estado = plano(f['Task Status']);
    if (/cancel/.test(estado)) return null;
    let tipo = String(f['Task Type'] || '').trim().toUpperCase();
    if (!['CM', 'PM', 'PLM'].includes(tipo)) tipo = (String(f._key || '').toUpperCase().match(/^(CM|PLM|PM)\b/) || [])[1] || '';
    if (!tipo) return null;
    const inicio = fecha(tipo === 'CM' ? f['Dispatch Time'] : f['Arrive Time']);
    const objetivo = Number(f['SLA Hour']) > 0 ? Number(f['SLA Hour']) : null;
    if (!inicio) return {clase: 'fv-sla-gris', icono: 'fa-hourglass-start', texto: 'Sin inicio', ayuda: (tipo === 'CM' ? 'Falta Dispatch Time' : 'Falta Arrive Time')};
    const meta = objetivo ? ' · objetivo ' + duracion(objetivo) : '';
    if (/complet|closed/.test(estado)) {
      const fin = fecha(f['Complete Time'] || f['FECHA CAMBIO ESTADO']);
      const usado = fin ? (fin - inicio) / 60000 : null;
      const st = plano(f['SLA Status']);
      const cumple = st === 'normal', falla = st.includes('violation');
      return {clase: cumple ? 'fv-sla-verde' : falla ? 'fv-sla-rojo' : 'fv-sla-gris', icono: cumple ? 'fa-circle-check' : falla ? 'fa-circle-xmark' : 'fa-stopwatch',
        texto: usado === null ? (cumple ? 'Cumplió' : falla ? 'No cumplió' : 'Cerrado') : duracion(usado),
        ayuda: (cumple ? 'Cumplió el SLA' : falla ? 'No cumplió el SLA' : 'Cerrado') + (usado === null ? '' : ' en ' + duracion(usado)) + meta};
    }
    const pasado = (Date.now() - inicio) / 60000;
    if (!objetivo) return {clase: 'fv-sla-gris', icono: 'fa-clock', texto: duracion(pasado), ayuda: 'Abierto hace ' + duracion(pasado) + ' · sin SLA Hour'};
    const resto = objetivo - pasado;
    if (resto < 0) return {clase: 'fv-sla-rojo', icono: 'fa-triangle-exclamation', texto: '+' + duracion(-resto), ayuda: 'Vencido hace ' + duracion(-resto) + meta};
    const urgente = resto <= objetivo * POR_VENCER[0] || resto <= POR_VENCER[1];
    return {clase: urgente ? 'fv-sla-ambar' : 'fv-sla-azul', icono: 'fa-hourglass-half', texto: duracion(resto),
      ayuda: (urgente ? 'Por vencer: quedan ' : 'En plazo: quedan ') + duracion(resto) + meta};
  }
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
    filtro = fila => (!grupo || grupoDe(fila['Task Status']) === grupo) && (!q || campos.some(c => plano(fila[c]).includes(q)));
    tabla.addFilter(filtro);
    pintarPestanas();
  }

  function pintarPestanas() {
    const datos = tabla.getData(), cuenta = {};
    datos.forEach(f => { const g = grupoDe(f['Task Status']); cuenta[g] = (cuenta[g] || 0) + 1; });
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
    if (tabla.getColumn('Task Status')) {
      tabla.updateColumnDefinition('Task Status', {formatter: celda => {
        const v = celda.getValue(); return v ? el('span', 'fv-chip ' + (CHIP[grupoDe(v)] || ''), v) : '';
      }});
    }
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
