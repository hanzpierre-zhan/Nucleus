import os
import re
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CARPETA = os.path.dirname(os.path.abspath(__file__))
# Busca chromedriver junto al script, en una subcarpeta Driver, o en rutas comunes
CANDIDATOS_DRIVER = [
    os.path.join(CARPETA, "chromedriver.exe"),
    os.path.join(CARPETA, "Driver", "chromedriver.exe"),
    r"C:\Python\chromedriver.exe",
    r"C:\Python\Driver\chromedriver.exe",
    r"C:\Onedrive\Python\Driver\chromedriver.exe",
]
CHROME_DRIVER = next((c for c in CANDIDATOS_DRIVER if os.path.exists(c)), CANDIDATOS_DRIVER[0])

URL = "https://300v-mx.teleows.com/dspcas/login?service=https%3A%2F%2F300v-mx.teleows.com%2Fportal%2Fweb%2Frest%2Fsso%2Findex%3Fori_url%3Dhttps%253A%252F%252F300v-mx.teleows.com%252Fportal-web%252Fportal%252Fhomepage.html"
URL_REPORTE = ("https://300v-mx.teleows.com/portal-web/portal/homepage.html"
               "#%2Fcm_checklist%2Fpint%2FConsole%20Report")
URL_BATCH = "https://300v-mx.teleows.com/portal-web/portal/homepage.html#adc.batch_records.export"

USUARIO = "mhuayanab.ofg"
CONTRASENA = "MAE123_LK34*r"

# Nombre estandar del archivo que se espera al final de la descarga
ARCHIVO_PINT = os.path.join(CARPETA, "PINT Checklist.xlsx")


def buscar_en_frames_rec(driver, by, selector, profundidad=0):
    try:
        return driver.find_element(by, selector)
    except Exception:
        pass
    if profundidad > 3:
        return None
    for frame in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(frame)
            el = buscar_en_frames_rec(driver, by, selector, profundidad + 1)
            if el is not None:
                return el
            driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                pass
    return None


def esperar_elemento(driver, by, selector, timeout=120, etiqueta=""):
    inicio = time.time()
    ultimo_aviso = 0
    while time.time() - inicio < timeout:
        driver.switch_to.default_content()
        el = buscar_en_frames_rec(driver, by, selector)
        if el is not None:
            return el
        if time.time() - ultimo_aviso > 15:
            print("  [esperando] %s... (%ds)" % (etiqueta, int(time.time() - inicio)))
            ultimo_aviso = time.time()
        time.sleep(3)
    print("  [TIEMPO AGOTADO] buscando: %s" % etiqueta)
    return None


def esperar_desaparezca_mascara(driver, timeout=90):
    print("  Esperando que termine la carga...")
    inicio = time.time()
    while time.time() - inicio < timeout:
        time.sleep(2)
        driver.switch_to.default_content()
        mascara = buscar_en_frames_rec(
            driver, By.CSS_SELECTOR,
            ".el-loading-mask:not([style*='display: none'])")
        if mascara is None:
            time.sleep(2)
            return True
    print("  [AVISO] La carga tardo demasiado.")
    return False


def escribir_valor(driver, campo, texto):
    try:
        driver.execute_script(
            "var el = arguments[0];"
            "var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
            "setter.call(el, arguments[1]);"
            "el.dispatchEvent(new Event('input', {bubbles: true}));"
            "el.dispatchEvent(new Event('change', {bubbles: true}));",
            campo, texto)
    except Exception:
        pass
    try:
        campo.send_keys(Keys.ENTER)
    except Exception:
        pass
    try:
        campo.send_keys(Keys.TAB)
    except Exception:
        pass


