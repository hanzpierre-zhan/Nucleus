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
URL_DASHBOARD = "https://300v-mx.teleows.com/portal-web/portal/homepage.html#%2Fwo_kpi_dashboard%2Fwo_kpi_dashboard%2FWOs%20Report%20Console%20Dashboard"

USUARIO = "mhuayanab.ofg"
CONTRASENA = "MAE123_LK34*r"

URL_NUCLEUS = "https://nucleus-j2cv.onrender.com/"
USUARIO_NUCLEUS = "hvargas"
CONTRASENA_NUCLEUS = "123456"

# Archivos estandar que se esperan al final de cada fase
ARCHIVO_FLM = os.path.join(CARPETA, "WOs List FLM.xlsx")
ARCHIVO_PEXT = os.path.join(CARPETA, "WOs List PEXT.xlsx")


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


def seleccionar_en_calendario(driver, fecha, es_fecha_hora):
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

        celdas = panel.find_elements(By.CSS_SELECTOR,
            "td.available:not(.prev-month):not(.next-month) .cell")
        dia_str = str(fecha.day)
        for celda in celdas:
            if celda.text.strip() == dia_str:
                celda.click()
                break
        time.sleep(1)

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


def configurar_fecha(driver, selector_css, fecha, es_fecha_hora):
    campo = esperar_elemento(driver, By.CSS_SELECTOR, selector_css,
                             timeout=20, etiqueta=selector_css)
    if campo is None:
        print("  [AVISO] Campo no encontrado, se omite:", selector_css)
        return False
    texto = fecha.strftime("%Y-%m-%d %H:%M:%S" if es_fecha_hora else "%Y-%m-%d")
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", campo)
        time.sleep(0.5)
        escribir_valor(driver, campo, texto)
        time.sleep(1)
        valor = campo.get_attribute("value") or ""
        if valor.strip():
            print("  OK:", selector_css, "=", valor)
            return True
    except Exception as e:
        print("  Fallo escritura:", e)
    print("  Usando calendario para:", selector_css)
    return seleccionar_en_calendario(driver, fecha, es_fecha_hora)


def seleccionar_dropdown(driver, id_selector, opciones):
    campo = esperar_elemento(driver, By.CSS_SELECTOR,
                             id_selector + " input.el-input__inner",
                             timeout=20, etiqueta=id_selector)
    if campo is None:
        print("  [AVISO] Select no encontrado:", id_selector)
        return
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", campo)
    time.sleep(1)
    if isinstance(opciones, str):
        opciones = [opciones]
    for opcion in opciones:
        opcion_may = opcion.upper()
        item = esperar_elemento(
            driver, By.XPATH,
            "//li[contains(@class,'el-select-dropdown__item')]"
            "[translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='"
            + opcion_may.lower() + "']",
            timeout=10, etiqueta=opcion)
        if item is not None:
            driver.execute_script("arguments[0].click();", item)
            print("  OK:", id_selector, "->", opcion)
            time.sleep(1)
        else:
            print("  [AVISO] Opcion no encontrada:", opcion)
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)


def limpiar_descargas():
    # Borra archivos de descarga anteriores, PERO conserva los WOs List FLM/PEXT
    # ya descargados (deben quedar los dos hasta la fase de importacion).
    for f in os.listdir(CARPETA):
        if (f.lower().endswith((".xlsx", ".xls", ".csv", ".zip"))
                and not f.lower().startswith("wos list flm")
                and not f.lower().startswith("wos list pext")):
            try:
                os.remove(os.path.join(CARPETA, f))
                print("  Eliminado archivo anterior:", f)
            except Exception as e:
                print("  No se pudo eliminar:", f, e)


