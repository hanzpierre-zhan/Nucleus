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
      fila.append(icono(simbolo), el('span', null, nombre), el('span', 'cc-cuenta', (clave ? cuenta[clave] || 0 : datos.length).toLocaleString('es-PE')));
      b.append(fila);
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
    const cab = document.querySelector('#data-grid .tabulator-header');
    if (cab) new MutationObserver(() => { clearTimeout(ajustarEncabezado.t); ajustarEncabezado.t = setTimeout(ajustarEncabezado, 50); }).observe(cab, {childList: true, subtree: true});
    // Estado como chip de color (solo cómo se ve).
    if (tabla.getColumn('Task Status')) {
      tabla.updateColumnDefinition('Task Status', {formatter: celda => {
        const v = celda.getValue(); return v ? el('span', 'fv-chip ' + (CHIP[grupoDe(v)] || ''), v) : '';
      }});
    }
    // Acciones: botón redondo que abre el mismo detalle que el clic en el ticket.
    if (!tabla.getColumn('_fv_acciones') && tabla.getColumn('_key')) {
      tabla.addColumn({title: 'Acciones', field: '_fv_acciones', headerSort: false, headerFilter: false, width: 92, minWidth: 92, hozAlign: 'center', download: false,
        formatter: celda => {
          const b = el('button', 'fv-accion'); b.type = 'button'; b.title = 'Ver / editar';
          b.setAttribute('aria-label', 'Ver o editar ' + (celda.getRow().getData()._key || ''));
          b.append(icono('fa-pen'));
          b.addEventListener('click', e => {
            e.stopPropagation();
            const destino = celda.getRow().getCell('_key')?.getElement();
            (destino?.querySelector('.wo-link') || destino)?.click();
          });
          return b;
        }}, true, '_key');
    }
    tabla.on('dataLoaded', () => setTimeout(pintarPestanas, 0));
    tabla.on('dataChanged', () => setTimeout(pintarPestanas, 0));
    if (grupo) aplicar(); else pintarPestanas();
  }

  // La tabla clásica se crea en otro script: se espera a que exista y tenga datos.
  let intentos = 0;
  const esperar = setInterval(() => {
    const t = window.Tabulator?.findTable?.('#data-grid')?.[0];
    if (t && t.initialized !== false && t.getData().length) { clearInterval(esperar); preparar(t); }
    else if (++intentos > 150) clearInterval(esperar);
  }, 200);
})();
