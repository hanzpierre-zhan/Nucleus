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
    const menus = new Map();
    const seleccion = key => Array.isArray(state[key]) ? state[key] : state[key] ? [state[key]] : [];
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
        if (menus.has(key)) {
            const actual = seleccion(key);
            state[key] = actual.includes(value) ? actual.filter(item => item !== value) : [...actual, value];
            syncFilter(key);
            render();
            return;
        }
        state[key] = state[key] === value ? '' : value;
        const select = get('df-' + key);
        if (select) select.value = state[key];
        render();
    }
    function mount(id, config, hasData, format = compact) {
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
        charts.set(id, new Chart(canvas, window.NucleusDashVisual?.prepare(config, format) || config));
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
        const selected = filterKey ? seleccion(filterKey) : [];
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
            if (kind === 'concepto') return number(item.count) + ' ítems';
            return measure === 'count' ? number(item.count) + ' registros · ' + money(item.amount)
                : money(item.amount) + ' · ' + number(item.count) + ' registros';
        };
        if (filterKey) options.onClick = (event, elements) => {
            if (elements.length) setFilter(filterKey, (items[elements[0].index].key || items[elements[0].index].label));
        };
        mount(id, {type: 'bar', data: {labels: items.map(item => filterKey === 'state' ? stateLabel(item.label) : !horizontal && item.label.includes(' · ') ? item.label.split(' · ').map(name) : name(item.label)), datasets: [{
            data: items.map(valueOf),
            backgroundColor: items.map((item, index) => alpha(color(item.label, index, kind), selected.length && !selected.includes(item.key || item.label) ? .28 : 1)),
            borderRadius: 4, maxBarThickness: horizontal ? 26 : 54, barPercentage: .72,
        }]}, options}, items.some(item => valueOf(item) !== 0), format);
    }
    function donut(entries) {
        const total = entries.reduce((value, item) => value + Math.max(0, item.amount), 0);
        const items = entries.filter(item => item.amount > 0), selected = seleccion('operator');
        const colors = items.map((item, i) => alpha(color(item.label, i, 'operator'), selected.length && !selected.includes(item.label) ? .28 : 1));
        const legend = get('df-legend'); legend.replaceChildren();
        items.forEach((item, i) => {
            const li = node('li'), dot = node('i'), label = node('span', name(item.label));
            dot.style.background = color(item.label, i, 'operator');
            li.className = selected.length && !selected.includes(item.label) ? 'is-dim' : '';
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
    function cotTrend(dailyEntries) {
        const escala = get('df-trend-period').value;
        const grupos = new Map();
        for (const entry of dailyEntries) {
            const key = window.ClaroModel.bucket(entry.label, escala);
            grupos.set(key, (grupos.get(key) || 0) + entry.amount);
        }
        const entries = [...grupos].map(([label, amount]) => ({label, amount}));
        const options = common(), t = theme();
        options.layout = {padding: {top: 22, right: 32, left: 12}};
        options.scales = {
            x: {grid: {display: false}, border: {display: false}, ticks: {color: t.muted, font: {size: 10}, maxRotation: 0}},
            y: {beginAtZero: true, border: {display: false}, grid: {color: t.grid}, grace: '15%', ticks: {color: t.muted, font: {size: 10}, callback: compact, maxTicksLimit: 5}}
        };
        const labelForPeriod = value => escala === 'dia' ? dayLabel(value) :
            escala === 'semana' ? 'Semana del ' + dayLabel(value) : value;
        options.plugins.tooltip.callbacks.title = ctx => labelForPeriod(entries[ctx[0].dataIndex].label);
        options.plugins.tooltip.callbacks.label = ctx => money(ctx.parsed.y);
        if (escala === 'dia') {
            options.onClick = (event, elements) => { if (elements.length) setFilter('day', entries[elements[0].index].label); };
        }
        const holder = get('df-trend-chart').parentElement;
        holder.style.minWidth = entries.length > 10 ? entries.length * 62 + 'px' : '';
        mount('df-trend-chart', {type: 'line', data: {labels: entries.map(e => e.label.length === 10 ? shortDay(e.label) : e.label), datasets: [{
            label: 'Pendiente de aprobación', data: entries.map(e => e.amount), borderColor: t.colors[2], pointRadius: 3,
        }]}, options}, entries.length > 0);
    }
    function kpis(summary) {
        const items = [
            ['Total rendido', money(summary.amount), 'Importe pagado registrado'],
            ['Total registros', number(summary.count), 'Solicitudes de la selección'],
            ['Total depositado', money(summary.deposited), 'Con depósito registrado'],
            ['Registros depositados', number(summary.depositedCount), 'Solicitudes con depósito'],
            ['Total sustentado', money(summary.supported), 'Importe pagado con sustento'],
            ['Registros sustentados', number(summary.supportedCount), 'Incluye sustentos por revisar'],
        ];
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
        const map = {month: row => row.mes, state: model.stage, operator: row => model.operator(row, mode),
            budget: row => mode === 'rendicion' ? row.presupuesto : row.gasto, type: row => model.type(row), person: row => model.person(row, mode),
            project: row => row.proyecto || 'Sin proyecto', approval: row => row.gasto_aprobacion,
            day: row => mode === 'rendicion' ? row.dia_pago : row.dia};
        return [...new Set(rows.map(map[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    }
    function multiFilter(key, select, values) {
        const group = node('div'), menu = node('details'), label = node('span', select.parentElement.firstChild.textContent.trim());
        const trigger = node('summary'), options = node('div'), all = node('input');
        group.className = 'df-filter-group';
        menu.className = 'df-filter-menu';
        options.className = 'df-filter-options';
        trigger.setAttribute('aria-label', 'Seleccionar ' + label.textContent.toLowerCase());
        if (key === 'project' && !values.some(value => value !== 'Sin proyecto')) group.hidden = true;
        const defaultLabel = select.options[0].text;
        function addOption(input, text) {
            const item = node('label');
            input.type = 'checkbox';
            item.append(input, node('span', text));
            options.append(item);
        }
        addOption(all, defaultLabel);
        for (const value of values) {
            const input = node('input');
            input.value = value;
            addOption(input, labelFor(key, value));
        }
        menu.append(trigger, options);
        group.append(label, menu);
        select.parentElement.replaceWith(group);
        menus.set(key, {menu, trigger, options, all, defaultLabel});
        options.addEventListener('change', event => {
            state[key] = event.target === all ? [] : [...options.querySelectorAll('input:checked')]
                .filter(input => input !== all).map(input => input.value);
            syncFilter(key);
            render();
        });
        menu.addEventListener('keydown', event => {
            if (event.key !== 'Escape') return;
            menu.open = false;
            trigger.focus();
        });
        syncFilter(key);
    }
    function syncFilter(key) {
        const {trigger, options, all, defaultLabel} = menus.get(key);
        const selected = seleccion(key);
        for (const option of options.querySelectorAll('input')) {
            option.checked = option === all ? !selected.length : selected.includes(option.value);
        }
        trigger.textContent = selected.length === 1 ? labelFor(key, selected[0])
            : selected.length ? selected.length + ' seleccionados' : defaultLabel;
        trigger.title = selected.map(value => labelFor(key, value)).join(', ');
    }
    function clearAll() {
        KEYS.forEach(key => {
            state[key] = key === 'month' && mode === 'cotizaciones' ? data.mes_actual : '';
            if (menus.has(key)) syncFilter(key);
            else if (get('df-' + key)) get('df-' + key).value = '';
        });
        const canceladas = get('df-canceladas');
        if (canceladas) canceladas.checked = state.incluirCanceladas = false;
        render();
    }
    function render() {
        const filtered = model.filter(rows, mode, state), summary = model.summary(filtered, mode);
        const commercial = mode === 'cotizaciones' ? model.cotizaciones(filtered) : null;
        if (mode === 'cotizaciones' && window.CotPuntual) {
            // Vista puntual (estilo Claro): KPIs, embudo, antigüedad, clientes y evolución.
            window.CotPuntual.render(filtered, {
                filtrar: cambios => model.filter(rows, mode, {...state, ...cambios}),
                mesesElegidos: () => seleccion('month'), redibujar: render,
            });
        } else if (mode === 'cotizaciones') {
            donut(summary.operators);
            window.NucleusRefacturables?.(filtered);
            bars('df-budget-chart', commercial.budgets);
            const conceptos = model.conceptos(filtered);
            const total = conceptos.reduce((sum, item) => sum + item.count, 0);
            const pendientes = conceptos.find(item => item.label === 'Por revisar')?.count || 0;
            get('df-concept-caption').textContent = total
                ? number(total) + ' ítems · ' + number(pendientes) + ' por revisar · 10 conceptos principales'
                : 'Sin ítems registrados en esta selección';
            const homologados = conceptos.filter(item => item.label !== 'Por revisar');
            const barras = homologados.slice(0, 10);
            const otros = homologados.slice(10).reduce((sum, item) => sum + item.count, 0);
            if (otros) barras.push({label: 'Otros conceptos', count: otros});
            if (pendientes) barras.push({label: 'Por revisar', count: pendientes});
            bars('df-concept-chart', barras, {horizontal: true, kind: 'concepto', measure: 'count', limit: 12});
            bars('df-attended-chart', commercial.attendedGroups);
            bars('df-cobra-chart', commercial.cobra);
            bars('df-refacturable-chart', commercial.refacturable);
            bars('df-states-chart', [...summary.states].sort((a,b) => b.count-a.count), {horizontal: true, limit: 12, measure: 'count', filterKey: 'state'});
            cotTrend(commercial.trend);
        } else {
            donut(summary.operators);
            kpis(summary);
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
            if (mode === 'cotizaciones') {
                if (key === 'month' && data.mes_actual && !list.includes(data.mes_actual)) list.unshift(data.mes_actual);
                multiFilter(key, select, list);
                return;
            }
            list.forEach(value => select.add(new Option(labelFor(key, value), value)));
            if (key === 'project' && list.filter(value => value !== 'Sin proyecto').length < 1) select.closest('label').hidden = true;
            select.addEventListener('change', event => { state[key] = event.target.value; render(); });
        });
        const months = values('month');
        if (data.mes_actual && (mode === 'cotizaciones' || months.includes(data.mes_actual))) {
            state.month = data.mes_actual;
            if (menus.has('month')) syncFilter('month');
            else get('df-month').value = state.month;
        }
        if (menus.size) document.addEventListener('click', event => {
            for (const {menu} of menus.values()) if (!menu.contains(event.target)) menu.open = false;
        });
        const canceladas = get('df-canceladas');
        if (canceladas) {
            state.incluirCanceladas = canceladas.checked;
            canceladas.addEventListener('change', () => {
                state.incluirCanceladas = canceladas.checked;
                render();
            });
        }
        get('df-clear').addEventListener('click', clearAll);
        get('df-trend-period')?.addEventListener('change', render);
        new MutationObserver(render).observe(document.body, {attributes: true, attributeFilter: ['class']});
        if (get('df-kpis')) new ResizeObserver(fitKpis).observe(get('df-kpis'));
        render();
    }
    initialize();
}());