def crear_driver():
    service = Service(CHROME_DRIVER)
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("prefs", {
        "download.default_directory": CARPETA,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    return webdriver.Chrome(service=service, options=options)


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


def abrir_dashboard(driver):
    print("Abriendo Dashboard en pestaña nueva...")
    driver.execute_script("window.open(arguments[0]);", URL_DASHBOARD)
    time.sleep(2)
    driver.switch_to.window(driver.window_handles[-1])
    if esperar_elemento(driver, By.CSS_SELECTOR, "span.form-arrow-down",
                        timeout=120, etiqueta="boton filtros V") is None:
        print("URL actual:", driver.current_url)
        print("Titulo:", driver.title)
        print("Iframes:", len(driver.find_elements(By.TAG_NAME, "iframe")))
    else:
        print("Dashboard cargado.")


def descargar_wo(driver, nombre_final, departamentos, categoria):
    """Rellena filtros, busca, exporta todo y renombra al nombre estandar."""
    print("Abriendo panel de filtros...")
    btn_filtros = esperar_elemento(driver, By.CSS_SELECTOR, "span.form-arrow-down",
                                   timeout=30, etiqueta="boton filtros")
    if btn_filtros is not None:
        driver.execute_script("arguments[0].click();", btn_filtros)
        time.sleep(2)

    print("Rellenando filtros...")
    seleccionar_dropdown(driver, "#wo_type_filter", "CM")
    seleccionar_dropdown(driver, "#department_filter", departamentos)
    seleccionar_dropdown(driver, "#genericfield2", categoria)

    ahora = datetime.now()
    inicio = ahora - timedelta(days=3)
    print("Rellenando fechas de creacion...")
    configurar_fecha(driver, "#creation_date_start_filter", inicio, True)
    time.sleep(1)
    configurar_fecha(driver, "#creation_date_end_filter", ahora, True)

    print("Clic en Buscar...")
    boton_buscar = esperar_elemento(
        driver, By.XPATH,
        "//span[contains(@class,'sdm_splitbutton_text') and normalize-space(.)='Buscar']",
        timeout=30, etiqueta="boton Buscar")
    if boton_buscar is not None:
        driver.execute_script("arguments[0].click();", boton_buscar)
        print("Buscando, esperando carga...")
        inicio_carga = time.time()
        while time.time() - inicio_carga < 90:
            time.sleep(2)
            driver.switch_to.default_content()
            mascara = buscar_en_frames_rec(
                driver, By.CSS_SELECTOR,
                ".el-loading-mask:not([style*='display: none'])")
            if mascara is None:
                break
        time.sleep(3)
        print("Busqueda completada.")
    else:
        print("[AVISO] No se encontro el boton Buscar.")

    print("Clic en Exportar...")
    boton_exportar = esperar_elemento(
        driver, By.XPATH,
        "//div[contains(@class,'ows_button')][.//span[normalize-space(.)='Exportar']]",
        timeout=30, etiqueta="boton Exportar")
    if boton_exportar is None:
        print("[AVISO] No se encontro el boton Exportar.")
        return False
    driver.execute_script("arguments[0].click();", boton_exportar)
    time.sleep(2)
    exportar_todo = esperar_elemento(
        driver, By.XPATH,
        "//li[contains(@class,'el-menu-item')][.//span[normalize-space(.)='Exportar todo']]",
        timeout=15, etiqueta="Exportar todo")
    if exportar_todo is None:
        print("[AVISO] No se encontro 'Exportar todo'.")
        return False

    limpiar_descargas()
    archivos_antes = set(os.listdir(CARPETA))
    try:
        ActionChains(driver).move_to_element(exportar_todo).click().perform()
    except Exception:
        driver.execute_script("arguments[0].click();", exportar_todo)

    print("Esperando descarga (hasta 120s)...")
    inicio_espera = time.time()
    ultimo_aviso = 0
    archivo_descargado = None
    while time.time() - inicio_espera < 120:
        time.sleep(3)
        nuevos = [f for f in os.listdir(CARPETA)
                  if f not in archivos_antes
                  and not f.endswith((".crdownload", ".part"))]
        if nuevos:
            archivo_descargado = max(
                nuevos,
                key=lambda f: os.path.getmtime(os.path.join(CARPETA, f)))
            print("Descargado:", archivo_descargado)
            ext = os.path.splitext(archivo_descargado)[1]
            nuevo_nombre = nombre_final + ext
            ruta_orig = os.path.join(CARPETA, archivo_descargado)
            ruta_nueva = os.path.join(CARPETA, nuevo_nombre)
            if os.path.exists(ruta_nueva):
                try:
                    os.remove(ruta_nueva)
                except Exception as e:
                    print("  No se pudo eliminar el anterior:", nuevo_nombre, e)
            try:
                os.rename(ruta_orig, ruta_nueva)
                print("Renombrado a:", nuevo_nombre)
            except Exception as e:
                print("  No se pudo renombrar:", e)
            return os.path.join(CARPETA, nuevo_nombre)
        if time.time() - ultimo_aviso > 30:
            print("  aun procesando...")
            ultimo_aviso = time.time()
    print("[AVISO] No se detecto archivo descargado en 120s.")
    return None


def importar_en_nucleus(driver, ruta_archivo, proyecto_nombre, proyecto_id, ya_logueado=False):
    print("Abriendo Nucleus en pestaña nueva...")
    driver.execute_script("window.open(arguments[0]);", URL_NUCLEUS)
    time.sleep(2)
    driver.switch_to.window(driver.window_handles[-1])

    if ya_logueado:
        # La sesion ya esta activa (segundo import): el login ya no aparece.
        print("Sesion ya activa, saltando login...")
        time.sleep(2)
    else:
        print("Esperando login de Nucleus...")
        campo_usuario = esperar_elemento(driver, By.CSS_SELECTOR, "input[name='username']",
                                         timeout=120, etiqueta="usuario Nucleus")
        if campo_usuario is None:
            print("[ERROR] No se encontro el login. URL:", driver.current_url)
            return False
        campo_usuario.clear()
        campo_usuario.send_keys(USUARIO_NUCLEUS)

        campo_password = esperar_elemento(driver, By.CSS_SELECTOR, "#password",
                                          timeout=15, etiqueta="password Nucleus")
        if campo_password is None:
            print("[ERROR] No se encontro campo password.")
            return False
        campo_password.clear()
        campo_password.send_keys(CONTRASENA_NUCLEUS)

        boton_login = esperar_elemento(driver, By.CSS_SELECTOR, "#login-btn",
                                       timeout=15, etiqueta="Iniciar Sesion")
        if boton_login is None:
            print("[ERROR] No se encontro boton Iniciar Sesion.")
            return False
        boton_login.click()
    print("Logueado en Nucleus, esperando menu %s..." % proyecto_nombre)

    link_proyecto = esperar_elemento(
        driver, By.XPATH,
        "//a[contains(@href,'/switch_project/%d?next=/')][.//span[normalize-space(.)='%s']]"
        % (proyecto_id, proyecto_nombre),
        timeout=60, etiqueta="link %s" % proyecto_nombre)
    if link_proyecto is None:
        print("[ERROR] No se encontro el link %s." % proyecto_nombre)
        print("URL actual:", driver.current_url)
        print("Titulo:", driver.title)
        return False
    link_proyecto.click()
    print("Abierto proyecto %s." % proyecto_nombre)

    boton_importar = esperar_elemento(
        driver, By.XPATH,
        "//button[contains(@onclick,'abrirModalImportar')]",
        timeout=60, etiqueta="boton Importar")
    if boton_importar is None:
        print("[ERROR] No se encontro el boton Importar.")
        return False
    driver.execute_script("arguments[0].click();", boton_importar)
    print("Modal de importacion abierto.")

    input_archivo = esperar_elemento(driver, By.ID, "import-file",
                                     timeout=30, etiqueta="selector de archivo")
    if input_archivo is None:
        print("[ERROR] No se encontro el selector de archivo.")
        return False
    print("Seleccionando archivo:", os.path.basename(ruta_archivo))
    input_archivo.send_keys(ruta_archivo)
    time.sleep(2)

    print("Esperando boton 'Importar ahora' habilitado...")
    inicio_b = time.time()
    btn = None
    while time.time() - inicio_b < 60:
        driver.switch_to.default_content()
        try:
            btn = driver.find_element(By.ID, "btn-import-now")
            if btn.get_attribute("disabled") is None:
                print("  Boton 'Importar ahora' listo.")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print("[ERROR] El boton Importar ahora no se habilito.")
        return False

    for _ in range(3):
        try:
            driver.switch_to.default_content()
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
            texto_btn = btn.text
            if "rocesando" in texto_btn or btn.get_attribute("disabled") is not None:
                print("  Click registrado, importando...")
                break
            print("  Reintentando click...")
        except Exception as e:
            print("  Reintentando click:", e)
            time.sleep(1)
    print("Importando, esperando resultado...")

    inicio_r = time.time()
    while time.time() - inicio_r < 120:
        driver.switch_to.default_content()
        try:
            box = driver.find_element(By.ID, "import-result")
            texto_resultado = (box.text or "").strip()
        except Exception:
            texto_resultado = ""
        if texto_resultado:
            print("Resultado:", texto_resultado)
            return True
        time.sleep(2)
    print("[AVISO] El resultado de la importacion no se mostro.")
    return True


def fase_descargar_flm():
    """Fase 1: descarga WOs List FLM en su propia sesion de Chrome."""
    print("\n========== FASE 1/3: DESCARGAR FLM ==========")
    driver = crear_driver()
    try:
        login_teleows(driver)
        abrir_dashboard(driver)
        ruta = descargar_wo(
            driver,
            nombre_final="WOs List FLM",
            departamentos=["HUANUCO", "PASCO", "JUNIN", "HUANCAVELICA", "ICA",
                           "CUSCO", "PUNO", "AREQUIPA", "TACNA", "APURIMAC",
                           "AYACUCHO", "MADRE DE DIOS", "MOQUEGUA"],
            categoria="O&M CRM")
        if ruta and os.path.exists(ruta):
            print("OK: FLM descargado en", ruta)
            return ruta
        print("[ERROR] FLM no se descargo correctamente.")
        return None
    finally:
        driver.quit()


def fase_descargar_pext():
    """Fase 2: descarga WOs List PEXT en su propia sesion de Chrome (limpia)."""
    print("\n========== FASE 2/3: DESCARGAR PEXT ==========")
    driver = crear_driver()
    try:
        login_teleows(driver)
        abrir_dashboard(driver)
        ruta = descargar_wo(
            driver,
            nombre_final="WOs List PEXT",
            departamentos=["LIMA", "ICA", "AREQUIPA"],
            categoria="O&M PEXT")
        if ruta and os.path.exists(ruta):
            print("OK: PEXT descargado en", ruta)
            return ruta
        print("[ERROR] PEXT no se descargo correctamente.")
        return None
    finally:
        driver.quit()


def fase_importar(ruta_flm, ruta_pext):
    """Fase 3: importa ambos archivos en Nucleus en una sola sesion."""
    print("\n========== FASE 3/3: IMPORTAR EN NUCLEUS ==========")
    driver = crear_driver()
    try:
        if ruta_flm and os.path.exists(ruta_flm):
            importar_en_nucleus(driver, ruta_flm, "FLM", 1, ya_logueado=False)
            time.sleep(3)
        if ruta_pext and os.path.exists(ruta_pext):
            importar_en_nucleus(driver, ruta_pext, "PEXT", 2, ya_logueado=True)
    finally:
        driver.quit()


def main():
    print("=== INICIO WOs Descargar FLM + PEXT -> Importar ===")
    inicio_total = time.time()

    ruta_flm = fase_descargar_flm()
    ruta_pext = fase_descargar_pext()

    # Importar solo si al menos un archivo existe
    if ruta_flm or ruta_pext:
        fase_importar(ruta_flm, ruta_pext)
    else:
        print("[ERROR] Ningun archivo se descargo. No se importara nada.")

    print("\n=== FIN (%d s) ===" % int(time.time() - inicio_total))


if __name__ == "__main__":
    main()