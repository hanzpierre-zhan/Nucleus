"""Reporte fotográfico XLSX desde la plantilla entregada, sin tocar la fuente."""
import io
import math
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
        result+=(dimension.width if dimension else sheet.sheet_format.defaultColWidth or 8.43)*7+5
    return int(result)

def picture(sheet,content,col,row,box_width,box_height,offset_y=4):
    with Image.open(io.BytesIO(content)) as original:
        image=ImageOps.exif_transpose(original).convert('RGB')
        scale=min((box_width-8)/image.width,(box_height-8)/image.height)
        target_w=max(1,int(image.width*scale));target_h=max(1,int(image.height*scale))
        # Excel guarda el original; el ancla define el tamaño de presentación.
        stream=io.BytesIO();image.save(stream,format='JPEG',quality=90);stream.seek(0)
    drawing=ExcelImage(stream)
    drawing.anchor=OneCellAnchor(_from=AnchorMarker(col=col-1,row=row-1,
        colOff=pixels_to_EMU(max(4,int((box_width-target_w)/2))),
        rowOff=pixels_to_EMU(offset_y+max(0,int((box_height-target_h)/2)))),
        ext=XDRPositiveSize2D(pixels_to_EMU(target_w),pixels_to_EMU(target_h)))
    sheet.add_image(drawing)

def collage(contents):
    """Hasta dos fotos ordenadas verticalmente, completas y sin recortar."""
    if len(contents)==1:return contents[0]
    canvas=Image.new('RGB',(1000,1500),'white')
    for index,content in enumerate(contents):
        with Image.open(io.BytesIO(content)) as raw:
            image=ImageOps.contain(ImageOps.exif_transpose(raw).convert('RGB'),(980,730))
            canvas.paste(image,((1000-image.width)//2,index*750+(750-image.height)//2))
    stream=io.BytesIO();canvas.save(stream,'JPEG',quality=92)
    return stream.getvalue()

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
            entries[path]=ET.tostring(sheet,encoding='utf-8',xml_declaration=True)
            path=f'xl/worksheets/_rels/sheet{sheet_id}.xml.rels'
            relationships=ET.fromstring(entries[path]) if path in entries else ET.Element('{'+package+'}Relationships')
            ET.SubElement(relationships,'{'+package+'}Relationship',{'Id':'nucleusHeader','Type':rel+'/vmlDrawing','Target':'../drawings/'+name})
            entries[path]=ET.tostring(relationships,encoding='utf-8',xml_declaration=True)
        content_types=ET.fromstring(entries['[Content_Types].xml'])
        if not any(n.get('Extension')=='vml' for n in content_types):
            ET.SubElement(content_types,'{'+types+'}Default',{'Extension':'vml','ContentType':'application/vnd.openxmlformats-officedocument.vmlDrawing'})
        entries['[Content_Types].xml']=ET.tostring(content_types,encoding='utf-8',xml_declaration=True)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in entries.items():archive.writestr(name,content)
    output.seek(0)
    return output

def generar(datos,manual,evidencia,wo,read_photo,report_date):
    items=items_cotizacion(datos)
    if not items:raise ValueError('La cotización no tiene ítems para generar el expediente.')
    book=load_workbook(TEMPLATE)
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
    fixed={'E3':'COBRA PERU S.A.C.','E4':'20253881438','E5':'Av. Argentina 1295, Cercado de Lima',
           'K3':'Hector Pujada' if 'ENTEL' in client else 'Dennis Unton',
           'K4':'Hector Pujada' if 'ENTEL' in client else 'Dennis Unton',
           'K5':manual.get('work_responsible'),'E6':evidencia.get('INICIO EJECUCION'),
           'K6':evidencia.get('FIN EJECUCION'),
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
        picture(general,read_photo(manual['location_picture']),2,13,width(general,2,13),300,offset_y=28)
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
        pages=max(1,max(math.ceil(len(v)/2) for v in photos.values()))
        for page in range(pages):
            for (offset,col),source in block.items():
                target=parts.cell(start+offset,col);target._style=copy(source._style)
                target.alignment=copy(source.alignment)
                if source.value is not None and col in (2,6,10):target.value=source.value
            for lo,col,hi,last in merges:parts.merge_cells(start_row=start+lo,start_column=col,end_row=start+hi,end_column=last)
            for offset,height in heights.items():
                if height:parts.row_dimensions[start+offset].height=height
            if page:parts.cell(start,2,'Partida | LPU · continuación '+str(page+1))
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
                batch=photos[phase][page*2:page*2+2]
                if batch:
                    picture(parts,collage([read_photo(url) for url in batch]),col,start+6,width(parts,col,col+3),258)
            for offset,key in ((2,'description_es'),(3,'description_en'),(7,'remarks')):
                value=fields.get(key) or (item['texto'] if offset==2 else fields.get('activity','') if offset==7 else '')
                parts.row_dimensions[start+offset].height=max(parts.row_dimensions[start+offset].height or 15,
                    min(409,14*max(1,math.ceil(len(value)/85))))
            start+=9
            parts.row_breaks.append(Break(id=start-1))
    parts.print_area=f'A1:N{start-1}'
    parts.print_title_rows='1:7'
    for sheet in (cover,general,details,parts):
        sheet.sheet_properties.pageSetUpPr.fitToPage=True
        sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0 if sheet==parts else 1
        sheet.sheet_view.showGridLines=False
    stream=io.BytesIO();book.save(stream);stream.seek(0)
    return conservar_logos_encabezado(stream)
