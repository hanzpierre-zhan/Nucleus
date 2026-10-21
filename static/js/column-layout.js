(function () {
    'use strict';
    function width(value) {
        const n = Number(value);
        return Number.isFinite(n) && n >= 40 && n <= 2000 ? Math.round(n) : null;
    }
    function apply(columns, layout, canEdit) {
        const saved = new Map((layout || []).map(c => [c.field, c]));
        columns.forEach(c => {
            c.resizable = canEdit;
            const w = width(saved.get(c.field)?.width);
            if (w === null) return;
            c.width = w;
            if (c.minWidth > w) c.minWidth = w;
            if (c.maxWidth && c.maxWidth < w) c.maxWidth = w;
        });
    }
    function snapshot(columns) {
        return columns.filter(c => c.getField()).map(c => {
            const def = c.getDefinition();
            const result = {field: c.getField(), visible: c.isVisible()};
            const w = width(c.getWidth()) ?? width(def.width);
            if (w !== null) result.width = w;
            return result;
        });
    }
    function providerLayout(base) {
        const fields = ['ADJUNTO CORREO CLIENTE', 'ADJUNTO COTIZACION PROVEEDOR'];
        const result = base.map(c => ({...c}));
        fields.forEach(field => {
            const column = result.find(c => c.field === field);
            if (column) column.visible = true;
            else result.push({field, visible: true});
        });
        return result;
    }
    function definitions(columns, layout, canEdit) {
        const byField = new Map(columns.filter(c => c.getField()).map(c => [c.getField(), c]));
        const saved = new Map(layout.map(c => [c.field, c]));
        const ordered = columns.filter(c => !c.getField());
        layout.forEach(c => {
            if (!byField.has(c.field)) return;
            ordered.push(byField.get(c.field));
            byField.delete(c.field);
        });
        ordered.push(...byField.values());
        const result = ordered.map(c => {
            const def = {...c.getDefinition()};
            if (c.getField()) def.visible = saved.get(c.getField())?.visible !== false && saved.has(c.getField());
            return def;
        });
        apply(result, layout, canEdit);
        return result;
    }
    window.NucleusColumnLayout = {width, apply, snapshot, providerLayout, definitions};
}());