def seleccionar_en_calendario(driver, fecha, es_fecha_hora=False):
    wait = WebDriverWait(driver, 10)
    try:
        panel = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".el-picker-panel")))
    except Exception:
        print("    No se abrio el panel del calendario")
        return False
    try:
        anio_o, mes_o = fecha.year, fecha.month
        for _ in range(13):
            try:
                labels = panel.find_elements(By.CSS_SELECTOR, ".el-date-picker__header-label")
                nums = [int(re.sub(r"\D", "", l.text)) for l in labels if re.sub(r"\D", "", l.text)]
                anio_act, mes_act = nums[0], nums[1]
            except Exception:
                break
            if (anio_act, mes_act) == (anio_o, mes_o):
                break
            if (anio_act, mes_act) < (anio_o, mes_o):
                panel.find_element(By.CSS_SELECTOR, ".el-date-picker__next-btn").click()
            else:
                panel.find_element(By.CSS_SELECTOR, ".el-date-picker__prev-btn").click()
            time.sleep(0.4)

        dia_str = str(fecha.day)
        dia_seleccionado = False
        # Probar varios selectores, del mas especifico al mas generico
        for sel in ["td.available:not(.prev-month):not(.next-month) .cell",
                     "td.available .cell",
                     "td.current:not(.prev-month):not(.next-month) .cell",
                     ".el-date-table td .cell"]:
            celdas = panel.find_elements(By.CSS_SELECTOR, sel)
            for celda in celdas:
                if celda.text.strip() == dia_str:
                    try:
                        driver.execute_script("arguments[0].click();", celda)
                    except Exception:
                        celda.click()
                    dia_seleccionado = True
                    break
            if dia_seleccionado:
                break
        if not dia_seleccionado:
            print("    AVISO: no se encontro el dia %s en el calendario" % dia_str)
            return False
        time.sleep(0.5)

        if es_fecha_hora:
            wrappers = panel.find_elements(By.CSS_SELECTOR, ".el-time-spinner__wrapper")
            if wrappers:
                for wrapper, valor in zip(wrappers, [fecha.hour, fecha.minute, fecha.second]):
                    items = wrapper.find_elements(By.CSS_SELECTOR, ".el-time-spinner__item")
                    for item in items:
                        if item.text.strip() == f"{valor:02d}":
                            item.click()
                            break
                time.sleep(0.5)

        time.sleep(0.5)
        for sel in [".el-picker-panel__footer button", ".el-picker-panel__footer .el-button",
                    "button.el-button--primary", ".el-picker-panel__footer-btn"]:
            try:
                for b in panel.find_elements(By.CSS_SELECTOR, sel):
                    if b.is_displayed():
                        b.click()
                        return True
            except Exception:
                pass
        return True
    except Exception as e:
        print("    Error en calendario:", e)
        return False


def recolectar_inputs(driver, placeholder):
    out = []

    def rec(prof=0):
        try:
            out.extend(driver.find_elements(
                By.CSS_SELECTOR, "input[placeholder='%s']" % placeholder))
        except Exception:
            pass
        if prof >= 3:
            return
        for frame in driver.find_elements(By.TAG_NAME, "iframe"):
            try:
                driver.switch_to.frame(frame)
                rec(prof + 1)
                driver.switch_to.parent_frame()
            except Exception:
                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    pass

    driver.switch_to.default_content()
    rec()
    return out


def buscar_input_inicio_especifico(driver, placeholder):
    """Busca el input de Fecha Inicio (fecha u hora) sin confundirlo con Fecha Fin.
    Usa JS para encontrar el contenedor que tiene 'Fecha Inicio' pero aun no 'Fecha Fin'."""
    try:
        el = driver.execute_script(
            "var ph=arguments[0];"
            "var inputs=Array.from(document.querySelectorAll('input[placeholder=\"'+ph+'\"]'));"
            "if(!inputs.length) return null;"
            "for(var i=0;i<inputs.length;i++){"
            "  var inp=inputs[i];"
            "  var p=inp; var foundInicio=false; var foundFin=false;"
            "  for(var d=0;d<6 && p; d++){"
            "    p=p.parentElement; if(!p) break;"
            "    var txt=(p.innerText||p.textContent||'');"
            "    if(txt.indexOf('Fecha Inicio')!==-1) foundInicio=true;"
            "    if(txt.indexOf('Fecha Fin')!==-1) foundFin=true;"
            "    if(foundInicio && !foundFin){"
            "      var rect=inp.getBoundingClientRect();"
            "      if(rect.width>0) return inp;"
            "    }"
            "    if(foundFin) break;"
            "  }"
            "}"
            "for(var i=0;i<inputs.length;i++){"
            "  var inp=inputs[i];"
            "  var lab=Array.from(document.querySelectorAll('*')).find(e=> (e.textContent||'').trim()==='Fecha Inicio');"
            "  if(lab){ var r1=lab.getBoundingClientRect(); var r2=inp.getBoundingClientRect();"
            "    if(Math.abs(r1.top-r2.top)<80 && r2.left>r1.left && r2.left-r1.left<400) return inp;"
            "  }"
            "}"
            "return null;", placeholder)
        if el is not None:
            try:
                if el.is_displayed():
                    return el
            except Exception:
                return el
    except Exception:
        pass
    return None


