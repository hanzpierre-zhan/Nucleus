import sys

with open(r'c:\Mega\Proyect\Nucleus\templates\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

BTN_PDF = 'id="btn-coti-pdf"'
if BTN_PDF in content:
    idx = content.find(BTN_PDF)
    start = content.rfind('<button', 0, idx)
    end = content.find('</button>', idx) + len('</button>')
    old_btn = content[start:end]

    admin_btn = '''
    {% if session.get('rol') in ('zeno', 'suport') %}
    <button type="button" id="btn-admin-cot" class="action-pill" onclick="adminCotAbrir()"
            title="Administrar estados de cotizaciones (forzar estados)"
            style="background:#00d4aa22; color:#00d4aa; border:1px solid #00d4aa55;">
        <i class="fa-solid fa-shield-halved"></i> Admin
    </button>
    {% endif %}'''

    if 'btn-admin-cot' not in content:
        content = content.replace(old_btn, old_btn + admin_btn)
        with open(r'c:\Mega\Proyect\Nucleus\templates\index.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Admin button injected successfully next to btn-coti-pdf')
    else:
        print('Admin button already exists')
else:
    print('btn-coti-pdf not found')
