(function () {
    'use strict';
    const get = id => document.getElementById('di-' + id);
    const {bucket, duration} = window.ClaroModel;
    const {blue, teal, red, amber, muted} = window.NucleusDashVisual.operationalColors;
    const colors = {created: blue, closed: teal, open: red, cancelled: muted,
        durations: [teal, amber, red]};
    const fmt = new Intl.NumberFormat('es-PE', {maximumFractionDigits: 1});

    function chart(id, groups, datasets, stacked = false) {
        const canvas = get(id);
        Chart.getChart(canvas)?.destroy();
        canvas.hidden = !groups.length;
        get(id + '-empty').hidden = !!groups.length;
        if (!groups.length) return;

        const theme = getComputedStyle(canvas);
        const muted = theme.getPropertyValue('--ios-secondary').trim();
        const grid = theme.getPropertyValue('--ios-hairline').trim();
        const config = {
            type: 'bar',
            data: {labels: groups.map(g => g.key), datasets},
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: {mode: 'index', intersect: false},
                plugins: {legend: {labels: {color: muted, boxWidth: 10, font: {size: 10}}}},
                scales: {
                    x: {stacked, ticks: {color: muted, maxTicksLimit: 8, maxRotation: 0}, grid: {display: false}},
                    y: {stacked, beginAtZero: true, ticks: {color: muted, precision: 0}, grid: {color: grid}},
                },
            },
        };
        new Chart(canvas, window.NucleusDashVisual?.prepare(config) || config);
    }

    function groupByPeriod(id) {
        const groups = new Map();
        const scale = get(id + '-scale').value;
        return {
            at(date) {
                const key = bucket(date, scale);
                if (!groups.has(key)) groups.set(key, {key, created: 0, closed: 0, open: 0, cancelled: 0, duration: [0, 0, 0]});
                return groups.get(key);
            },
            ordered: () => [...groups.values()].sort((a, b) => a.key.localeCompare(b.key)),
        };
    }

    function render(rows, today) {
        const evolution = groupByPeriod('evolution');
        const closures = groupByPeriod('closures');
        let closed = 0, measured = 0, onTime = 0, timed = 0;
        for (const row of rows) {
            const isClosed = !row.cancelado && row.grupo === 'Producción';
            if (row.fecha) {
                const group = evolution.at(row.fecha);
                group.created++;
                if (!isClosed && !row.cancelado && row.fecha <= today) group.open++;
            }
            if (row.cancelacion) evolution.at(row.cancelacion).cancelled++;
            if (!isClosed) continue;
            closed++;
            if (row.sla !== null) {
                measured++;
                if (row.sla) onTime++;
            }
            if (!row.cierre) continue;
            evolution.at(row.cierre).closed++;
            const hours = duration(row);
            if (hours === null || !Number.isFinite(hours) || hours < 0) continue;
            closures.at(row.cierre).duration[hours <= 24 ? 0 : hours <= 48 ? 1 : 2]++;
            timed++;
        }
        const groups = evolution.ordered();
        const series = [['created', 'Creadas'], ['closed', 'Cerradas'], ['cancelled', 'Canceladas']]
            .filter(([key]) => key !== 'cancelled' || groups.some(g => g.cancelled))
            .map(([key, label]) => ({label, data: groups.map(g => g[key]), backgroundColor: colors[key], borderRadius: 4}));
        series.unshift({type: 'line', label: 'Abiertas hoy', data: groups.map(g => g.open),
            borderColor: colors.open, backgroundColor: colors.open, borderWidth: 2.5, tension: .25,
            pointRadius: groups.length > 50 ? 0 : 2});
        chart('evolution', groups, series);

        const periods = closures.ordered();
        chart('closures', periods, ['Hasta 24 h', 'Más de 24 a 48 h', 'Más de 48 h'].map((label, i) =>
            ({label, data: periods.map(g => g.duration[i]), backgroundColor: colors.durations[i], borderRadius: 3})), true);
        get('closures-note').textContent = `De creación a cierre · ${fmt.format(timed)} de ${fmt.format(closed)} cierres con duración`;

        const percentage = measured ? onTime / measured * 100 : null;
        const arc = get('sla-arc');
        arc.setAttribute('visibility', measured ? 'visible' : 'hidden');
        arc.setAttribute('stroke-dasharray', `${percentage ?? 0} 100`);
        get('sla-value').textContent = measured ? fmt.format(percentage) + '%' : '—';
        get('sla-note').textContent = measured
            ? `${fmt.format(onTime)} dentro de SLA de ${fmt.format(measured)} evaluadas · ${fmt.format(closed - measured)} sin dato`
            : 'Sin datos de SLA para esta selección.';
    }

    window.NucleusOperationalCharts = {render};
})();
