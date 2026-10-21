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
    getDefinition: () => ({field, title: field}), isVisible: () => field !== 'Campo oculto',
}));
const context = vm.createContext({
    window: {},
    document: {getElementById: () => grid},
    table: {getColumns: () => columns},
    escapeHtml: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
});
vm.runInContext(controller.slice(controller.indexOf('    function rendEstadoDe('), controller.indexOf('    // Botones del flujo:')), context);
vm.runInContext(detail.slice(detail.indexOf('function rendPoblarDetalle('), detail.indexOf('let _textoAmplioTarget')), context);

context.rendPoblarDetalle({ESTADO: 'RECHAZADO', 'Campo oculto': 'Dato oculto',
    'Campo fuera del esquema': 'También visible', OBSERVACIONES: '<Motivo anterior>',
    _HISTORIAL_FLUJO: ['privado'], _key: 'interno', SUBESTADO: ''}, 'detalle');
assert.doesNotMatch(grid.innerHTML, /Dato oculto|Campo oculto/);
assert.doesNotMatch(grid.innerHTML, /También visible|Campo fuera del esquema|SUBESTADO/);
assert.match(grid.innerHTML, /MOTIVO RECHAZO/);
assert.match(grid.innerHTML, /&lt;Motivo anterior&gt;/);
assert.doesNotMatch(grid.innerHTML, /privado|_key/);
assert.equal(columns.length, 3, 'El detalle no modifica las columnas de la tabla');
columns[2].isVisible = () => false;
context.rendPoblarDetalle({ESTADO: 'RECHAZADO', 'MOTIVO RECHAZO': 'No mostrar'}, 'detalle');
assert.doesNotMatch(grid.innerHTML, /MOTIVO RECHAZO|No mostrar/);
for (const desde of ['CON SUSTENTO', 'OBSERVADO', 'SUSTENTADO']) {
    assert.equal(context.rendEstadoParaVista({ESTADO: 'RECHAZADO', 'RECHAZADO DESDE': desde}), 'DEPOSITADO');
}
for (const estado of ['CON SUSTENTO', 'SUSTENTADO']) {
    const row = {ESTADO: estado, SUBESTADO: 'OBSERVADO'};
    assert.equal(context.rendEstadoDe(row), estado);
    assert.equal(context.rendEstadoParaVista(row), 'OBSERVADO');
}
assert.equal(context.rendEstadoParaVista({ESTADO: 'SUSTENTADO', SUBESTADO: 'ARCHIVADO'}), 'ARCHIVADO');
// La configuración por hoja prevalece sobre defaults, columnas nuevas y navegador.
const base = {visibles: {'ESTADO': true, 'SUBESTADO': true, 'MOTIVO RECHAZO': true,
    'DEPARTAMENTO': true, 'SUSTENTO_NUEVO': true, 'RECHAZADO POR': false},
    orden: ['ESTADO', 'SUBESTADO', 'MOTIVO RECHAZO', 'DEPARTAMENTO', 'SUSTENTO_NUEVO', 'RECHAZADO POR'], anchos: {}};
const saved = [{field: 'MOTIVO RECHAZO', visible: false}, {field: 'ESTADO', visible: true},
    {field: 'RECHAZADO POR', visible: true}, {field: 'DEPARTAMENTO', visible: false}];
const layoutContext = vm.createContext({
    _rendEstadoListo: false, _rendEstadoVistas: {}, _rendSnapshot: () => base,
    REND_VISTAS: {validacion: {showCols: ['SUBESTADO']}, evidencia: {showPrefijos: ['SUSTENTO_']}},
    columnLayoutVistas: {validacion: saved}, columnLayout: [{field: 'ESTADO', visible: false}],
    _rendEsColumnaDeVista: f => Boolean(f), _rendAnchosClave: vista => 'anchos-' + vista,
    localStorage: {getItem: () => '{}'},
});
vm.runInContext(detail.slice(detail.indexOf('function _rendInitEstados()'), detail.indexOf('// Reordena columnas al orden guardado')), layoutContext);
layoutContext._rendInitEstados();
const vista = layoutContext._rendEstadoVistas.validacion;
assert.equal(vista.visibles['MOTIVO RECHAZO'], false);
assert.equal(vista.visibles['DEPARTAMENTO'], false);
assert.equal(vista.visibles.SUBESTADO, false);
assert.equal(vista.visibles.SUSTENTO_NUEVO, false);
assert.equal(vista.visibles['RECHAZADO POR'], true);
assert.deepEqual(Array.from(vista.orden.slice(0, 4)), saved.map(c => c.field));
assert.equal(layoutContext._rendEstadoVistas.evidencia.visibles.ESTADO, false);
assert.equal(layoutContext._rendEstadoVistas.evidencia.visibles.SUSTENTO_NUEVO, false);
assert.equal(base.visibles.DEPARTAMENTO, true, 'Inicializar no modifica la configuración original');
console.log('OK: detalle solo visible y configuración de columnas respetada');
