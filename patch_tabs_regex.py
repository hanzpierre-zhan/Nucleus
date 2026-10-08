# -*- coding: utf-8 -*-
import sys
import re

path = r'c:\Mega\Proyect\Nucleus\templates\index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = r"function cotPestaniaDe\(row\) \{[\s\S]*?return 'registro';\s*\}"
NEW = '''function cotPestaniaDe(row) {
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

new_content, count = re.subn(OLD, NEW, content)

if count > 0:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("cotPestaniaDe updated successfully via regex!")
else:
    print("Regex replacement failed.")
