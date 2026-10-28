"""Reporte fotográfico XLSX desde la plantilla entregada, sin tocar la fuente."""
import io
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from copy import copy
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.pagebreak import Break
from PIL import Image, ImageOps
from services.cotizacion_ficha import items_cotizacion

TEMPLATE=Path(__file__).resolve().parent.parent/'data/plantillas/reporte_fotografico.xlsx'
PHASES=('before','during','after')

def xml_bytes(element):
    """Mantener el namespace raíz por defecto, como lo escribe Excel."""
    text=ET.tostring(element,encoding='unicode')
    prefix=re.match(r'<([^: >]+):',text)
    if prefix:
        name=prefix.group(1)
        text=text.replace('<'+name+':','<').replace('</'+name+':','</').replace('xmlns:'+name+'=','xmlns=')
    return text.encode('utf-8')

def texto(sheet,cell,value):
    target=sheet[cell]
    target.value=str(value or '')
    # El texto manual nunca se interpreta como una fórmula de Excel.
    target.data_type='s'
    target.number_format='@'
    alignment=copy(target.alignment);alignment.wrap_text=True;alignment.vertical='center'
    target.alignment=alignment

def width(sheet,start,end):
    # Excel aplica el ancho de una dimensión agrupada a todas sus columnas.
    result=0
    for col in range(start,end+1):
        dimension=next((d for d in sheet.column_dimensions.values() if d.min<=col<=d.max),None)
        result+=int((dimension.width if dimension else sheet.sheet_format.defaultColWidth or 8.43)*7+0.5)+5
    return int(result)

def picture(sheet,content,col,row,box_width,box_height,offset_y=0,offset_x=0):
    with Image.open(io.BytesIO(content)) as original:
        image=ImageOps.exif_transpose(original).convert('RGB')
        padding=min(4,box_width/10,box_height/10)
        scale=min((box_width-2*padding)/image.width,(box_height-2*padding)/image.height)
        target_w=max(1,int(image.width*scale));target_h=max(1,int(image.height*scale))
        # Excel guarda el original; el ancla define el tamaño de presentación.
        stream=io.BytesIO();image.save(stream,format='JPEG',quality=90);stream.seek(0)
    drawing=ExcelImage(stream)
    x=int(offset_x+max(padding,(box_width-target_w)/2))
    y=int(offset_y+max(padding,(box_height-target_h)/2))
    # Excel puede reajustar offsets mayores que una columna: convertirlos a
    # columna + offset local para evitar que fotos distintas se superpongan.
    while x>=width(sheet,col,col):
        x-=width(sheet,col,col);col+=1
    while y>=int((sheet.row_dimensions[row].height or sheet.sheet_format.defaultRowHeight)*96/72):
        y-=int((sheet.row_dimensions[row].height or sheet.sheet_format.defaultRowHeight)*96/72);row+=1
    drawing.anchor=OneCellAnchor(_from=AnchorMarker(col=col-1,row=row-1,
        colOff=pixels_to_EMU(x),rowOff=pixels_to_EMU(y)),
        ext=XDRPositiveSize2D(pixels_to_EMU(target_w),pixels_to_EMU(target_h)))
    sheet.add_image(drawing)

def fotos_independientes(sheet,contents,col,row,box_width,box_height):
    """Distribuir por filas según cantidad y orientación, sin unir imágenes."""
    if not contents:return
    ratios=[]
    for content in contents:
        with Image.open(io.BytesIO(content)) as source:
            image=ImageOps.exif_transpose(source)
            ratios.append(image.width/image.height)
    for x,y,w,h,content in distribuir_fotos(contents,ratios,box_width,box_height):
        picture(sheet,content,col,row,w,h,offset_x=x,offset_y=y)

def distribuir_fotos(contents,ratios,box_width,box_height):
    """Filas de altura variable: verticales juntas y horizontales a su ancho."""
    count=len(contents);gap=5
    candidates=set()
    if count<=10:
        for mask in range(1<<(count-1)):
            cuts=tuple(i+1 for i in range(count-1) if mask&(1<<i))+(count,)
            candidates.add(cuts)
    else:
        for group in range(1,count+1):candidates.add(tuple(range(group,count,group))+(count,))
        candidates.update((split,count) for split in range(1,count))
        kind=lambda r:0 if r<0.85 else 2 if r>1.25 else 1
        candidates.add(tuple(i for i in range(1,count) if kind(ratios[i])!=kind(ratios[i-1]))+(count,))
    def layout(cuts):
        rows=[];start=0
        for stop in cuts:
            available=box_width-gap*(stop-start+1)
            if available<=0:return None
            rows.append((start,stop,available/sum(ratios[start:stop])))
            start=stop
        available_height=box_height-gap*(len(rows)+1)
        if available_height<=0:return None
        lo=0;hi=available_height
        for _ in range(35):
            cap=(lo+hi)/2
            if sum(min(h,cap) for _,_,h in rows)>available_height:hi=cap
            else:lo=cap
        rectangles=[];y=gap
        for start,stop,natural in rows:
            h=min(natural,lo)
            used=sum(ratios[start:stop])*h+gap*(stop-start-1)
            x=(box_width-used)/2
            for index in range(start,stop):
                w=ratios[index]*h
                rectangles.append((x,y,w,h,contents[index]))
                x+=w+gap
            y+=h+gap
        return rectangles
    best=None;best_score=None
    for cuts in sorted(candidates):
        rectangles=layout(cuts)
        if not rectangles:continue
        areas=[max(0,w-8)*max(0,h-8) for _,_,w,h,_ in rectangles]
        score=(sum(areas),min(areas),-len(cuts))
        if best_score is None or score>best_score:best,best_score=rectangles,score
    return best or []