def buscar_input_por_etiqueta(driver, etiqueta, placeholder, intento_idx=None):
    # Para Fecha Inicio, usa busqueda especifica que no contamina con Fecha Fin
    if etiqueta == "Fecha Inicio":
        el = buscar_input_inicio_especifico(driver, placeholder)
        if el is not None:
            return el
    xpaths = [
        "//label[normalize-space(.)='%s']/following::input[@placeholder='%s'][1]" % (etiqueta, placeholder),
        "//span[normalize-space(.)='%s']/following::input[@placeholder='%s'][1]" % (etiqueta, placeholder),
        "//div[normalize-space(.)='%s']/following::input[@placeholder='%s'][1]" % (etiqueta, placeholder),
        "//*[contains(normalize-space(.),'%s')]/following::input[@placeholder='%s'][1]" % (etiqueta, placeholder),
    ]
    for xp in xpaths:
        el = esperar_elemento(driver, By.XPATH, xp, timeout=8, etiqueta="%s/%s" % (etiqueta, placeholder))
        if el is not None:
            return el
    if intento_idx is not None:
        inputs = recolectar_inputs(driver, placeholder)
        if intento_idx < len(inputs):
            print("  (%s/%s encontrado por orden, pos %d)" % (etiqueta, placeholder, intento_idx))
            return inputs[intento_idx]
    return None


def seleccionar_hora_panel(driver, hora_dt):
    wait = WebDriverWait(driver, 10)
    try:
        panel = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".el-time-panel, .el-picker-panel")))
    except Exception:
        print("    No se abrio el panel de hora")
        return False
    try:
        wrappers = panel.find_elements(By.CSS_SELECTOR, ".el-time-spinner__wrapper")
        if wrappers:
            for wrapper, valor in zip(wrappers, [hora_dt.hour, hora_dt.minute, hora_dt.second]):
                items = wrapper.find_elements(By.CSS_SELECTOR, ".el-time-spinner__item")
                for item in items:
                    if item.text.strip() == f"{valor:02d}":
                        driver.execute_script("arguments[0].click();", item)
                        break
            time.sleep(0.5)
        for sel in [".el-time-panel__btn.confirm", ".el-picker-panel__footer button",
                    ".el-picker-panel__footer .el-button", "button.el-button--primary"]:
            try:
                for b in panel.find_elements(By.CSS_SELECTOR, sel):
                    if b.is_displayed() and "confirmar" in b.text.lower():
                        driver.execute_script("arguments[0].click();", b)
                        return True
            except Exception:
                pass
        return True
    except Exception as e:
        print("    Error en panel hora:", e)
        return False


