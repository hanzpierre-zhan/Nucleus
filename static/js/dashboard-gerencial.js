(function () {
    'use strict';
    const el = id => document.getElementById('dg-' + id);
    const {actividad, rend, cot} = JSON.parse(el('datos').textContent);
    const {bucket} = window.ClaroModel;
    const {prepare, operationalColors} = window.NucleusDashVisual;
    const campos = ['depositado', 'depositos', 'por_rendir', 'por_validar', 'cotizado', 'cotizaciones'];
    const proyectos = [...new Set(actividad.map(fila => fila.proyecto))].sort();
    const colores = ['#4b8cff', '#22b5aa', '#b18bfa', '#e9ac45', '#ed7d89', '#82a65a'];
    const dinero = new Intl.NumberFormat('es-PE', {style: 'currency', currency: 'PEN'});
    const compacto = new Intl.NumberFormat('es-PE', {notation: 'compact', maximumFractionDigits: 1});
    const cantidades = new Intl.NumberFormat('es-PE');
    const soles = monto => dinero.format(monto);
    let chart;

    for (const proyecto of proyectos) {
        el('proyecto').add(new Option(proyecto, proyecto));
    }

    function sumar(destino, fila) {
        for (const campo of campos) destino[campo] = (destino[campo] || 0) + (fila[campo] || 0);
    }

    function tabla(porProyecto, metrica) {
        const tbody = el('proyectos');
        tbody.replaceChildren();
        const orden = [...porProyecto].sort((a, b) => (b[1][metrica] || 0) - (a[1][metrica] || 0) || a[0].localeCompare(b[0]));
        for (const [nombre, datos] of orden) {
            const fila = tbody.insertRow();
            const titulo = document.createElement('th');
            titulo.scope = 'row';
            titulo.textContent = nombre;
            fila.append(titulo);
            for (const [visible, campo, conteo] of [[rend, 'depositado', 'depositos'], [cot, 'cotizado', 'cotizaciones']]) {
                if (!visible) continue;
                const celda = fila.insertCell();
                const importe = document.createElement('strong');
                const cantidad = document.createElement('small');
                importe.textContent = soles(datos[campo] || 0);
                cantidad.textContent = cantidades.format(datos[conteo] || 0) + ' registros';
                celda.append(importe, cantidad);
            }
        }
        el('sin-proyectos').hidden = orden.length > 0;
    }

    function dibujar(barras, metrica) {
        chart?.destroy();
        const conteo = metrica === 'depositado' ? 'depositos' : 'cotizaciones';
        const periodos = [...new Set([...barras.values()].flatMap(serie => [...serie.keys()]))].sort();
        const datasets = proyectos.filter(nombre => barras.has(nombre)).map(nombre => {
            const serie = barras.get(nombre);
            return {
                label: nombre,
                data: periodos.map(periodo => serie.get(periodo)?.[metrica] || 0),
                cantidades: periodos.map(periodo => serie.get(periodo)?.[conteo] || 0),
                backgroundColor: colores[proyectos.indexOf(nombre) % colores.length],
                maxBarThickness: 64,
                stack: 'proyectos',
                order: 1,
            };
        }).filter(serie => serie.cantidades.some(Boolean));
        el('grafico').hidden = !datasets.length;
        el('vacio').hidden = !!datasets.length;
        if (!datasets.length) return;
        const total = periodos.map((_, index) => datasets.reduce((sum, serie) => sum + serie.data[index], 0));
        datasets.push({
            type: 'line',
            label: metrica === 'depositado' ? 'Total depositado' : 'Total cotizado',
            data: total,
            borderColor: operationalColors.red,
            backgroundColor: operationalColors.red,
            pointRadius: periodos.length <= 35 ? 3 : 0,
            stack: 'total',
        });
        const canvas = el('evolucion');
        const style = getComputedStyle(canvas);
        const texto = style.getPropertyValue('--ios-secondary').trim();
        const borde = style.getPropertyValue('--ios-hairline').trim();
        chart = new Chart(canvas, prepare({
            type: 'bar',
            data: {labels: periodos, datasets},
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                plugins: {
                    legend: {position: 'bottom', labels: {color: texto, usePointStyle: true, boxWidth: 8, padding: 12}},
                    tooltip: {callbacks: {label: item => {
                        const cantidad = item.dataset.cantidades?.[item.dataIndex];
                        if (cantidad == null) return item.dataset.label + ' · ' + soles(item.parsed.y);
                        return item.dataset.label + ' · ' + soles(item.parsed.y) + ' · ' + cantidades.format(cantidad) + ' registros';
                    }}},
                },
                scales: {
                    x: {stacked: true, grid: {display: false}, ticks: {color: texto, maxTicksLimit: 8, maxRotation: 0}},
                    y: {stacked: true, beginAtZero: true, grid: {color: borde}, ticks: {color: texto, callback: monto => 'S/ ' + compacto.format(monto)}},
                },
            },
        }, monto => 'S/ ' + compacto.format(monto)));
    }

    function render() {
        const desde = el('desde').value;
        const hasta = el('hasta').value;
        const proyecto = el('proyecto').value;
        const escala = el('periodo').value;
        const metrica = el('metrica')?.value || (rend ? 'depositado' : 'cotizado');
        const invalido = Boolean(desde && hasta && desde > hasta);
        el('error').hidden = !invalido;
        el('error').textContent = invalido ? 'La fecha inicial debe ser anterior o igual a la fecha final.' : '';
        el('chart-title').textContent = metrica === 'depositado' ? 'Evolución de depósitos' : 'Evolución de cotizaciones';
        const fechaBase = metrica === 'depositado' ? 'Fecha de pago' : 'Fecha de cotización o registro';
        el('fecha-base').textContent = fechaBase + (escala === 'semana' ? ' · Semanas desde el lunes' : '');

        const total = {};
        const porProyecto = new Map();
        const barras = new Map();
        for (const fila of actividad) {
            if (invalido || (desde && fila.fecha < desde) || (hasta && fila.fecha > hasta) ||
                (proyecto && fila.proyecto !== proyecto)) continue;
            sumar(total, fila);
            if (!porProyecto.has(fila.proyecto)) porProyecto.set(fila.proyecto, {});
            sumar(porProyecto.get(fila.proyecto), fila);
            if (!barras.has(fila.proyecto)) barras.set(fila.proyecto, new Map());
            const serie = barras.get(fila.proyecto);
            const periodo = bucket(fila.fecha, escala);
            if (!serie.has(periodo)) serie.set(periodo, {});
            sumar(serie.get(periodo), fila);
        }
        for (const campo of campos) {
            const indicador = el(campo);
            if (!indicador) continue;
            const valor = total[campo] || 0;
            indicador.textContent = campo === 'depositos' || campo === 'cotizaciones'
                ? cantidades.format(valor) + ' ' + (campo === 'depositos' ? 'depósitos' : 'cotizaciones')
                : soles(valor);
        }
        tabla(porProyecto, metrica);
        dibujar(barras, metrica);
    }

    for (const filtro of ['desde', 'hasta', 'proyecto', 'periodo', 'metrica']) {
        el(filtro)?.addEventListener('change', render);
    }
    new MutationObserver(render).observe(document.body, {attributes: true, attributeFilter: ['class']});
    render();
}());
