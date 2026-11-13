/* FLM con el estilo de Caja Chica (solo diseño): buscador, pestañas por estado, acciones redondas y estado en chip.
   No cambia datos ni funciones: filtra lo que ya está cargado y reutiliza los clics de la tabla clásica. */
(() => {
  'use strict';
  const main = document.querySelector('.excel-main.vista-flm');
  if (!main) return;
  const el = (tag, cls, texto) => { const n = document.createElement(tag); if (cls) n.className = cls; if (texto !== undefined) n.textContent = texto; return n; };
  const icono = nombre => { const i = el('i', 'fa-solid ' + nombre); i.setAttribute('aria-hidden', 'true'); return i; };
  const plano = t => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  // Estados de "Task Status" agrupados como en Caja Chica.
  const GRUPOS = [
    ['', 'Todos', '#1d4ed8'],
    ['pendiente', 'Pendiente', '#d97706'],
    ['proceso', 'En proceso', '#2563eb'],
    ['completado', 'Completado', '#16a34a'],
    ['cancelado', 'Cancelado', '#64748b'],
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

  function aplicar() {
    if (filtro) tabla.removeFilter(filtro);
    const campos = tabla.getColumns().filter(c => c.isVisible() && c.getField()).map(c => c.getField());
    const q = plano(texto.trim());
    filtro = fila => (!grupo || grupoDe(fila['Task Status']) === grupo) && (!q || campos.some(c => plano(fila[c]).includes(q)));
    tabla.addFilter(filtro);
    pintarPestanas();
  }

  const barra = el('div', 'fv-barra');
  const buscar = Object.assign(el('input', 'fv-buscar'), {type: 'search', placeholder: 'Buscar ticket, site, operador o WO'});
  buscar.setAttribute('aria-label', 'Buscar en la tabla');
  let espera;
  buscar.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => { texto = buscar.value; aplicar(); }, 200); });
  const pestanas = el('nav', 'fv-tabs'); pestanas.setAttribute('aria-label', 'Estado del ticket');
  barra.append(buscar, pestanas);

  function pintarPestanas() {
    const datos = tabla.getData();
    const cuenta = {};
    datos.forEach(f => { const g = grupoDe(f['Task Status']); cuenta[g] = (cuenta[g] || 0) + 1; });
    pestanas.replaceChildren(...GRUPOS.map(([clave, nombre, color]) => {
      const b = el('button', 'fv-tab' + (grupo === clave ? ' activa' : '')); b.type = 'button'; b.style.setProperty('--fv-color', color);
      b.setAttribute('aria-pressed', String(grupo === clave));
      b.append(el('span', null, nombre), el('strong', null, (clave ? cuenta[clave] || 0 : datos.length).toLocaleString('es-PE')));
      b.addEventListener('click', () => { grupo = clave; try { localStorage.setItem('fv-grupo', grupo); } catch (_) {} aplicar(); });
      return b;
    }));
  }

  function preparar(t) {
    tabla = t;
    const fila = document.querySelector('.topbar-row');
    if (fila && !fila.querySelector('.fv-barra')) fila.prepend(barra);
    // Estado como chip de color (solo cómo se ve).
    if (tabla.getColumn('Task Status')) {
      tabla.updateColumnDefinition('Task Status', {formatter: celda => {
        const v = celda.getValue(); if (!v) return '';
        const s = el('span', 'fv-chip ' + (CHIP[grupoDe(v)] || ''), v); return s;
      }});
    }
    // Acciones: botón redondo que abre el mismo detalle que el clic en el ticket.
    if (!tabla.getColumn('_fv_acciones') && tabla.getColumn('_key')) {
      tabla.addColumn({title: 'Acciones', field: '_fv_acciones', headerSort: false, headerFilter: false, width: 74, minWidth: 74, hozAlign: 'center', download: false,
        formatter: celda => {
          const b = el('button', 'fv-accion'); b.type = 'button'; b.title = 'Ver / editar'; b.setAttribute('aria-label', 'Ver o editar ' + (celda.getRow().getData()._key || ''));
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
