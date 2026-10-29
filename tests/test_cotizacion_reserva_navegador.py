from pathlib import Path

import pytest

playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor


@pytest.fixture
def pagina_numeracion():
    with playwright_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as error:
            pytest.skip('Chromium no disponible: ' + str(error))
        page = browser.new_page()
        page.set_content('<select id="cliente"><option>ENTEL</option><option>CLARO</option></select><input id="numero">')
        page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static/js/cotizacion-numeracion.js'))
        yield page
        browser.close()


def test_provisional_se_actualiza_y_manual_no_se_sobrescribe(pagina_numeracion):
    page = pagina_numeracion
    page.evaluate("""() => {
        window.next = 531;
        window.fetch = async () => ({ok:true,json:async()=>({next:window.next,year:2026,month:10})});
        CotizacionNumeracion.configurarCampo(document.querySelector('#numero'),document.querySelector('#cliente'),
            cliente => (cliente==='CLARO'?'CL':'EN')+'-2026-10-');
    }""")
    page.wait_for_function("document.querySelector('#numero').value==='EN-2026-10-000531'")
    assert page.locator('#numero').evaluate('(el)=>el.readOnly')
    page.locator('input[type=checkbox]').check()
    page.locator('#numero').fill('EN-2026-10-000550')
    page.evaluate('window.next=532')
    page.locator('#numero').focus()
    assert page.locator('#numero').input_value() == 'EN-2026-10-000550'
    page.locator('input[type=checkbox]').uncheck()
    page.wait_for_function("document.querySelector('#numero').value==='EN-2026-10-000532'")
    page.select_option('#cliente', label='CLARO')
    page.wait_for_function("document.querySelector('#numero').value==='CL-2026-10-000532'")


@pytest.mark.parametrize('aceptar', [False, True])
def test_manual_ocupado_conserva_datos_y_solo_reenvia_con_aceptacion(pagina_numeracion, aceptar):
    result = pagina_numeracion.evaluate("""async aceptar => {
        const requests=[];
        window.nucleusConfirm=async()=>aceptar;
        window.fetch=async(url,options)=>{
            requests.push(JSON.parse(options.body));
            return requests.length===1 ? {ok:false,status:409,json:async()=>({code:'COTIZACION_NUMERO_NO_DISPONIBLE',suggested:'CL-2026-10-000532'})}
                : {ok:true,status:200,json:async()=>({success:true,key:'CL-2026-10-000533'})};
        };
        const data={CLIENTE:'CLARO',MOTIVO:'Conservar solicitud',ITEMS_JSON:'[{"texto":"Servicio"}]'};
        const result=await CotizacionNumeracion.crear({key:'CL-2026-10-000531',data,numeracion_modo:'manual'});
        return {requests,result,data};
    }""", aceptar)
    assert len(result['requests']) == (2 if aceptar else 1)
    assert all(request['data'] == result['data'] for request in result['requests'])
    if aceptar:
        assert result['requests'][1]['numeracion_modo'] == 'automatico'
        assert result['result']['key'] == 'CL-2026-10-000533'
    else:
        assert result['result'] is None


def test_fallo_de_red_no_repite_un_alta_que_pudo_haberse_guardado(pagina_numeracion):
    result = pagina_numeracion.evaluate("""async () => {
        let calls=0;
        window.fetch=async()=>{calls++;throw Error('Sin conexión');};
        try { await CotizacionNumeracion.crear({data:{MOTIVO:'No perder'}}); }
        catch(error) { return {calls,error:error.message}; }
    }""")
    assert result == {'calls': 1, 'error': 'Sin conexión'}


def test_editor_generar_usa_clave_confirmada_y_no_repite_alta_si_falla_pdf(app, auth_client, servidor):
    from models import Proyecto
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    auth_client.get(f'/switch_project/{pid}')
    cookie = auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as error:
            pytest.skip('Chromium no disponible: ' + str(error))
        try:
            context = browser.new_context()
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors, altas, pdfs = [], [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def alta(route):
                altas.append(route.request.post_data_json)
                route.fulfill(json={'success': True, 'key': 'EN-2026-10-9000300', 'numero': 'EN-2026-10-9000300'})
            def pdf(route):
                pdfs.append(route.request.post_data_json)
                route.fulfill(status=400, json={'error': 'PDF de prueba no generado'})
            page.route('**/api/rows/add', alta)
            page.route('**/api/cotizacion/registro_generar', pdf)
            page.goto(servidor + '/', wait_until='networkidle')
            page.wait_for_function('typeof aniadirRegistroCotizaciones === "function"')
            page.evaluate("""() => {
                cotiEditMode=false;cotiEditKey=null;
                const body=document.querySelector('#mar-fields');body.innerHTML='';
                aniadirRegistroCotizaciones(body);
                document.querySelector('#modal-add-registro').style.display='flex';
                const cliente=body.querySelector('[data-field="CLIENTE"]');cliente.value='ENTEL';
                cliente.dispatchEvent(new Event('change'));
                cotRegRecoger=()=>[{texto:'Servicio',valor_total:'10.00'}];
                guardarModalRegistro('generar');
            }""")
            page.wait_for_function('cotiEditKey === "EN-2026-10-9000300"')
            page.get_by_text('PDF de prueba no generado', exact=True).wait_for()
            assert len(altas) == 1
            assert altas[0]['key'] == ''
            assert altas[0]['numeracion_modo'] == 'automatico'
            assert 'undefined' not in altas[0]['data']
            assert pdfs == [{'key': 'EN-2026-10-9000300'}]
            assert page.evaluate('cotiEditMode') is True
            assert not errors, errors
        finally:
            browser.close()
