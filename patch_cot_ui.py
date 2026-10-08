# -*- coding: utf-8 -*-
"""
Aplica 3 mejoras visuales a las Cotizaciones en index.html:
  1. Pestañas con color por vista
  2. Badge de color en ESTADO COTIZACION
  3. Botones FLUJO más compactos y bonitos
"""
import re, sys

path = r'c:\Mega\Proyect\Nucleus\templates\index.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# ─── 1. CSS: Colores de pestaña + badge estados + botones mejorados ──────────
CSS_EXTRA = """
    /* ── Cotizaciones: colores por pestaña ─────────────── */
    #cot-tabs .rend-tab[data-vista="registro"]  { --tab-c: #8E8E93; }
    #cot-tabs .rend-tab[data-vista="cliente"]   { --tab-c: #FF9500; }
    #cot-tabs .rend-tab[data-vista="atendido"]  { --tab-c: #28A745; }
    #cot-tabs .rend-tab[data-vista="cancelado"] { --tab-c: #6B7280; }

    #cot-tabs .rend-tab[data-vista="registro"]:not(.active)  { color:#8E8E93; border-color:#8E8E9355; }
    #cot-tabs .rend-tab[data-vista="cliente"]:not(.active)   { color:#FF9500; border-color:#FF950055; }
    #cot-tabs .rend-tab[data-vista="atendido"]:not(.active)  { color:#28A745; border-color:#28A74555; }
    #cot-tabs .rend-tab[data-vista="cancelado"]:not(.active) { color:#6B7280; border-color:#6B728055; }

    /* ── Badge: ESTADO COTIZACION ───────────────────────── */
    .cot-est-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 10.5px;
        font-weight: 700;
        white-space: nowrap;
        letter-spacing: 0.2px;
    }

    /* ── Botones FLUJO Cotizaciones: tamaño ajustado ────── */
    .rend-acciones { display: flex; align-items: center; gap: 4px; padding: 0; }
    .cot-btn {
        border: none; border-radius: 7px; cursor: pointer;
        font-size: 13px; padding: 4px 7px; color: #fff;
        transition: filter .15s, transform .1s;
        box-shadow: 0 1px 3px rgba(0,0,0,.2);
        line-height: 1;
    }
    .cot-btn:hover  { filter: brightness(1.15); transform: translateY(-1px); }
    .cot-btn:active { filter: brightness(0.9);  transform: scale(0.95); }
    .cot-btn:disabled { opacity: .4; cursor: not-allowed; transform: none; }
    .cot-btn-gen    { background: linear-gradient(135deg,#007AFF,#005ecb); }
    .cot-btn-ok     { background: linear-gradient(135deg,#28A745,#1e8a38); }
    .cot-btn-rev    { background: linear-gradient(135deg,#FF9500,#e07f00); }
    .cot-btn-cancel { background: linear-gradient(135deg,#6B7280,#4b5563); }
    .cot-btn-done   { background: linear-gradient(135deg,#28A745,#1e8a38); font-size:16px; padding: 3px 6px; }
    .cot-btn-atend  { background: linear-gradient(135deg,#AF52DE,#8e3ab8); }
"""

# Inyectar antes del cierre </style>
html = html.replace('</style>', CSS_EXTRA + '\n    </style>', 1)

# ─── 2. Añadir IS_COTIZACIONES block en columnas: badge ESTADO COTIZACION ─────
COL_BADGE = """
            // Cotizaciones: ESTADO COTIZACION → badge de color
            if (IS_COTIZACIONES && fieldName === 'ESTADO COTIZACION') {
                colDef.editor = false;
                colDef.headerFilter = listaHeaderFilter(manualDef ? manualDef.opciones : [
                    'Pdt. Cotización','En proceso','Cotizado','En Aprobación','Observado','Rechazado','Atendido','Cancelado','Anulada'
                ]);
                colDef.formatter = function (cell) {
                    const rawEst = String(cell.getValue() || '').trim();
                    const est    = cotEstadoDe({ 'ESTADO COTIZACION': rawEst });
                    const c = COT_ESTADO_COLORS[est] || COT_ESTADO_COLORS[rawEst] || { bg: '#8E8E93', fg: '#fff' };
                    const span = document.createElement('span');
                    span.className = 'cot-est-badge';
                    span.textContent = rawEst || est;
                    span.style.background = c.bg;
                    span.style.color      = c.fg;
                    return span;
                };
            }

"""