def click_icono_almanaque(driver, campo):
    """Hace click en el icono del almanaque del date/time picker (no en el input)."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
        time.sleep(0.3)
    except Exception:
        pass
    try:
        icon = driver.execute_script(
            "var p = arguments[0].parentElement;"
            "if (p) {"
            "  var q = p.querySelector('.el-input__suffix i, .el-input__suffix-inner i, .el-input__icon');"
            "  if (q) return q;"
            "  q = p.querySelector('.el-input__suffix, .el-input__suffix-inner');"
            "  if (q) return q;"
            "}"
            "return null;", campo)
        if icon is not None:
            driver.execute_script("arguments[0].click();", icon)
            time.sleep(0.8)
            return True
    except Exception:
        pass
    # Fallback al click directo en el input
    try:
        driver.execute_script("arguments[0].click();", campo)
        time.sleep(0.8)
        return True
    except Exception as e:
        print("  Fallo click icono:", e)
    return False


def configurar_fecha(driver, campo, fecha, es_fecha_hora):
    if campo is None:
        return False
    esperado = fecha.strftime("%Y-%m-%d")
    for intento in range(3):
        click_icono_almanaque(driver, campo)
        ok = seleccionar_en_calendario(driver, fecha, es_fecha_hora)
        time.sleep(0.7)
        try:
            valor = campo.get_attribute("value") or ""
        except Exception:
            valor = ""
        # Debe contener el dia esperado, no solo estar no vacio
        if ok and esperado in valor:
            print("  OK fecha:", esperado, "->", valor)
            return True
        if ok and valor.strip() and esperado not in valor and intento == 0:
            print("    Valor no coincide (%s vs %s), reintentando..." % (valor, esperado))
        # Fallback al ultimo intento: escritura directa
        if intento == 1 and not ok:
            try:
                campo.send_keys(Keys.CONTROL, "a")
                time.sleep(0.2)
                campo.send_keys(Keys.DELETE)
                time.sleep(0.2)
                escribir_valor(driver, campo, fecha.strftime("%Y-%m-%d %H:%M:%S" if es_fecha_hora else "%Y-%m-%d"))
                time.sleep(0.8)
                valor2 = campo.get_attribute("value") or ""
                if esperado in valor2:
                    print("  OK fecha (escritura directa):", esperado, "->", valor2)
                    return True
            except Exception:
                pass
        print("    Intento %d no confirmado (valor='%s'), reintentando..." % (intento + 1, valor))
        # Cerrar panel si quedo abierto
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass
    print("  [AVISO] No se pudo fijar la fecha %s en el campo." % esperado)
    return False


def configurar_hora(driver, campo, hora_dt):
    if campo is None:
        return False
    for intento in range(2):
        click_icono_almanaque(driver, campo)
        ok = seleccionar_hora_panel(driver, hora_dt)
        if not ok:
            try:
                campo.send_keys(Keys.CONTROL, "a")
                time.sleep(0.2)
                campo.send_keys(hora_dt.strftime("%H:%M:%S"))
                campo.send_keys(Keys.ENTER)
                time.sleep(0.5)
                ok = True
            except Exception:
                pass
        time.sleep(0.5)
        try:
            valor = campo.get_attribute("value") or ""
        except Exception:
            valor = ""
        if valor.strip():
            print("  OK hora:", hora_dt.strftime("%H:%M:%S"), "->", valor)
            return True
        print("    Intento hora %d no confirmado, reintentando..." % (intento + 1))
    print("  [AVISO] No se pudo fijar la hora en el campo.")
    return False


def asegurar_frame_export_logs(driver, timeout=30):
    """Localiza y cambia el contexto al frame que contiene la tabla 'Data Export Logs'."""
    inicio = time.time()
    script_evaluar = """
    var txt = (document.body ? document.body.innerText || '' : '');
    if (txt.indexOf('Data Export Logs') !== -1) return true;
    if (txt.indexOf('Task ID') !== -1 && txt.indexOf('Task Status') !== -1) return true;
    if (document.querySelector("input[placeholder*='task ID']") || 
        document.querySelector("button i.el-icon-refresh")) return true;
    return false;
    """
    while time.time() - inicio < timeout:
        driver.switch_to.default_content()
        # 1. Probar en default_content
        try:
            if driver.execute_script(script_evaluar):
                return True
        except Exception:
            pass

        # 2. Probar recursivamente en iframes
        def buscar_en_iframes(profundidad=0):
            if profundidad > 4:
                return False
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            for f in frames:
                try:
                    driver.switch_to.frame(f)
                    try:
                        if driver.execute_script(script_evaluar):
                            return True
                    except Exception:
                        pass
                    if buscar_en_iframes(profundidad + 1):
                        return True
                    driver.switch_to.parent_frame()
                except Exception:
                    try:
                        driver.switch_to.parent_frame()
                    except Exception:
                        pass
            return False

        if buscar_en_iframes():
            return True
        time.sleep(2)
    return False





def obtener_info_tarea(driver):
    """Extrae la informacion de la primera fila (tarea mas reciente) de Data Export Logs."""
    script = """
    var mainRows = Array.from(document.querySelectorAll('.el-table__body-wrapper table tbody tr, .el-table__body tbody tr, table.el-table__body tbody tr'));
    if (!mainRows.length) {
        mainRows = Array.from(document.querySelectorAll('table tbody tr')).filter(r => r.querySelectorAll('td').length >= 4);
    }
    if (!mainRows.length) {
        return null;
    }
    var row0 = mainRows[0];
    var celdas = Array.from(row0.querySelectorAll('td')).map(td => (td.innerText || td.textContent || '').trim());
    
    // Buscar si hay fixed-right para operaciones
    var fixedRows = Array.from(document.querySelectorAll('.el-table__fixed-right .el-table__fixed-body-wrapper tbody tr, .el-table__fixed-right tbody tr'));
    var opText = '';
    var hasDownload = false;
    
    // Revisar fixed row 0
    if (fixedRows.length > 0) {
        opText = (fixedRows[0].innerText || fixedRows[0].textContent || '').trim();
        var els = fixedRows[0].querySelectorAll('a, button, span, div');
        for (var i = 0; i < els.length; i++) {
            if ((els[i].innerText || els[i].textContent || '').trim() === 'Download') {
                hasDownload = true;
                break;
            }
        }
    }
    
    // Revisar main row 0 tambien
    var elsM = row0.querySelectorAll('a, button, span, div');
    for (var j = 0; j < elsM.length; j++) {
        var t = (elsM[j].innerText || elsM[j].textContent || '').trim();
        if (t === 'Download') {
            hasDownload = true;
            break;
        }
    }
    if (!opText && celdas.length > 0) {
        opText = celdas[celdas.length - 1];
    }
    
    var textoCompleto = (row0.innerText || row0.textContent || '').trim();
    
    return {
        textoCompleto: textoCompleto,
        celdas: celdas,
        opText: opText,
        hasDownload: hasDownload
    };
    """
    try:
        return driver.execute_script(script)
    except Exception:
        return None


def hacer_click_download(driver, task_id=None):
    """Busca el boton/enlace Download en la primera fila (o la fila con task_id) y hace clic."""
    script_click = """
    var targetTaskId = arguments[0];
    var fixedRows = Array.from(document.querySelectorAll('.el-table__fixed-right .el-table__fixed-body-wrapper tbody tr, .el-table__fixed-right tbody tr'));
    var mainRows = Array.from(document.querySelectorAll('.el-table__body-wrapper table tbody tr, .el-table__body tbody tr, table.el-table__body tbody tr'));
    if (!mainRows.length) {
        mainRows = Array.from(document.querySelectorAll('table tbody tr')).filter(r => r.querySelectorAll('td').length >= 4);
    }
    
    var rowIndex = 0;
    if (targetTaskId) {
        for (var i = 0; i < mainRows.length; i++) {
            if ((mainRows[i].innerText || '').indexOf(targetTaskId) !== -1) {
                rowIndex = i;
                break;
            }
        }
    }
    
    // 1. Probar en fixedRows en rowIndex
    if (fixedRows.length > rowIndex) {
        var elsF = fixedRows[rowIndex].querySelectorAll('a, button, span, div');
        for (var f = 0; f < elsF.length; f++) {
            if ((elsF[f].innerText || elsF[f].textContent || '').trim() === 'Download') {
                elsF[f].scrollIntoView({block: 'center'});
                elsF[f].click();
                return { ok: true, metodo: 'fixedRows', tag: elsF[f].tagName };
            }
        }
    }
    
    // 2. Probar en mainRows en rowIndex
    if (mainRows.length > rowIndex) {
        var elsM = mainRows[rowIndex].querySelectorAll('a, button, span, div');
        for (var m = 0; m < elsM.length; m++) {
            if ((elsM[m].innerText || elsM[m].textContent || '').trim() === 'Download') {
                elsM[m].scrollIntoView({block: 'center'});
                elsM[m].click();
                return { ok: true, metodo: 'mainRows', tag: elsM[m].tagName };
            }
        }
    }
    
    // 3. Buscar cualquier fila que tenga 'Succeed' y 'Download'
    var rowsSucceed = Array.from(document.querySelectorAll('tr')).filter(r => (r.innerText || '').indexOf('Succeed') !== -1);
    for (var r = 0; r < rowsSucceed.length; r++) {
        var elsS = rowsSucceed[r].querySelectorAll('a, button, span, div');
        for (var s = 0; s < elsS.length; s++) {
            if ((elsS[s].innerText || elsS[s].textContent || '').trim() === 'Download') {
                elsS[s].scrollIntoView({block: 'center'});
                elsS[s].click();
                return { ok: true, metodo: 'succeedRow', tag: elsS[s].tagName };
            }
        }
    }
    
    return { ok: false };
    """
    try:
        res = driver.execute_script(script_click, task_id)
        if res and res.get("ok"):
            print("  [OK] Click en Download ejecutado vía script (%s)." % res.get("metodo"))
            return True
    except Exception as e:
        print("  Error en script Download:", e)

    # Fallback con Selenium
    xpaths = [
        "//div[contains(@class,'el-table__fixed-right')]//tr[1]//*[normalize-space(.)='Download']",
        "//tr[contains(@class,'el-table__row')][1]//*[normalize-space(.)='Download']",
        "//tr[contains(.,'Succeed')][1]//*[normalize-space(.)='Download']",
        "//*[normalize-space(.)='Download']"
    ]
    for xp in xpaths:
        try:
            elem = driver.find_element(By.XPATH, xp)
            if elem.is_displayed():
                try:
                    ActionChains(driver).move_to_element(elem).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", elem)
                print("  [OK] Click en Download ejecutado vía XPath (%s)." % xp)
                return True
        except Exception:
            continue

    return False


def esperar_download_tabla(driver, timeout=900):
    """En Data Export Logs, espera que la primera fila (la tarea generada) pase a Succeed recargando con F5, y hace clic en Download."""
    print("Esperando que el export se complete en Data Export Logs (hasta %ds)..." % timeout)
    inicio = time.time()
    ultimo_f5 = inicio
    ultimo_aviso = 0
    task_id_detectado = None

    # 1. Asegurar que estamos en el frame de Data Export Logs
    print("  Localizando frame de Data Export Logs...")
    if not asegurar_frame_export_logs(driver, timeout=45):
        print("  [AVISO] No se detecto el frame en primer intento, reintentando...")
        time.sleep(3)
        if not asegurar_frame_export_logs(driver, timeout=30):
            print("[ERROR] No se pudo encontrar la tabla de Data Export Logs.")
            return False

    print("  Tabla de Data Export Logs encontrada. Iniciando monitoreo con F5...")
    time.sleep(3)

    while time.time() - inicio < timeout:
        # Asegurar frame en cada iteracion
        asegurar_frame_export_logs(driver, timeout=5)

        info = obtener_info_tarea(driver)
        if info:
            texto = info.get("textoCompleto", "")
            has_download = info.get("hasDownload", False)
            celdas = info.get("celdas", [])

            # Detectar y guardar Task ID si aun no lo tenemos
            if not task_id_detectado and len(celdas) > 1 and celdas[1]:
                task_id_detectado = celdas[1][:25].strip()
                print("  Tarea en monitoreo [ID: %s]" % task_id_detectado)

            texto_lower = texto.lower()

            # Verificar si ya finalizo con exito o Download esta habilitado
            if "succeed" in texto_lower or has_download:
                print("  [LISTO] Tarea completada con estado Succeed en %ds." % int(time.time() - inicio))
                time.sleep(2)

                # Clic en Download
                print("  Haciendo clic en Download...")
                for intento_dl in range(3):
                    if hacer_click_download(driver, task_id_detectado):
                        time.sleep(3)
                        return True
                    time.sleep(2)
                print("[ERROR] No se pudo hacer clic en Download a pesar de estar en Succeed.")
                return False

            elif "failed" in texto_lower:
                print("  [ERROR] La tarea marco estado 'Failed' en el servidor.")
                return False

            elif "running" in texto_lower:
                if time.time() - ultimo_aviso >= 15:
                    duracion_celda = celdas[5] if len(celdas) > 5 else ""
                    print("  [Procesando] Estado: Running... (%ds transcurridos%s)" % 
                          (int(time.time() - inicio), f", Duracion: {duracion_celda}s" if duracion_celda else ""))
                    ultimo_aviso = time.time()
            else:
                if time.time() - ultimo_aviso >= 15:
                    print("  [Esperando] Estado actual: %s (%ds transcurridos)" % 
                          (texto[:50], int(time.time() - inicio)))
                    ultimo_aviso = time.time()
        else:
            if time.time() - ultimo_aviso >= 15:
                print("  [Esperando carga de datos...] (%ds transcurridos)" % int(time.time() - inicio))
                ultimo_aviso = time.time()

        # F5: recargar la pagina completa cada 25 segundos para actualizar el estado
        if time.time() - ultimo_f5 >= 25:
            ultimo_f5 = time.time()
            print("  F5: recargando pagina (%ds transcurridos)..." % int(time.time() - inicio))
            try:
                driver.switch_to.default_content()
                driver.refresh()
                time.sleep(7)
            except Exception as e:
                print("  Error en F5:", e)
                time.sleep(3)

            # Asegurar que sigamos en la URL de batch_records tras el F5
            try:
                if "batch_records" not in driver.current_url:
                    print("  Re-navegando a batch_records tras F5...")
                    driver.get(URL_BATCH)
                    time.sleep(7)
            except Exception as e:
                print("  Error verificando URL tras F5:", e)

            # Volver a ingresar al frame
            asegurar_frame_export_logs(driver, timeout=30)
            continue

        time.sleep(3)

    print("[TIMEOUT] Se agoto el tiempo limite (%ds) esperando el export." % timeout)
    return False


def crear_driver():
    service = Service(CHROME_DRIVER)
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--safebrowsing-disable-download-protection")
    options.add_experimental_option("prefs", {
        "download.default_directory": CARPETA,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "safebrowsing.disable_download_protection": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    })
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": CARPETA
        })
    except Exception:
        pass
    return driver


def login_teleows(driver):
    print("=== Login teleows ===")
    driver.get(URL)
    wait = WebDriverWait(driver, 30)
    campo_usuario = wait.until(EC.presence_of_element_located((By.ID, "username")))
    campo_usuario.clear()
    campo_usuario.send_keys(USUARIO)
    campo_password = wait.until(EC.presence_of_element_located((By.ID, "password")))
    campo_password.clear()
    campo_password.send_keys(CONTRASENA)
    boton_login = wait.until(EC.element_to_be_clickable((By.ID, "loginButton")))
    boton_login.click()
    print("Esperando ingreso al portal...")
    wait.until(lambda d: "login" not in d.current_url)
    wait.until(lambda d: "homepage" in d.current_url)
    time.sleep(3)
    print("Logueado en teleows.")


def abrir_reporte_pint(driver):
    print("Abriendo reporte PINT (CM Checklist) en pestaña nueva...")
    driver.execute_script("window.open(arguments[0]);", URL_REPORTE)
    time.sleep(2)
    driver.switch_to.window(driver.window_handles[-1])
    hoy = datetime.now()
    fecha_inicio = hoy - timedelta(days=2)
    fecha_fin = hoy

    # Intenta primero el formato antiguo de un solo input (datetime combinado)
    campo_inicio_single = esperar_elemento(driver, By.CSS_SELECTOR, "input#start_time",
                                          timeout=8, etiqueta="start_time")
    if campo_inicio_single is not None:
        # Formato antiguo: solo Fecha Inicio (Fecha Fin no necesaria)
        print("Fecha Inicio:", fecha_inicio.strftime("%Y-%m-%d") + " 00:00:00")
        configurar_fecha(driver, campo_inicio_single,
                         datetime(fecha_inicio.year, fecha_inicio.month, fecha_inicio.day), True)
        # Cerrar cualquier panel que haya quedado abierto sin tocar Fecha Fin
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass
    else:
        # Formato visto en captura: Fecha Inicio con dos inputs (fecha + hora separados)
        campo_inicio_fecha = buscar_input_por_etiqueta(driver, "Fecha Inicio", "Seleccionar fecha", intento_idx=0)
        campo_inicio_hora = buscar_input_por_etiqueta(driver, "Fecha Inicio", "Seleccionar hora", intento_idx=0)
        if campo_inicio_fecha is None:
            print("[ERROR] No se encontro el campo Fecha Inicio (fecha).")
            return False
        print("Fecha Inicio:", fecha_inicio.strftime("%Y-%m-%d"))
        configurar_fecha(driver, campo_inicio_fecha,
                         datetime(fecha_inicio.year, fecha_inicio.month, fecha_inicio.day), False)
        if campo_inicio_hora is not None:
            print("Hora Inicio: 00:00:00")
            configurar_hora(driver, campo_inicio_hora,
                            datetime(fecha_inicio.year, fecha_inicio.month, fecha_inicio.day, 0, 0, 0))
        # Asegurar que el calendario de Fecha Inicio se cierre y NO tocar Fecha Fin
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
            # Click en un area neutra para cerrar overlay
            driver.execute_script("document.body.click();")
            time.sleep(0.5)
        except Exception:
            pass

    print("Clic en Buscar...")
    boton_buscar = esperar_elemento(
        driver, By.XPATH,
        "//span[contains(@class,'sdm_splitbutton_text')][normalize-space(.)='Buscar']",
        timeout=30, etiqueta="boton Buscar")
    if boton_buscar is None:
        print("[ERROR] No se encontro el boton Buscar.")
        return False
    driver.execute_script("arguments[0].click();", boton_buscar)
    esperar_desaparezca_mascara(driver, 90)
    print("Busqueda completada.")

    print("Clic en Exportar...")
    # PINT usa split-button: el texto es span.sdm_splitbutton_text pero el clic debe ir al boton contenedor
    boton_exportar = esperar_elemento(
        driver, By.XPATH,
        "//span[contains(@class,'sdm_splitbutton_text')][normalize-space(.)='Exportar']",
        timeout=30, etiqueta="boton Exportar")
    if boton_exportar is None:
        boton_exportar = esperar_elemento(
            driver, By.XPATH,
            "//div[contains(@class,'ows_button')][.//span[normalize-space(.)='Exportar']]",
            timeout=10, etiqueta="boton Exportar (ows)")
    if boton_exportar is None:
        print("[AVISO] No se encontro el boton Exportar.")
        return False
    # Click robusto sobre el ancestro clickeable (button/div) para desplegar el menu
    try:
        driver.execute_script(
            "var el=arguments[0];"
            "var btn=el.closest('button, .ows_button, .sdm_splitbutton, .el-button, div');"
            "if(btn) btn.scrollIntoView({block:'center'});",
            boton_exportar)
        time.sleep(0.3)
    except Exception:
        pass
    try:
        # Intenta hover + click via ActionChains (como en WOs_descargar_y_importar.py)
        ActionChains(driver).move_to_element(boton_exportar).click().perform()
    except Exception:
        pass
    try:
        driver.execute_script(
            "var el=arguments[0];"
            "var btn=el.closest('button, .ows_button, .sdm_splitbutton, .el-button, div');"
            "if(btn) btn.click(); else el.click();",
            boton_exportar)
    except Exception:
        driver.execute_script("arguments[0].click();", boton_exportar)
    time.sleep(2)
    # Ahora el menu debe mostrar "Exportar todo"
    exportar_todo = esperar_elemento(
        driver, By.XPATH,
        "//li[contains(@class,'el-menu-item')][.//span[normalize-space(.)='Exportar todo']]",
        timeout=15, etiqueta="Exportar todo")
    if exportar_todo is None:
        exportar_todo = esperar_elemento(
            driver, By.XPATH,
            "//*[normalize-space(.)='Exportar todo']",
            timeout=10, etiqueta="Exportar todo (generico)")
    if exportar_todo is None:
        # Reintenta desplegar el menu una vez mas
        print("  Reintentando desplegar menu Exportar...")
        try:
            ActionChains(driver).move_to_element(boton_exportar).click().perform()
            time.sleep(1)
            driver.execute_script("arguments[0].click();", boton_exportar)
            time.sleep(1)
        except Exception:
            pass
        exportar_todo = esperar_elemento(
            driver, By.XPATH,
            "//*[normalize-space(.)='Exportar todo']",
            timeout=10, etiqueta="Exportar todo (reintento)")
    if exportar_todo is None:
        print("[AVISO] No se encontro 'Exportar todo'.")
        return False
    # Click asegurado: hover + JS
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", exportar_todo)
        time.sleep(0.3)
        ActionChains(driver).move_to_element(exportar_todo).click().perform()
        time.sleep(0.5)
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", exportar_todo)
    except Exception as e:
        print("  Error clic Exportar todo:", e)
        return False

    # Esperar al menos 5s para que el click y el export se registren bien
    print("Esperando 5s para confirmar el Exportar todo...")
    time.sleep(5)

    # Capturar archivos antes de la descarga para no perder la referencia del nuevo archivo
    archivos_antes = set(os.listdir(CARPETA))

    # Tras Exportar todo, asegurar navegacion a Data Export Logs
    print("Accediendo a Data Export Logs...")
    encontrado = False
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "batch_records" in driver.current_url:
            encontrado = True
            break
    if not encontrado:
        driver.execute_script("window.open(arguments[0]);", URL_BATCH)
        time.sleep(3)
        driver.switch_to.window(driver.window_handles[-1])

    # El export va a Data Export Logs y se procesa hasta que aparezca Download
    ok_download = esperar_download_tabla(driver, 900)
    if not ok_download:
        print("[ERROR] No se pudo habilitar la descarga del export.")
        return False

    return archivos_antes


def esperar_descarga(driver, archivos_antes=None, timeout=180):
    print("Esperando recepcion del archivo descargado (hasta %ds)..." % timeout)
    if os.path.exists(ARCHIVO_PINT):
        try:
            os.remove(ARCHIVO_PINT)
            print("  Eliminado archivo PINT anterior.")
        except Exception as e:
            print("  No se pudo eliminar el anterior:", e)

    if archivos_antes is None:
        archivos_antes = set(os.listdir(CARPETA))

    inicio = time.time()
    ultimo_aviso = 0
    while time.time() - inicio < timeout:
        time.sleep(3)
        # Comprobar si hay descargas activas en progreso
        en_descarga = [f for f in os.listdir(CARPETA) if f.endswith((".crdownload", ".part", ".tmp"))]
        if en_descarga:
            if time.time() - ultimo_aviso > 10:
                print("  Descargando archivo (%s)..." % en_descarga[0])
                ultimo_aviso = time.time()
            continue

        # Archivos nuevos en la carpeta
        nuevos = [f for f in os.listdir(CARPETA)
                  if f not in archivos_antes
                  and not f.endswith((".crdownload", ".part", ".tmp"))
                  and f != "PINT Checklist.xlsx"]

        # Tambien buscar si hay un archivo pint_checklist reciente
        if not nuevos:
            for f in os.listdir(CARPETA):
                if f.lower().startswith("pint_checklist") and not f.endswith((".crdownload", ".part", ".tmp")):
                    ruta_f = os.path.join(CARPETA, f)
                    if os.path.getmtime(ruta_f) >= inicio - 15:
                        nuevos.append(f)

        if nuevos:
            archivo = max(nuevos, key=lambda f: os.path.getmtime(os.path.join(CARPETA, f)))
            print("Descargado:", archivo)
            ext = os.path.splitext(archivo)[1]
            ruta_orig = os.path.join(CARPETA, archivo)
            ruta_final = ARCHIVO_PINT if ext.lower() == ".xlsx" else os.path.join(CARPETA, "PINT Checklist" + ext)

            for _ in range(10):
                try:
                    if os.path.exists(ruta_final):
                        os.remove(ruta_final)
                    os.rename(ruta_orig, ruta_final)
                    print("Guardado en:", ruta_final)
                    return ruta_final
                except Exception:
                    time.sleep(1)
            return ruta_orig

        if time.time() - ultimo_aviso > 30:
            print("  aun esperando archivo descargado...")
            ultimo_aviso = time.time()

    print("[AVISO] No se detecto archivo descargado en %ds." % timeout)
    return None


def main():
    print("=== INICIO Login teleows + Descargar PINT ===")
    driver = crear_driver()
    try:
        login_teleows(driver)
        archivos_antes = abrir_reporte_pint(driver)
        if archivos_antes is not False:
            ruta = esperar_descarga(driver, archivos_antes, timeout=180)
            if ruta:
                print("OK: reporte PINT en", ruta)
            else:
                print("[ERROR] No llego el archivo descargado.")
        else:
            print("[ERROR] No se pudo completar el reporte PINT.")
        input("Presiona ENTER para cerrar Chrome...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()