def conservar_logos_encabezado(stream):
    """Los dibujos VML de encabezado no son conservados por openpyxl."""
    main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    package='http://schemas.openxmlformats.org/package/2006/relationships'
    types='http://schemas.openxmlformats.org/package/2006/content-types'
    with zipfile.ZipFile(stream) as current,zipfile.ZipFile(TEMPLATE) as template:
        entries={name:current.read(name) for name in current.namelist()}
        entries['xl/media/nucleus_header.png']=template.read('xl/media/image3.png')
        for sheet_id,vml_id in ((2,1),(3,2),(4,3)):
            name=f'nucleus_header_{vml_id}.vml'
            entries['xl/drawings/'+name]=template.read(f'xl/drawings/vmlDrawing{vml_id}.vml')
            entries['xl/drawings/_rels/'+name+'.rels']=template.read(f'xl/drawings/_rels/vmlDrawing{vml_id}.vml.rels').replace(b'../media/image3.png',b'../media/nucleus_header.png')
            path=f'xl/worksheets/sheet{sheet_id}.xml'
            sheet=ET.fromstring(entries[path])
            ET.SubElement(sheet,'{'+main+'}legacyDrawingHF',{'{'+rel+'}id':'nucleusHeader'})
            entries[path]=xml_bytes(sheet)
            path=f'xl/worksheets/_rels/sheet{sheet_id}.xml.rels'
            relationships=ET.fromstring(entries[path]) if path in entries else ET.Element('{'+package+'}Relationships')
            ET.SubElement(relationships,'{'+package+'}Relationship',{'Id':'nucleusHeader','Type':rel+'/vmlDrawing','Target':'../drawings/'+name})
            entries[path]=xml_bytes(relationships)
        content_types=ET.fromstring(entries['[Content_Types].xml'])
        if not any(n.get('Extension')=='vml' for n in content_types):
            ET.SubElement(content_types,'{'+types+'}Default',{'Extension':'vml','ContentType':'application/vnd.openxmlformats-officedocument.vmlDrawing'})
        entries['[Content_Types].xml']=xml_bytes(content_types)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in entries.items():archive.writestr(name,content)
    output.seek(0)
    return output

