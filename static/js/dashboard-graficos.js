/* Rankings compartidos: la medida nunca compite con el ancho de la barra. */
(function () {
    'use strict';
    const currency = new Intl.NumberFormat('es-PE', {style: 'currency', currency: 'PEN'});
    const number = new Intl.NumberFormat('es-PE');
    const cases = value => number.format(value) + (value === 1 ? ' caso' : ' casos');
    const modes = new Map();
    const charts = new Map();
    const compactLimit = () => (document.querySelector('.di-executive')?.getBoundingClientRect().height || innerHeight) <= 650 ? 2 : 3;
    function node(tag, className, text) {
        const e = document.createElement(tag);
        if (className) e.className = className;
        if (text !== undefined) e.textContent = text;
        return e;
    }
    function render(id, values, options = {}) {
        charts.set(id, {values, options});
        const box = document.getElementById(id);
        box.classList.add('di-ranking');
        box.replaceChildren();
        if (!values.length) {
            box.append(node('p', 'di-empty', 'No hay registros para estos filtros.'));
            return;
        }
        // Cuarta posición: importe real, sin incrustarlo ni recortarlo en el nombre.
        const paired = values.every(v => Number.isFinite(v[3]));
        const mode = paired ? modes.get(id) || 'count' : 'value';
        let selected = values;
        if (paired) {
            const controls = node('div', 'di-ranking-controls');
            controls.append(node('span', '', 'Comparar por'));
            for (const [key, title] of [['count', 'Cantidad'], ['money', 'Monto']]) {
                const button = node('button', '', title);
                button.type = 'button';
                button.setAttribute('aria-pressed', String(mode === key));
                button.addEventListener('click', () => {
                    modes.set(id, key);
                    const notes = [...box.children].filter(e => e.matches('.dc-chips,.dr-chips,.cb-chips'));
                    render(id, values, options);
                    box.prepend(...notes);
                });
                controls.append(button);
            }
            box.append(controls);
            selected = [...values].sort((a, b) => b[mode === 'money' ? 3 : 1] - a[mode === 'money' ? 3 : 1]);
        }
        const measure = v => Number(v[mode === 'money' ? 3 : 1]) || 0;
        const max = Math.max(...selected.map(measure), 1);
        const list = node('div', 'di-ranking-items');
        const compact = Boolean(box.closest('.di-main-charts'));
        const expanded = box.dataset.expanded === 'true';
        const display = compact && !expanded ? selected.filter(v => v[1] || v[3]).slice(0, compactLimit()) : selected;
        if (!display.length) list.append(node('p', 'di-empty', 'No hay casos en las etapas de esta selección.'));
        for (const item of display) {
            const [label, value, hint, amount] = item;
            const row = node('div', 'di-bar-row');
            const name = node('span', 'di-bar-name', window.NucleusIdentity.text(label));
            const metrics = node('div', 'di-bar-metrics');
            const main = mode === 'money' ? currency.format(amount) : paired ? cases(value) : options.fmt ? options.fmt(value) : number.format(value);
            metrics.append(node('b', '', main));
            if (paired) metrics.append(node('small', '', mode === 'money' ? cases(value) : currency.format(amount)));
            else if (Number.isFinite(item[4])) metrics.append(node('small', '', cases(item[4])));
            if (hint) row.title = hint;
            const track = node('div', 'di-bar-track');
            const fill = node('div', 'di-bar-fill');
            if (options.color && options.color(label)) fill.style.background = options.color(label);
            fill.style.width = Math.max(0, 100 * measure(item) / max) + '%';
            track.append(fill); row.append(name, metrics, track); list.append(row);
        }
        box.append(list);
        if (compact && (selected.length > display.length || expanded)) {
            const more = node('button', 'di-ranking-more', expanded ? 'Reducir gráfico' : 'Ver todos los grupos (' + selected.length + ')');
            more.type = 'button'; more.setAttribute('aria-expanded', String(expanded));
            more.addEventListener('click', () => {
                box.dataset.expanded = String(!expanded);
                const notes = [...box.children].filter(e => e.matches('.dc-chips,.dr-chips'));
                render(id, values, options); box.prepend(...notes);
            });
            box.append(more);
        }
    }
    let previousLimit = compactLimit(), resizeFrame;
    window.addEventListener('resize', () => {
        cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => {
            const limit = compactLimit();
            if (limit === previousLimit) return;
            previousLimit = limit;
            charts.forEach(({values, options}, id) => {
                const box = document.getElementById(id);
                const notes = [...box.children].filter(e => e.matches('.dc-chips,.dr-chips'));
                render(id, values, options); box.prepend(...notes);
            });
        });
    });
    function observeWidth(element, callback) {
        let width = element.clientWidth, frame;
        const observer = new ResizeObserver(() => {
            if (element.clientWidth === width) return;
            width = element.clientWidth;
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(callback);
        });
        observer.observe(element);
    }
    window.NucleusDashboardGraficos = {render, observeWidth};
})();
