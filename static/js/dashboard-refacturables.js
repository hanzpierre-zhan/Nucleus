(() => {
    'use strict';
    const panel = document.getElementById('df-analysis');
    if (!panel) return;

    const get = id => document.getElementById('df-ref-' + id);
    const node = (tag, text) => {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        return element;
    };
    const money = new Intl.NumberFormat('es-PE', {style: 'currency', currency: 'PEN'});
    const number = new Intl.NumberFormat('es-PE');
    const amount = cents => money.format(cents / 100);
    const types = ['Gasto Cobra', 'Refacturable'];
    const zero = () => ({count: 0, cents: 0});
    const supervisor = get('supervisor');
    let rows = [];
    const charts = new Map();
    const tramos = [
        ['0–1 días', 1, '#1baf7a'], ['2–3 días', 3, '#65a30d'],
        ['4–7 días', 7, '#ca8a04'], ['8–15 días', 15, '#ea580c'],
        ['Más de 15 días', Infinity, '#dc2626'], ['Sin fecha', null, '#64748b'],
    ];
    const hoy = Date.parse(panel.dataset.hoy);
    function edad(fecha) {
        const dias = (hoy - Date.parse(fecha)) / 86400000;
        return Number.isFinite(dias) && dias >= 0 ? Math.floor(dias) : null;
    }
    function dibujar(id, labels, datasets, stacked, detalles) {
        const canvas = get(id);
        charts.get(id)?.destroy();
        charts.delete(id);
        canvas.hidden = !labels.length;
        canvas.parentElement.querySelector('.df-ref-vacio')?.remove();
        if (!labels.length) {
            const aviso = node('p', 'Sin casos refacturables para estos filtros.');
            aviso.className = 'df-ref-vacio';
            canvas.parentElement.append(aviso);
            return;
        }
        if (!window.Chart) return;
        const color = getComputedStyle(panel).getPropertyValue('--ios-label').trim();
        charts.set(id, new Chart(canvas, {
            type: 'bar', data: {labels, datasets},
            options: {indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false,
                scales: {x: {stacked, ticks: {color, callback: value => money.format(value)}},
                    y: {stacked, ticks: {color}, grid: {display: false}}},
                plugins: {legend: {display: stacked, labels: {color, boxWidth: 9}},
                    tooltip: {callbacks: {label: ctx => {
                        const caso = detalles[ctx.datasetIndex][ctx.dataIndex];
                        return (stacked ? ctx.dataset.label + ' · ' : '') + amount(caso.cents) + ' · ' + caso.count + ' casos';
                    }}}},
            },
        }));
    }
    function graficos(byStage) {
        const grupos = [...byStage].map(([stage, items]) => {
            const bloques = tramos.map(zero);
            const total = zero();
            for (const row of items) {
                if (!Object.hasOwn(row.gastos.Refacturable || {}, stage)) continue;
                const cents = row.gastos.Refacturable[stage];
                const dias = edad(row.fecha);
                const tramo = bloques[dias === null ? tramos.length - 1 : tramos.findIndex(([, fin]) => dias <= fin)];
                tramo.count++; tramo.cents += cents;
                total.count++; total.cents += cents;
            }
            return {stage, bloques, total};
        }).filter(g => g.total.count).sort((a, b) => b.total.cents - a.total.cents);
        const labels = grupos.map(g => g.stage);
        const totals = grupos.map(g => g.total);
        dibujar('state-chart', labels, [{data: totals.map(g => g.cents / 100), backgroundColor: '#1baf7a',
            borderRadius: 4, maxBarThickness: 28}], false, [totals]);
        const porEdad = tramos.map((_, i) => grupos.map(g => g.bloques[i]));
        const activos = tramos.map((_, i) => i).filter(i => porEdad[i].some(g => g.count));
        dibujar('age-chart', labels, activos.map(i => ({label: tramos[i][0], backgroundColor: tramos[i][2],
            maxBarThickness: 28, data: porEdad[i].map(g => g.cents / 100)})), true, activos.map(i => porEdad[i]));
    }

    function summarize(items, stage) {
        const totals = [zero(), zero(), zero()];
        for (const row of items) {
            const relevant = Object.entries(row.gastos).map(([type, stages]) => [
                type, Object.entries(stages).filter(([label]) => !stage || label === stage),
            ]).filter(([, entries]) => entries.length);
            if (!relevant.length) continue;
            totals[0].count++;
            for (const [type, entries] of relevant) {
                const cents = entries.reduce((sum, [, value]) => sum + value, 0);
                totals[0].cents += cents;
                const index = types.indexOf(type);
                if (index === -1) continue;
                const target = totals[index + 1];
                target.count++;
                target.cents += cents;
            }
        }
        return totals;
    }

    function renderComparison(id, groups) {
        const body = get(id);
        body.replaceChildren();
        for (const [label, totals] of groups) {
            const tr = body.insertRow();
            tr.insertCell().textContent = label;
            for (const stat of totals.slice(1)) {
                tr.insertCell().append(node('strong', amount(stat.cents)),
                    node('span', number.format(stat.count) + (stat.count === 1 ? ' caso' : ' casos')));
            }
        }
        if (!groups.length) empty(body, 3);
    }

    function empty(body, columns) {
        const cell = body.insertRow().insertCell();
        cell.colSpan = columns;
        cell.textContent = 'Sin datos para esta selección.';
    }

    function renderConcepts() {
        const counts = new Map();
        for (const row of rows) {
            if (supervisor.value && row.supervisor !== supervisor.value) continue;
            for (const [concept, count] of Object.entries(row.conceptos)) {
                counts.set(concept, (counts.get(concept) || 0) + count);
            }
        }
        const body = get('concepts');
        body.replaceChildren();
        const ranked = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'es'));
        for (const [concept, count] of ranked) {
            const tr = body.insertRow();
            tr.insertCell().textContent = concept;
            tr.insertCell().textContent = number.format(count);
        }
        if (!ranked.length) empty(body, 2);
    }

    function render() {
        const box = get('kpis');
        box.replaceChildren();
        summarize(rows).forEach((stat, index) => {
            const card = node('article');
            card.className = 'di-card df-analysis-kpi';
            card.append(node('span', ['Total de la selección', ...types][index]),
                node('strong', amount(stat.cents)),
                node('small', number.format(stat.count) + (stat.count === 1 ? ' caso' : ' casos')));
            box.append(card);
        });
        const byProject = new Map(), byStage = new Map();
        for (const row of rows) {
            if (!byProject.has(row.proyecto)) byProject.set(row.proyecto, []);
            byProject.get(row.proyecto).push(row);
            const stages = new Set(Object.values(row.gastos).flatMap(value => Object.keys(value)));
            for (const stage of stages) {
                if (!byStage.has(stage)) byStage.set(stage, []);
                byStage.get(stage).push(row);
            }
        }
        const highestFirst = (a, b) => b[1][2].cents - a[1][2].cents || b[1][0].cents - a[1][0].cents;
        renderComparison('projects', [...byProject].map(([label, items]) => [label, summarize(items)]).sort(highestFirst));
        renderComparison('states', [...byStage].map(([label, items]) => [label, summarize(items, label)]).sort(highestFirst));
        graficos(byStage);

        const previous = supervisor.value;
        supervisor.replaceChildren(new Option('Todos los supervisores', ''));
        for (const name of [...new Set(rows.map(row => row.supervisor))].sort()) supervisor.add(new Option(name, name));
        supervisor.value = [...supervisor.options].some(option => option.value === previous) ? previous : '';
        renderConcepts();
        get('excel').disabled = !rows.length;
    }

    supervisor.addEventListener('change', renderConcepts);
    const data = get('data');
    get('excel').addEventListener('click', () => {
        const headings = ['Código', 'Proyecto', 'Supervisor', 'Fecha', 'Estado', 'Tipo de gasto', 'Importe (S/)', 'Antigüedad (días)'];
        const entries = rows.flatMap(row => Object.entries(row.gastos).flatMap(([type, stages]) =>
            Object.entries(stages).map(([stage, cents]) =>
                [row.codigo, row.proyecto, row.supervisor, row.fecha, stage, type, cents / 100, edad(row.fecha)])));
        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([headings, ...entries]), 'Detalle');
        XLSX.writeFile(workbook, (data ? 'caja-chica' : 'cotizaciones') + '-gastos.xlsx');
    });

    if (data) {
        const all = JSON.parse(data.textContent);
        const month = get('month'), project = get('project'), cancelled = document.getElementById('df-canceladas');
        for (const name of [...new Set(all.map(row => row.proyecto))].sort()) project.add(new Option(name, name));
        function applyFilters() {
            rows = all.filter(row => (cancelled.checked || !row.cancelada)
                && (!month.value || row.fecha.startsWith(month.value)) && (!project.value || row.proyecto === project.value));
            render();
        }
        for (const field of [month, project, cancelled]) field.addEventListener('change', applyFilters);
        applyFilters();
    } else {
        window.NucleusRefacturables = filtered => {
            rows = filtered.map(row => ({
                codigo: row.n, proyecto: row.proyecto, supervisor: row.supervisor,
                fecha: row.dia, conceptos: row.conceptos || {},
                gastos: {[row.gasto]: {[row.etapa_modulo || row.estado]: Math.round(Number(row.monto_modulo ?? row.monto) * 100)}},
            }));
            render();
        };
    }
})();
