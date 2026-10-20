(function (root) {
    'use strict';
    const sum = (rows, key) => rows.reduce((n, r) => n + (Number(r[key]) || 0), 0);
    const amountPresent = (r, key) => r[({monto:'monto_registrado', facturado:'facturado_registrado', pagado:'pago_registrado', solicitado:'solicitado_registrado'})[key]] ?? (r[key] !== undefined && r[key] !== null);
    function aggregate(rows, key, metric) {
        const stages = [...new Set(rows.map(r => r.situacion))].sort();
        const groups = new Map();
        for (const r of rows) {
            const name = r[key] || 'Sin datos';
            if (!groups.has(name)) groups.set(name, { name, n: 0, amount: 0, missing: 0, cells: new Map() });
            const g = groups.get(name), c = g.cells.get(r.situacion) || { n: 0, amount: 0, missing: 0, ages: [] };
            g.n++; g.amount += Number(r[metric]) || 0;
            c.n++; c.amount += Number(r[metric]) || 0;
            if (!amountPresent(r, metric)) { c.missing++; g.missing++; }
            if (Number.isFinite(r.dias_etapa)) c.ages.push(r.dias_etapa);
            g.cells.set(r.situacion, c);
        }
        return { stages, groups: [...groups.values()].sort((a, b) => b.n - a.n || b.amount - a.amount || a.name.localeCompare(b.name)),
            n: rows.length, amount: sum(rows, metric) };
    }
    function create(rows, data) {
        const get = id => document.getElementById(id), panel = get('dq-panel');
        const rend = panel.dataset.mode === 'rendicion';
        const identity = v => root.NucleusIdentity ? root.NucleusIdentity.display(String(v)) : String(v);
        const money = n => new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(n || 0);
        const el = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
        let selection = [], drill = null, page = 0;
        const fields = [['dq-department', 'departamento'], ['dq-state', 'estado'], ['dq-situation', 'situacion'],
            ['dq-recorder', 'registrador'], ['dq-name', 'nombre'], ['dq-closer', rend ? 'sustento_por' : 'atendido_por'],
            ...(rend ? [['dq-assigned', 'responsable_validacion'], ['dq-validator', 'valido_por'], ['dq-depositor', 'deposito_por'],
                ['dq-person', 'beneficiario'], ['dq-supervisor', 'supervisor'], ['dq-expense', 'gasto']] : [['dq-approval', 'gasto_aprobacion']])];
        const dates = rend ? [['dia_solicitud', 'Solicitud'], ['dia_pago', 'Depósito'], ['dia_validacion', 'Validación'], ['dia_sustento', 'Cierre del sustento']]
            : [['dia_solicitud', 'Solicitud'], ['dia_cotizacion', 'Cotización / envío'], ['dia_aprobacion', 'Aprobación del cliente'], ['dia_atencion', 'Atención']];
        const groups = [[rend ? 'proyecto' : 'proyecto_familia', 'Proyecto FLM'], ['solicito', 'Solicitante'], ['registrador', 'Usuario registrador'],
            ['departamento', 'Departamento'], ['nombre', 'Nombre registrado'], [rend ? 'sustento_por' : 'atendido_por', 'Persona que cerró / atendió'],
            ...(rend ? [['responsable_validacion', 'Responsable asignado de validación'], ['valido_por', 'Persona que validó'], ['deposito_por', 'Persona que depositó'], ['supervisor', 'Supervisor encargado'], ['beneficiario', 'Beneficiario'], ['gasto', 'Tipo de gasto'], ['presupuesto', 'Presupuesto']]
                : [['genero', 'Usuario que generó'], ['gestor', 'Gestor'], ['gasto', 'Gasto de solicitud'], ['gasto_aprobacion', 'Gasto de aprobación']])];
        dates.forEach(([value, label]) => get('dq-date').add(new Option(label, value)));
        groups.forEach(([value, label]) => get('dq-group').add(new Option(label, value)));
        (rend ? [['solicitado', 'Monto solicitado'], ['pagado', 'Pago registrado']] : [['monto', 'Monto cotizado'], ['facturado', 'Factura de proveedor']])
            .forEach(([value, label]) => get('dq-money').add(new Option(label, value)));
        fields.forEach(([id, key]) => [...new Set(rows.map(r => r[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b))
            .forEach(value => get(id).add(new Option(identity(value), value))));
        rows.forEach(r => { r.dia_solicitud = r.dia_solicitud || r.dia || ''; });
        function applyDate() {
            const key = get('dq-date').value;
            rows.forEach(r => { r.dia = r[key] || ''; r.mes = r.dia.slice(0, 7); });
            const month = get('di-month'); month.replaceChildren(new Option('Todos', ''));
            [...new Set(rows.map(r => r.mes).filter(Boolean))].sort().forEach(m => month.add(new Option(m, m)));
            get('dq-date-note').textContent = 'Mes, día y rango se aplican a: ' + get('dq-date').selectedOptions[0].textContent + '. Sin fecha registrada no se asigna un período ficticio.';
            const caption = document.querySelector('.di-month-card > p');
            if (caption) caption.textContent = 'Cantidad y montos por fecha de ' + get('dq-date').selectedOptions[0].textContent.toLowerCase();
            get('di-month').parentElement.firstChild.textContent = 'Mes consultado';
        }
        function matches(r) {
            const from = get('dq-from').value, to = get('dq-to').value;
            if ((from || to) && (!r.dia || (from && r.dia < from) || (to && r.dia > to))) return false;
            if (!fields.every(([id, key]) => !get(id).value || r[key] === get(id).value)) return false;
            const norm = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
            const query = norm(get('dq-search').value).trim();
            return !query || norm([r.key, r.n, r.codigo, r.wo, r.site, r.nombre, r.solicito, r.registrador, r.genero, r.beneficiario].join(' ')).includes(query);
        }
        function summary(v) {
            const box = get('dq-summary'); box.replaceChildren();
            const tile = (title, items, metric) => { const a = el('article'); a.append(el('strong', title), el('span', items.length + ' casos'), el('small', money(sum(items, metric)))); box.append(a); };
            if (rend) {
                tile('Solicitado', v, 'solicitado'); tile('Depósitos registrados vigentes', v.filter(r => r.depositado), 'pagado');
                tile('Depositado · falta sustento', v.filter(r => r.estado === 'DEPOSITADO'), 'pagado');
                tile('Sustento cargado · falta validar', v.filter(r => r.estado === 'CON SUSTENTO'), 'pagado');
                tile('Sustentado / archivado', v.filter(r => ['SUSTENTADO', 'ARCHIVADO'].includes(r.estado)), 'pagado');
                get('dq-selection').textContent = v.length + ' casos · ' + v.filter(r => !r.pago_registrado).length + ' sin importe de pago registrado';
            } else {
                tile('Cotizado', v, 'monto'); tile('Pendiente del cliente', v.filter(r => r.pestania === 'cliente'), 'monto');
                tile('Aprobado / atendido', v.filter(r => ['sustentar', 'atendido'].includes(r.pestania)), 'monto');
                tile('Sustento validado y atendido', v.filter(r => r.pestania === 'atendido' && r.sustento_ok), 'monto');
                get('dq-selection').textContent = v.length + ' cotizaciones · sin duplicar la vista Proveedor';
            }
        }
        function matrix(v) {
            const key = get('dq-group').value, metric = get('dq-money').value;
            const result = aggregate(v, key, metric), head = el('tr');
            [get('dq-group').selectedOptions[0].textContent, ...result.stages, 'Total'].forEach(s => head.append(el('th', s)));
            get('dq-matrix-head').replaceChildren(head);
            const body = get('dq-matrix'); body.replaceChildren();
            result.groups.forEach(g => {
                const tr = el('tr'); tr.append(el('th', identity(g.name)));
                [...result.stages, null].forEach(stage => {
                    const c = stage === null ? { n: g.n, amount: g.amount, missing: g.missing, ages: [] } : g.cells.get(stage) || { n: 0, amount: 0, missing: 0, ages: [] };
                    const td = el('td'), b = el('button', c.n + ' casos'); b.type = 'button';
                    b.append(el('small', money(c.amount)));
                    if (c.missing) b.append(el('small', c.missing + ' sin importe registrado'));
                    if (c.ages.length) b.append(el('small', 'Mayor espera: ' + Math.max(...c.ages) + ' días · ' + c.ages.length + ' con fecha de etapa'));
                    b.addEventListener('click', () => { drill = { key, name: g.name, stage }; page = 0; cases(); get('dq-cases').closest('details').open = true; }); td.append(b); tr.append(td);
                });
                body.append(tr);
            });
            const footer = el('tr'); footer.append(el('th', 'Total de la selección'));
            [...result.stages, null].forEach(s => { const items = s === null ? v : v.filter(r => r.situacion === s); const td = el('td', items.length + ' casos'); td.append(el('small', money(sum(items, metric)))); footer.append(td); });
            get('dq-matrix-total').replaceChildren(footer);
        }
        function cases() {
            const v = selection.filter(r => !drill || ((r[drill.key] || 'Sin datos') === drill.name && (!drill.stage || r.situacion === drill.stage)))
                .slice().sort((a, b) => (b.dias_etapa ?? -1) - (a.dias_etapa ?? -1) || String(a.key).localeCompare(String(b.key)));
            const pages = Math.max(1, Math.ceil(v.length / 40)); page = Math.max(0, Math.min(page, pages - 1));
            const body = get('dq-cases'); body.replaceChildren();
            v.slice(page * 40, page * 40 + 40).forEach(r => {
                const tr = el('tr'), td = el('td'), a = el('a', r.n || r.codigo || r.key);
                a.href = '/switch_project/' + panel.dataset.projectId + '?' + new URLSearchParams({ next: '/?caso=' + encodeURIComponent(r.key) });
                td.append(a); tr.append(td);
                const responsable = rend ? (r.cerrado ? 'Cerró: ' + identity(r.sustento_por || 'Sin usuario registrado') : r.etapa === 'VALIDACION' ? r.responsable_validacion : r.etapa === 'DEPOSITOS' ? 'Sin responsable de depósito asignado'
                    : r.etapa === 'SUSTENTO' ? 'Sin revisor final asignado' : r.supervisor + ' · supervisor registrado')
                    : (r.cerrado ? 'Atendió: ' + identity(r.atendido_por || 'Sin usuario registrado') : r.pestania === 'cliente' ? 'Cliente · espera externa; generó ' + identity(r.genero) : 'Solicitante (referencia): ' + identity(r.solicito));
                const dias = r.dia_solicitud ? Math.floor((Date.parse(data.hoy + 'T00:00:00Z') - Date.parse(r.dia_solicitud + 'T00:00:00Z')) / 86400000) : null;
                [r.proyecto_familia || r.proyecto, r.situacion, identity(r.solicito) + ' / ' + identity(r.registrador), responsable,
                    amountPresent(r, get('dq-money').value) ? money(r[get('dq-money').value]) : 'Sin importe registrado', r.cerrado ? 'Cerrado' : r.dias_etapa === null ? 'Sin fecha válida de etapa' : r.dias_etapa + ' días',
                    (r.fecha_etapa || '—') + ' · ' + r.fuente_fecha_etapa, dias === null || dias < 0 ? 'Sin fecha válida' : dias + ' días']
                    .forEach(value => tr.append(el('td', value)));
                body.append(tr);
            });
            if (!v.length) { const tr = el('tr'), td = el('td', 'No hay casos para esta selección.'); td.colSpan = 9; tr.append(td); body.append(tr); }
            get('dq-page').textContent = 'Página ' + (page + 1) + ' de ' + pages;
            get('dq-cases-count').textContent = '(' + v.length + ')'; get('dq-prev').disabled = page === 0; get('dq-next').disabled = page >= pages - 1;
        }
        get('dq-prev').addEventListener('click', () => { page--; cases(); });
        get('dq-next').addEventListener('click', () => { page++; cases(); });
        get('dq-reset-drill').addEventListener('click', () => { drill = null; page = 0; cases(); });
        return {
            dateLabel() { return 'por fecha de ' + get('dq-date').selectedOptions[0].textContent.toLowerCase(); },
            matches, render(v) { selection = v; drill = null; page = 0; summary(v); matrix(v); cases(); },
            bind(render, fillDays) {
                const ids = [...fields.map(f => f[0]), 'dq-from', 'dq-to', 'dq-search'];
                ids.forEach(id => get(id).addEventListener(id === 'dq-search' ? 'input' : 'change', render));
                ['dq-group', 'dq-money'].forEach(id => get(id).addEventListener('change', () => { drill = null; matrix(selection); cases(); }));
                get('dq-date').addEventListener('change', () => { applyDate(); fillDays(); render(); });
                get('di-clear').addEventListener('click', () => { ids.forEach(id => get(id).value = ''); get('dq-date').value = 'dia_solicitud'; applyDate(); fillDays(); render(); });
                applyDate(); fillDays();
            }
        };
    }
    root.NucleusDashboardConsulta = { create, aggregate };
    if (typeof module !== 'undefined' && module.exports) module.exports = { aggregate };
})(typeof window === 'undefined' ? globalThis : window);
