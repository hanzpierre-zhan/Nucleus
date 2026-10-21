const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const toastSource = fs.readFileSync(path.join(root, 'static/js/toast.js'), 'utf8');
const controller = fs.readFileSync(path.join(root, 'templates/index/table-controller.html'), 'utf8');
const syncSource = controller.match(/function sincronizarTodo\(\) \{[\s\S]*?\n    \}/)[0];
function environment(responses = [], storage = new Map()) {
    const nodes = new Map(), timers = [];
    const button = {disabled: false, innerHTML: 'Sincronizar'};
    nodes.set('btn-sync-rendicion', button);
    const makeNode = () => ({children: [], setAttribute() {},
        replaceChildren() {this.children = [];}, append(...children) {this.children.push(...children);}});
    const env = vm.createContext({
        document: {getElementById: id => nodes.get(id), createElement: makeNode,
            body: {appendChild: node => nodes.set(node.id, node)}},
        sessionStorage: {getItem: k => storage.get(k) || null,
            setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k)},
        setTimeout: (fn, duration) => {timers.push({fn, duration}); return timers.length;}, clearTimeout() {},
        location: {reload: () => {env.reloads++;}}, reloads: 0, _rendVista: 'observado',
        fetch: async () => {const response = responses.shift(); if (response instanceof Error) throw response; return response;},
        nucleusLeerRespuestaJSON: async r => r.json(),
        alert: () => assert.fail('No debe abrir un diálogo'), nucleusAlert: () => assert.fail('No debe abrir un modal'),
    });
    env.window = env;
    vm.runInContext(toastSource, env);
    vm.runInContext(syncSource, env);
    return {env, nodes, timers, button, storage};
}
const ok = json => ({ok: true, json: async () => json});
(async () => {
    const run = environment([ok({nuevas: 0}), ok({actualizados: 2})]);
    await run.env.sincronizarTodo();
    assert.equal(run.env.reloads, 1);
    assert.equal(run.button.disabled, false);
    assert.equal(run.storage.get('rend_vista_tras_sync'), 'observado');
    const reloaded = environment([], run.storage);
    const toast = reloaded.nodes.get('nucleus-toast');
    assert.equal(toast.children[1].textContent, 'Sincronización completada');
    assert.equal(reloaded.timers[0].duration, 4000);
    reloaded.timers[0].fn();
    assert.equal(toast.hidden, true);
    assert.equal(environment([], run.storage).nodes.has('nucleus-toast'), false, 'Se muestra una sola vez');

    const partial = environment([{ok: false, json: async () => ({error: 'Formulario no disponible'})}, ok({actualizados: 0})]);
    await partial.env.sincronizarTodo();
    assert.equal(partial.env.reloads, 0);
    assert.match(partial.nodes.get('nucleus-toast').children[1].textContent, /Formulario no disponible/);
    assert.equal(partial.timers[0].duration, 8000);
    const network = environment([new Error('Sin red')]);
    await network.env.sincronizarTodo();
    assert.equal(network.button.disabled, false);
    assert.equal(network.env.reloads, 0);
    assert.match(network.nodes.get('nucleus-toast').className, /is-error/);
    console.log('OK: confirmación tras recarga, autocierre y errores sin modal');
})().catch(error => {console.error(error); process.exitCode = 1;});
