(function () {
    'use strict';
    const selector = 'button, a.action-pill, a.btn-primary, summary.action-pill';
    function decorate(button) {
        if (button.closest('.tabulator-header, .sidebar, nav') ||
            button.matches('[role="tab"], .wo-tab, .ref-quote-link') ||
            /(?:tab|pagination|page-btn)/i.test(button.className)) return;
        const text = [button.textContent, button.title, button.getAttribute('aria-label')].join(' ')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        let action = 'neutral';
        if (/eliminar|borrar|rechazar|anular/.test(text)) action = 'danger';
        else if (/aprobar|validar|confirmar|guardar|registrar/.test(text)) action = 'success';
        else if (/descargar|exportar/.test(text)) action = 'download';
        else if (/nuevo|nueva|anadir|agregar|crear|ingresar/.test(text)) action = 'primary';
        else if (/editar|modificar|observar/.test(text)) action = 'warning';
        else if (/cancelar|cerrar|limpiar|volver|copiar|configuracion|recursos|actualizar|ver /.test(text)) action = 'neutral';
        if (action) {
            button.dataset.action = action;
            const label = button.textContent.replace(/[\uE000-\uF8FF]/g, '').trim();
            if (!label) button.dataset.actionIcon = 'true';
        }
    }
    function scan(root) {
        if (root.matches?.(selector)) decorate(root);
        root.querySelectorAll?.(selector).forEach(decorate);
    }
    scan(document);
    // Decorate only new controls; table cell updates do not rescan the page.
    new MutationObserver(records => {
        for (const record of records) for (const node of record.addedNodes)
            if (node.nodeType === 1) scan(node);
    }).observe(document.body, { childList: true, subtree: true });
})();
