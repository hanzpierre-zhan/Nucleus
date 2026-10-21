// Ejecutar con: node tests/test_rendicion_detalle.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const controller = fs.readFileSync(path.join(root, 'templates/index/table-controller.html'), 'utf8');
const detail = fs.readFileSync(path.join(root, 'templates/index/rendicion-detalle-avisos.html'), 'utf8');
const grid = {innerHTML: ''};
const columns = ['ESTADO', 'Campo oculto', 'MOTIVO RECHAZO'].map(field => ({
    getDefinition: () => ({field, title: field}), isVisible: () => false,
}));
const context = vm.createContext({
    document: {getElementById: () => grid},
    table: {getColumns: () => columns},
    escapeHtml: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
});
vm.runInContext(controller.slice(controller.indexOf('    function rendEstadoDe('), controller.indexOf('    // Botones del flujo:')), context);
vm.runInContext(detail.slice(detail.indexOf('function rendPoblarDetalle('), detail.indexOf('let _textoAmplioTarget')), context);

context.rendPoblarDetalle({ESTADO: 'RECHAZADO', 'Campo oculto': 'Dato oculto',
    'Campo fuera del esquema': 'También visible', OBSERVACIONES: '<Motivo anterior>',
    _HISTORIAL_FLUJO: ['privado'], _key: 'interno', SUBESTADO: ''}, 'detalle');
assert.match(grid.innerHTML, /Dato oculto/);
assert.match(grid.innerHTML, /También visible/);
assert.match(grid.innerHTML, /MOTIVO RECHAZO/);
assert.match(grid.innerHTML, /&lt;Motivo anterior&gt;/);
assert.doesNotMatch(grid.innerHTML, /privado|_key/);
assert.equal(columns.length, 3, 'El detalle no modifica las columnas de la tabla');
for (const desde of ['CON SUSTENTO', 'OBSERVADO', 'SUSTENTADO']) {
    assert.equal(context.rendEstadoParaVista({ESTADO: 'RECHAZADO', 'RECHAZADO DESDE': desde}), 'DEPOSITADO');
}
for (const estado of ['CON SUSTENTO', 'SUSTENTADO']) {
    const row = {ESTADO: estado, SUBESTADO: 'OBSERVADO'};
    assert.equal(context.rendEstadoDe(row), estado);
    assert.equal(context.rendEstadoParaVista(row), 'OBSERVADO');
}
assert.equal(context.rendEstadoParaVista({ESTADO: 'SUSTENTADO', SUBESTADO: 'ARCHIVADO'}), 'ARCHIVADO');
console.log('OK: detalle completo, motivo seguro y vistas por subestado/rechazo');
