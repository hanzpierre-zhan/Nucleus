(function () {
    'use strict';
    const selector = document.getElementById('dg-periodo');
    const canvas = document.getElementById('dg-evolucion');
    const depositos = JSON.parse(document.getElementById('dg-depositos').textContent);
    const {bucket} = window.ClaroModel;
    const {prepare, operationalColors} = window.NucleusDashVisual;
    const series = {
        'Gasto Cobra': operationalColors.blue,
        Refacturable: operationalColors.teal,
        'Sin clasificar': operationalColors.amber,
    };
    const dinero = new Intl.NumberFormat('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const compacto = new Intl.NumberFormat('es-PE', {notation: 'compact', maximumFractionDigits: 1});
    const soles = value => 'S/ ' + compacto.format(value);
    let chart;

    function render() {
        const grupos = new Map();
        for (const [fecha, montos] of Object.entries(depositos)) {
            const periodo = bucket(fecha, selector.value);
            if (!grupos.has(periodo)) grupos.set(periodo, {});
            const grupo = grupos.get(periodo);
            for (const [tipo, monto] of Object.entries(montos)) {
                grupo[tipo] = (grupo[tipo] || 0) + monto;
            }
        }
        const periodos = [...grupos.keys()].sort();
        const datasets = Object.entries(series).map(([label, color]) => ({
            label,
            data: periodos.map(periodo => grupos.get(periodo)[label] || 0),
            borderColor: color,
            pointRadius: periodos.length <= 35 ? 3 : 0,
        })).filter(dataset => dataset.data.some(Boolean));
        const theme = getComputedStyle(canvas);
        const texto = theme.getPropertyValue('--ios-secondary').trim();
        chart?.destroy();
        chart = new Chart(canvas, prepare({
            type: 'line',
            data: {labels: periodos, datasets},
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: {mode: 'index', intersect: false},
                plugins: {
                    legend: {labels: {color: texto}},
                    tooltip: {callbacks: {label: item => item.dataset.label + ' · S/ ' + dinero.format(item.parsed.y)}},
                },
                scales: {
                    x: {ticks: {color: texto, maxTicksLimit: 10, maxRotation: 0}, grid: {display: false}},
                    y: {beginAtZero: true, ticks: {color: texto, callback: soles}},
                },
            },
        }, soles));
    }

    selector.addEventListener('change', render);
    new MutationObserver(render).observe(document.body, {attributes: true, attributeFilter: ['class']});
    render();
}());
