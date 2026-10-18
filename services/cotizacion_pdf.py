# -*- coding: utf-8 -*-
"""services/cotizacion_pdf.py
Generacion de los PDFs de cotizacion y armado de su respuesta HTTP.

Se separo de `apoyo.py` (que mezclaba evidencia, reporte PEXT y PDFs) para que
el render de documentos viva lejos del almacenamiento de fotos. Los imports de
`reportlab` siguen siendo diferidos: solo se cargan al generar un PDF.
"""
import io
import json
import os
import re
from datetime import datetime

from flask import jsonify, make_response, request, session

from db import db
from models import Proyecto, NucleusData
from services.utilidades import ahora_peru, audit_user

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# ── PDFs de cotización ─────────────────────────────────────────────────────
def _fecha_larga_es(fecha=None):
    """Fecha en formato largo español: 'viernes, 21 de Agosto de 2026'."""
    DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
             'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    f = fecha or datetime.now()
    return f'{DIAS[f.weekday()]}, {f.day} de {MESES[f.month - 1]} de {f.year}'


def _parse_fecha_registro(v):
    """Convierte el valor guardado de FECHA a datetime.
    Acepta datetime o strings: 'YYYY-MM-DD HH:MM[:SS]', 'YYYY-MM-DD',
    'DD/MM/YYYY [HH:MM [a.m./p.m.]]'. Devuelve None si no se interpreta."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0))
        except ValueError:
            return None
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?:\s*([ap])\.?\s*m\.?)?)?$',
                 s, re.IGNORECASE)
    if m:
        try:
            hh = int(m.group(4) or 0)
            ap = (m.group(6) or '').lower()
            if ap == 'p' and hh < 12:
                hh += 12
            if ap == 'a' and hh == 12:
                hh = 0
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                            hh, int(m.group(5) or 0))
        except ValueError:
            return None
    return None


def _generar_pdf_cotizacion(numero, nota, ticket, cotizado_por, revisado_por, fecha, gastos, mano_obra):
    """Genera el PDF de cotización con el formato exacto de la imagen."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    PAGE_W, PAGE_H = landscape(A4)
    M = 6 * mm  # margen

    # Colores corporativos
    NAVY = colors.HexColor('#1B3A6B')
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor('#F2F2F2')
    MID_GRAY = colors.HexColor('#D9D9D9')
    DARK = colors.HexColor('#1a1a1a')

    def fmt_soles(v):
        try:
            f = float(v)
            return f'S/ {f:,.2f}'
        except Exception:
            return 'S/ -'

    def safe_str(v):
        return str(v) if v is not None else ''

    # Calcular subtotales
    subtotal_a = sum(float(g.get('total_p', 0) or 0) for g in gastos)
    subtotal_b = sum(float(m.get('total_p', 0) or 0) for m in mano_obra)
    total_ab = subtotal_a + subtotal_b

    # Estilos de párrafo
    style_normal = ParagraphStyle('normal', fontName='Helvetica', fontSize=7, leading=8)
    style_bold = ParagraphStyle('bold', fontName='Helvetica-Bold', fontSize=7, leading=8)
    style_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=NAVY)
    style_header_white = ParagraphStyle('hw', fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=WHITE)
    style_section = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=WHITE)
    style_right = ParagraphStyle('right', fontName='Helvetica', fontSize=7, leading=8, alignment=TA_RIGHT)
    style_right_bold = ParagraphStyle('rb', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                             leftMargin=M, rightMargin=M,
                             topMargin=M, bottomMargin=M)
    W = PAGE_W - 2 * M
    story = []

    # ---- CABECERA: Logo | N° Cotización ---
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'cobra-logo.png')
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=30*mm, height=17*mm)
    else:
        logo = Paragraph('<b>cobra</b>', style_title)

    num_para = Paragraph(f'<b>N° Cotización :&nbsp;&nbsp;&nbsp;{numero}</b>', style_title)
    header_data = [[logo, num_para]]
    header_tbl = Table(header_data, colWidths=[W * 0.4, W * 0.6])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 1.5 * mm))

    # ---- SECCIÓN A: DATOS DEL CLIENTE ---
    def section_row(label):
        return [Paragraph(f'<b>{label}</b>', style_header_white), '', '', '']

    def client_row(label, value, label2='', value2=''):
        cells = [
            Paragraph(f'<b>{label}</b>', style_bold),
            Paragraph(safe_str(value), style_normal),
            Paragraph(f'<b>{label2}</b>', style_bold) if label2 else '',
            Paragraph(safe_str(value2), style_normal) if value2 else '',
        ]
        return cells

    c1 = W * 0.18
    c2 = W * 0.42
    c3 = W * 0.12
    c4 = W * 0.28

    sec_a_data = [
        [Paragraph('<b>A: DATOS DEL CLIENTE</b>', style_header_white), '', '', ''],
        client_row('Cliente:', 'HUAWEI DEL PERU', 'RUC:', '20507646728'),
        client_row('Domicilio:', 'Cal. las Begonias Nro. 415 Int. 2301'),
        client_row('Solicitado por:', 'Even Vivar'),
        client_row('Validador:', 'Sergio Huaman'),
        client_row('Nota:', nota or ''),
    ]
    sec_a_tbl = Table(sec_a_data, colWidths=[c1, c2, c3, c4])
    sec_a_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('SPAN', (0, 0), (-1, 0)),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, 2), (3, 2)),
        ('SPAN', (1, 3), (3, 3)),
        ('SPAN', (1, 4), (3, 4)),
        ('SPAN', (1, 5), (3, 5)),
    ]))
    story.append(sec_a_tbl)
    story.append(Spacer(1, 1 * mm))

    # ---- SECCIÓN B: DATOS DE COTIZACIÓN ---
    sec_b_data = [
        [Paragraph('<b>B: DATOS DE COTIZACION</b>', style_header_white), '', '', ''],
        client_row('Cotizado por:', 'Dennis Unton', 'Fecha:', fecha),
        client_row('Revisado por:', 'Dennis Unton', 'Fecha:', fecha),
    ]
    sec_b_tbl = Table(sec_b_data, colWidths=[c1, c2, c3, c4])
    sec_b_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('SPAN', (0, 0), (-1, 0)),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sec_b_tbl)
    story.append(Spacer(1, 1 * mm))

    # ---- TABLA 1: Materiales, Herramientas y/o Homologaciones ---
    col_item = W * 0.06
    col_cod = W * 0.07
    col_desc = W * 0.30
    col_unid = W * 0.07
    col_cant = W * 0.08
    col_pu = W * 0.18
    col_tp = W * 0.24

    t1_cols = [col_item, col_cod, col_desc, col_unid, col_cant, col_pu, col_tp]

    t1_header_sub = [Paragraph('<b>1. Materiales,  Herramientas y/o Homologaciones</b>', style_section), '', '', '', '', '', '']
    t1_col_header = [
        Paragraph('<b>Item</b>', style_bold),
        Paragraph('<b>Cod.</b>', style_bold),
        Paragraph('<b>Descripción</b>', style_bold),
        Paragraph('<b>Unid</b>', style_bold),
        Paragraph('<b>Cant</b>', style_bold),
        Paragraph('<b>Precio unid.</b>', style_bold),
        Paragraph('<b>Total P.</b>', style_bold),
    ]

    t1_rows = [t1_header_sub, t1_col_header]
    MAX_ROWS_1 = max(len(gastos), 2)
    for i in range(MAX_ROWS_1):
        if i < len(gastos):
            g = gastos[i]
            row = [
                Paragraph(safe_str(g.get('item', i+1)), style_normal),
                Paragraph(safe_str(g.get('cod', 'SC')), style_normal),
                Paragraph(safe_str(g.get('descripcion', '')), style_normal),
                Paragraph(safe_str(g.get('unid', '')), style_normal),
                Paragraph(safe_str(g.get('cant', '')), style_normal),
                Paragraph(fmt_soles(g.get('precio_unid', '')), style_right),
                Paragraph(fmt_soles(g.get('total_p', '')), style_right),
            ]
        else:
            row = ['', '', '', '', '', Paragraph('S/', style_right), Paragraph('-', style_right)]
        t1_rows.append(row)

    # Fila Total subtotal A
    t1_rows.append(['', '', '', '', '', '', ''])
    t1_rows.append([
        Paragraph('<b>Total</b>', style_bold), '', '', '', '', '',
        Paragraph(f'<b>Subtotal_A&nbsp;&nbsp;&nbsp;{fmt_soles(subtotal_a)}</b>', style_right_bold),
    ])

    t1_tbl = Table(t1_rows, colWidths=t1_cols)
    n_data_rows_1 = len(t1_rows)
    t1_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 2), (-1, n_data_rows_1-3), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, n_data_rows_1-1), (-1, n_data_rows_1-1), LIGHT_GRAY),
        ('SPAN', (0, n_data_rows_1-1), (4, n_data_rows_1-1)),
        ('SPAN', (5, n_data_rows_1-1), (5, n_data_rows_1-1)),
    ]
    t1_tbl.setStyle(TableStyle(t1_style))
    story.append(t1_tbl)
    story.append(Spacer(1, 1.5 * mm))

    # ---- TABLA 2: Mano de Obra ---
    t2_cols = [col_item, col_cod, col_desc, col_unid, col_cant, col_pu, col_tp]

    t2_header_sub = [Paragraph('<b>2. Mano de Obra</b>', style_section), '', '', '', '', '', '']
    t2_col_header = [
        Paragraph('<b>Item</b>', style_bold),
        Paragraph('<b>Cod.</b>', style_bold),
        Paragraph('<b>Descripción</b>', style_bold),
        Paragraph('<b>Unid</b>', style_bold),
        Paragraph('<b>Cant</b>', style_bold),
        Paragraph('<b>Precio unid.</b>', style_bold),
        Paragraph('<b>Total P.</b>', style_bold),
    ]

    t2_rows = [t2_header_sub, t2_col_header]
    MAX_ROWS_2 = max(len(mano_obra), 2)
    for i in range(MAX_ROWS_2):
        if i < len(mano_obra):
            m = mano_obra[i]
            row = [
                Paragraph(safe_str(m.get('item', i+1)), style_normal),
                Paragraph(safe_str(m.get('cod', 'SC')), style_normal),
                Paragraph(safe_str(m.get('descripcion', '')), style_normal),
                Paragraph(safe_str(m.get('unid', '')), style_normal),
                Paragraph(safe_str(m.get('cant', '')), style_normal),
                Paragraph(fmt_soles(m.get('precio_unid', '')), style_right),
                Paragraph(fmt_soles(m.get('total_p', '')), style_right),
            ]
        else:
            row = ['', '', '', '', '', '', '']
        t2_rows.append(row)

    t2_rows.append([
        Paragraph('<b>Total</b>', style_bold), '', '', '', '', '',
        Paragraph(f'<b>Subtotal_B&nbsp;&nbsp;&nbsp;{fmt_soles(subtotal_b)}</b>', style_right_bold),
    ])

    t2_tbl = Table(t2_rows, colWidths=t2_cols)
    n_data_rows_2 = len(t2_rows)
    t2_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 2), (-1, n_data_rows_2-2), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, n_data_rows_2-1), (-1, n_data_rows_2-1), LIGHT_GRAY),
        ('SPAN', (0, n_data_rows_2-1), (5, n_data_rows_2-1)),
    ]
    t2_tbl.setStyle(TableStyle(t2_style))
    story.append(t2_tbl)
    story.append(Spacer(1, 2 * mm))

    # ---- CONDICIONES COMERCIALES + TOTAL FINAL ---
    try:
        total_val = f'{total_ab:,.2f}'
    except Exception:
        total_val = '0.00'

    cond_col_left = W * 0.50
    cond_col_mid = W * 0.25
    cond_col_soles = W * 0.07
    cond_col_monto = W * 0.18

    style_cond_hdr = ParagraphStyle('condh', fontName='Helvetica-Bold', fontSize=7, leading=9)
    style_cond_body = ParagraphStyle('condb', fontName='Helvetica', fontSize=7, leading=10)
    style_total_label = ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER)
    style_soles = ParagraphStyle('sol', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER)
    style_monto = ParagraphStyle('mnt', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_RIGHT)

    cond_lines = 'Moneda Nacional soles (S/)<br/>Pagos Según contrato<br/>No incluye IGV'
    cond_data = [
        [
            Paragraph('<b>Condiciones Comerciales</b>', style_cond_hdr),
            '', '', ''
        ],
        [
            Paragraph(cond_lines, style_cond_body),
            Paragraph('<b>Total Cotización (A+B)</b>', style_total_label),
            Paragraph('<b>S/</b>', style_soles),
            Paragraph(f'<b>{total_val}</b>', style_monto),
        ],
    ]
    cond_tbl = Table(cond_data, colWidths=[cond_col_left, cond_col_mid, cond_col_soles, cond_col_monto])
    cond_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_GRAY),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (0, 1), WHITE),
        ('BACKGROUND', (1, 1), (3, 1), LIGHT_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 1), (3, 1), 'RIGHT'),
    ]))
    story.append(cond_tbl)

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _generar_pdf_cotizacion_cobra(numero, site, supervisor, objetivo, ticket, elaborado_por, items, fecha=None):
    """
    Genera el PDF de cotizacion FLM con el formato Cobra:
    cabecera (FECHA/EMPRESA/DIRIGIDO A/SITE/N COTIZACION/OBJETIVO + RESPONSABLE/
    ELABORADO POR/SUPERVISOR/TICKET), tabla unica de items con FEE y secciones
    fijas de cierre.
    `fecha`: datetime o string del campo FECHA del registro. Si no se puede
    interpretar, se usa la fecha actual (comportamiento anterior).
    """
    from services.identidades import nombre_usuario
    elaborado_por = nombre_usuario(elaborado_por)
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    PAGE_W, PAGE_H = landscape(A4)
    M = 8 * mm

    NAVY = colors.HexColor('#1F4E79')
    STEEL = colors.HexColor('#2E75B6')
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor('#F2F2F2')
    MID_GRAY = colors.HexColor('#BFBFBF')
    YELLOW = colors.HexColor('#FFF2CC')
    DARK = colors.HexColor('#1a1a1a')

    def safe_str(v):
        return str(v) if v is not None else ''

    def fmt_soles(v):
        try:
            return f'S/ {float(v):,.2f}'
        except Exception:
            return 'S/ 0.00'

    def fmt_num(v):
        try:
            f = float(v)
            return ('%g' % f) if f == int(f) else f'{f:,.2f}'
        except Exception:
            return ''

    # ---- Estilos ----
    st_norm = ParagraphStyle('n', fontName='Helvetica', fontSize=8, leading=10)
    st_bold = ParagraphStyle('b', fontName='Helvetica-Bold', fontSize=8, leading=10)
    st_hdr_w = ParagraphStyle('hw', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=WHITE)
    st_sec = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=DARK)
    st_cell_c = ParagraphStyle('cc', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_CENTER)
    st_cell_r = ParagraphStyle('cr', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=M, rightMargin=M,
                            topMargin=M, bottomMargin=M)
    W = PAGE_W - 2 * M
    story = []

    # ---- LOGO + Supplier name and RUC No ----
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'cobra-logo.png')
    logo_cell = []
    if os.path.exists(logo_path):
        logo_cell.append(RLImage(logo_path, width=42 * mm, height=20 * mm))
    else:
        logo_cell.append(Paragraph('<b>cobra</b>', ParagraphStyle(
            'lg', fontName='Helvetica-Bold', fontSize=22, leading=24, textColor=NAVY)))
    logo_cell.append(Paragraph('COBRA PERU S.A.C. — RUC 20253881438', ParagraphStyle(
        'ruc', fontName='Helvetica', fontSize=7, leading=9, textColor=colors.HexColor('#333333'))))

    fecha_dt = _parse_fecha_registro(fecha) or ahora_peru()
    fecha_str = _fecha_larga_es(fecha_dt)
    num_para = Paragraph(f'<b>N° COTIZACIÓN :&nbsp;&nbsp;&nbsp;&nbsp;{safe_str(numero)}</b>',
                         ParagraphStyle('np', fontName='Helvetica-Bold', fontSize=12, leading=15))
    head_tbl = Table([[logo_cell, num_para]], colWidths=[W * 0.45, W * 0.55])
    head_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(head_tbl)
    story.append(Spacer(1, 2 * mm))

    # ---- CABECERA DE DATOS (4 columnas) ----
    c1, c2, c3, c4 = W * 0.14, W * 0.36, W * 0.14, W * 0.36

    def row_lbl(lbl, val, lbl2='', val2=''):
        return [
            Paragraph(f'<b>{lbl}</b>', st_bold),
            Paragraph(safe_str(val), st_norm),
            Paragraph(f'<b>{lbl2}</b>', st_bold) if lbl2 else '',
            Paragraph(safe_str(val2), st_norm) if val2 else '',
        ]

    hdr_data = [
        row_lbl('FECHA:', fecha_str),
        row_lbl('EMPRESA:', 'Cobra Perú'),
        row_lbl('DIRIGIDO A :', 'Huawei del Perú', 'RESPONSABLE', 'Juan Balarezo'),
        row_lbl('SITE:', site, 'ELABORADO POR', elaborado_por),
        row_lbl('N° COTIZACIÓN :', numero, 'SUPERVISOR', supervisor),
        row_lbl('OBJETIVO:', objetivo, 'TICKET', ticket),
    ]
    hdr_tbl = Table(hdr_data, colWidths=[c1, c2, c3, c4])
    hdr_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, MID_GRAY),
        ('BACKGROUND', (0, 0), (0, -1), LIGHT_GRAY),
        ('BACKGROUND', (2, 0), (2, -1), LIGHT_GRAY),
        # N° COTIZACION resaltado en amarillo
        ('BACKGROUND', (0, 4), (1, 4), YELLOW),
        ('SPAN', (1, 0), (3, 0)),   # FECHA valor ancho
        ('SPAN', (1, 1), (3, 1)),   # EMPRESA valor ancho
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 3 * mm))

    # ---- TABLA DE ITEMS ---- (ajustado para que REEMBOLSABLE no se corte)
    col_correl = W * 0.065
    col_tipo = W * 0.11
    col_texto = W * 0.26
    col_und = W * 0.055
    col_cant = W * 0.065
    col_vu = W * 0.10
    col_fee = W * 0.06
    col_vt = W * 0.115
    col_coment = W * 0.17
    it_cols = [col_correl, col_tipo, col_texto, col_und, col_cant, col_vu, col_fee, col_vt, col_coment]

    it_header = [
        Paragraph('<b>CORRELATIVO</b>', st_hdr_w),
        Paragraph('<b>TIPO</b>', st_hdr_w),
        Paragraph('<b>TEXTO EXPLICATIVO</b>', st_hdr_w),
        Paragraph('<b>UND</b>', st_hdr_w),
        Paragraph('<b>CANTIDAD</b>', st_hdr_w),
        Paragraph('<b>VALOR UNITARIO</b>', st_hdr_w),
        Paragraph('<b>FEE %</b>', st_hdr_w),
        Paragraph('<b>VALOR TOTAL</b>', st_hdr_w),
        Paragraph('<b>COMENTARIOS</b>', st_hdr_w),
    ]

    it_rows = [it_header]
    items_ok = []
    for i, it in enumerate(items or []):
        try:
            cant = float(str(it.get('cantidad', '') or 0).replace(',', '.'))
        except Exception:
            cant = 0.0
        try:
            vu = float(str(it.get('valor_unitario', '') or 0).replace(',', '.'))
        except Exception:
            vu = 0.0
        tipo = str(it.get('tipo', '') or '').strip().upper()
        fee = 5.0 if tipo == 'REEMBOLSABLE' else 0.0
        vt = cant * vu * (1 + fee / 100.0)
        items_ok.append(vt)
        it_rows.append([
            Paragraph(str(i + 1), st_cell_c),
            Paragraph(safe_str(tipo), st_cell_c),
            Paragraph(safe_str(it.get('texto', '')), st_norm),
            Paragraph(safe_str(it.get('und', '')), st_cell_c),
            Paragraph(fmt_num(cant), st_cell_r),
            Paragraph(fmt_soles(vu), st_cell_r),
            Paragraph(f'{fee:g}%', st_cell_c),
            Paragraph(fmt_soles(vt), st_cell_r),
            Paragraph(safe_str(it.get('comentarios', '')), st_norm),
        ])

    total_fee = sum(items_ok)
    it_rows.append([
        '', '', '', '', '', '',
        Paragraph('<b>sub total + FEE</b>', st_bold),
        Paragraph(f'<b>{fmt_soles(total_fee)}</b>', st_cell_r),
        '',
    ])

    n_it = len(it_rows)
    it_tbl = Table(it_rows, colWidths=it_cols, repeatRows=1)
    it_style = [
        ('BACKGROUND', (0, 0), (-1, 0), STEEL),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.4, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, max(n_it - 2, 1)), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Fila total resaltada
        ('BACKGROUND', (0, n_it - 1), (-1, n_it - 1), YELLOW),
        ('SPAN', (0, n_it - 1), (5, n_it - 1)),
        ('ALIGN', (6, n_it - 1), (7, n_it - 1), 'RIGHT'),
    ]
    if not items_ok:
        it_style.append(('SPAN', (0, 1), (-1, 1)))
        it_rows.append([Paragraph('Sin items registrados.', st_norm), '', '', '', '', '', '', '', ''])
    it_tbl.setStyle(TableStyle(it_style))
    story.append(it_tbl)
    story.append(Spacer(1, 4 * mm))

    # ---- SECCIONES FIJAS DE CIERRE ----
    secciones_cierre = {
        'TIEMPO DE ENTREGA': '',
        'LUGAR DE ENTREGA': 'En la puerta del site',
        'VALIDEZ DE LA OFERTA': '2 días calendario',
        'CONDICIONES GENERALES': ''
    }
    for titulo, contenido in secciones_cierre.items():
        sec_tbl = Table([[Paragraph(f'<b>{titulo}</b>', st_sec)]], colWidths=[W])
        sec_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, MID_GRAY),
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(sec_tbl)
        if contenido:
            body_tbl = Table([[Paragraph(contenido, st_norm)]], colWidths=[W])
            body_tbl.setStyle(TableStyle([
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(body_tbl)
        story.append(Spacer(1, 1.5 * mm))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _obtener_registro_cotizacion():
    """Valida proyecto actual = Cotizaciones y devuelve el registro por key."""
    data = request.json or {}
    key_val = str(data.get('key', '')).strip()
    pid = session.get('current_proyecto_id')
    proy_obj = db.session.get(Proyecto, pid)
    if not key_val:
        return None, None, ({'error': 'Falta la clave del registro'}, 400)
    if not proy_obj or (proy_obj.nombre or '').strip().lower() != 'cotizaciones':
        return None, None, ({'error': 'Proyecto inválido'}, 400)
    rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=key_val).first()
    if not rec:
        return None, None, ({'error': 'Cotización no encontrada'}, 404)
    return rec, proy_obj, None


def _cotizacion_registro_pdf_response(rec):
    """Construye el PDF Cobra desde un registro del módulo Cotizaciones.
    Solo si la cotización ya fue GENERADA (bloqueo respetado en todas las vías).
    Si NUMERO WO está vacío, muestra CM-PENDIENTE como en Combustible."""
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    if str(d.get('GENERADA', '') or '') != '1':
        return jsonify({'error': 'La cotización aún no ha sido generada. Usa "Generar Cotización" primero.'}), 400
    try:
        items = json.loads(d.get('ITEMS_JSON') or '[]')
    except Exception:
        items = []
    numero = str(d.get('N° COTIZACION', '') or '')
    # NUMERO WO → CM-PENDIENTE si está vacío, igual que Combustible
    numero_wo = str(d.get('NUMERO WO', '') or '').strip()
    ticket_raw = str(d.get('TICKET', '') or '').strip()
    # Para el PDF, el campo TICKET muestra el NUMERO WO asociado o CM-PENDIENTE
    pdf_ticket = numero_wo if numero_wo else "CM-PENDIENTE"
    pdf_bytes = _generar_pdf_cotizacion_cobra(
        numero=numero,
        site=str(d.get('SITE', '') or d.get('NOMBRE SITE', '') or ''),
        supervisor=str(d.get('SUPERVISOR', '') or ''),
        objetivo=str(d.get('OBJETIVO', '') or ''),
        ticket=pdf_ticket,
        elaborado_por=str(d.get('GESTOR', '') or audit_user()),
        items=items,
        # FECHA registrada de la cotización (no la fecha de descarga)
        fecha=d.get('FECHA')
    )
    from flask import make_response
    resp = make_response(pdf_bytes)
    safe_num = numero.replace('/', '-').replace(' ', '_') or 'cotizacion'
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Cotizacion_{safe_num}.pdf'
    return resp