# Insertar después de la sección de "lista" pero antes de "Rendicion: ESTADO"
TARGET_COL = "            // Rendicion: ESTADO muestra un badge con el color de su estado dentro"
html = html.replace(TARGET_COL, COL_BADGE + '            ' + TARGET_COL.strip(), 1)

# ─── 3. Reemplazar botones del FLUJO de Cotizaciones por cot-btn ─────────────
OLD_FLUJO = """                function mk(clase, texto, titulo, fn) {

                    const b = document.createElement('button');

                    b.type = 'button';

                    b.className = 'rend-btn ' + clase;

                    if (String(texto).trim().charAt(0) === '<') b.innerHTML = texto;

                    else b.textContent = texto;

                    b.title = titulo;

                    b.disabled = !puede;

                    b.onclick = (e) => { e.stopPropagation(); fn(); };

                    wrap.appendChild(b);

                }



                if (pest === 'registro') {
                    // Boton principal: Generar cotizacion
                    mk('rend-btn-ok', '<i class="fa-solid fa-file-circle-plus"></i>',
                       'Generar cotizacion: abre el desglose de partidas',"""

NEW_FLUJO = """                function mk(clase, texto, titulo, fn) {
                    const b = document.createElement('button');
                    b.type = 'button';
                    b.className = 'cot-btn ' + clase;
                    if (String(texto).trim().charAt(0) === '<') b.innerHTML = texto;
                    else b.textContent = texto;
                    b.title = titulo;
                    b.disabled = !puede;
                    b.onclick = (e) => { e.stopPropagation(); fn(); };
                    wrap.appendChild(b);
                }

                if (pest === 'registro') {
                    // Boton principal: Generar cotizacion
                    mk('cot-btn-gen', '<i class="fa-solid fa-file-circle-plus"></i>',
                       'Generar cotizacion: abre el desglose de partidas',"""

html = html.replace(OLD_FLUJO, NEW_FLUJO, 1)

# Arreglar botones de cliente
html = html.replace(
    "mk('rend-btn-sus', '<i class=\"fa-solid fa-circle-check\"></i>',\n                       'Aprobar - requiere fecha + correo .msg del cliente',",
    "mk('cot-btn-ok', '<i class=\"fa-solid fa-circle-check\"></i>',\n                       'Aprobar - requiere fecha + correo .msg del cliente',"
)
html = html.replace(
    "mk('rend-btn-rev rend-btn-mini', '<i class=\"fa-solid fa-rotate-left\"></i>',\n                       'Rechazar - regresa a Pdt. Cotizacion',",
    "mk('cot-btn-rev', '<i class=\"fa-solid fa-rotate-left\"></i>',\n                       'Rechazar - regresa a Pdt. Cotizacion',"
)
html = html.replace(
    "mk('rend-btn rend-btn-mini', '<i class=\"fa-solid fa-ban\"></i>',\n                       'Cancelar - pasa a Anulado',",
    "mk('cot-btn-cancel', '<i class=\"fa-solid fa-ban\"></i>',\n                       'Cancelar - pasa a Anulado',"
)

# Verificar tambien posibles botones del estado atendido
html = html.replace(
    "chk.className = 'rend-btn-done rend-pill rend-pill-sus';",
    "chk.className = 'cot-btn cot-btn-done';"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print("✅ 3 mejoras aplicadas:")
print("   1. Pestañas con colores")
print("   2. Badge en ESTADO COTIZACION")
print("   3. Botones FLUJO compactos")
