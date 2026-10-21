(function () {
    'use strict';
    const page = document.querySelector('[data-finance]');
    if (!page) return;
    const mode = page.dataset.finance;
    const data = JSON.parse(document.getElementById('di-data').textContent);
    const rows = data.detalle || [];
    const model = window.NucleusFinanceModel;
    const get = id => document.getElementById(id);
    const money = v => new Intl.NumberFormat('es-PE', {style: 'currency', currency: 'PEN', maximumFractionDigits: 2}).format(v || 0);
    const number = v => new Intl.NumberFormat('es-PE').format(v);
    const compact = v => 'S/ ' + new Intl.NumberFormat('es-PE', {notation: 'compact', maximumFractionDigits: 1}).format(v);
    const name = value => window.NucleusIdentity?.display(value) || String(value);
    const charts = new Map();
    const filters = ['month', 'state', 'operator', 'budget', 'type', 'person'].filter(key => get('df-' + key));
    const node = (tag, text) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; return element; };
    function theme() {
        const css = getComputedStyle(page), value = key => css.getPropertyValue(key).trim();
        return {text: value('--ios-label'), muted: value('--ios-secondary'), grid: value('--ios-hairline'),
            card: value('--ios-card-bg'), colors: ['--di-blue', '--di-green', '--di-cyan', '--di-amber', '--di-purple'].map(value)};
    }
    function brand(label, fallback) {
        const value = model.normalize(label);
        if (value.includes('PEXT')) return '#ff9b35';
        if (value.includes('CLARO')) return '#da291c';
        if (value.includes('INTEGRATEL') || value.includes('MOVISTAR')) return '#66cd00';
        if (value.includes('ENTEL')) return '#0057b8';
        return fallback;
    }
    function color(label, index, kind) {
        const t = theme();
        if (kind === 'operator') return brand(label, t.colors[index % t.colors.length]);
        const value = model.normalize(label);
        if (value.includes('REFACTURABLE') && !value.startsWith('NO ')) return t.colors[1];
        if (value.includes('GASTO COBRA')) return t.colors[2];
        if (value === 'SIN CLASIFICAR' || value === 'SIN DEFINIR') return t.colors[0];
        if (value === 'COSTO COBRA') return t.colors[4];
        return t.colors[index % t.colors.length];
    }
    function mount(id, config, hasData) {
        const canvas = get(id);
        if (!canvas || !window.Chart) return;
        charts.get(id)?.destroy();
        charts.delete(id);
        const parent = canvas.parentElement;
        parent.querySelector('.df-empty')?.remove();
        canvas.hidden = !hasData;
        if (!hasData) {
            const empty = node('span', 'Sin datos para esta selección'); empty.className = 'df-empty'; parent.append(empty);
            return;
        }
        charts.set(id, new Chart(canvas, config));
    }
    function common() {
        const t = theme();
        return {responsive: true, maintainAspectRatio: false, animation: false,
            plugins: {legend: {display: false}, tooltip: {backgroundColor: t.card, titleColor: t.text,
                bodyColor: t.muted, borderColor: t.grid, borderWidth: 1, padding: 11,
                callbacks: {label: ctx => money(typeof ctx.parsed === 'number' ? ctx.parsed : ctx.parsed[ctx.chart.options.indexAxis === 'y' ? 'x' : 'y'])}}}};
    }
    function bars(id, entries, horizontal = false, kind = '', limit = 10) {
        const t = theme(), items = entries.slice(0, limit), options = common();
        const moneyAxis = {beginAtZero: true, grid: {color: t.grid}, border: {display: false},
            ticks: {color: t.muted, font: {size: 10}, maxTicksLimit: 5, callback: compact}};
        const labelAxis = {grid: {display: false}, border: {display: false},
            ticks: {color: t.muted, font: {size: 10}, autoSkip: false}};
        if (horizontal) labelAxis.ticks.callback = function (value) {
            const label = this.getLabelForValue(value);
            return label.length > 26 ? label.slice(0, 25) + '…' : label;
        };
        options.indexAxis = horizontal ? 'y' : 'x';
        options.scales = horizontal ? {x: moneyAxis, y: labelAxis} : {x: labelAxis, y: moneyAxis};
        options.plugins.tooltip.callbacks.afterLabel = ctx => number(items[ctx.dataIndex].count) + ' registros';
        const labels = {id: 'financeValues', afterDatasetsDraw(chart) {
            const ctx = chart.ctx; ctx.save(); ctx.font = '600 10px system-ui';
            chart.getDatasetMeta(0).data.forEach((bar, index) => {
                const value = items[index].amount;
                if (!value) return;
                const label = compact(value), textWidth = ctx.measureText(label).width;
                if (horizontal) {
                    const inside = Math.abs(bar.x - bar.base) > textWidth + 12;
                    ctx.textAlign = inside ? 'right' : 'left'; ctx.textBaseline = 'middle';
                    const hex = color(items[index].label, index, kind).replace('#', '');
                    const light = hex.length === 6 && (parseInt(hex.slice(0,2),16) * .299 + parseInt(hex.slice(2,4),16) * .587 + parseInt(hex.slice(4,6),16) * .114) > 155;
                    ctx.fillStyle = inside ? (light ? '#10233f' : '#fff') : t.text;
                    ctx.fillText(label, inside ? bar.x - 6 : bar.x + 5, bar.y);
                } else {
                    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillStyle = t.text;
                    ctx.fillText(label, bar.x, Math.max(chart.chartArea.top + 11, bar.y - 4));
                }
            });
            ctx.restore();
        }};
        mount(id, {type: 'bar', plugins: [labels], data: {labels: items.map(item => name(item.label)), datasets: [{
            data: items.map(item => item.amount), backgroundColor: items.map((item, i) => color(item.label, i, kind)),
            borderRadius: 4, maxBarThickness: horizontal ? 26 : 54, barPercentage: .72,
        }]}, options}, items.some(item => item.amount !== 0));
    }
    function donut(entries) {
        const total = entries.reduce((value, item) => value + Math.max(0, item.amount), 0);
        const items = entries.filter(item => item.amount > 0), colors = items.map((item, i) => color(item.label, i, 'operator'));
        const legend = get('df-legend'); legend.replaceChildren();
        items.forEach((item, i) => {
            const li = node('li'), dot = node('i'), label = node('span', name(item.label));
            dot.style.background = colors[i];
            li.title = name(item.label) + ' · ' + money(item.amount) + ' · ' + number(item.count) + ' registros';
            li.append(dot, label, node('b', number(Math.round(item.amount / total * 1000) / 10) + '%'));
            legend.append(li);
        });
        get('df-ring-total').textContent = total ? compact(total) : '—';
        get('df-ring-total').parentElement.hidden = !total;
        const options = common(); options.cutout = '70%';
        options.plugins.tooltip.callbacks.label = ctx => money(items[ctx.dataIndex].amount) + ' · ' + number(items[ctx.dataIndex].count) + ' registros';
        mount('df-operator-chart', {type: 'doughnut', data: {labels: items.map(item => name(item.label)),
            datasets: [{data: items.map(item => item.amount), backgroundColor: colors, borderColor: theme().card, borderWidth: 3, hoverOffset: 4}]}, options}, total > 0);
    }
    function line(filtered) {
        const trend = model.trend(filtered, mode), t = theme(), options = common();
        options.interaction = {mode: 'index', intersect: false};
        options.scales = {x: {grid: {display: false}, border: {display: false}, ticks: {color: t.muted, font: {size: 10}, maxTicksLimit: 12, maxRotation: 0}},
            y: {beginAtZero: true, grid: {color: t.grid}, border: {display: false}, ticks: {color: t.muted, font: {size: 10}, maxTicksLimit: 5, callback: compact}}};
        options.plugins.legend = {display: true, position: 'top', align: 'end', labels: {color: t.muted, boxWidth: 8, boxHeight: 8, usePointStyle: true, font: {size: 10}}};
        options.plugins.tooltip.callbacks.title = contexts => trend.periods[contexts[0].dataIndex];
        options.plugins.tooltip.callbacks.label = ctx => ctx.dataset.label + ': ' + money(ctx.parsed.y);
        const labels = trend.periods.map(period => new Intl.DateTimeFormat('es-PE', mode === 'rendicion'
            ? {day: 'numeric', month: 'short'} : {month: 'short', year: '2-digit'}).format(new Date(period + (period.length === 7 ? '-15T12:00:00' : 'T12:00:00'))));
        mount('df-trend-chart', {type: 'line', data: {labels, datasets: trend.series.map((series, i) => ({
            label: series.label, data: series.values, borderColor: color(series.label, i), backgroundColor: color(series.label, i),
            borderWidth: 2, tension: .28, pointRadius: trend.periods.length > 40 ? 0 : 2.5, pointHoverRadius: 5, fill: false,
        }))}, options}, trend.periods.length > 0);
    }
    function kpis(summary) {
        const items = mode === 'rendicion' ? [
            ['Total rendido', money(summary.amount), 'Importe pagado registrado'],
            ['Total registros', number(summary.count), 'Solicitudes de la selección'],
            ['Total depositado', money(summary.deposited), 'Con depósito registrado'],
            ['Registros depositados', number(summary.depositedCount), 'Solicitudes con depósito'],
            ['Total sustentado', money(summary.supported), 'Importe pagado con sustento'],
            ['Registros sustentados', number(summary.supportedCount), 'Incluye sustentos por revisar'],
        ] : [['SUB TOTAL + FEE', money(summary.amount), 'Importe total cotizado'],
            ['Total cotizaciones', number(summary.count), 'Solicitudes de la selección']];
        const container = get('df-kpis'); container.replaceChildren();
        items.forEach(([title, value, hint]) => {
            const card = node('article'), figure = node('strong', value); figure.title = value;
            card.append(node('span', title), figure, node('small', hint)); container.append(card);
        });
        requestAnimationFrame(fitKpis);
    }
    function fitKpis() {
        get('df-kpis').querySelectorAll('strong').forEach(figure => {
            figure.style.fontSize = '';
            let size = parseFloat(getComputedStyle(figure).fontSize);
            while (figure.scrollWidth > figure.clientWidth && size > 10) figure.style.fontSize = (--size) + 'px';
        });
    }
    function types(entries, summary) {
        const body = get('df-types-body'), foot = get('df-types-foot');
        body.replaceChildren(); foot.replaceChildren();
        const row = (label, count, value) => {const tr = node('tr'), th = node('th', label); th.scope = 'row'; tr.append(th, node('td', number(count)), node('td', money(value))); return tr;};
        entries.forEach(item => body.append(row(item.label, item.count, item.amount)));
        if (!entries.length) {const tr = node('tr'), td = node('td', 'Sin registros'); td.colSpan = 3; tr.append(td); body.append(tr);}
        foot.append(row('Total', summary.count, summary.amount));
    }
    function values(key) {
        const map = {month: row => row.mes, state: row => row.estado, operator: row => model.operator(row, mode),
            budget: row => mode === 'rendicion' ? row.presupuesto : row.gasto, type: row => row.tipo, person: row => model.person(row, mode)};
        return [...new Set(rows.map(map[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    }
    function render() {
        const active = Object.fromEntries(filters.map(key => [key, get('df-' + key).value]));
        const filtered = model.filter(rows, mode, active), summary = model.summary(filtered, mode);
        kpis(summary); donut(summary.operators); bars('df-budget-chart', summary.budgets);
        bars('df-person-chart', summary.people, true, '', mode === 'rendicion' ? 8 : 10); line(filtered);
        if (mode === 'rendicion') {
            bars('df-sust-budget-chart', summary.supportedBudgets);
            bars('df-sust-operator-chart', summary.supportedOperators, true, 'operator');
        } else { bars('df-approval-chart', summary.approval); types(summary.types, summary); }
        const undated = filtered.filter(row => !(mode === 'rendicion' ? row.dia_pago : row.mes)).length;
        get('df-caption').textContent = number(filtered.length) + ' registros en la selección'
            + (undated ? ' · ' + number(undated) + ' sin fecha para la evolución' : '')
            + (mode === 'cotizaciones' ? ' · Proveedor se cuenta una sola vez.' : ' · Los importes corresponden a pagos registrados.');
    }
    filters.forEach(key => {
        values(key).forEach(value => get('df-' + key).add(new Option(key === 'month'
            ? new Intl.DateTimeFormat('es-PE', {month: 'long', year: 'numeric'}).format(new Date(value + '-15T12:00:00')) : name(value), value)));
        get('df-' + key).addEventListener('change', render);
    });
    get('df-clear').addEventListener('click', () => {filters.forEach(key => {get('df-' + key).value = '';}); render();});
    new MutationObserver(render).observe(document.body, {attributes: true, attributeFilter: ['class']});
    new ResizeObserver(fitKpis).observe(get('df-kpis'));
    render();
}());
