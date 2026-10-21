(function () {
    'use strict';
    let timer;
    const pendingKey = 'nucleus-sync-confirmacion';
    function show(message, options = {}) {
        let toast = document.getElementById('nucleus-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'nucleus-toast';
            toast.setAttribute('role', 'status');
            toast.setAttribute('aria-live', 'polite');
            toast.setAttribute('aria-atomic', 'true');
            document.body.appendChild(toast);
        }
        clearTimeout(timer);
        toast.replaceChildren();
        const icon = document.createElement('span');
        icon.className = 'nucleus-toast-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = options.error ? '!' : '✓';
        const text = document.createElement('span');
        text.textContent = message;
        toast.append(icon, text);
        toast.className = 'nucleus-toast' + (options.error ? ' is-error' : '');
        toast.hidden = false;
        timer = setTimeout(() => { toast.hidden = true; }, options.error ? 8000 : 4000);
    }
    window.nucleusToast = show;
    window.nucleusToastTrasRecargar = message => {
        try {
            sessionStorage.setItem(pendingKey, JSON.stringify({message, fecha: Date.now()}));
            return true;
        } catch (_) { return false; }
    };
    try {
        const pending = sessionStorage.getItem(pendingKey);
        sessionStorage.removeItem(pendingKey);
        if (pending) {
            const data = JSON.parse(pending);
            if (typeof data.message === 'string' && Date.now() - data.fecha < 60000) show(data.message);
        }
    } catch (_) {}
}());
