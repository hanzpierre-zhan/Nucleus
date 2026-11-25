(() => {
  'use strict';
  const root = document.documentElement;
  const sun = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>';
  const moon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.7 13A9 9 0 0 1 11 3.3 9 9 0 1 0 20.7 13Z"/></svg>';
  function apply(theme) {
    root.dataset.theme = theme === 'dark' ? 'dark' : 'light';
    const dark = root.dataset.theme === 'dark';
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = dark ? '#181818' : '#f5f7fa';
    const button = document.getElementById('form-theme-toggle');
    if (button) {
      const label = dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
      if (button.hasAttribute('data-theme-text')) button.textContent = label;
      else button.innerHTML = dark ? sun : moon;
      button.setAttribute('aria-label', label);
      button.title = label;
    }
  }
  let saved = 'light';
  try { saved = localStorage.getItem('nucleus-theme') || 'light'; } catch (_) {}
  apply(saved);
  document.addEventListener('DOMContentLoaded', () => {
    apply(root.dataset.theme);
    const ajustes = document.querySelector('.mobile-ajustes');
    if (ajustes) {
      document.addEventListener('click', event => {
        if (!ajustes.contains(event.target) || event.target.closest('.mobile-ajustes-panel button')) ajustes.open = false;
      });
      ajustes.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || !ajustes.open) return;
        ajustes.open = false;
        ajustes.querySelector('summary').focus();
      });
    }
    document.getElementById('form-theme-toggle')?.addEventListener('click', () => {
      const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      apply(theme);
      try { localStorage.setItem('nucleus-theme', theme); } catch (_) {}
    });
  });
  window.addEventListener('storage', event => {
    if (event.key === 'nucleus-theme') apply(event.newValue);
  });
})();
