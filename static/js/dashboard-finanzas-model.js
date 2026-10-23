(function () {
    'use strict';
    const numeric = value => Number.isFinite(Number(value)) ? Number(value) : 0;
    const sum = (rows, value) => rows.reduce((total, row) => total + numeric(value(row)), 0);
    const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();
    const person = (row, mode) => mode === 'cotizaciones' ? row.genero || 'Sin datos'
        : row.beneficiario_id || row.beneficiario || 'Sin beneficiario';
    const operator = (row, mode) => mode === 'cotizaciones' ? row.cliente || 'Sin operador' : row.proyecto || 'Sin operador';
    const amount = (row, mode) => mode === 'cotizaciones' ? numeric(row.monto) : row.pago_registrado ? numeric(row.pagado) : 0;
    const type = row => row.tipo === 'Sin tipo' ? 'Sin clasificar' : row.tipo;
    const supported = row => ['SUSTENTO', 'OBSERVADO', 'ATENDIDO', 'ARCHIVADO'].includes(row.etapa);
    function group(rows, key, value) {
        const result = new Map();
        rows.forEach(row => {
            const label = key(row) || 'Sin clasificar';
            const current = result.get(label) || {label, count: 0, amount: 0};
            current.count++;
            current.amount += numeric(value(row));
            result.set(label, current);
        });
        return [...result.values()].sort((a, b) => b.amount - a.amount || b.count - a.count || a.label.localeCompare(b.label));
    }
    function filter(rows, mode, filters) {
        return rows.filter(row => (!filters.month || row.mes === filters.month)
            && (!filters.state || row.estado === filters.state)
            && (!filters.operator || operator(row, mode) === filters.operator)
            && (!filters.budget || (mode === 'rendicion' ? row.presupuesto : row.gasto) === filters.budget)
            && (!filters.type || type(row) === filters.type)
            && (!filters.person || person(row, mode) === filters.person)
            && (!filters.project || (row.proyecto || 'Sin proyecto') === filters.project)
            && (!filters.approval || (row.gasto_aprobacion || 'Sin definir') === filters.approval)
            && (!filters.day || (mode === 'rendicion' ? row.dia_pago : row.dia) === filters.day));
    }
    function summary(rows, mode) {
        const value = row => amount(row, mode);
        const peopleNames = new Map(rows.map(row => [person(row, mode), row.beneficiario]));
        const budget = row => mode === 'rendicion' ? row.presupuesto : row.gasto;
        const paid = rows.filter(row => row.pago_registrado);
        const deposited = rows.filter(row => row.depositado);
        const sustained = rows.filter(supported);
        return {
            count: rows.length, amount: sum(rows, value),
            paidCount: paid.length, deposited: sum(deposited, value), depositedCount: deposited.length,
            supported: sum(sustained, value), supportedCount: sustained.length,
            budgets: group(rows, budget, value),
            operators: group(mode === 'rendicion' ? rows.filter(row => row.etapa === 'EVIDENCIA') : rows,
                row => operator(row, mode), value),
            people: group(rows, row => person(row, mode), value).map(item => mode === 'rendicion'
                ? {...item, key: item.label, label: peopleNames.get(item.label) || 'Sin beneficiario'} : item),
            supportedBudgets: group(sustained, budget, value),
            supportedOperators: group(sustained, row => operator(row, mode), value),
            approval: group(rows, row => row.gasto_aprobacion, value),
            states: group(rows, row => row.estado, value),
            types: group(rows, type, value),
        };
    }
    function trend(rows, mode) {
        const period = row => mode === 'rendicion' ? row.dia_pago : row.dia;
        const dated = rows.filter(row => /^\d{4}-\d{2}(-\d{2})?$/.test(period(row) || '')
            && (mode !== 'rendicion' || row.pago_registrado));
        const periods = [...new Set(dated.map(period))].sort();
        const key = row => (mode === 'rendicion' ? row.presupuesto : row.gasto) || 'Sin clasificar';
        const series = [...new Set(dated.map(key))].sort().map(label => {
            const values = new Map();
            dated.filter(row => key(row) === label).forEach(row => values.set(period(row),
                (values.get(period(row)) || 0) + amount(row, mode)));
            return {label, values: periods.map(p => values.get(p) || 0)};
        });
        return {periods, series};
    }
    function cotizaciones(rows) {
        const amount = row => numeric(row.monto);
        const pending = rows.filter(row => row.pestania === 'cliente');
        const approved = rows.filter(row => row.pestania === 'sustentar');
        const attended = rows.filter(row => row.pestania === 'atendido');
        const destination = row => row.gasto_aprobacion || 'Sin definir';
        return {
            pending, approved, attended,
            budgets: group(pending, row => row.gasto, amount),
            managers: group(pending, row => row.gestor, amount),
            attendedGroups: group(attended, row => (row.gasto || 'Sin clasificar') + ' · ' + destination(row), amount),
            cobra: group(approved.filter(row => normalize(row.gasto) === 'GASTO COBRA'), destination, amount),
            refacturable: group(approved.filter(row => normalize(row.gasto) === 'REFACTURABLE'), destination, amount),
            trend: group(pending.filter(row => row.dia), row => row.dia, amount).sort((a,b) => a.label.localeCompare(b.label)),
        };
    }
    window.NucleusFinanceModel = {numeric, sum, normalize, person, operator, amount, type, group, filter, summary, trend, cotizaciones};
}());
