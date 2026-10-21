(function () {
    'use strict';
    const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
    function brand(value) {
        const name = String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
        // Nombres completos y variantes como FLM - ENTEL o Entel - Pext.
        const words = name.match(/[A-Z0-9]+/g) || [];
        if (!words.length || words.some(w => !['FLM','CLARO','ENTEL','PEXT','INTEGRATEL','MOVISTAR'].includes(w))) return '';
        if (words.includes('PEXT')) return 'pext';
        if (words.includes('CLARO')) return 'claro';
        if (words.includes('INTEGRATEL') || words.includes('MOVISTAR')) return 'movistar';
        if (words.includes('ENTEL')) return 'entel';
        return '';
    }
    function isProjectField(field) {
        return /proyecto|cliente|operador/i.test(String(field));
    }
    function html(value) {
        const key = brand(value);
        return key ? `<span class="project-badge project-badge--${key}">${escape(value)}</span>` : escape(value);
    }
    window.NucleusProjectBadge = {brand, isProjectField, html};
}());
