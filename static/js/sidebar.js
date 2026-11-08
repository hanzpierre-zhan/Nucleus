// Menú lateral: plegar, modo noche, grupos, menú de usuario y contador de Caja Chica.
(function () {
  const barra = document.querySelector('.app-sidebar.sb');
  if (!barra) return;
  const leer = (clave, defecto) => { try { return localStorage.getItem(clave) ?? defecto; } catch (_) { return defecto; } };
  const guardar = (clave, valor) => { try { localStorage.setItem(clave, valor); } catch (_) {} };

  // Plegar / desplegar (se recuerda en el navegador)
  const plegar = document.getElementById('sidebar-collapse');
  const iconoPlegar = () => {
    plegar.querySelector('i').className = document.body.classList.contains('sidebar-collapsed') ? 'fa-solid fa-chevron-right' : 'fa-solid fa-chevron-left';
  };
  if (leer('nucleus-sidebar') === 'collapsed') document.body.classList.add('sidebar-collapsed');
  iconoPlegar();
  plegar.addEventListener('click', () => {
    const cerrado = document.body.classList.toggle('sidebar-collapsed');
    guardar('nucleus-sidebar', cerrado ? 'collapsed' : 'expanded');
    iconoPlegar();
    window.dispatchEvent(new Event('resize'));
  });

  // Modo noche (interruptor)
  const noche = document.getElementById('theme-toggle');
  const pintarNoche = () => {
    const oscuro = document.body.classList.contains('dark-mode');
    noche.setAttribute('aria-checked', String(oscuro));
    noche.querySelector('i').className = oscuro ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
  };
  pintarNoche();
  noche.addEventListener('click', () => {
    const oscuro = document.body.classList.toggle('dark-mode');
    guardar('nucleus-theme', oscuro ? 'dark' : 'light');
    pintarNoche();
  });

  // Grupos: se recuerda cuáles están abiertos; el que tiene la página actual se abre solo.
  let abiertos = {};
  try { abiertos = JSON.parse(leer('nucleus-sb-grupos', '{}')) || {}; } catch (_) {}
  barra.querySelectorAll('.sb-grupo').forEach(grupo => {
    const boton = grupo.querySelector('.sb-grupo-btn');
    const clave = grupo.dataset.grupo;
    const activo = grupo.querySelector('.sidebar-link.active');
    boton.setAttribute('aria-expanded', String(Boolean(activo) || abiertos[clave] !== false));
    boton.addEventListener('click', () => {
      const abrir = boton.getAttribute('aria-expanded') !== 'true';
      boton.setAttribute('aria-expanded', String(abrir));
      abiertos[clave] = abrir;
      guardar('nucleus-sb-grupos', JSON.stringify(abiertos));
    });
  });

  // Menú del usuario
  const usuario = document.getElementById('sb-usuario-btn'), menuUsuario = document.getElementById('sb-usuario-menu');
  const cerrarUsuario = () => { menuUsuario.hidden = true; usuario.setAttribute('aria-expanded', 'false'); };
  usuario.addEventListener('click', e => {
    e.stopPropagation();
    const abrir = menuUsuario.hidden;
    menuUsuario.hidden = !abrir; usuario.setAttribute('aria-expanded', String(abrir));
  });
  document.addEventListener('click', e => { if (!menuUsuario.hidden && !menuUsuario.contains(e.target)) cerrarUsuario(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menuUsuario.hidden) { cerrarUsuario(); usuario.focus(); } });

  // Contador de Caja Chica: solicitudes que esperan validación.
  const chip = document.getElementById('sb-cc-pendientes');
  if (chip) {
    fetch('/api/caja-chica/resumen').then(r => (r.ok ? r.json() : null)).then(datos => {
      const n = Number(datos?.por_validar || 0);
      if (n > 0) { chip.textContent = n > 99 ? '99+' : String(n); chip.hidden = false; }
    }).catch(() => {});
  }
})();
