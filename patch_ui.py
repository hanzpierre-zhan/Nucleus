# -*- coding: utf-8 -*-
"""Script to add UI button and JS for migration"""

import sys

path = r'c:\Mega\Proyect\Nucleus\templates\index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = '''    <button type="button" id="btn-admin-cot" class="action-pill" onclick="adminCotAbrir()"
            title="Administrar estados de cotizaciones (forzar estados)"
            style="background:#00d4aa22; color:#00d4aa; border:1px solid #00d4aa55;">
        <i class="fa-solid fa-shield-halved"></i> Admin
    </button>
    {% endif %}'''

NEW = '''    <button type="button" id="btn-admin-cot" class="action-pill" onclick="adminCotAbrir()"
            title="Administrar estados de cotizaciones (forzar estados)"
            style="background:#00d4aa22; color:#00d4aa; border:1px solid #00d4aa55;">
        <i class="fa-solid fa-shield-halved"></i> Admin
    </button>
    <button type="button" class="action-pill" onclick="migrarCotizacionesEnProceso()"
            title="Migrar registros antiguos a 2. Cliente (En Aprobación)"
            style="background:rgba(255,149,0,0.15); color:#FF9500; border:1px solid rgba(255,149,0,0.5);">
        <i class="fa-solid fa-wand-magic-sparkles"></i> Migrar 2.Cliente
    </button>
    {% endif %}'''

if OLD in content:
    content = content.replace(OLD, NEW)
    print("HTML Button added")
else:
    print("HTML OLD block not found. Trying another way...")
    # fallback
    if '<i class="fa-solid fa-shield-halved"></i> Admin' in content and 'Migrar 2.Cliente' not in content:
        content = content.replace('{% endif %}\n\n    <!-- Botón Excel', 
        '<button type="button" class="action-pill" onclick="migrarCotizacionesEnProceso()" style="background:rgba(255,149,0,0.15); color:#FF9500; border:1px solid rgba(255,149,0,0.5);"><i class="fa-solid fa-wand-magic-sparkles"></i> Migrar 2.Cliente</button>\n    {% endif %}\n\n    <!-- Botón Excel')
        print("HTML Button added via fallback")


js_func = '''
function migrarCotizacionesEnProceso() {
    if (!confirm('¿Seguro que deseas migrar los registros (En proceso) a la pestaña 2. Cliente? Esto cambiará su estado a En Aprobación.')) return;
    
    fetch('/api/cotizacion/migrar_antiguos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json().then(j => ({ ok: r.ok, status: r.status, j })))
    .then(({ ok, status, j }) => {
        if (!ok || !j.success) {
            alert(j.error || ('Error ' + status));
        } else {
            alert('¡Migración exitosa! ' + j.migrados + ' registros migrados a 2. Cliente.');
            location.reload();
        }
    })
    .catch(err => {
        alert('Error de red: ' + err.message);
    });
}
'''

if 'migrarCotizacionesEnProceso()' not in content:
    idx_script = content.rfind('</script>')
    if idx_script > 0:
        content = content[:idx_script] + js_func + content[idx_script:]
        print("JS function added")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
