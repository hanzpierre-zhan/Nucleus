const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({window: {}});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/dashboard-finanzas-model.js'), 'utf8'), context);
const model = context.window.NucleusFinanceModel;
const rendicion = [
    {mes: '2026-10', estado: 'DEPOSITADO', etapa: 'EVIDENCIA', presupuesto: 'GASTO COBRA', proyecto: 'ENTEL', solicito: 'Ana', pago_registrado: true, depositado: true, pagado: 100, dia_pago: '2026-10-01'},
    {mes: '2026-10', estado: 'PENDIENTE', etapa: 'VALIDACION', presupuesto: 'GASTO COBRA', proyecto: 'ENTEL', solicito: 'Ana', pago_registrado: false, solicitado: 9000},
    {mes: '2026-10', estado: 'SUSTENTADO', etapa: 'OBSERVADO', presupuesto: 'REFACTURABLE', proyecto: 'CLARO', solicito: 'Bea', pago_registrado: true, depositado: true, pagado: 20, dia_pago: '2026-10-01'},
    {mes: '2026-10', estado: 'SUSTENTADO', etapa: 'ARCHIVADO', presupuesto: 'REFACTURABLE', proyecto: 'CLARO', pago_registrado: true, depositado: true, pagado: 10},
];
const rend = model.summary(rendicion, 'rendicion');
assert.equal(rend.count, 4);
assert.equal(rend.amount, 130, 'Los importes solicitados sin pago no se presentan como dinero pagado');
assert.equal(rend.supported, 30, 'Los sustentos observados y archivados conservan sus importes');
assert.equal(rend.supportedCount, 2);
assert.equal(rend.operators.length, 1);
assert.equal(rend.operators[0].amount, 100, 'La dona incluye solo pendientes en Evidencia');
assert.equal(model.filter(rendicion, 'rendicion', {month: '2026-10', operator: 'CLARO', budget: 'REFACTURABLE', person: 'Bea'}).length, 1);
const line = model.trend(rendicion, 'rendicion');
assert.deepEqual(Array.from(line.periods), ['2026-10-01']);
assert.equal(line.series.reduce((sum, s) => sum + s.values[0], 0), 120, 'Un pago sin fecha no se asigna a un día inventado');
const cotizaciones = [
    {monto: 100, proveedor: true, cliente: 'ENTEL', genero: 'Ana', tipo: 'Servicio', gasto: 'Refacturable', mes: '2026-09', dia: '2026-09-10', estado: 'Aprobado', gasto_aprobacion: 'Proveedor', proyecto: 'Obra Norte'},
    {monto: 50, proveedor: true, cliente: 'CLARO', genero: 'Bea', tipo: 'Sin tipo', gasto: 'Gasto Cobra', mes: '2026-10', dia: '2026-10-02', estado: 'En Aprobación', gasto_aprobacion: 'Caja Chica', proyecto: 'Obra Sur'},
];
const cot = model.summary(cotizaciones, 'cotizaciones');
assert.equal(cot.count, 2);
assert.equal(cot.amount, 150, 'La vista paralela de Proveedor no duplica solicitudes');
assert.equal(cot.types.find(t => t.label === 'Sin clasificar').amount, 50);
assert.equal(cot.states.find(s => s.label === 'Aprobado').count, 1, 'Estados para el gráfico de barras');
assert.deepEqual(Array.from(model.trend(cotizaciones, 'cotizaciones').periods), ['2026-09-10', '2026-10-02'], 'La evolución es diaria');
assert.equal(model.filter(cotizaciones, 'cotizaciones', {day: '2026-10-02'}).length, 1);
assert.equal(model.filter(cotizaciones, 'cotizaciones', {approval: 'Proveedor'}).length, 1);
assert.equal(model.filter(cotizaciones, 'cotizaciones', {project: 'Obra Sur'}).length, 1);
assert.equal(model.filter(cotizaciones, 'cotizaciones', {type: 'Sin clasificar'}).length, 1, 'El tipo vacío se filtra con la etiqueta que ve el usuario');
assert.equal(model.summary([], 'rendicion').amount, 0);
console.log('OK: importes registrados, filtros, sustentos y evolución sin duplicados');
