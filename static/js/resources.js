(() => {
    'use strict';
    const panel = document.getElementById('render-runtime');
    const number = new Intl.NumberFormat('es-PE', {maximumFractionDigits: 1});
    const mib = value => `${number.format(value / 1024 ** 2)} MiB`;
    let loading = false;

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
    refresh();
    setInterval(refresh, 15000);
})();
