import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'c:\Mega\Proyect\Nucleus\templates\index.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

print('CSS cot-est-badge:', 'cot-est-badge' in html)
print('IS_COTIZACIONES badge formatter:', 'IS_COTIZACIONES && fieldName' in html)
print('cot-btn-gen:', 'cot-btn-gen' in html)
print('Colored tabs CSS (#8E8E93):', '#8E8E93' in html and 'cot-tabs' in html)
print('Migrar 2.Cliente button:', 'migrarCotizacionesEnProceso' in html)
