(function(){
    'use strict';
    const dialog = document.getElementById('rend-validator-dialog'); if (!dialog) return;
    const body = document.getElementById('rend-validator-users'), status = document.getElementById('rend-validator-status');
    const enabled = document.getElementById('rend-validator-active');
    document.getElementById('rend-validator-close').onclick = () => dialog.close();
    window.abrirValidadoresRendicion = async () => {
        document.getElementById('module-settings-menu')?.classList.remove('show');
        status.textContent = 'Cargando…'; body.replaceChildren(); dialog.showModal();
        try {
            const response = await fetch('/api/rendicion/validadores'); const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'No se pudo cargar.');
            enabled.checked = !!data.configuracion.activo;
            for (const user of data.usuarios) {
                const tr = document.createElement('tr'), name = document.createElement('th'); name.scope='row';
                const full = document.createElement('strong'), login = document.createElement('small');
                full.textContent = user.nombre; login.textContent = user.username + (user.admin ? ' · Administración: todos los proyectos' : '');
                name.append(full,login); tr.append(name);
                for (const project of data.proyectos) {
                    const td = document.createElement('td'), box = document.createElement('input'); box.type='checkbox';
                    box.dataset.user = user.id; box.dataset.project = project; box.disabled = user.admin;
                    box.checked = user.admin || (data.configuracion.asignaciones?.[user.id] || []).includes(project);
                    box.setAttribute('aria-label',`${user.nombre}: validar ${project}`);td.append(box);tr.append(td);
                }
                body.append(tr);
            }
            status.textContent = '';
        } catch(error) {status.textContent = error.message;}
    };
    document.getElementById('rend-validator-save').onclick = async function(){
        this.disabled = true; status.textContent='Guardando…';
        try {
            const asignaciones = {};
            body.querySelectorAll('input:not(:disabled)').forEach(box=>{
                const id=box.dataset.user; asignaciones[id] ||= [];
                if(box.checked) asignaciones[id].push(box.dataset.project);
            });
            const response=await fetch('/api/rendicion/validadores',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({activo:enabled.checked,asignaciones})});
            const result=await response.json(); if(!response.ok) throw new Error(result.error || 'No se pudo guardar.');
            window.REND_VALIDADORES_CONFIG = result.configuracion;
            status.textContent='Asignaciones guardadas.';
        } catch(error){status.textContent=error.message;} finally {this.disabled=false;}
    };
})();
