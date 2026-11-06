(() => {
    'use strict';
    const buscar = document.getElementById('gestion-buscar');
    const fichas = [...document.querySelectorAll('[data-busqueda]')];
    buscar?.addEventListener('input', () => {
        const valor = buscar.value.trim().toLocaleLowerCase('es');
        for (const ficha of fichas) {
            ficha.hidden = !ficha.dataset.busqueda.toLocaleLowerCase('es').includes(valor);
        }
        document.getElementById('gestion-sin-resultados').hidden = fichas.some(ficha => !ficha.hidden);
    });
    for (const boton of document.querySelectorAll('[data-copiar]')) {
        boton.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(boton.dataset.copiar);
                boton.textContent = 'Copiado';
            } catch {
                boton.textContent = 'Selecciona el número';
            }
        });
    }
})();
