/* El número mostrado es provisional; la reserva definitiva pertenece al servidor. */
(function (root) {
    'use strict';
    let timer = null;
    let currentInput = null;
    let guardando = false;

    function detener() {
        if (timer !== null) clearInterval(timer);
        timer = null;
        currentInput = null;
    }

    function configurarCampo(input, cliente, prefijo) {
        detener();
        currentInput = input;
        input.dataset.numeracionModo = 'automatico';
        input.readOnly = true;
        const help = document.createElement('small');
        help.style.cssText = 'display:block;margin-top:5px;color:var(--ios-secondary);font-size:11px';
        help.textContent = 'Provisional. El número definitivo se asigna al guardar.';
        const label = document.createElement('label');
        label.style.cssText = 'display:flex;gap:6px;align-items:center;font-size:11px;margin-top:5px';
        const manual = document.createElement('input');
        manual.type = 'checkbox';
        manual.style.width = 'auto';
        label.append(manual, document.createTextNode('Elegir número manual'));
        input.after(help, label);

        async function refrescar() {
            if (currentInput !== input || manual.checked) return;
            try {
                const response = await fetch('/api/cotizacion/next_seq', {cache: 'no-store'});
                const data = await response.json();
                if (!response.ok || !data.next || currentInput !== input || manual.checked || !input.isConnected) return;
                const base = prefijo(cliente.value).split('-')[0];
                const now = new Date();
                input.value = base + '-' + (data.year || now.getFullYear()) + '-'
                    + String(data.month || now.getMonth() + 1).padStart(2, '0') + '-'
                    + String(data.next).padStart(6, '0');
            } catch (_) {
                // Una lectura fallida no borra el formulario ni reserva números.
            }
        }
        manual.addEventListener('change', function () {
            input.dataset.numeracionModo = manual.checked ? 'manual' : 'automatico';
            input.readOnly = !manual.checked;
            help.textContent = manual.checked ? 'Se validará que el número esté disponible al guardar.'
                : 'Provisional. El número definitivo se asigna al guardar.';
            if (manual.checked) input.focus();
            else refrescar();
        });
        cliente.addEventListener('change', refrescar);
        input.addEventListener('focus', refrescar);
        timer = setInterval(function () {
            if (!input.isConnected) detener();
            else refrescar();
        }, 15000);
        refrescar();
    }

    async function crear(payload) {
        if (guardando) return null;
        guardando = true;
        try {
        let request = {...payload, numeracion_modo: payload.numeracion_modo || 'automatico'};
        // Reenviar solo tras un rechazo explícito: nunca reintentar una respuesta
        // de red incierta, que podría corresponder a un alta ya confirmada.
        for (let intento = 0; intento < 2; intento++) {
            const response = await fetch('/api/rows/add', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)
            });
            const result = await response.json();
            if (response.ok && result.success) return result;
            if (response.status === 409 && result.code === 'COTIZACION_NUMERO_NO_DISPONIBLE'
                    && request.numeracion_modo === 'manual' && intento === 0) {
                const usar = await nucleusConfirm('El número manual no está disponible. ¿Guardar con el siguiente automático'
                    + (result.suggested ? ' (ahora ' + result.suggested + ')' : '')
                    + '? Se conservarán todos los datos de la solicitud.');
                if (!usar) return null;
                request = {...request, key: '', numeracion_modo: 'automatico'};
                continue;
            }
            throw new Error(result.error || 'No se pudo guardar la solicitud. Tus datos siguen en el formulario.');
        }
        } finally {
            guardando = false;
        }
    }

    function confirmar(result) {
        const mensaje = 'Solicitud registrada con el número ' + result.key + '.';
        if (typeof nucleusToast === 'function') nucleusToast(mensaje);
        if (typeof nucleusToastTrasRecargar === 'function') {
            nucleusToastTrasRecargar(mensaje);
        }
    }

    root.CotizacionNumeracion = {configurarCampo, detener, crear, confirmar};
})(window);
