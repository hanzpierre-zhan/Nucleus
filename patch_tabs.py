# -*- coding: utf-8 -*-
"""Script to patch cotPestaniaDe"""

path = r'c:\Mega\Proyect\Nucleus\templates\index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = '''    function cotPestaniaDe(row) {
        if (!IS_COTIZACIONES) return '';
        const v = String((row && row['ESTADO COTIZACION']) || '').trim().toLowerCase();
        if (v === 'cotizado' || v === 'en cotización' || v === 'en cotizacion') return 'cliente'; // pasa directo a cliente tras generar
        if (v === 'en aprobación' || v === 'en aprobacion') return 'cliente';
        if (v === 'atendido' || v === 'validado') return 'atendido';
        if (v === 'cancelado' || v === 'anulado' || v === 'anulada') return 'cancelado';
        return 'registro';
    }'''

NEW = '''    function cotPestaniaDe(row) {
        if (!IS_COTIZACIONES) return '';
        const v = String((row && row['ESTADO COTIZACION']) || '').trim().toLowerCase();
        
        // 4. Cancelado
        if (v === 'cancelado' || v === 'anulado' || v === 'anulada') return 'cancelado';
        
        // 3. Atendido
        if (v === 'atendido' || v === 'validado') return 'atendido';
        
        // 1. Registro (SOLO Pdt. Cotización)
        if (v === 'pdt. cotización' || v === 'pdt. cotizacion') return 'registro';
        
        // 2. Cliente (Cualquier otro estado antiguo como "En proceso", o nuevos como "Cotizado", "En Aprobación")
        return 'cliente';
    }'''

if OLD in content:
    content = content.replace(OLD, NEW)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("cotPestaniaDe updated successfully!")
else:
    print("Could not find OLD block. Trying to locate it manually...")
    idx = content.find('function cotPestaniaDe')
    print(repr(content[idx:idx+500]))
