(function () {
    'use strict';
    const data = JSON.parse(document.getElementById('di-data').textContent);
    const get = id => document.getElementById(id);
    const rows = data.detalle;
    const consulta = window.NucleusDashboardConsulta.create(rows, data);
    let page = 0, visible = [];

    const num = v => new Intl.NumberFormat('es-PE').format(v);
    const _currency = new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' });
    const money = v => _currency.format(v || 0);
    const moneyShort = money; // Mantener céntimos también en resúmenes.
    const total = (items, k) => items.reduce((a, r) => a + (r[k] || 0), 0);

    const ETAPAS = [
        ['VALIDACION', 'Validación', '#34C759'], ['DEPOSITOS', 'Depósitos', '#007AFF'],
        ['EVIDENCIA', 'Evidencia', '#FFCC00'], ['SUSTENTO', 'Sustento', '#5AC8FA'],
        ['OBSERVADO', 'Observado', '#FF9500'], ['ATENDIDO', 'Atendido', '#34C759'],
        ['ARCHIVADO', 'Archivar', '#5AC8FA'], ['ANULADO', 'Anulado', '#6B7280'],
    ];
    const ETAPA_LABEL = {};
    const ETAPA_COLOR = {};
    ETAPAS.forEach(([k, l, c]) => { ETAPA_LABEL[k] = l; ETAPA_COLOR[k] = c; });
    const CERRADAS = ['ATENDIDO', 'ARCHIVADO', 'ANULADO'];
    const SUSTENTADAS = ['SUSTENTO', 'ATENDIDO', 'ARCHIVADO'];
    const esSustentado = r => SUSTENTADAS.indexOf(r.etapa) >= 0;
    // El formulario no siempre trae solicitante; se usa el beneficiario como persona real.
    const persona = r => (r.solicito && r.solicito !== 'Sin datos') ? r.solicito
        : (r.beneficiario && r.beneficiario !== 'Sin beneficiario' ? r.beneficiario : 'Sin datos');

    for (const [id, key] of [['di-client', 'proyecto'], ['di-budget', 'presupuesto'], ['di-owner', 'solicito']]) {
        [...new Set(rows.map(r => r[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b))
            .forEach(v => get(id).add(new Option(window.NucleusIdentity.display(v), v)));
    }
    [...new Set(rows.map(r => r.mes).filter(Boolean))].sort().forEach(v => get('di-month').add(new Option(window.NucleusIdentity.display(v), v)));

    function fillDays() {
        const m = get('di-month').value, sel = get('di-day'), prev = sel.value;
        sel.disabled = !m;
        sel.replaceChildren(new Option('Todos', ''));
        if (!m) return;
        const dias = [...new Set(rows.filter(r => r.mes === m && r.dia).map(r => r.dia.slice(8, 10)))].sort();
        dias.forEach(d => sel.add(new Option(d, d)));
        if (dias.includes(prev)) sel.value = prev;
    }

    function filtered() {
        const m = get('di-month').value, d = get('di-day').value, p = get('di-client').value,
            b = get('di-budget').value, o = get('di-owner').value;
        return rows.filter(r =>
            (!m || r.mes === m) && (!d || (r.dia || '').slice(8, 10) === d) &&
            (!p || r.proyecto === p) && (!b || r.presupuesto === b) && (!o || r.solicito === o) && consulta.matches(r)
            && (!get('dr-etapa-filtro').value || r.etapa === get('dr-etapa-filtro').value));
    }

    const bars = window.NucleusDashboardGraficos.render;

    function agg(items, keyFn) {
        const m = new Map();
        items.forEach(r => {
            const k = keyFn(r) || 'Sin datos';
            const e = m.get(k) || { n: 0, monto: 0 };
            e.n++; e.monto += r.monto || 0; m.set(k, e);
        });
        return [...m.entries()];
    }

    function groupAgg(items, key) {
        return agg(items, r => r[key]).sort((a, b) => b[1].n - a[1].n || b[1].monto - a[1].monto);
    }

    // ── Chart.js: dona, barras y línea temporal ────────────────────────────────
    const charts = new Map();
    const compactMoney = new Intl.NumberFormat('es-PE', { notation: 'compact', maximumFractionDigits: 1 });
    const chartFont = 'SF Pro Display, Segoe UI, Roboto, sans-serif';
    const cssVar = name => getComputedStyle(document.querySelector('.dr-page') || document.body)
        .getPropertyValue(name).trim();

    function rgba(color, alpha) {
        const hex = String(color || '').trim();
        if (/^#([0-9a-f]{6})$/i.test(hex)) {
            const n = parseInt(hex.slice(1), 16);
            return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
        }
        return hex;
    }
    function chartTheme() {
        const accents = ['--di-blue', '--di-amber', '--di-green', '--di-cyan', '--di-purple'].map(cssVar).filter(Boolean);
        return {
            label: cssVar('--ios-label') || '#1C1C1E',
            secondary: cssVar('--ios-secondary') || '#8E8E93',
            hairline: cssVar('--ios-hairline') || '#E5E5EA',
            card: cssVar('--ios-card-bg') || '#FFFFFF',
            accents: accents.length ? accents : ['#356dcc'],
        };
    }
    function palette(size) {
        const base = chartTheme().accents;
        const out = [];
        for (let i = 0; out.length < size; i++) out.push(i % 2 ? rgba(base[(i >> 1) % base.length], 0.55) : base[i % base.length]);
        return out;
    }
    function tooltipBase(theme) {
        return {
            backgroundColor: theme.card, titleColor: theme.label, bodyColor: theme.secondary,
            borderColor: theme.hairline, borderWidth: 1, padding: 10, cornerRadius: 7, displayColors: true,
        };
    }
    function destroyChart(id) {
        const inst = charts.get(id);
        if (inst) { inst.destroy(); charts.delete(id); }
    }
    function mountChart(id, config) {
        if (!window.Chart) return;
        const canvas = get(id);
        if (!canvas) return;
        destroyChart(id);
        charts.set(id, new window.Chart(canvas.getContext('2d'), config));
    }

    function donutPend(v) {
        const pend = v.filter(r => r.depositado && !esSustentado(r));
        const entries = agg(pend, r => r.proyecto).filter(x => x[1].monto > 0)
            .sort((a, b) => b[1].monto - a[1].monto);
        const totalM = entries.reduce((a, x) => a + x[1].monto, 0);
        const theme = chartTheme(), colors = palette(entries.length);
        const legend = get('dr-pend-legend');
        legend.replaceChildren();
        entries.forEach(([name, e], i) => {
            const li = document.createElement('li'), dot = document.createElement('i'),
                label = document.createElement('span'), value = document.createElement('b');
            dot.style.background = colors[i];
            label.textContent = window.NucleusIdentity.text(name);
            value.textContent = money(e.monto) + ' · ' + (totalM ? Math.round(e.monto / totalM * 1000) / 10 : 0) + '%';
            li.title = name + ': ' + money(e.monto) + ' en ' + e.n + ' casos';
            li.append(dot, label, value); legend.append(li);
        });
        if (!entries.length) {
            const li = document.createElement('li');
            li.textContent = 'Sin importes pendientes de sustento.';
            legend.append(li);
        }
        get('dr-pend-total').textContent = 'S/ ' + compactMoney.format(totalM);
        mountChart('dr-chart-pend', {
            type: 'doughnut',
            data: {
                labels: entries.map(([name]) => window.NucleusIdentity.text(name)),
                datasets: [{ data: entries.map(([, e]) => e.monto), backgroundColor: colors, borderColor: theme.card, borderWidth: 2, hoverOffset: 5 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '64%', layout: { padding: 2 },
                plugins: {
                    legend: { display: false },
                    tooltip: Object.assign(tooltipBase(theme), {
                        callbacks: {
                            label(ctx) {
                                const e = entries[ctx.dataIndex][1];
                                const pct = totalM ? Math.round(e.monto / totalM * 1000) / 10 : 0;
                                return ' ' + money(e.monto) + ' · ' + e.n + ' casos (' + pct + '%)';
                            },
                        },
                    }),
                },
            },
        });
    }

    function verticalChart(id, entries, opts = {}) {
        const theme = chartTheme(), colors = palette(entries.length);
        const isMoney = opts.money !== false;
        mountChart(id, {
            type: 'bar',
            data: {
                labels: entries.map(([label]) => window.NucleusIdentity.text(label)),
                datasets: [{ data: entries.map(([, e]) => isMoney ? e.monto : e.n), backgroundColor: colors, borderRadius: 4, maxBarThickness: 56 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: theme.secondary, font: { size: 10, family: chartFont }, maxRotation: 32, minRotation: 0, autoSkip: false },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: theme.hairline },
                        ticks: {
                            precision: 0, color: theme.secondary, font: { size: 10, family: chartFont },
                            callback: value => isMoney ? 'S/ ' + compactMoney.format(value) : value,
                        },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: Object.assign(tooltipBase(theme), {
                        callbacks: {
                            label: ctx => ' ' + (isMoney ? money(ctx.parsed.y) : ctx.parsed.y + ' casos'),
                            afterLabel: ctx => {
                                const e = entries[ctx.dataIndex][1];
                                return isMoney ? e.n + ' registros' : money(e.monto);
                            },
                        },
                    }),
                },
            },
        });
    }

    function pagadoLine(v) {
        const pagos = v.filter(r => r.pago_registrado && r.dia_pago);
        const days = [...new Set(pagos.map(r => r.dia_pago))].sort();
        const series = [['GASTO COBRA', 'Gasto Cobra'], ['REFACTURABLE', 'Refacturable']];
        const theme = chartTheme();
        const totals = {};
        const datasets = series.map(([key, label], i) => {
            const byDay = new Map();
            pagos.filter(r => r.presupuesto === key).forEach(r => byDay.set(r.dia_pago, (byDay.get(r.dia_pago) || 0) + (r.pagado || 0)));
            totals[key] = [...byDay.values()].reduce((a, b) => a + b, 0);
            const color = theme.accents[i] || theme.accents[0];
            return {
                label: label, data: days.map(d => byDay.get(d) || 0),
                borderColor: color, backgroundColor: rgba(color, 0.16), borderWidth: 2,
                fill: false, tension: 0.3, pointRadius: 2.5, pointHoverRadius: 5,
                pointBackgroundColor: theme.card, pointBorderColor: color, pointBorderWidth: 2,
            };
        });
        mountChart('dr-chart-pagado', {
            type: 'line',
            data: { labels: days.map(d => d.slice(5)), datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: theme.secondary, font: { size: 10, family: chartFont }, maxRotation: 32, autoSkip: true, maxTicksLimit: 12 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: theme.hairline },
                        ticks: { color: theme.secondary, font: { size: 10, family: chartFont }, callback: value => 'S/ ' + compactMoney.format(value) },
                    },
                },
                plugins: {
                    legend: {
                        display: true, position: 'top', align: 'end',
                        labels: { color: theme.secondary, boxWidth: 10, boxHeight: 10, usePointStyle: true, font: { size: 10, family: chartFont } },
                    },
                    tooltip: Object.assign(tooltipBase(theme), {
                        callbacks: {
                            title: ctx => days[ctx[0].dataIndex] || '',
                            label: ctx => ' ' + ctx.dataset.label + ': ' + money(ctx.parsed.y),
                        },
                    }),
                },
            },
        });
    }

    function vizKpis(v) {
        const pagados = v.filter(r => r.pago_registrado);
        const depositos = v.filter(r => r.depositado);
        const sustentadas = v.filter(esSustentado);
        const pct = v.length ? Math.round(depositos.length / v.length * 1000) / 10 : 0;
        get('dr-viz-pagado').textContent = money(total(pagados, 'pagado'));
        get('dr-viz-pagado-n').textContent = pagados.length + (pagados.length === 1 ? ' pago registrado' : ' pagos registrados');
        get('dr-viz-registros').textContent = num(v.length);
        get('dr-viz-depositado').textContent = money(total(depositos, 'pagado'));
        get('dr-viz-depositado-n').textContent = depositos.length + (depositos.length === 1 ? ' depósito' : ' depósitos');
        get('dr-viz-dep-n').textContent = num(depositos.length);
        get('dr-viz-dep-pct').textContent = pct + '% de la selección';
        get('dr-viz-sustentado').textContent = money(total(sustentadas, 'monto'));
        get('dr-viz-sustentado-n').textContent = sustentadas.length + (sustentadas.length === 1 ? ' caso sustentado' : ' casos sustentados');
        get('dr-viz-registrado').textContent = money(total(v, 'solicitado'));
    }

    function vizCharts(v) {
        donutPend(v);
        verticalChart('dr-chart-presupuesto',
            agg(v, r => r.presupuesto).sort((a, b) => b[1].monto - a[1].monto), { money: true });
        bars('dr-viz-personas', agg(v, persona)
            .sort((a, b) => b[1].monto - a[1].monto || b[1].n - a[1].n)
            .map(([k, e]) => [k, e.n, e.n + (e.n === 1 ? ' caso · ' : ' casos · ') + money(e.monto), e.monto]));

        const sustentadas = v.filter(esSustentado);
        verticalChart('dr-chart-sust-gasto',
            agg(sustentadas, r => r.presupuesto).sort((a, b) => b[1].n - a[1].n), { money: false });
        bars('dr-viz-sust-clientes', agg(sustentadas, r => r.proyecto)
            .sort((a, b) => b[1].n - a[1].n || b[1].monto - a[1].monto)
            .map(([k, e]) => [k, e.n, e.n + ' sustentadas · ' + money(e.monto), e.monto]));
        pagadoLine(v);
    }

    function kpis(v) {
        const set = { total: v };
        ETAPAS.forEach(([k]) => { set[k.toLowerCase()] = v.filter(r => r.etapa === k); });
        for (const [k, lst] of Object.entries(set)) {
            get('dr-kpi-' + k).textContent = num(lst.length);
            get('dr-kpi-' + k + '-m').textContent = moneyShort(total(lst, 'monto'));
        }
        return set;
    }

    function story(v, set) {
        const atendidas = set.atendido.length + set.archivado.length;
        const pct = v.length ? atendidas / v.length * 100 : 0;
        get('di-story-title').textContent = v.length
            ? 'El ' + num(Math.round(pct * 10) / 10) + '% está atendido o archivado'
            : 'Sin rendiciones para esta selección';
        const msgs = [moneyShort(total(v, 'monto')) + ' en juego · validación ' + moneyShort(total(set.validacion, 'monto')) + '.'];
        if (set.validacion.length) msgs.push(set.validacion.length + ' esperando validación.');
        if (set.depositos.length) msgs.push(set.depositos.length + ' listas para depositar (' + moneyShort(total(set.depositos, 'monto')) + ').');
        if (set.evidencia.length) msgs.push(set.evidencia.length + ' depositadas sin evidencia cargada.');
        if (set.observado.length) msgs.push(set.observado.length + ' observadas por corregir.');
        get('di-story-detail').textContent = msgs.join(' ');
        get('di-progress-fill').style.width = pct + '%';
        get('di-progress-fill').parentElement.title = atendidas + ' cerradas de ' + v.length;
    }

    function months(v) {
        const p = get('di-client').value, b = get('di-budget').value, o = get('di-owner').value;
        const half = v.filter(r => r.mes);
        const porMes = new Map();
        half.forEach(r => {
            const e = porMes.get(r.mes) || { n: 0, atn: 0, monto: 0, pagado: 0 };
            e.n++; if (CERRADAS.includes(r.etapa)) e.atn++; e.monto += r.monto || 0; e.pagado += r.pagado || 0;
            porMes.set(r.mes, e);
        });
        const lista = [...porMes.entries()].sort((a, b2) => a[0].localeCompare(b2[0]));
        const max = Math.max(0, ...lista.map(x => x[1].n), 1);
        const sel = get('di-month').value || data.mes_actual;
        const box = get('di-months'); box.replaceChildren();
        const alto = 110;
        lista.forEach(([mes, e]) => {
            const bar = document.createElement('div');
            bar.className = 'di-month' + (mes === sel ? ' di-month-selected' : '');
            bar.title = mes + ': ' + e.n + ' solicitudes · ' + e.atn + ' cerradas · ' + money(e.monto) + ' (pagado ' + money(e.pagado) + ')';
            const b3 = document.createElement('b'); b3.textContent = e.n;
            const fill = document.createElement('i'); fill.style.height = e.n / max * alto + 'px';
            const label = document.createElement('span'); label.textContent = mes;
            bar.append(b3, fill, label); box.append(bar);
        });
        if (!lista.length) box.textContent = 'No hay rendiciones con fecha para estos filtros.';
    }

    function daily(v) {
        const month = get('di-month').value || data.mes_actual;
        const parts = month.split('-').map(Number);
        const days = new Date(parts[0], parts[1], 0).getDate();
        const counts = Array(days).fill(0), montos = Array(days).fill(0);
        v.filter(r => r.mes === month && r.dia).forEach(r => {
            const d = Number(r.dia.slice(8, 10)) - 1;
            if (d >= 0 && d < days) { counts[d]++; montos[d] += r.monto || 0; }
        });
        const totalN = counts.reduce((a, b) => a + b, 0), max = Math.max(...counts, 1);
        get('di-daily-month').textContent = month;
        get('di-daily-caption').textContent = totalN
            ? totalN + ' solicitudes · ' + money(montos.reduce((a, b) => a + b, 0)) + ' · ' + consulta.dateLabel()
            : 'Nada solicitado en este mes; elige otro mes para consultar el histórico';
        const ns = 'http://www.w3.org/2000/svg';
        const el = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v2]) => e.setAttribute(k, v2)); if (text !== undefined) e.textContent = text; return e; };
        const box = get('di-daily');
        const width = Math.max(320, box.clientWidth), height = 170;
        const left = 24, right = width - 6, bottom = height - 18;
        const svg = el('svg', { viewBox: '0 0 ' + width + ' ' + height, preserveAspectRatio: 'none', role: 'img', 'aria-label': totalN + ' rendiciones por día en ' + month });
        const step = (right - left) / days;
        const x = i => left + (i + 0.5) * step, y = v2 => bottom - v2 / max * (bottom - 18);
        [0, max].forEach(v2 => { svg.append(el('line', { x1: left, y1: y(v2), x2: right, y2: y(v2), class: 'di-daily-grid' })); svg.append(el('text', { x: left - 5, y: y(v2) + 3, 'text-anchor': 'end', class: 'di-daily-label' }, v2)); });
        counts.forEach((v2, i) => {
            if (v2) {
                const bar = el('rect', { x: x(i) - step * 0.32, y: y(v2), width: step * 0.64, height: Math.max(1, bottom - y(v2)), rx: 2, class: 'di-daily-dot' });
                bar.append(el('title', {}, month + '-' + String(i + 1).padStart(2, '0') + ': ' + v2 + ' solicitudes · ' + money(montos[i]))); svg.append(bar);
                svg.append(el('text', { x: x(i), y: y(v2) - 5, 'text-anchor': 'middle', class: 'di-daily-value' }, v2));
            }
            if (width >= 500 || i % 5 === 0 || i === days - 1) svg.append(el('text', { x: x(i), y: height - 3, 'text-anchor': 'middle', class: 'di-daily-label' }, i + 1));
        });
        box.replaceChildren(svg);
    }

    function paneles(v) {
        const abiertas = v.filter(r => !CERRADAS.includes(r.etapa));

        bars('dr-etapas', ETAPAS.map(([k, l]) => {
            const it = v.filter(r => r.etapa === k);
            return [l, it.length, it.length + ' casos · ' + money(total(it, 'monto')), total(it, 'monto')];
        }));
        bars('dr-money', ETAPAS.map(([k, l]) => {
            const it = v.filter(r => r.etapa === k);
            return [l, total(it, 'monto'), it.length + ' casos', undefined, it.length];
        }).filter(x => x[1] > 0), { fmt: money });

        bars('dr-owner', groupAgg(abiertas, 'solicito')
            .map(([k, e]) => [k, e.n, e.n + ' casos abiertos · ' + money(e.monto), e.monto]));

        // Validado pero sin depositar: lo que está frenado en Depósitos
        const pend = v.filter(r => r.etapa === 'DEPOSITOS');
        bars('dr-pend', groupAgg(pend, 'valido_por')
            .map(([k, e]) => [k, e.n, e.n + ' por depositar · ' + money(e.monto), e.monto]));
        const chips = document.createElement('div');
        chips.className = 'dr-chips';
        chips.innerHTML = '<span class="dr-chip">Validado sin pagar: <strong>' + pend.length + '</strong></span>' +
            '<span class="dr-chip">Monto: ' + moneyShort(total(pend, 'monto')) + '</span>';
        get('dr-pend').prepend(chips);

        const buckets = [['0–7 días', 0], ['8–15 días', 0], ['16–30 días', 0], ['Más de 30', 0], ['Sin fecha', 0]];
        abiertas.forEach(r => {
            if (r.aging === null || r.aging === undefined) buckets[4][1]++;
            else if (r.aging <= 7) buckets[0][1]++;
            else if (r.aging <= 15) buckets[1][1]++;
            else if (r.aging <= 30) buckets[2][1]++;
            else buckets[3][1]++;
        });
        bars('dr-aging', buckets);

        bars('dr-budget', groupAgg(v, 'presupuesto').map(([k, e]) => [k, e.n, '', e.monto]));
        bars('dr-prov', groupAgg(v, 'proyecto').map(([k, e]) => [k, e.n, '', e.monto]));

        const rech = new Map();
        v.forEach(r => { if (r.veces_rechazado) { const k = r.veces_rechazado + ' vez/veces'; rech.set(k, (rech.get(k) || 0) + 1); } });
        const conRechazo = v.filter(r => r.veces_rechazado).length;
        bars('dr-rechazos', [...rech.entries()].sort((a, b) => b[0].localeCompare(a[0])));
        const chipsR = document.createElement('div');
        chipsR.className = 'dr-chips';
        chipsR.innerHTML = '<span class="dr-chip">Casos con rechazo: <strong>' + conRechazo + '</strong></span>' +
            '<span class="dr-chip">Anulados: <strong>' + v.filter(r => r.etapa === 'ANULADO').length + '</strong></span>';
        get('dr-rechazos').prepend(chipsR);

        bars('dr-estados', groupAgg(v, 'estado').map(([k, e]) => [k, e.n]));
    }

    function table() {
        const etapa = get('dr-etapa-filtro').value;
        const subset = visible.filter(r => !etapa || r.etapa === etapa);
        const pages = Math.max(1, Math.ceil(subset.length / 50));
        page = Math.min(page, pages - 1);
        const tb = get('dr-orders'); tb.replaceChildren();
        subset.slice(page * 50, page * 50 + 50).forEach(r => {
            const tr = document.createElement('tr');
            [r.codigo, r.proyecto, r.site || '—', r.beneficiario, r.pago_registrado ? money(r.pagado) : 'Sin importe registrado', money(r.solicitado),
             r.estado, ETAPA_LABEL[r.etapa], r.solicito, r.valido_por || '—', r.deposito_por || '—', r.dia_solicitud || '—',
             r.foto_pago ? 'Sí' : '—']
                .forEach((c, i) => {
                    const td = document.createElement('td');
                    if (i === 7) {
                        const s = document.createElement('span');
                        s.className = 'dr-badge'; s.style.background = ETAPA_COLOR[r.etapa]; s.textContent = c;
                        td.append(s);
                    } else if (i === 1) td.innerHTML = window.NucleusProjectBadge.html(c);
                    else td.textContent = window.NucleusIdentity.display(c);
                    tr.append(td);
                });
            tb.append(tr);
        });
        get('dr-page-count').textContent = subset.length + ' rendiciones · página ' + (page + 1) + ' de ' + pages;
        get('dr-prev').disabled = page === 0;
        get('dr-next').disabled = page >= pages - 1;
        get('dr-detail-count').textContent = '(' + subset.length + ')';
    }

    function render() {
        visible = filtered();
        const set = kpis(visible);
        story(visible, set);
        vizKpis(visible);
        vizCharts(visible);
        months(visible);
        daily(visible);
        paneles(visible);
        consulta.render(visible);
        page = 0; table();
    }

    ['di-month', 'di-client', 'di-budget', 'di-owner'].forEach(id => get(id).addEventListener('change', () => { if (id === 'di-month') fillDays(); render(); }));
    get('di-day').addEventListener('change', render);
    get('dr-etapa-filtro').addEventListener('change', render);
    get('di-clear').addEventListener('click', () => {
        ['di-month', 'di-day', 'di-client', 'di-budget', 'di-owner', 'dr-etapa-filtro'].forEach(id => get(id).value = '');
        fillDays(); render();
    });
    get('dr-prev').addEventListener('click', () => { page--; table(); });
    get('dr-next').addEventListener('click', () => { page++; table(); });
    const themeToggle = get('theme-toggle');
    if (themeToggle) themeToggle.addEventListener('click', () => setTimeout(() => vizCharts(visible), 80));
    consulta.bind(render, fillDays);
    fillDays();
    render();
    window.NucleusDashboardGraficos.observeWidth(document.getElementById('di-daily'), () => daily(visible));
})();
