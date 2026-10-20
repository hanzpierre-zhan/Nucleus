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

    const PEST_LABEL = { registro: '1. Registro', cliente: '2. Cliente', sustentar: '3. Sustentar', atendido: '3. Atendido', cancelado: '4. Anulado', proveedor: '5. Proveedor' };
    const PEST_COLOR = { registro: '#8E8E93', cliente: '#FF9500', sustentar: '#5AC8FA', atendido: '#34C759', cancelado: '#6B7280', proveedor: '#5AC8FA' };
    const PEST_ORDER = ['registro', 'cliente', 'sustentar', 'atendido', 'cancelado'];

    // ── Opciones de los filtros ────────────────────────────────────────────────
    for (const [id, key] of [['di-client', 'cliente'], ['di-type', 'tipo'], ['di-owner', 'solicito'], ['dc-project', 'proyecto'], ['dc-expense', 'gasto'], ['dc-generator', 'genero']]) {
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

    function extraFilters(r) {
        return [['dc-project','proyecto'], ['dc-expense','gasto'], ['dc-generator','genero']]
            .every(([id, key]) => !get(id).value || r[key] === get(id).value) && consulta.matches(r)
            && (!get('dc-pest').value || (get('dc-pest').value === 'proveedor' ? r.proveedor : r.pestania === get('dc-pest').value));
    }
    function matrix(v) {
        const stages = ['registro', 'cliente', 'sustentar', 'atendido'];
        const mode = get('dc-group').value;
        const groups = new Map();
        const empty = () => stages.map(() => ({n:0, monto:0}));
        const sums = empty();
        for (const r of v) {
            const index = stages.indexOf(r.pestania); if (index < 0) continue;
            const key = mode === 'responsable' ? (r.pestania === 'cliente' ? r.genero : r.solicito) : r[mode];
            const label = key || 'Sin datos';
            if (!groups.has(label)) groups.set(label, empty());
            groups.get(label)[index].n++; groups.get(label)[index].monto += r.monto || 0;
            sums[index].n++; sums[index].monto += r.monto || 0;
        }
        const paintRow = (label, counts) => {
            const tr = document.createElement('tr'), name = document.createElement('th');
            name.scope = 'row'; name.textContent = window.NucleusIdentity.text(label); tr.append(name);
            const all = {n: counts.reduce((a,x)=>a+x.n,0), monto: counts.reduce((a,x)=>a+x.monto,0)};
            [...counts, all].forEach(value => {
                const td = document.createElement('td'), count = document.createElement('strong'), amount = document.createElement('span');
                count.textContent = num(value.n) + (value.n === 1 ? ' caso' : ' casos');
                amount.textContent = money(value.monto); td.append(count, amount); tr.append(td);
            });
            return tr;
        };
        const body = get('dc-matrix'); body.replaceChildren();
        [...groups].sort((a,b)=>b[1].reduce((sum,x)=>sum+x.monto,0)-a[1].reduce((sum,x)=>sum+x.monto,0) || a[0].localeCompare(b[0]))
            .forEach(([label, counts]) => body.append(paintRow(label, counts)));
        if (!groups.size) { const tr = document.createElement('tr'), td = document.createElement('td'); td.colSpan=6; td.textContent='Sin casos activos para estos filtros.'; tr.append(td); body.append(tr); }
        get('dc-matrix-total').replaceChildren(paintRow('Total', sums));
        get('dc-group-label').textContent = get('dc-group').selectedOptions[0].textContent;
        get('dc-role-caption').hidden = mode !== 'responsable';
    }
    function filtered() {
        const m = get('di-month').value, d = get('di-day').value, c = get('di-client').value,
            t = get('di-type').value, o = get('di-owner').value;
        return rows.filter(r =>
            (!m || r.mes === m) && (!d || (r.dia || '').slice(8, 10) === d) &&
            (!c || r.cliente === c) && (!t || r.tipo === t) && (!o || r.solicito === o) && extraFilters(r));
    }

    // ── Renderers genéricos (mismo patrón que el dashboard operativo) ──────────
    const bars = window.NucleusDashboardGraficos.render;

    function groupAgg(items, key) {
        const m = new Map();
        items.forEach(r => {
            const k = r[key] || 'Sin datos';
            const e = m.get(k) || { n: 0, monto: 0 };
            e.n++; e.monto += r.monto || 0; m.set(k, e);
        });
        return [...m.entries()].sort((a, b) => b[1].n - a[1].n || b[1].monto - a[1].monto);
    }

    // ── KPIs: cantidad y plata por pestaña ─────────────────────────────────────
    function kpis(v) {
        const set = {
            total: v,
            registro: v.filter(r => r.pestania === 'registro'),
            cliente: v.filter(r => r.pestania === 'cliente'),
            sustentar: v.filter(r => r.pestania === 'sustentar'),
            atendido: v.filter(r => r.pestania === 'atendido'),
            anulado: v.filter(r => r.pestania === 'cancelado'),
            proveedor: v.filter(r => r.proveedor),
        };
        for (const [k, lst] of Object.entries(set)) {
            get('dc-kpi-' + k).textContent = num(lst.length);
            get('dc-kpi-' + k + '-m').textContent = money(total(lst, 'monto'));
        }
        for (const stage of ['registro','cliente','sustentar','atendido']) {
            const key = stage === 'cliente' ? 'genero' : 'solicito';
            const names = new Set(set[stage].map(r=>r[key]).filter(x=>x && x!=='Sin datos'));
            get('dc-kpi-' + stage + '-users').textContent = names.size + (stage === 'cliente' ? (names.size === 1 ? ' usuario que cotizó' : ' usuarios que cotizaron') : (names.size === 1 ? ' solicitante' : ' solicitantes'));
        }
        return set;
    }

    function story(v, set) {
        const pct = v.length ? set.atendido.length / v.length * 100 : 0;
        get('di-story-title').textContent = v.length
            ? 'El ' + num(Math.round(pct * 10) / 10) + '% de las solicitudes está atendido'
            : 'Sin cotizaciones para esta selección';
        const msgs = [moneyShort(total(set.atendido, 'monto')) + ' atendidos de ' + moneyShort(total(v, 'monto')) + ' cotizados.'];
        if (set.cliente.length) msgs.push(set.cliente.length + ' esperando al cliente · ' + moneyShort(total(set.cliente, 'monto')) + ' sin aprobar.');
        if (set.sustentar.length) msgs.push(set.sustentar.length + ' pendientes de sustento.');
        get('di-story-detail').textContent = msgs.join(' ');
        get('di-progress-fill').style.width = pct + '%';
        get('di-progress-fill').parentElement.title = set.atendido.length + ' atendidas de ' + v.length;
    }

    // ── Gráficos de tiempo ─────────────────────────────────────────────────────
    function months(v) {
        const c = get('di-client').value, t = get('di-type').value, o = get('di-owner').value;
        const half = v.filter(r => r.mes);
        const porMes = new Map();
        half.forEach(r => {
            const e = porMes.get(r.mes) || { n: 0, atn: 0, monto: 0 };
            e.n++; if (r.pestania === 'atendido') e.atn++; e.monto += r.monto || 0;
            porMes.set(r.mes, e);
        });
        const lista = [...porMes.entries()].sort((a, b) => a[0].localeCompare(b[0]));
        const max = Math.max(0, ...lista.map(x => x[1].n), 1);
        const sel = get('di-month').value || data.mes_actual;
        const box = get('di-months'); box.replaceChildren();
        const alto = 110;
        lista.forEach(([mes, e]) => {
            const bar = document.createElement('div');
            bar.className = 'di-month' + (mes === sel ? ' di-month-selected' : '');
            bar.title = mes + ': ' + e.n + ' creadas · ' + e.atn + ' atendidas · ' + money(e.monto);
            const b = document.createElement('b'); b.textContent = e.n;
            const fill = document.createElement('i'); fill.style.height = e.n / max * alto + 'px';
            const label = document.createElement('span'); label.textContent = mes;
            bar.append(b, fill, label); box.append(bar);
        });
        if (!lista.length) box.textContent = 'No hay cotizaciones con fecha para estos filtros.';
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
        const totalM = montos.reduce((a, b) => a + b, 0);
        get('di-daily-month').textContent = month;
        get('di-daily-caption').textContent = totalN
            ? totalN + ' cotizaciones · ' + money(totalM) + ' · ' + consulta.dateLabel()
            : 'Ninguna cotización creada en este mes; elige otro mes para consultar el histórico';
        const ns = 'http://www.w3.org/2000/svg';
        const el = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v2]) => e.setAttribute(k, v2)); if (text !== undefined) e.textContent = text; return e; };
        const box = get('di-daily');
        const width = Math.max(320, box.clientWidth), height = 170;
        const left = 24, right = width - 6, bottom = height - 18;
        const svg = el('svg', { viewBox: '0 0 ' + width + ' ' + height, preserveAspectRatio: 'none', role: 'img', 'aria-label': totalN + ' cotizaciones por día en ' + month });
        const step = (right - left) / days;
        const x = i => left + (i + 0.5) * step, y = v2 => bottom - v2 / max * (bottom - 18);
        [0, max].forEach(v2 => { svg.append(el('line', { x1: left, y1: y(v2), x2: right, y2: y(v2), class: 'di-daily-grid' })); svg.append(el('text', { x: left - 5, y: y(v2) + 3, 'text-anchor': 'end', class: 'di-daily-label' }, v2)); });
        counts.forEach((v2, i) => {
            if (v2) {
                const bar = el('rect', { x: x(i) - step * 0.32, y: y(v2), width: step * 0.64, height: Math.max(1, bottom - y(v2)), rx: 2, class: 'di-daily-dot' });
                bar.append(el('title', {}, month + '-' + String(i + 1).padStart(2, '0') + ': ' + v2 + ' cotizaciones · ' + money(montos[i]))); svg.append(bar);
                svg.append(el('text', { x: x(i), y: y(v2) - 5, 'text-anchor': 'middle', class: 'di-daily-value' }, v2));
            }
            if (width >= 500 || i % 5 === 0 || i === days - 1) svg.append(el('text', { x: x(i), y: height - 3, 'text-anchor': 'middle', class: 'di-daily-label' }, i + 1));
        });
        box.replaceChildren(svg);
    }

    // ── Paneles por pestaña ────────────────────────────────────────────────────
    function paneles(v) {
        // Cliente: quién generó las que aún no aprueban
        const cli = v.filter(r => r.pestania === 'cliente');
        bars('dc-cli-users', groupAgg(cli, 'genero')
            .map(([k, e]) => [k, e.n, e.n + ' cotizaciones · ' + money(e.monto) + ' pendientes de aprobación', e.monto]));
        bars('dc-cli-proy', groupAgg(cli, 'proyecto')
            .map(([k, e]) => [k, e.n, e.n + ' pendientes de aprobación · ' + money(e.monto), e.monto]));

        // Sustentar: quién pidió lo que falta sustentar + evidencia
        const sus = v.filter(r => r.pestania === 'sustentar');
        const conSust = sus.filter(r => r.sustento_ok).length;
        bars('dc-sus-users', groupAgg(sus, 'solicito')
            .map(([k, e]) => [k, e.n, e.n + ' pendientes de cierre · ' + money(e.monto), e.monto]));
        const chips = document.createElement('div');
        chips.className = 'dc-chips';
        chips.innerHTML = '<span class="dc-chip">Sustento validado: <strong>' + conSust + '</strong></span><span class="dc-chip">Sin validación registrada: <strong>' + (sus.length - conSust) + '</strong></span><span class="dc-chip">Monto: ' + moneyShort(total(sus, 'monto')) + '</span>';
        get('dc-sus-users').prepend(chips);

        // Proveedor: archivos cargados y cierre
        const prov = v.filter(r => r.proveedor);
        const atn = prov.filter(r => r.pestania === 'atendido').length;
        const pct = f => prov.length ? Math.round(prov.filter(f).length / prov.length * 100) : 0;
        bars('dc-prov', [
            ['Factura proveedor', pct(r => r.factura_ok), prov.filter(r => r.factura_ok).length + ' de ' + prov.length + ' con factura cargada'],
            ['Cotización proveedor', pct(r => r.cotprov_ok), prov.filter(r => r.cotprov_ok).length + ' de ' + prov.length + ' con cotización del proveedor'],
            ['Correo del cliente', pct(r => r.correo_ok), prov.filter(r => r.correo_ok).length + ' de ' + prov.length + ' con correo adjunto'],
        ], { fmt: x => x + '%' });
        get('dc-prov-caption').textContent = atn + ' atendidas de ' + prov.length + ' · ' + moneyShort(total(prov, 'facturado')) + ' facturados de ' + moneyShort(total(prov, 'monto')) + ' cotizados';

        // Antigüedad de lo pendiente de sustento
        const buckets = [['0–7 días', 0], ['8–15 días', 0], ['16–30 días', 0], ['Más de 30', 0], ['Sin fecha', 0]];
        sus.forEach(r => {
            if (r.aging === null || r.aging === undefined) buckets[4][1]++;
            else if (r.aging <= 7) buckets[0][1]++;
            else if (r.aging <= 15) buckets[1][1]++;
            else if (r.aging <= 30) buckets[2][1]++;
            else buckets[3][1]++;
        });
        bars('dc-aging', buckets);

        // Dinero y distribución
        bars('dc-money', PEST_ORDER.map(p => {
            const it = v.filter(r => r.pestania === p);
            return [PEST_LABEL[p], total(it, 'monto'), it.length + ' cotizaciones', undefined, it.length];
        }).filter(x => x[1] > 0), { fmt: money });
        bars('dc-types', groupAgg(v, 'tipo').map(([k, e]) => [k, e.n, '', e.monto]));
        bars('dc-estados', groupAgg(v, 'estado').map(([k, e]) => [k, e.n, e.n + ' casos · ' + money(e.monto), e.monto]));
    }

    // ── Tabla detalle ──────────────────────────────────────────────────────────
    function table() {
        const pest = get('dc-pest').value;
        const subset = visible.filter(r => !pest || (pest === 'proveedor' ? r.proveedor : r.pestania === pest));
        const pages = Math.max(1, Math.ceil(subset.length / 50));
        page = Math.min(page, pages - 1);
        const tb = get('dc-orders'); tb.replaceChildren();
        subset.slice(page * 50, page * 50 + 50).forEach(r => {
            const tr = document.createElement('tr');
            [r.n, r.cliente, r.proyecto, r.gasto, r.site || '—', r.tipo, money(r.monto), r.estado, PEST_LABEL[r.pestania],
             r.solicito, r.genero, r.dia_solicitud || '—', r.wo || '—', r.factura_ok ? 'Sí' : '—', r.cotprov_ok ? 'Sí' : '—']
                .forEach((c, i) => {
                    const td = document.createElement('td');
                    if (i === 8) {
                        const s = document.createElement('span');
                        s.className = 'dc-badge'; s.style.background = PEST_COLOR[r.pestania]; s.textContent = c;
                        td.append(s);
                    } else td.textContent = window.NucleusIdentity.display(c);
                    tr.append(td);
                });
            tb.append(tr);
        });
        get('dc-page-count').textContent = subset.length + ' cotizaciones · página ' + (page + 1) + ' de ' + pages;
        get('dc-prev').disabled = page === 0;
        get('dc-next').disabled = page >= pages - 1;
        get('dc-detail-count').textContent = '(' + subset.length + ')';
    }

    function render() {
        visible = filtered();
        const set = kpis(visible);
        story(visible, set);
        months(visible);
        daily(visible);
        paneles(visible);
        matrix(visible);
        consulta.render(visible);
        page = 0; table();
    }

    ['di-month', 'di-client', 'di-type', 'di-owner', 'dc-project', 'dc-expense', 'dc-generator'].forEach(id => get(id).addEventListener('change', () => { if (id === 'di-month') fillDays(); render(); }));
    get('dc-group').addEventListener('change', () => matrix(visible));
    get('di-day').addEventListener('change', render);
    get('dc-pest').addEventListener('change', render);
    get('di-clear').addEventListener('click', () => {
        ['di-month', 'di-day', 'di-client', 'di-type', 'di-owner', 'dc-pest', 'dc-project', 'dc-expense', 'dc-generator'].forEach(id => get(id).value = '');
        fillDays(); render();
    });
    get('dc-prev').addEventListener('click', () => { page--; table(); });
    get('dc-next').addEventListener('click', () => { page++; table(); });
    consulta.bind(render, fillDays);
    fillDays();
    render();
    window.NucleusDashboardGraficos.observeWidth(document.getElementById('di-daily'), () => daily(visible));
})();
