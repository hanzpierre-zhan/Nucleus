(function () {
    'use strict';
    const data = JSON.parse(document.getElementById('di-data').textContent);
    const get = id => document.getElementById(id);
    const rows = data.detalle || [];
    let page = 0, visible = [];

    const num = v => new Intl.NumberFormat('es-PE').format(v);
    const _currency = new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' });
    const money = v => _currency.format(v || 0);
    const moneyShort = v => 'S/ ' + new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0 }).format(Math.round(v || 0));
    const total = (items, k) => items.reduce((a, r) => a + (r[k] || 0), 0);
    const CLIENTE_ORDEN = ['ENTEL', 'CLARO', 'INTEGRATEL', 'MIXTO'];

    for (const [id, key] of [['di-client', 'cliente']]) {
        [...new Set(rows.map(r => r[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b))
            .forEach(v => get(id).add(new Option(window.NucleusIdentity.display(v), v)));
    }
    [...new Set(rows.map(r => r.mes_cierre).filter(Boolean))].sort().forEach(v => get('di-month').add(new Option(v, v)));

    function filtered() {
        const cli = get('di-client').value, exp = get('di-expense').value,
            mes = get('di-month').value, cien = get('di-cien').value;
        return rows.filter(r =>
            (!cli || r.cliente === cli) &&
            (!exp || (exp === 'con' ? r.con_expense : !r.con_expense)) &&
            (!mes || r.mes_cierre === mes) &&
            (!cien || (cien === '100' ? r.completo : !r.completo)));
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

    function clientes() {
        const mapa = new Map();
        visible.forEach(r => {
            const e = mapa.get(r.cliente) || { n: 0, cien: 0, monto: 0, montoCien: 0, evid: 0 };
            e.n++; e.monto += r.monto || 0;
            if (r.completo) { e.cien++; e.montoCien += r.monto || 0; }
            if (r.con_evidencia) e.evid++;
            mapa.set(r.cliente, e);
        });
        const orden = [...mapa.entries()].sort((a, b) => {
            const ia = CLIENTE_ORDEN.indexOf(a[0]), ib = CLIENTE_ORDEN.indexOf(b[0]);
            return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || b[1].monto - a[1].monto;
        });
        return { mapa, orden };
    }

    function kpis(v) {
        const cien = v.filter(r => r.completo);
        const evid = v.filter(r => r.con_evidencia);
        const sinevid = v.filter(r => !r.con_evidencia);
        const exp = v.filter(r => r.con_expense);
        const noexp = v.filter(r => !r.con_expense);
        const monto = total(v, 'monto');
        const porMes = new Map();
        v.forEach(r => { if (r.mes_cierre) porMes.set(r.mes_cierre, (porMes.get(r.mes_cierre) || 0) + (r.monto || 0)); });
        const pico = [...porMes.entries()].sort((a, b) => b[1] - a[1])[0];
        const set = { total: v, cien, evid, sinevid, exp, noexp };
        for (const [k, lst] of Object.entries(set)) {
            get('cb-kpi-' + k).textContent = num(lst.length);
            get('cb-kpi-' + k + '-m').textContent = moneyShort(total(lst, 'monto'));
        }
        get('cb-kpi-mes').textContent = pico ? pico[0] : '—';
        get('cb-kpi-mes-m').textContent = pico ? moneyShort(pico[1]) : '—';
        get('cb-kpi-ticket').textContent = v.length ? moneyShort(monto / v.length) : '—';
        get('cb-kpi-ticket-m').textContent = v.length ? moneyShort(monto) + ' en ' + v.length + ' casos' : '—';
        return { cien, evid, exp, noexp, monto, porMes };
    }

    function story(v, set) {
        const pct = v.length ? set.exp.length / v.length * 100 : 0;
        get('di-story-title').textContent = v.length
            ? 'El ' + num(Math.round(pct * 10) / 10) + '% tiene Número Expense registrado'
            : 'Sin casos para esta selección';
        const sinEvid = v.filter(r => !r.con_evidencia);
        const msgs = [moneyShort(set.monto) + ' por cobrar en ' + v.length + ' casos.'];
        if (set.noexp.length) msgs.push(set.noexp.length + ' sin Número Expense (' + moneyShort(total(set.noexp, 'monto')) + ').');
        if (set.cien.length) msgs.push(set.cien.length + ' cotizaciones al 100% (' + moneyShort(total(set.cien, 'monto')) + ').');
        if (sinEvid.length) msgs.push(sinEvid.length + ' sin evidencia cargada.');
        get('di-story-detail').textContent = msgs.join(' ');
        get('di-progress-fill').style.width = pct + '%';
        get('di-progress-fill').parentElement.title = set.exp.length + ' con Expense de ' + v.length;
    }

    function months() {
        const cli = get('di-client').value, exp = get('di-expense').value, cien = get('di-cien').value;
        const base = rows.filter(r => r.mes_cierre && (!cli || r.cliente === cli) &&
            (!exp || (exp === 'con' ? r.con_expense : !r.con_expense)) &&
            (!cien || (cien === '100' ? r.completo : !r.completo)));
        const porMes = new Map();
        base.forEach(r => {
            const e = porMes.get(r.mes_cierre) || { n: 0, monto: 0 };
            e.n++; e.monto += r.monto || 0; porMes.set(r.mes_cierre, e);
        });
        const lista = [...porMes.entries()].sort((a, b) => a[0].localeCompare(b[0]));
        const max = Math.max(0, ...lista.map(x => x[1].monto), 1);
        const sel = get('di-month').value;
        const box = get('cb-meses'); box.replaceChildren();
        const alto = Math.max(54, box.clientHeight - 32);
        lista.forEach(([mes, e]) => {
            const bar = document.createElement('div');
            bar.className = 'di-month' + (mes === sel ? ' di-month-selected' : '');
            bar.title = mes + ': ' + e.n + ' casos · ' + money(e.monto);
            const b = document.createElement('b'); b.textContent = moneyShort(e.monto);
            const fill = document.createElement('i'); fill.style.height = e.monto / max * alto + 'px';
            const label = document.createElement('span'); label.textContent = mes;
            bar.append(b, fill, label); box.append(bar);
        });
        if (!lista.length) box.textContent = 'No hay casos con mes de cierre para esta selección.';
    }

    function paneles(v) {
        const { mapa, orden } = clientes();

        bars('cb-clientes', orden.map(([cli, e]) => [
            cli, e.cien, e.cien + ' al 100% de ' + e.n + ' · ' + money(e.montoCien)
        ]));
        const chipsC = document.createElement('div'); chipsC.className = 'cb-chips';
        chipsC.innerHTML = '<span class="cb-chip">Al 100%: <strong>' + v.filter(r => r.completo).length + '</strong></span>' +
            '<span class="cb-chip">' + moneyShort(total(v.filter(r => r.completo), 'monto')) + ' listo para cobrar</span>';
        get('cb-clientes').prepend(chipsC);

        bars('cb-plata', orden.map(([cli, e]) => [
            cli, Math.round(e.monto), e.n + ' casos · ' + money(e.monto)
        ]), { fmt: moneyShort });

        bars('cb-evid', orden.map(([cli, e]) => [
            cli + ' (' + e.evid + '/' + e.n + ')', e.evid, e.n + ' casos · ' + e.evid + ' con evidencia · ' + (e.n - e.evid) + ' sin'
        ]));
        const chipsE = document.createElement('div'); chipsE.className = 'cb-chips';
        const conE = v.filter(r => r.con_evidencia), sinE = v.filter(r => !r.con_evidencia);
        chipsE.innerHTML = '<span class="cb-chip">Con evidencia: <strong>' + conE.length + '</strong></span>' +
            '<span class="cb-chip">Sin evidencia: <strong>' + sinE.length + '</strong></span>' +
            '<span class="cb-chip">' + moneyShort(total(sinE, 'monto')) + ' sin respaldo</span>';
        get('cb-evid').prepend(chipsE);

        const exp = v.filter(r => r.con_expense), noexp = v.filter(r => !r.con_expense);
        bars('cb-expense', [
            ['Con Expense', exp.length, exp.length + ' casos · ' + money(total(exp, 'monto'))],
            ['Sin Expense', noexp.length, noexp.length + ' casos · ' + money(total(noexp, 'monto'))],
        ]);
        const chipsX = document.createElement('div'); chipsX.className = 'cb-chips';
        chipsX.innerHTML = '<span class="cb-chip">Con: <strong>' + exp.length + '</strong> · ' + moneyShort(total(exp, 'monto')) + '</span>' +
            '<span class="cb-chip">Sin: <strong>' + noexp.length + '</strong> · ' + moneyShort(total(noexp, 'monto')) + '</span>';
        get('cb-expense').prepend(chipsX);

        const box = get('cb-cobrado'); box.replaceChildren();
        const stat = (cls, label, amount, n) => {
            const d = document.createElement('div'); d.className = 'cb-stat ' + cls;
            d.innerHTML = '<span>' + label + '</span><b>' + money(amount) + '</b><small>' + n + ' casos</small>';
            return d;
        };
        box.append(
            stat('is-ok', 'Cobrado (con Expense)', total(exp, 'monto'), exp.length),
            stat('is-pend', 'Pendiente (sin Expense)', total(noexp, 'monto'), noexp.length),
        );

        alertas(v, mapa);
    }

    function alertas(v, mapa) {
        const box = get('cb-alertas'); box.replaceChildren();
        const ul = document.createElement('ul');
        const add = (txt, warn) => {
            const li = document.createElement('li');
            if (warn) li.classList.add('is-warn');
            li.innerHTML = txt; ul.append(li);
        };
        const noExp = v.filter(r => !r.con_expense);
        const sinEvid = v.filter(r => !r.con_evidencia);
        const sinMes = v.filter(r => !r.mes_cierre);
        const sinMonto = v.filter(r => !r.monto_manual);
        const incompletos = v.filter(r => !r.completo);
        if (noExp.length) add('<strong>' + noExp.length + '</strong> casos sin Número Expense · ' + moneyShort(total(noExp, 'monto')) + ' pendiente de cobro.', true);
        if (sinMonto.length) add('<strong>' + sinMonto.length + '</strong> casos sin monto de cobro declarado (se usa el monto de cotización).');
        if (sinMes.length) add('<strong>' + sinMes.length + '</strong> casos sin mes de cierre declarado (no entran al cronograma).', true);
        if (sinEvid.length) add('<strong>' + sinEvid.length + '</strong> casos sin evidencia cargada.', true);
        if (incompletos.length) add('<strong>' + incompletos.length + '</strong> casos por debajo del 100% de avance de documentos.');
        const pico = [...mapa.entries()].sort((a, b) => b[1].monto - a[1].monto)[0];
        if (pico) add('Mayor monto por cliente: <strong>' + window.NucleusIdentity.display(pico[0]) + '</strong> · ' + moneyShort(pico[1].monto) + '.');
        add('Plata total de la selección: <strong>' + moneyShort(total(v, 'monto')) + '</strong> en ' + v.length + ' casos.');
        if (!ul.children.length) add('Sin alertas: todo lo seleccionado tiene Expense, mes de cierre y evidencia.');
        box.append(ul);
    }

    function table() {
        const filtro = get('cb-cobro-filtro').value;
        const subset = visible.filter(r =>
            !filtro ||
            (filtro === 'con' && r.con_expense) ||
            (filtro === 'sin' && !r.con_expense) ||
            (filtro === '100' && r.completo) ||
            (filtro === 'sinevid' && !r.con_evidencia));
        const pages = Math.max(1, Math.ceil(subset.length / 50));
        page = Math.min(page, pages - 1);
        const tb = get('cb-orders'); tb.replaceChildren();
        subset.slice(page * 50, page * 50 + 50).forEach(r => {
            const tr = document.createElement('tr');
            [r.cotizacion, r.cliente, r.wo || '—', r.gestor || '—', money(r.monto), r.avance + '%',
             r.con_evidencia ? 'Sí' : '—', r.numero_expense || '—', r.mes_cierre || '—',
             r.estado_cotizacion || r.estatus || '—']
                .forEach(c => {
                    const td = document.createElement('td');
                    td.textContent = window.NucleusIdentity.display(c);
                    tr.append(td);
                });
            tb.append(tr);
        });
        get('cb-page-count').textContent = subset.length + ' casos · página ' + (page + 1) + ' de ' + pages;
        get('cb-prev').disabled = page === 0;
        get('cb-next').disabled = page >= pages - 1;
        get('cb-detail-count').textContent = '(' + subset.length + ')';
    }

    function render() {
        visible = filtered();
        const set = kpis(visible);
        story(visible, set);
        months();
        paneles(visible);
        page = 0; table();
    }

    ['di-client', 'di-expense', 'di-month', 'di-cien'].forEach(id => get(id).addEventListener('change', render));
    get('cb-cobro-filtro').addEventListener('change', () => { page = 0; table(); });
    get('di-clear').addEventListener('click', () => {
        ['di-client', 'di-expense', 'di-month', 'di-cien', 'cb-cobro-filtro'].forEach(id => get(id).value = '');
        render();
    });
    get('cb-prev').addEventListener('click', () => { page--; table(); });
    get('cb-next').addEventListener('click', () => { page++; table(); });
    render();
})();