def generar(datos,manual,evidencia,wo,read_photo,report_date):
    items=items_cotizacion(datos)
    if not items:raise ValueError('La cotización no tiene ítems para generar el expediente.')
    book=load_workbook(TEMPLATE)
    # La métrica de columnas de Aptos Narrow varía al abrir sin esa fuente.
    # Normalizar solo el estilo base mantiene las anclas dentro de las celdas;
    # los estilos explícitos de textos y encabezados de la plantilla se conservan.
    normal_font=copy(book._named_styles['Normal'].font)
    normal_font.name='Calibri';normal_font.sz=11
    book._named_styles['Normal'].font=normal_font
    cover,general,details,parts=(book[n] for n in ('Carátula','Información general','Detalles','Partidas'))
    cover['E43']=report_date.date();cover['E43'].number_format='dd/mm/yyyy'
    for cell,value in {'E44':manual.get('ajb_ejb'),'K44':manual.get('expense'),
                       'E45':datos.get('N° COTIZACION') or datos.get('_key'),
                       'K45':wo or 'NA'}.items():texto(cover,cell,value)
    # El logo COBRA está guardado como imagen de celda enriquecida (#VALUE!).
    # Reinsertarlo como dibujo estándar para que funcione en Excel y visores.
    cover['F25']=None
    with zipfile.ZipFile(TEMPLATE) as archive:
        logo=archive.read('xl/media/image1.png')
    picture(cover,logo,6,25,width(cover,6,9),180)
    client=str(datos.get('CLIENTE') or '').upper()
    # Las fechas de ejecución mandan desde la evidencia del WO; si el WO no las
    # tiene se recuperan de la cotización para que el reporte nunca las omita.
    def fecha(campo, obra):
        valor=evidencia.get(campo) or datos.get(campo) or datos.get(obra)
        valor=str(valor or '').strip()
        return valor+' 00:00:00' if len(valor)==10 else valor
    fixed={'E3':'COBRA PERU S.A.C.','E4':'20253881438','E5':'Av. Argentina 1295, Cercado de Lima',
           'K3':'Hector Pujada' if 'ENTEL' in client else 'Dennis Unton',
           'K4':'Hector Pujada' if 'ENTEL' in client else 'Dennis Unton',
           'K5':manual.get('work_responsible'),
           'E6':fecha('INICIO EJECUCION','FECHA INICIO OBRA'),
           'K6':fecha('FIN EJECUCION','FECHA FIN OBRA'),
           'E9':manual.get('site_name'),'K9':manual.get('site_id'),'E10':manual.get('site_address'),
           'E11':manual.get('site_type'),'K11':manual.get('district'),'E12':manual.get('province'),
           'K12':manual.get('region')}
    for cell,value in fixed.items():texto(general,cell,value)
    for cell,phase in [('B3','INICIO'),('B6','PROCESO'),('B9','CIERRE')]:
        value=str(evidencia.get('_BITACORA_'+phase) or '')
        texto(details,cell,value)
        details.row_dimensions[details[cell].row].height=max(details.row_dimensions[details[cell].row].height or 0,
            min(409,14*max(1,math.ceil(len(value)/100))))
    if manual.get('location_picture'):
        alignment=copy(general['B13'].alignment);alignment.vertical='top';general['B13'].alignment=alignment
        content=read_photo(manual['location_picture'])
        available_width=width(general,2,13)
        photo_height=(general.row_dimensions[13].height or general.sheet_format.defaultRowHeight)*96/72-28
        picture(general,content,2,13,available_width,photo_height,offset_y=28)
    # Copiar el bloque de ejemplo como diseño; nunca sus valores de demostración.
    block={(r-9,c):copy(parts.cell(r,c)) for r in range(9,17) for c in range(1,15)}
    merges=[(m.min_row-9,m.min_col,m.max_row-9,m.max_col) for m in parts.merged_cells.ranges if m.min_row>=9 and m.max_row<=16]
    heights={r-9:parts.row_dimensions[r].height for r in range(9,17)}
    for merged in list(parts.merged_cells.ranges):
        if merged.min_row>=9:parts.unmerge_cells(str(merged))
    parts.delete_rows(9,parts.max_row)
    parts.row_breaks.brk=[]
    start=9
    for number,item in enumerate(items,1):
        fields=manual.get('item_details',{}).get(item['key'],{})
        photos={phase:[] for phase in PHASES}
        for photo in manual.get('item_photos',{}).get(item['key'],[]):
            if isinstance(photo,dict) and photo.get('url'):
                photos[photo.get('phase','before') if photo.get('phase','before') in PHASES else 'before'].append(photo['url'])
        for (offset,col),source in block.items():
            target=parts.cell(start+offset,col);target._style=copy(source._style)
            target.alignment=copy(source.alignment)
            if source.value is not None and col in (2,6,10):target.value=source.value
        for lo,col,hi,last in merges:parts.merge_cells(start_row=start+lo,start_column=col,end_row=start+hi,end_column=last)
        for offset,height in heights.items():
            if height:parts.row_dimensions[start+offset].height=height
        parts.cell(start,13,number)
        for cell,value in {(start+1,4):fields.get('unique_code') or '8828126757',
                           (start+1,12):fields.get('unit') or item.get('und'),
                           (start+2,5):fields.get('description_es') or item['texto'],
                           (start+3,5):fields.get('description_en'),
                           (start+4,5):item['texto'],
                           (start+7,5):fields.get('remarks') or fields.get('activity') or ''}.items():
            texto(parts,parts.cell(*cell).coordinate,value)
        parts.cell(start+1,8,1)
        for phase,col in zip(PHASES,(2,6,10)):
            fotos_independientes(parts,[read_photo(url) for url in photos[phase]],col,start+6,
                                  width(parts,col,col+3),heights[6]*96/72)
        for offset,key in ((2,'description_es'),(3,'description_en'),(7,'remarks')):
            value=fields.get(key) or (item['texto'] if offset==2 else fields.get('activity','') if offset==7 else '')
            parts.row_dimensions[start+offset].height=max(parts.row_dimensions[start+offset].height or 15,
                min(409,14*max(1,math.ceil(len(value)/85))))
        start+=9
        if number<len(items):parts.row_breaks.append(Break(id=start-1))
    parts.print_area=f'A1:N{start-1}'
    parts.print_title_rows='1:7'
    parts.sheet_properties.pageSetUpPr.autoPageBreaks=False
    for sheet in (cover,general,details,parts):
        sheet.sheet_properties.pageSetUpPr.fitToPage=True
        sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0 if sheet==parts else 1
        sheet.sheet_view.showGridLines=False
    stream=io.BytesIO();book.save(stream);stream.seek(0)
    return conservar_logos_encabezado(stream)
