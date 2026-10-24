import io,json,zipfile
from datetime import datetime
import pytest
from openpyxl import load_workbook
from PIL import Image
from db import db
from models import NucleusData
from test_sustento_por_wo import caso,foto
from services.cotizacion_expediente import generar
from services.cotizacion_ficha import items_cotizacion

@pytest.mark.parametrize('client,manager',[('CLARO','Dennis Unton'),('INTEGRATEL','Dennis Unton'),('ENTEL','Hector Pujada')])
def test_plantilla_por_cliente_y_fotos_completas_sin_formulas_rotas(client,manager,tmp_path):
    datos={'CLIENTE':client,'SUPERVISOR':'No usar este valor','N° COTIZACION':'HW-2026-000345',
           'ITEMS_JSON':json.dumps([{'texto':'Compra de cable','und':'UND','cantidad':18},{'texto':'Instalación','und':'m','cantidad':5}])}
    items=items_cotizacion(datos)
    manual={'work_responsible':'Gestor Responsable','ajb_ejb':'AJB-1','expense':'EXP-2',
            'site_name':'Sitio de prueba','site_id':'00123','site_address':'Dirección del sitio','site_type':'Outdoor',
            'district':'Distrito','province':'Provincia','region':'Región','location_picture':'ubicacion',
            'item_details':{i['key']:{'unique_code':'8828126757','unit':'EACH','description_es':'Partida ES',
                            'description_en':'LPU EN','remarks':'Actividad realizada '+str(n)} for n,i in enumerate(items,1)},
            'item_photos':{items[0]['key']:[{'url':'foto-'+str(n),'phase':'before'} for n in range(5)]+
                                         [{'url':'durante','phase':'during'},{'url':'despues','phase':'after'}]}}
    photo=io.BytesIO();Image.new('RGB',(800,400),'navy').save(photo,'PNG')
    loaded=[]
    def read(url):loaded.append(url);return photo.getvalue()
    output=generar(datos,manual,{'_BITACORA_INICIO':'Antecedentes','_BITACORA_PROCESO':'Objetivos',
        '_BITACORA_CIERRE':'Trabajo realizado','INICIO EJECUCION':'2026-10-01 08:30','FIN EJECUCION':'2026-10-02 18:00'},'WO-1',read,datetime(2026,10,23,12,0))
    book=load_workbook(output)
    assert book['Carátula']['E43'].value.date().isoformat()=='2026-10-23'
    assert book['Carátula']['E45'].value=='HW-2026-000345'
    assert book['Carátula']['E44'].value=='AJB-1'
    general=book['Información general']
    assert general['E3'].value=='COBRA PERU S.A.C.'
    assert general['E4'].value=='20253881438'
    assert general['K3'].value==general['K4'].value==manager
    assert general['K5'].value=='Gestor Responsable'
    assert general['E9'].value=='Sitio de prueba' and general['K9'].value=='00123'
    assert book['Detalles']['B3'].value=='Antecedentes'
    assert len(general._images)==1 and len(book['Carátula']._images)==2
    parts=book['Partidas']
    assert [parts.cell(r,13).value for r in (9,18,27,36)]==[1,1,1,2]
    assert [parts.cell(r,8).value for r in (10,19,28,37)]==[1,1,1,1]
    assert parts['E13'].value=='Compra de cable'
    assert parts['E16'].value=='Actividad realizada 1'
    assert loaded==['ubicacion','foto-0','foto-1','durante','despues','foto-2','foto-3','foto-4']
    assert len(parts._images)==5
    for sheet in book:
        for row in sheet:
            assert all(c.data_type not in ('f','e') for c in row),sheet.title
    output.seek(0);(tmp_path/('expediente-'+client+'.xlsx')).write_bytes(output.read())
    output.seek(0)
    with zipfile.ZipFile(output) as archive:
        assert 'xl/media/nucleus_header.png' in archive.namelist()
        assert b'legacyDrawingHF' in archive.read('xl/worksheets/sheet2.xml')

def test_descarga_incluye_fotos_guardadas_y_no_cambia_la_cotizacion(app,auth_client,caso,monkeypatch,tmp_path):
    import blueprints.cotizacion as cot
    monkeypatch.setattr(cot,'evidencia_usa_b2',lambda:False)
    monkeypatch.setattr(cot,'_ubicacion_folder',lambda cid:str(tmp_path/str(cid)))
    with app.app_context():
        row=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(row.data_json)
        d['ITEMS_JSON']=json.dumps([{'texto':'Compra de cable','und':'UND','cantidad':5}]);d['N° COTIZACION']='QA-EXPEDIENTE'
        row.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/'+str(caso['cot']))
    item=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['items'][0]
    upload=auth_client.post('/api/cotizacion/sustento/item-foto',data={'key':'COT-SUST-TEST','wo':'WO-SUST-1','item_key':item['key'],
        'phase':'before','foto':(foto(),'foto.png')})
    assert upload.status_code==200,upload.json
    result=auth_client.get('/api/cotizacion/sustento/expediente',query_string={'key':'COT-SUST-TEST','wo':'WO-SUST-1'})
    assert result.status_code==200,result.data[:300]
    assert 'attachment' in result.headers['Content-Disposition']
    assert len(load_workbook(io.BytesIO(result.data))['Partidas']._images)==1
    assert auth_client.get('/api/cotizacion/sustento/expediente?key=COT-SUST-TEST&wo=OTRA').status_code==400
    assert auth_client.get('/api/cotizacion/sustento/expediente?key=NO-EXISTE&wo=WO-SUST-1').status_code==404
    with app.app_context():
        row=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(row.data_json)
        assert json.loads(d['ITEMS_JSON'])[0]['cantidad']==5
        d['CLIENTE']='PEXT';row.data_json=json.dumps(d);db.session.commit()
    assert auth_client.get('/api/cotizacion/sustento/expediente?key=COT-SUST-TEST&wo=WO-SUST-1').status_code==400

def test_catalogo_responsables_persistente_y_sin_cambiar_opciones_supervisor(app,auth_client,caso):
    auth_client.get('/switch_project/'+str(caso['cot']))
    result=auth_client.patch('/api/cotizacion/sustento/responsables',json={'opciones':['Responsable A','Responsable B','Responsable A']})
    assert result.status_code==200 and result.json['opciones']==['Responsable A','Responsable B']
    assert auth_client.get('/api/cotizacion/sustento/responsables').json['opciones']==result.json['opciones']
    assert auth_client.patch('/api/cotizacion/sustento/responsables',json={'opciones':['']}).status_code==400
    assert app.test_client().get('/api/cotizacion/sustento/expediente').status_code in (302,401)
