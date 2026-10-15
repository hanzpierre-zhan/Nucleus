(function(){
    'use strict';
    const node = document.getElementById('nucleus-user-names');
    const names = node ? JSON.parse(node.textContent) : {};
    const display = value => names[String(value ?? '')] || String(value ?? '');
    const isUserField = field => /GESTOR|INTERACCION|SOLICITANTE|(?:CREADO|EDITADO|SOLICITADO|COTIZADO|ENVIADO|APROBADO|VALIDADO|ATENDIDO|DEPOSITADO|RECHAZADO|ANULADO|ARCHIVADO|DESARCHIVADO|SUSTENTADO|OBSERVADO|ELABORADO|CERRADO|ACTUALIZADO) POR|RESPONSABLE DE LA VALIDACI[ÓO]N|USUARIO|AUTOR/i.test(String(field || '').replace(/_/g, ' '));
    function columns(defs) {
        defs.forEach(def => {
            if (def.columns) columns(def.columns);
            if (!isUserField(def.field)) return;
            const original = def.formatter;
            def.formatter = function(cell, ...args) {
                const raw = cell.getValue();
                if (typeof raw === 'string' && names[raw]) {
                    const label = document.createElement('span'); label.textContent = display(raw); label.title = raw;
                    return label;
                }
                return typeof original === 'function' ? original.call(this,cell,...args) : (raw == null ? '' : String(raw));
            };
            if (def.headerFilter === 'input') def.headerFilterFunc = (search, value) =>
                (display(value) + ' ' + String(value ?? '')).toLocaleLowerCase().includes(String(search).toLocaleLowerCase());
        });
        return defs;
    }
    function text(value) {
        return String(value ?? '').split(/([\s·,:;—()]+)/).map(part=>display(part)).join('');
    }
    window.NucleusIdentity = {display, isUserField, columns, text};
})();
