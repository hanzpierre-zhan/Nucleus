(function (root) {
    'use strict';
    const normalizar = v => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();

    function fecha(valor) {
        if (valor instanceof Date) return Number.isFinite(valor.getTime()) ? valor.getTime() : null;
        let s = String(valor == null ? '' : valor).trim().replace(/\s+/g, ' ')
            .replace(/([ap])\.?\s*m\.?$/i, '$1m');
        if (!s) return null;
        let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$/i);
        let y, mes, dia, h, min, seg;
        if (m) {
            if (m[7]) {
                const t = Date.parse(s);
                return Number.isFinite(t) ? t : null;
            }
            [, y, mes, dia, h = '0', min = '0', seg = '0'] = m;
        } else {
            m = s.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[ ,]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?)?$/i);
            if (!m) return null;
            [, dia, mes, y, h = '0', min = '0', seg = '0'] = m;
            if (m[7]) {
                if (+h < 1 || +h > 12) return null;
                h = (+h % 12) + (m[7].toLowerCase() === 'pm' ? 12 : 0);
            }
        }
        [y, mes, dia, h, min, seg] = [y, mes, dia, h, min, seg].map(Number);
        if (mes < 1 || mes > 12 || dia < 1 || h > 23 || min > 59 || seg > 59) return null;
        const d = new Date(y, mes - 1, dia, h, min, seg);
        return d.getFullYear() === y && d.getMonth() === mes - 1 && d.getDate() === dia ? d.getTime() : null;
    }

    function numero(valor) {
        if (typeof valor === 'number') return Number.isFinite(valor) ? valor : null;
        let s = String(valor == null ? '' : valor).trim();
        const negativo = /^\(.*\)$/.test(s);
        s = s.replace(/^\((.*)\)$/, '$1').replace(/^(?:S\/\.?|USD|PEN|US\$|\$)\s*/i, '').replace(/\s/g, '');
        if (!s || !/^[+-]?\d[\d.,]*$/.test(s)) return null;
        if (s.includes(',') && s.includes('.')) {
            s = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
        } else if (s.includes(',')) {
            s = /^[+-]?\d{1,3}(,\d{3})+$/.test(s) && !/^[+-]?0,/.test(s) ? s.replace(/,/g, '') : s.replace(',', '.');
        } else if (/^[+-]?\d{1,3}(\.\d{3}){2,}$/.test(s)) {
            s = s.replace(/\./g, '');
        }
        const n = Number(s);
        return Number.isFinite(n) ? n * (negativo ? -1 : 1) : null;
    }

    function comparar(parsear) {
        return function (a, b, aRow, bRow, column, dir) {
            const x = parsear(a), y = parsear(b);
            if (x === null && y === null) return 0;
            // Tabulator invierte el resultado en descendente. Vacíos al final siempre.
            if (x === null) return dir === 'desc' ? -1 : 1;
            if (y === null) return dir === 'desc' ? 1 : -1;
            return x - y;
        };
    }

    const cronologico = comparar(fecha), numerico = comparar(numero);
    function configurar(columnas, manuales, proyecto) {
        for (const c of columnas) {
            if (c.columns) configurar(c.columns, manuales, proyecto);
            const nombre = normalizar(c.field), def = manuales.find(m => m.nombre === c.field);
            if (normalizar(proyecto) === 'combustible' && nombre === 'fecha') continue;
            if (nombre === 'marca temporal' || /^fecha(?:\s|$)/.test(nombre) || normalizar(def && def.tipo) === 'fecha') {
                c.sorter = cronologico;
            } else if (['numero', 'moneda', 'decimal'].includes(normalizar(def && def.tipo)) ||
                /^(?:monto(?:\s|$)|precio(?:\s|$)|cantidad(?:\s|$)|sub total(?:\s|$)|total$)/.test(nombre) ||
                ['galones', 'saldo disponible', 'saldo antes', 'n° orden'].includes(nombre)) {
                c.sorter = numerico;
            }
        }
    }
    const api = { fecha, numero, cronologico, numerico, configurar };
    root.NucleusOrden = api;
    if (typeof module !== 'undefined') module.exports = api;
})(typeof window === 'undefined' ? globalThis : window);
