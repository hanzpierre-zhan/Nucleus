(() => {
    'use strict';
    const panel = document.getElementById('render-runtime');
    const monitor = document.getElementById('resources-monitor');
    const number = new Intl.NumberFormat('es-PE', {maximumFractionDigits: 1});
    const mib = value => `${number.format(value / 1024 ** 2)} MiB`;
    let loading = false;
    let inventoryLoading = false;
    let inventoryAt = 0;
    const interval = 5 * 60 * 1000;
    const setLive = (key, value) => {
        monitor.querySelector('[data-live="' + key + '"]').textContent = value;
    };
    const lectura = new Intl.DateTimeFormat('es-PE', {
        timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short',
    });

    async function refreshInventory() {
        if (document.hidden || inventoryLoading || Date.now() - inventoryAt < interval) return;
        inventoryLoading = true;
        try {
            const response = await fetch(monitor.dataset.url, {headers: {Accept: 'application/json'}});
            if (!response.ok) throw new Error('No disponible');
            const {neon, b2, timestamp} = await response.json();
            const at = lectura.format(new Date(timestamp));
            setLive('neon-size', neon.status === 'ok' ? mib(neon.size_bytes) : '—');
            setLive('neon-connections', neon.status === 'ok' ? number.format(neon.connections) : '—');
            setLive('neon-note', neon.status === 'ok' ? 'Lectura de la base conectada · ' + at : neon.note || neon.error);
            const prefix = b2.status === 'partial' ? '≥ ' : '';
            setLive('b2-size', b2.size_bytes == null ? '—' : prefix + mib(b2.size_bytes));
            setLive('b2-files', b2.files == null ? '—' : prefix + number.format(b2.files));
            setLive('b2-note', b2.size_bytes == null ? b2.note || b2.error : b2.note + ' · ' + at);
        } catch {
            setLive('neon-note', 'No se pudo actualizar la lectura.');
            setLive('b2-note', 'No se pudo actualizar el inventario.');
        } finally {
            inventoryAt = Date.now();
            inventoryLoading = false;
        }
    }

    function display(key, percent, detail) {
        const card = panel.querySelector(`[data-runtime="${key}"]`);
        const arc = card.querySelector('[data-gauge-fill]');
        card.dataset.level = percent > 80 ? 'critical' : percent > 50 ? 'warning' : 'normal';
        card.querySelector('[data-percent]').textContent = percent == null ? '—' : `${number.format(percent)}%`;
        arc.setAttribute('stroke-dasharray', `${Math.min(100, Math.max(0, percent ?? 0))} 100`);
        card.querySelector('[data-detail]').textContent = detail;
    }

    async function refresh() {
        if (loading || document.hidden) return;
        loading = true;
        try {
            const response = await fetch(panel.dataset.url, {headers: {Accept: 'application/json'}});
            if (!response.ok) throw new Error('No disponible');
            const {memory, cpu, note} = await response.json();
            let ram = 'No disponible';
            if (memory.size_bytes != null) {
                ram = mib(memory.size_bytes);
                if (memory.limit_bytes != null) ram += ` / ${mib(memory.limit_bytes)}`;
                if (memory.scope?.startsWith('Solo este proceso')) ram += ' · proceso';
            }
            display('memory', memory.pct_used, ram);
            display('cpu', cpu.pct_used, cpu.used_cores == null ? 'No disponible' :
                `${number.format(cpu.used_cores)}${cpu.limit_cores == null ? '' : ' / ' + number.format(cpu.limit_cores)} vCPU`);
            panel.querySelector('[data-runtime-note]').textContent = note || '';
        } catch {
            display('memory', null, 'No disponible');
            display('cpu', null, 'No disponible');
            panel.querySelector('[data-runtime-note]').textContent = 'No se pudo actualizar la lectura.';
        } finally {
            loading = false;
        }
    }

    document.addEventListener('visibilitychange', refresh);
    document.addEventListener('visibilitychange', refreshInventory);
    refresh();
    refreshInventory();
    setInterval(refresh, 15000);
    setInterval(refreshInventory, interval);
})();
