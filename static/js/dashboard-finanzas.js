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
    const KEYS = ['month', 'state', 'operator', 'budget', 'type', 'person', 'project', 'approval', 'day'];
    const selectKeys = KEYS.filter(key => get('df-' + key));
    const state = Object.fromEntries(KEYS.map(key => [key, '']));
    const node = (tag, text) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; return element; };
    const monthLabel = value => new Intl.DateTimeFormat('es-PE', {month: 'long', year: 'numeric'}).format(new Date(value + '-15T12:00:00'));
    const dayLabel = value => new Intl.DateTimeFormat('es-PE', {day: 'numeric', month: 'short', year: 'numeric'}).format(new Date(value + 'T12:00:00'));
    const shortDay = value => new Intl.DateTimeFormat('es-PE', {day: 'numeric', month: 'short'}).format(new Date(value + 'T12:00:00'));
    const stateLabel = value => mode === 'rendicion' ? window.NucleusRendicionStates.label(value) : name(value);
    const personLabels = new Map(rows.map(row => [model.person(row, mode), mode === 'rendicion' ? row.beneficiario : row.genero]));
    const labelFor = (key, value) => key === 'person' ? name(personLabels.get(value) || value) : key === 'state' ? stateLabel(value) : key === 'month' ? monthLabel(value) : key === 'day' ? dayLabel(value) : name(value);
    const TITLES = {month: 'Mes', state: 'Estado', operator: 'Operador', budget: mode === 'rendicion' ? 'Presupuesto' : 'Tipo de gasto',
        type: 'Tipo', person: mode === 'rendicion' ? 'Beneficiario' : 'Responsable', project: 'Proyecto',
        approval: 'Destino', day: 'Día'};
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
    function alpha(value, opacity) {
        const hex = String(value || '').replace('#', '');
        if (opacity >= 1 || hex.length !== 6) return value;
        const int = parseInt(hex, 16);
        return 'rgba(' + (int >> 16 & 255) + ',' + (int >> 8 & 255) + ',' + (int & 255) + ',' + opacity + ')';
    }
    function setFilter(key, value) {
        if (!value) return;
        state[key] = state[key] === value ? '' : value;
        const select = get('df-' + key);
        if (select) select.value = state[key];
        render();
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
        charts.set(id, new Chart(canvas, window.NucleusDashVisual?.prepare(config) || config));
    }
    function common() {
        const t = theme();
        return {responsive: true, maintainAspectRatio: false, animation: false,
            onHover(event, elements, chart) { chart.canvas.style.cursor = elements.length ? 'pointer' : 'default'; },
            plugins: {legend: {display: false}, tooltip: {backgroundColor: t.card, titleColor: t.text,
                bodyColor: t.muted, borderColor: t.grid, borderWidth: 1, padding: 11,
                callbacks: {label: ctx => money(typeof ctx.parsed === 'number' ? ctx.parsed : ctx.parsed[ctx.chart.options.indexAxis === 'y' ? 'x' : 'y'])}}}};
    }
    function bars(id, entries, {horizontal = false, kind = '', limit = 10, measure = 'amount', filterKey = ''} = {}) {
        const t = theme(), items = entries.slice(0, limit), options = common();
        const selected = filterKey ? state[filterKey] : '';
        const valueOf = item => measure === 'count' ? item.count : item.amount;
        const format = measure === 'count' ? number : compact;
        const moneyAxis = {beginAtZero: true, grid: {color: t.grid}, border: {display: false},
            ticks: {color: t.muted, font: {size: 10}, maxTicksLimit: 5, callback: measure === 'count' ? number : compact}};
        const labelAxis = {grid: {display: false}, border: {display: false},
            ticks: {color: t.muted, font: {size: 10}, autoSkip: false}};
        if (horizontal) labelAxis.ticks.callback = function (value) {
            const label = this.getLabelForValue(value);
            const short = label.length > 26 ? label.slice(0, 25) + '…' : label;
            return short;
        };
        options.indexAxis = horizontal ? 'y' : 'x';
        options.scales = horizontal ? {x: moneyAxis, y: labelAxis} : {x: labelAxis, y: moneyAxis};
        options.plugins.tooltip.callbacks.label = ctx => {
            const item = items[ctx.dataIndex];
            return measure === 'count' ? number(item.count) + ' registros · ' + money(item.amount)
                : money(item.amount) + ' · ' + number(item.count) + ' registros';
        };
        if (filterKey) options.onClick = (event, elements) => {
            if (elements.length) setFilter(filterKey, (items[elements[0].index].key || items[elements[0].index].label));
        };
        const labels = {id: 'financeValues', afterDatasetsDraw(chart) {
            const ctx = chart.ctx; ctx.save(); ctx.font = '600 10px system-ui';
            chart.getDatasetMeta(0).data.forEach((bar, index) => {
                const value = valueOf(items[index]);
                if (!value) return;
                const label = format(value), textWidth = ctx.measureText(label).width;
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
        mount(id, {type: 'bar', plugins: [labels], data: {labels: items.map(item => filterKey === 'state' ? stateLabel(item.label) : !horizontal && item.label.includes(' · ') ? item.label.split(' · ').map(name) : name(item.label)), datasets: [{
            data: items.map(valueOf),
            backgroundColor: items.map((item, index) => alpha(color(item.label, index, kind), selected && (item.key || item.label) !== selected ? .28 : 1)),
            borderRadius: 4, maxBarThickness: horizontal ? 26 : 54, barPercentage: .72,
        }]}, options}, items.some(item => valueOf(item) !== 0));
    }
    function donut(entries) {
        const total = entries.reduce((value, item) => value + Math.max(0, item.amount), 0);
        const items = entries.filter(item => item.amount > 0), selected = state.operator;
        const colors = items.map((item, i) => alpha(color(item.label, i, 'operator'), selected && item.label !== selected ? .28 : 1));
        const legend = get('df-legend'); legend.replaceChildren();
        items.forEach((item, i) => {
            const li = node('li'), dot = node('i'), label = node('span', name(item.label));
            dot.style.background = color(item.label, i, 'operator');
            li.className = selected && item.label !== selected ? 'is-dim' : '';
            li.title = 'Clic para filtrar por ' + name(item.label) + ' · ' + money(item.amount) + ' · ' + number(item.count) + ' registros';
            li.append(dot, label, node('b', compact(item.amount) + ' · ' + number(Math.round(item.amount / total * 1000) / 10) + '%'));
            li.addEventListener('click', () => setFilter('operator', item.label));
            legend.append(li);
        });
        get('df-ring-total').textContent = total ? compact(total) : '—';
        get('df-ring-total').parentElement.hidden = !total;
        const options = common(); options.cutout = '70%';
        options.plugins.tooltip.callbacks.label = ctx => money(items[ctx.dataIndex].amount) + ' · ' + number(items[ctx.dataIndex].count) + ' registros';
        options.onClick = (event, elements) => { if (elements.length) setFilter('operator', items[elements[0].index].label); };
        mount('df-operator-chart', {type: 'doughnut', data: {labels: items.map(item => name(item.label)),
            datasets: [{data: items.map(item => item.amount), backgroundColor: colors, borderColor: theme().card, borderWidth: 3, hoverOffset: 4}]}, options}, total > 0);
    }
    function trendChart(filtered) {
        const trend = model.trend(filtered, mode), t = theme(), options = common();
        const barsMode = mode === 'cotizaciones';
        const series = barsMode
            ? trend.series.filter(item => ['GASTO COBRA', 'REFACTURABLE'].includes(model.normalize(item.label)))
            : trend.series;
        options.interaction = {mode: 'index', intersect: false};
        options.scales = {
            x: {stacked: false, grid: {display: false}, border: {display: false},
                ticks: {color: t.muted, font: {size: 10}, maxTicksLimit: barsMode ? 16 : 12, maxRotation: 0}},
            y: {stacked: false, beginAtZero: true, grid: {color: t.grid}, border: {display: false},
                ticks: {color: t.muted, font: {size: 10}, maxTicksLimit: 5, callback: compact}}};
        options.plugins.legend = {display: true, position: 'top', align: 'end',
            onClick: (event, item) => { const s = series[item.datasetIndex]; if (s) setFilter('budget', s.label); },
            labels: {color: t.muted, boxWidth: 8, boxHeight: 8, usePointStyle: true, font: {size: 10}}};
        options.plugins.tooltip.callbacks.title = contexts => dayLabel(trend.periods[contexts[0].dataIndex]);
        options.plugins.tooltip.callbacks.label = ctx => ctx.dataset.label + ': ' + money(ctx.parsed.y);
        options.onClick = (event, elements) => { if (elements.length) setFilter('day', trend.periods[elements[0].index]); };
        const labels = trend.periods.map(shortDay);
        const datasets = series.map((s, i) => {
            const base = color(s.label, i), dimSeries = state.budget && state.budget !== s.label;
            if (barsMode) return {label: s.label, data: s.values,
                backgroundColor: trend.periods.map(period => alpha(base, state.day && state.day !== period ? .18 : dimSeries ? .22 : .88)),
                borderColor: base, borderWidth: 0, borderRadius: 2, maxBarThickness: 16, barPercentage: .9, categoryPercentage: .92};
            return {label: s.label, data: s.values, borderColor: alpha(base, dimSeries ? .28 : 1), backgroundColor: base,
                borderWidth: 2, tension: .28, pointHoverRadius: 5, fill: false,
                pointRadius: trend.periods.map(period => state.day && state.day !== period ? 0 : trend.periods.length > 40 ? 0 : 2.5)};
        });
        mount('df-trend-chart', {type: barsMode ? 'bar' : 'line', data: {labels, datasets}, options},
            trend.periods.length > 0 && series.length > 0);
    }
    function cotTrend(entries) {
        const options = common(), t = theme();
        options.layout = {padding: {top: 22, right: 32, left: 12}};
        options.scales = {
            x: {grid: {display: false}, border: {display: false}, ticks: {color: t.muted, font: {size: 10}, maxRotation: 0}},
            y: {beginAtZero: true, border: {display: false}, grid: {color: t.grid}, grace: '15%', ticks: {color: t.muted, font: {size: 10}, callback: compact, maxTicksLimit: 5}}
        };
        options.plugins.tooltip.callbacks.title = ctx => dayLabel(entries[ctx[0].dataIndex].label);
        options.plugins.tooltip.callbacks.label = ctx => money(ctx.parsed.y);
        options.onClick = (event, elements) => { if (elements.length) setFilter('day', entries[elements[0].index].label); };
        const labels = {id: 'cotTrendValues', afterDatasetsDraw(chart) {
            const ctx = chart.ctx; ctx.save(); ctx.fillStyle = t.text; ctx.font = '600 10px system-ui'; ctx.textAlign = 'center';
            chart.getDatasetMeta(0).data.forEach((point, i) => {
                if (entries[i].amount) ctx.fillText(compact(entries[i].amount), point.x, point.y - (i % 2 ? 18 : 7));
            }); ctx.restore();
        }};
        const holder = get('df-trend-chart').parentElement;
        holder.style.minWidth = entries.length > 10 ? entries.length * 62 + 'px' : '';
        mount('df-trend-chart', {type: 'line', plugins: [labels], data: {labels: entries.map(e => shortDay(e.label)), datasets: [{
            label: 'Pendiente de aprobación', data: entries.map(e => e.amount), borderColor: t.colors[2], pointRadius: 3,
        }]}, options}, entries.length > 0);
    }
    function kpis(summary, commercial, visibleRows) {
        const items = mode === 'rendicion' ? [
            ['Total rendido', money(summary.amount), 'Importe pagado registrado'],
            ['Total registros', number(summary.count), 'Solicitudes de la selección'],
            ['Total depositado', money(summary.deposited), 'Con depósito registrado'],
            ['Registros depositados', number(summary.depositedCount), 'Solicitudes con depósito'],
            ['Total sustentado', money(summary.supported), 'Importe pagado con sustento'],
            ['Registros sustentados', number(summary.supportedCount), 'Incluye sustentos por revisar'],
        ] : [['SUB TOTAL + FEE', money(summary.amount), 'Importe total cotizado'],
            ['Total cotizaciones', number(summary.count), 'Solicitudes de la selección'],
            ['Pendiente de aprobación', money(model.sum(commercial.pending, r => r.monto)), number(commercial.pending.length) + ' cotizaciones'],
            ['Aprobadas por ejecutar', money(model.sum(commercial.approved, r => r.monto)), number(commercial.approved.length) + ' cotizaciones'],
            ['Atendidas y ejecutadas', money(model.sum(commercial.attended, r => r.monto)), number(commercial.attended.length) + ' cotizaciones'],
            ['Anuladas', money(model.sum(visibleRows.filter(r => r.pestania === 'cancelado'), r => r.monto)), 'Fuera de las etapas activas']];
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
        function values(key) {
        const map = {month: row => row.mes, state: row => row.estado, operator: row => model.operator(row, mode),
            budget: row => mode === 'rendicion' ? row.presupuesto : row.gasto, type: row => model.type(row), person: row => model.person(row, mode),
            project: row => row.proyecto || 'Sin proyecto', approval: row => row.gasto_aprobacion,
            day: row => mode === 'rendicion' ? row.dia_pago : row.dia};
        return [...new Set(rows.map(map[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    }
    function clearAll() {
        KEYS.forEach(key => { state[key] = ''; const select = get('df-' + key); if (select) select.value = ''; });
        render();
    }
    function render() {
        const filtered = model.filter(rows, mode, state), summary = model.summary(filtered, mode);
        const commercial = mode === 'cotizaciones' ? model.cotizaciones(filtered) : null;
        kpis(summary, commercial, filtered); donut(summary.operators);
        if (mode === 'cotizaciones') {
            bars('df-budget-chart', commercial.budgets);
            bars('df-person-chart', commercial.managers, {horizontal: true, limit: 10});
            bars('df-attended-chart', commercial.attendedGroups);
            bars('df-cobra-chart', commercial.cobra);
            bars('df-refacturable-chart', commercial.refacturable);
            bars('df-states-chart', [...summary.states].sort((a,b) => b.count-a.count), {horizontal: true, limit: 12, measure: 'count', filterKey: 'state'});
            cotTrend(commercial.trend);
        } else {
            bars('df-budget-chart', summary.budgets, {filterKey: 'budget'});
            bars('df-person-chart', summary.people, {horizontal: true, limit: 8, filterKey: 'person'});
            trendChart(filtered);
            bars('df-sust-budget-chart', summary.supportedBudgets);
            bars('df-sust-operator-chart', summary.supportedOperators, {horizontal: true, kind: 'operator'});
            bars('df-states-chart', [...summary.states].sort((a,b) => b.count-a.count), {horizontal: true, limit: 12, measure: 'count', filterKey: 'state'});
        }

        const undated = filtered.filter(row => !(mode === 'rendicion' ? row.dia_pago : row.dia)).length;
        get('df-caption').textContent = number(filtered.length) + ' registros en la selección'
            + (undated ? ' · ' + number(undated) + ' sin fecha para la evolución' : '')
            + (mode === 'cotizaciones' ? ' · Proveedor se cuenta una sola vez.' : ' · Los importes corresponden a pagos registrados.');
    }
    function initialize() {
        selectKeys.forEach(key => {
            const select = get('df-' + key), list = values(key).sort((a,b) => labelFor(key,a).localeCompare(labelFor(key,b)));
            list.forEach(value => select.add(new Option(labelFor(key, value), value)));
            if (key === 'project' && list.filter(value => value !== 'Sin proyecto').length < 1) select.closest('label').hidden = true;
            select.addEventListener('change', event => { state[key] = event.target.value; render(); });
        });
        const months = values('month');
        if (data.mes_actual && months.includes(data.mes_actual)) { state.month = data.mes_actual; get('df-month').value = state.month; }
        get('df-clear').addEventListener('click', clearAll);
        new MutationObserver(render).observe(document.body, {attributes: true, attributeFilter: ['class']});
        new ResizeObserver(fitKpis).observe(get('df-kpis'));
        render();
    }
    initialize();
}());
