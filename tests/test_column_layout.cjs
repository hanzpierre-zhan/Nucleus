const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = vm.createContext({window: {}});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/column-layout.js'), 'utf8'), context);
const layout = context.window.NucleusColumnLayout;
const saved = [{field: 'SITE', visible: true, width: 380}, {field: 'ESTADO', visible: false, width: 120}];
for (const canEdit of [false, true]) {
    const columns = [{field: 'SITE', width: 150, maxWidth: 260, resizable: true},
        {field: 'ESTADO', width: 150, resizable: true}, {formatter: 'rowSelection', resizable: true}];
    layout.apply(columns, saved, canEdit);
    assert.equal(columns[0].width, 380);
    assert.equal(columns[0].maxWidth, 380);
    assert.equal(columns[1].width, 120);
    assert.ok(columns.every(c => c.resizable === canEdit));
}
const snapshot = layout.snapshot([
    {getField: () => 'SITE', isVisible: () => true, getWidth: () => 380, getDefinition: () => ({width: 150})},
    {getField: () => 'ESTADO', isVisible: () => false, getWidth: () => 0, getDefinition: () => ({width: 120})},
    {getField: () => undefined}
]);
assert.equal(JSON.stringify(snapshot), JSON.stringify(saved));
console.log('OK: anchos compartidos y redimensionado exclusivo de administradores');

const controller = fs.readFileSync(path.join(__dirname, '../templates/index/table-controller.html'), 'utf8');
const original = [{field: 'CLIENTE', visible: true, width: 150},
    {field: 'ADJUNTO CORREO CLIENTE', visible: false, width: 160},
    {field: 'ADJUNTO COTIZACION PROVEEDOR', visible: false, width: 180},
    {field: 'ADJUNTO FACTURA PROVEEDOR', visible: false, width: 220}];
let current = original.map(c => ({...c}));
const column = def => ({getField: () => def.field, getDefinition: () => def,
    isVisible: () => def.visible, getWidth: () => def.width});
const calls = [];
const providerContext = vm.createContext({
    window: context.window, isAdmin: false, IS_RENDICION: false, IS_COTIZACIONES: true,
    _cotVista: 'proveedor', _cotLayoutGeneral: null, _cotCambiandoColumnas: false,
    columnLayoutVistas: {}, columnLayout: original.map(c => ({...c})),
    persistColumnLayout: (columns, vista) => calls.push({columns, vista}),
    table: {getColumns: () => current.map(column), getSorters: () => [],
        setColumns: definitions => {current = definitions;}},
});
const start = controller.indexOf('    function cotAplicarColumnasVista(');
vm.runInContext(controller.slice(start, controller.indexOf('    let _cotCambiandoAnchos', start)), providerContext);
providerContext.cotAplicarColumnasVista('proveedor');
assert.equal(current.find(c => c.field === 'ADJUNTO CORREO CLIENTE').visible, true);
assert.equal(current.find(c => c.field === 'ADJUNTO COTIZACION PROVEEDOR').visible, true);
assert.equal(current.find(c => c.field === 'ADJUNTO FACTURA PROVEEDOR').visible, false);
assert.ok(current.every(c => c.resizable === false));
assert.deepEqual(current.map(c => c.field), original.map(c => c.field));
providerContext.cotAplicarColumnasVista('registro');
assert.equal(current.find(c => c.field === 'ADJUNTO CORREO CLIENTE').visible, false);
assert.equal(current.find(c => c.field === 'ADJUNTO COTIZACION PROVEEDOR').visible, false);
assert.equal(calls.length, 0, 'Cambiar de pestaña no guarda cambios automáticos');
providerContext.cotAplicarColumnasVista('proveedor');
providerContext.isAdmin = true;
vm.runInContext(controller.slice(controller.indexOf('    function saveColumnLayout('), controller.indexOf('    async function woToast')), providerContext);
providerContext.saveColumnLayout();
assert.equal(calls.length, 1);
assert.equal(calls[0].vista, 'proveedor');
assert.equal(JSON.stringify(providerContext.columnLayout), JSON.stringify(original), 'La vista general no cambia');
console.log('OK: Proveedor muestra ambos adjuntos y conserva las demás vistas');
