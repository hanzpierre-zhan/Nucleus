(function () {
    'use strict';
    const data = JSON.parse(document.getElementById('di-data').textContent);
    const get = id => document.getElementById(id);
    const rows = data.detalle;
    let page = 0, visible = [];

    const num = v => new Intl.NumberFormat('es-PE').format(v);
    const _currency = new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' });
    const money = v => _currency.format(v || 0);
    const moneyShort = v => 'S/ ' + new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0 }).format(Math.round(v || 0));
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

    for (const [id, key] of [['di-client', 'proyecto'], ['di-budget', 'presupuesto'], ['di-owner', 'solicito']]) {
        [...new Set(rows.map(r => r[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b))
            .forEach(v => get(id).add(new Option(window.NucleusIdentity.display(v), v)));
    }
    [...new Set(rows.map(r => r.mes).filter(Boolean))].sort().forEach(v => get('di-month').add(new Option(window.NucleusIdentity.display(v), v)));

    function fillDays() {
        const m = get('di-month').value, sel = get('di-day'), prev = sel.value;
        sel.disabled = !m;
        sel.replaceChildren(new Option('Todos los días', ''));
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
            (!p || r.proyecto === p) && (!b || r.presupuesto === b) && (!o || r.solicito === o));
    }

    function bars(id, values, opts) {
        opts = opts || {};
        const box = get(id); box.classList.add('di-ranking'); box.replaceChildren();
        if (!values.length) {
            const empty = document.createElement('p');
            empty.className = 'di-empty'; empty.textContent = 'No hay registros para estos filtros.';
            box.append(empty); return;
        }
        const max = Math.max(...values.map(v => v[1]), 1);
        values.forEach(([label, value, hint]) => {
            const row = document.createElement('div'); row.className = 'di-bar-row';
            const name = document.createElement('span'); name.className = 'di-bar-name';
            name.textContent = window.NucleusIdentity.text(label); name.title = label;
            const track = document.createElement('div'); track.className = 'di-bar-track';
            const fill = document.createElement('div'); fill.className = 'di-bar-fill';
            fill.style.width = (100 * value / max) + '%'; track.append(fill);
            const b = document.createElement('b'); b.textContent = opts.fmt ? opts.fmt(value) : value;
            if (hint) row.title = hint;
            row.append(name, track, b); box.append(row);
        });
    }

    function groupAgg(items, key) {
        const m = new Map();
        items.forEach(r => {
            const k = r[key] || 'Sin datos';
            const e = m.get(k) || { n: 0, monto: 0 };
            e.n++; e.monto += r.monto || 0; m.set(k, e);
        });
        return [...m.entries()].sort((a, b) => b[1].n - a[1].n || b[1].monto - a[1].monto);
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

    function months() {
        const p = get('di-client').value, b = get('di-budget').value, o = get('di-owner').value;
        const half = rows.filter(r => r.mes && (!p || r.proyecto === p) && (!b || r.presupuesto === b) && (!o || r.solicito === o));
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
        const alto = Math.max(54, box.clientHeight - 32);
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
            ? totalN + ' solicitudes · ' + money(montos.reduce((a, b) => a + b, 0)) + ' · por fecha de solicitud'
            : 'Nada solicitado en este mes; elige otro mes para consultar el histórico';
        const ns = 'http://www.w3.org/2000/svg';
        const el = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v2]) => e.setAttribute(k, v2)); if (text !== undefined) e.textContent = text; return e; };
        const box = get('di-daily');
        const width = Math.max(320, box.clientWidth), height = Math.max(96, box.clientHeight);
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
            svg.append(el('text', { x: x(i), y: height - 3, 'text-anchor': 'middle', class: 'di-daily-label' }, i + 1));
        });
        box.replaceChildren(svg);
    }

    function paneles(v) {
        const abiertas = v.filter(r => !CERRADAS.includes(r.etapa));

        bars('dr-etapas', ETAPAS.map(([k, l]) => {
            const it = v.filter(r => r.etapa === k);
            return [l, it.length, it.length + ' casos · ' + money(total(it, 'monto'))];
        }));
        bars('dr-money', ETAPAS.map(([k, l]) => {
            const it = v.filter(r => r.etapa === k);
            return [l, Math.round(total(it, 'monto')), money(total(it, 'monto'))];
        }).filter(x => x[1] > 0), { fmt: moneyShort });

        bars('dr-owner', groupAgg(abiertas, 'solicito').slice(0, 8)
            .map(([k, e]) => [k + ' · ' + moneyShort(e.monto), e.n, e.n + ' casos abiertos · ' + money(e.monto)]));

        // Validado pero sin depositar: lo que está frenado en Depósitos
        const pend = v.filter(r => r.etapa === 'DEPOSITOS');
        bars('dr-pend', groupAgg(pend, 'valido_por').slice(0, 8)
            .map(([k, e]) => [k + ' · ' + moneyShort(e.monto), e.n, e.n + ' por depositar · ' + money(e.monto)]));
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

        bars('dr-budget', groupAgg(v, 'presupuesto').slice(0, 8).map(([k, e]) => [k + ' · ' + moneyShort(e.monto), e.n]));
        bars('dr-prov', groupAgg(v, 'proyecto').slice(0, 8).map(([k, e]) => [k + ' · ' + moneyShort(e.monto), e.n]));

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
            [r.codigo, r.proyecto, r.site || '—', r.beneficiario, money(r.pagado || r.monto), money(r.solicitado),
             r.estado, ETAPA_LABEL[r.etapa], r.solicito, r.valido_por || '—', r.deposito_por || '—', r.dia || '—',
             r.foto_pago ? 'Sí' : '—']
                .forEach((c, i) => {
                    const td = document.createElement('td');
                    if (i === 7) {
                        const s = document.createElement('span');
                        s.className = 'dr-badge'; s.style.background = ETAPA_COLOR[r.etapa]; s.textContent = c;
                        td.append(s);
                    } else td.textContent = window.NucleusIdentity.display(c);
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
        months();
        daily(visible);
        paneles(visible);
        page = 0; table();
    }

    ['di-month', 'di-client', 'di-budget', 'di-owner'].forEach(id => get(id).addEventListener('change', () => { if (id === 'di-month') fillDays(); render(); }));
    get('di-day').addEventListener('change', render);
    get('dr-etapa-filtro').addEventListener('change', () => { page = 0; table(); });
    get('di-clear').addEventListener('click', () => {
        ['di-month', 'di-day', 'di-client', 'di-budget', 'di-owner', 'dr-etapa-filtro'].forEach(id => get(id).value = '');
        fillDays(); render();
    });
    get('dr-prev').addEventListener('click', () => { page--; table(); });
    get('dr-next').addEventListener('click', () => { page++; table(); });
    fillDays();
    render();
})();
