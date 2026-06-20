import streamlit as st
import pandas as pd
import requests
import urllib.parse
from bs4 import BeautifulSoup
import datetime
import os
import time
import io
import base64
import shutil
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ==========================================================
# CONFIGURACIÓN GLOBAL
# ==========================================================
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SHEET_ID = "1SSAS4NLafR3p8K3nIlBoHp0AKklO5JNfWwQbSfNdbGU"
ADMIN_USER = "admin"

COLUMNAS_USUARIOS = ["usuario", "contraseña", "nombre", "fecha_nacimiento"]

# ==========================================================
# FUNCIONES DE CONEXIÓN Y AUTENTICACIÓN
# ==========================================================

def get_gspread_client():
    creds_dict = dict(st.secrets["gcp"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    return gspread.authorize(creds)


def asegurar_columnas_usuarios(sheet_users):
    try:
        encabezados = sheet_users.row_values(1)
    except Exception:
        encabezados = []
    for idx, nombre_columna in enumerate(COLUMNAS_USUARIOS, start=1):
        if idx > len(encabezados):
            sheet_users.update_cell(1, idx, nombre_columna)


def _obtener_hoja_usuarios():
    client = get_gspread_client()
    doc = client.open_by_key(SHEET_ID)
    sheet_users = doc.worksheet("Usuarios")
    asegurar_columnas_usuarios(sheet_users)
    return sheet_users


def validar_usuario(usuario, password):
    try:
        sheet_users = _obtener_hoja_usuarios()
        datos_usuarios = sheet_users.get_all_records(numericise_ignore=['all'])
        for fila in datos_usuarios:
            usuario_db = str(fila.get('usuario', '')).strip()
            pass_db = str(fila.get('contraseña', '')).strip()
            if usuario_db == usuario.strip() and pass_db == password.strip():
                return True
        return False
    except Exception as e:
        st.error(f"Error técnico de conexión: {e}")
        return False


def obtener_logs():
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_logs = doc.worksheet("Logs")
        datos = sheet_logs.get_all_values()
        if len(datos) <= 1:
            return pd.DataFrame(columns=["Fecha", "Usuario", "Búsqueda", "Resultados"])
        df = pd.DataFrame(datos[1:], columns=["Fecha", "Usuario", "Búsqueda", "Resultados"])
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df = df.sort_values("Fecha", ascending=False).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Error al obtener historiales: {e}")
        return pd.DataFrame(columns=["Fecha", "Usuario", "Búsqueda", "Resultados"])


def registrar_log(usuario, busqueda, cantidad_resultados):
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_logs = doc.worksheet("Logs")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet_logs.append_row([timestamp, usuario, busqueda, cantidad_resultados], value_input_option='RAW')
    except Exception as e:
        st.error(f"Error al guardar log: {e}")


def obtener_usuarios():
    try:
        sheet_users = _obtener_hoja_usuarios()
        datos = sheet_users.get_all_records(numericise_ignore=['all'])
        return datos, sheet_users
    except Exception as e:
        st.error(f"Error al obtener usuarios: {e}")
        return [], None


def obtener_perfil(usuario):
    datos, _ = obtener_usuarios()
    for fila in datos:
        if str(fila.get('usuario', '')).strip().lower() == usuario.strip().lower():
            return fila
    return None


def agregar_usuario(nuevo_usuario, nueva_password, nombre=""):
    try:
        sheet_users = _obtener_hoja_usuarios()
        datos = sheet_users.get_all_records(numericise_ignore=['all'])
        for fila in datos:
            if str(fila.get('usuario', '')).strip().lower() == nuevo_usuario.strip().lower():
                return False, "El usuario ya existe."
        sheet_users.append_row(
            [nuevo_usuario.strip(), str(nueva_password).strip(), nombre.strip(), ""],
            value_input_option='RAW'
        )
        return True, "Usuario creado correctamente."
    except Exception as e:
        return False, f"Error: {e}"


def eliminar_usuario(usuario_a_eliminar):
    try:
        if usuario_a_eliminar.strip().lower() == ADMIN_USER.lower():
            return False, "No se puede eliminar al administrador."
        sheet_users = _obtener_hoja_usuarios()
        datos = sheet_users.get_all_values()
        for i, fila in enumerate(datos):
            if len(fila) > 0 and str(fila[0]).strip().lower() == usuario_a_eliminar.strip().lower():
                sheet_users.delete_rows(i + 1)
                return True, f"Usuario '{usuario_a_eliminar}' eliminado."
        return False, "Usuario no encontrado."
    except Exception as e:
        return False, f"Error: {e}"


def actualizar_perfil(usuario_objetivo, nuevo_nombre=None, nueva_fecha=None, nueva_password=None):
    try:
        sheet_users = _obtener_hoja_usuarios()
        datos = sheet_users.get_all_values()
        for i, fila in enumerate(datos):
            if len(fila) > 0 and str(fila[0]).strip().lower() == usuario_objetivo.strip().lower():
                fila_idx = i + 1
                if nueva_password:
                    sheet_users.update(f"B{fila_idx}", [[str(nueva_password).strip()]], value_input_option='RAW')
                if nuevo_nombre is not None:
                    sheet_users.update(f"C{fila_idx}", [[str(nuevo_nombre).strip()]], value_input_option='RAW')
                if nueva_fecha is not None:
                    sheet_users.update(f"D{fila_idx}", [[str(nueva_fecha).strip()]], value_input_option='RAW')
                return True, "Datos actualizados correctamente."
        return False, "Usuario no encontrado."
    except Exception as e:
        return False, f"Error: {e}"


def parsear_fecha(valor):
    if not valor:
        return None
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None

# ==========================================================
# FUNCIONES AUXILIARES DE IMAGEN
# ==========================================================

def obtener_base64_imagen(ruta_archivo):
    if os.path.exists(ruta_archivo):
        with open(ruta_archivo, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    return ""

def buscar_logo(nombre_base):
    for ext in [".png", ".jpg", ".jpeg"]:
        ruta = nombre_base + ext
        if os.path.exists(ruta):
            return obtener_base64_imagen(ruta)
    return ""

# ==========================================================
# ACCESSGUDID — FUNCIÓN DE BÚSQUEDA POR REFERENCIA (extraída
# para poder paralelizarla con ThreadPoolExecutor y así acelerar
# la extracción masiva sin perder ninguna lógica existente)
# ==========================================================

def _buscar_referencia_accessgudid(ref, session, headers, company_names_filtro):
    """Busca una referencia en AccessGUDID y devuelve la lista de filas
    encontradas (puede ser más de un dispositivo, o una fila de aviso si
    no hay coincidencias / hubo error). Es la misma lógica que ya tenías,
    solo aislada en una función para poder ejecutarla en paralelo."""
    url_busqueda = f"https://accessgudid.nlm.nih.gov/devices/search?query={urllib.parse.quote(ref)}"
    try:
        response = session.get(url_busqueda, headers=headers, timeout=15)
        if response.status_code == 429:
            time.sleep(8)
            response = session.get(url_busqueda, headers=headers, timeout=15)

        if response.status_code != 200:
            return [{
                "Referencia_Original": ref, "Primary_DI_Number": "No encontrado",
                "Nombre_Empresa_FDA": "No encontrado", "Codigo_GMDN": "No encontrado",
                "Definicion_GMDN": "No encontrado", "Estado_GMDN": "No encontrado",
                "Issuing_Agency": "No encontrado"
            }]

        soup = BeautifulSoup(response.text, 'html.parser')
        enlaces = list(dict.fromkeys([
            a['href'] for a in soup.find_all('a', href=True)
            if '/devices/' in a['href'] and 'search' not in a['href']
        ]))
        coincidencias = []
        for href in enlaces:
            try:
                res = session.get(f"https://accessgudid.nlm.nih.gov{href}", headers=headers, timeout=15)
                if res.status_code != 200:
                    continue
                soup2 = BeautifulSoup(res.text, 'html.parser')
                texto = soup2.get_text()
                lineas = [l.strip() for l in texto.split('\n') if l.strip()]

                company = "No encontrado"
                for i2, l in enumerate(lineas):
                    if "Company Name" in l:
                        company = lineas[i2+1] if l.replace(":", "").strip() == "Company Name" and i2+1 < len(lineas) else l.replace("Company Name", "").replace(":", "").strip()
                        break
                company = " ".join(company.split()).strip() or "No encontrado"
                if company_names_filtro and not any(n in company.upper() for n in company_names_filtro):
                    continue

                gmdn_code = "No encontrado"
                for p in texto.replace(':', ' ').replace('(', ' ').replace(')', ' ').split():
                    if p.isdigit() and len(p) == 5:
                        gmdn_code = p
                        break

                gmdn_def, gmdn_status = "No encontrado", "No encontrado"
                for i2, l in enumerate(lineas):
                    if "GMDN Term Definition" in l:
                        candidatos = [
                            x.replace("[?]", "").strip() for x in lineas[i2:]
                            if x.replace("[?]", "").strip() and not any(
                                h in x for h in ["GMDN Term Code", "GMDN Term Name",
                                "GMDN Term Definition", "GMDN Term Status", "Implantable?"]
                            ) and not (x.strip().isdigit() and len(x.strip()) == 5)
                        ]
                        if len(candidatos) >= 2:
                            gmdn_def, gmdn_status = candidatos[1], candidatos[2] if len(candidatos) > 2 else candidatos[1]
                        elif len(candidatos) == 1:
                            gmdn_def = candidatos[0]
                        break

                diccionario_estados = {"active": "Activo", "obsolete": "Obsoleto", "no encontrado": "No encontrado"}
                gmdn_status = diccionario_estados.get(gmdn_status.lower(), gmdn_status)

                if gmdn_def and gmdn_def.lower() != "no encontrado":
                    gmdn_def = _traducir_gmdn_con_ia(gmdn_def.replace('"', '').replace("'", ""))

                issuing = "No encontrado"
                for i2, l in enumerate(lineas):
                    if "Issuing Agency" in l:
                        issuing = lineas[i2+1] if l.replace(":", "").strip() == "Issuing Agency" and i2+1 < len(lineas) else l.replace("Issuing Agency", "").replace(":", "").strip()
                        break
                issuing = " ".join(issuing.split()).strip() or "No encontrado"

                coincidencias.append({
                    "Referencia_Original": ref,
                    "Primary_DI_Number": href.split('/')[-1].strip(),
                    "Nombre_Empresa_FDA": company,
                    "Codigo_GMDN": gmdn_code,
                    "Definicion_GMDN": " ".join(str(gmdn_def).split()).strip(),
                    "Estado_GMDN": " ".join(str(gmdn_status).split()).strip(),
                    "Issuing_Agency": issuing
                })
            except Exception:
                continue

        if coincidencias:
            return coincidencias
        return [{
            "Referencia_Original": "Filtrado", "Primary_DI_Number": "Filtrado",
            "Nombre_Empresa_FDA": "No coincide", "Codigo_GMDN": "Filtrado",
            "Definicion_GMDN": "Filtrado", "Estado_GMDN": "Filtrado", "Issuing_Agency": "Filtrado"
        }]
    except Exception:
        return [{
            "Referencia_Original": ref, "Primary_DI_Number": "Error de Red",
            "Nombre_Empresa_FDA": "Error", "Codigo_GMDN": "Error",
            "Definicion_GMDN": "Error", "Estado_GMDN": "Error", "Issuing_Agency": "Error"
        }]


# ==========================================================
# FUNCIONES EUDAMED — VERSIÓN OPTIMIZADA
# ==========================================================

URL_EUDAMED_HOME = "https://ec.europa.eu/tools/eudamed/eudamed"
LIMITE_RESULTADOS_POR_REFERENCIA_EUDAMED = 15


def _clic_js(driver, elemento):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
    driver.execute_script("arguments[0].click();", elemento)


def _aceptar_cookies_eudamed(driver, espera=6):
    try:
        boton_cookies = WebDriverWait(driver, espera).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[normalize-space(text())='Accept all cookies'] "
                "| //button[normalize-space(text())='Accept only essential cookies'] "
                "| //button[contains(normalize-space(text()),'Accept')]"
            ))
        )
        _clic_js(driver, boton_cookies)
        try:
            WebDriverWait(driver, 6).until(
                EC.invisibility_of_element_located((
                    By.XPATH, "//*[contains(text(),'This site uses cookies')]"
                ))
            )
        except Exception:
            time.sleep(1.5)
    except Exception:
        pass


def _crear_driver_eudamed():
    opciones = webdriver.ChromeOptions()
    opciones.add_argument("--headless=new")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-dev-shm-usage")
    opciones.add_argument("--disable-gpu")
    opciones.add_argument("--window-size=1440,1000")
    opciones.add_argument("--lang=en-US")
    opciones.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    ruta_navegador = (
        shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    )
    if ruta_navegador:
        opciones.binary_location = ruta_navegador

    ruta_driver = shutil.which("chromedriver")
    try:
        if ruta_driver:
            servicio = Service(executable_path=ruta_driver)
            driver = webdriver.Chrome(service=servicio, options=opciones)
        else:
            driver = webdriver.Chrome(options=opciones)
    except Exception as e:
        raise RuntimeError(
            "No se pudo iniciar Chromium para Eudamed.\n"
            f"— Chromium detectado en: {ruta_navegador or 'NO ENCONTRADO'}\n"
            f"— Chromedriver detectado en: {ruta_driver or 'NO ENCONTRADO'}\n"
            f"— Error original de Selenium: {type(e).__name__}: {e}\n"
            "Verifica que el archivo 'packages.txt' del repositorio incluya las líneas "
            "'chromium' y 'chromium-driver', y que 'selenium' esté en requirements.txt."
        ) from e

    driver.set_page_load_timeout(45)
    return driver


def _esperar(driver, segundos=20):
    return WebDriverWait(driver, segundos)


def _poner_status_all_eudamed(driver):
    try:
        etiqueta_status = driver.find_element(By.XPATH, "//label[normalize-space(text())='Status']")
        contenedor = etiqueta_status.find_element(By.XPATH, "./..")
        control = contenedor.find_element(
            By.XPATH,
            ".//*[self::div or self::span or self::button]"
            "[contains(@class,'dropdown') or contains(@class,'select') or @role='combobox']"
        )
        _clic_js(driver, control)
        opcion_all = _esperar(driver, 8).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//li[normalize-space(text())='All'] | //*[@role='option'][normalize-space(text())='All']"
            ))
        )
        _clic_js(driver, opcion_all)
        time.sleep(0.4)
        return True
    except Exception:
        return False


def _iniciar_busqueda_eudamed(driver, referencia, primera_vez):
    if primera_vez:
        driver.get(URL_EUDAMED_HOME)
        _aceptar_cookies_eudamed(driver)
        enlace_devices = _esperar(driver, 30).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//a[normalize-space(text())='Devices, Systems, Procedure packs'] "
                "| //*[normalize-space(text())='Devices, Systems, Procedure packs']"
            ))
        )
        _clic_js(driver, enlace_devices)
    else:
        try:
            enlace_nueva = _esperar(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='New search']"))
            )
            _clic_js(driver, enlace_nueva)
        except TimeoutException:
            driver.get(URL_EUDAMED_HOME)
            _aceptar_cookies_eudamed(driver, espera=3)
            enlace_devices = _esperar(driver, 30).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//a[normalize-space(text())='Devices, Systems, Procedure packs'] "
                    "| //*[normalize-space(text())='Devices, Systems, Procedure packs']"
                ))
            )
            _clic_js(driver, enlace_devices)

    _esperar(driver, 25).until(
        EC.presence_of_element_located((
            By.XPATH, "//label[contains(., 'Reference') and contains(., 'Catalogue')]"
        ))
    )

    _aceptar_cookies_eudamed(driver, espera=2)
    _poner_status_all_eudamed(driver)

    campo_ref = _esperar(driver, 12).until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//label[contains(., 'Reference') and contains(., 'Catalogue')]/following::input[1]"
        ))
    )
    campo_ref.clear()
    campo_ref.send_keys(referencia)

    boton_buscar = _esperar(driver, 10).until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//label[contains(., 'Reference') and contains(., 'Catalogue')]"
            "/following::button[normalize-space(.)='Search'][1] "
            "| //label[contains(., 'Reference') and contains(., 'Catalogue')]"
            "/following::button[.//*[normalize-space(text())='Search']][1]"
        ))
    )
    _clic_js(driver, boton_buscar)

    _esperar(driver, 25).until(
        EC.any_of(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'records found')]")),
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'No record')]")),
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'0 records')]")),
        )
    )


def _contar_resultados_eudamed(driver):
    try:
        texto = driver.find_element(By.XPATH, "//*[contains(text(),'records found')]").text
        digitos = "".join(ch for ch in texto.split()[0] if ch.isdigit())
        return int(digitos) if digitos else 0
    except Exception:
        return 0


def _mensaje_error_limpio(e):
    texto = str(e).split("Stacktrace:")[0].strip()
    return texto if texto else type(e).__name__


def _obtener_valor_celda_detalle(driver, etiqueta):
    xpaths = [
        f"//tr[td[normalize-space(text())='{etiqueta}']]/td[2]",
        f"//tr[td[normalize-space(.)='{etiqueta}']]/td[last()]",
        f"//tr[th[normalize-space(text())='{etiqueta}']]/td[1]",
        f"//dt[normalize-space(text())='{etiqueta}']/following-sibling::dd[1]",
        f"//*[normalize-space(text())='{etiqueta}']/following-sibling::*[1]",
        f"//*[normalize-space(text())='{etiqueta}']/parent::*/following-sibling::*[1]",
        f"//*[contains(normalize-space(text()),'{etiqueta}')]/ancestor::tr[1]/td[last()]",
    ]
    for xp in xpaths:
        try:
            elementos = driver.find_elements(By.XPATH, xp)
            for el in elementos:
                texto = el.text.strip()
                if texto and texto != etiqueta:
                    return texto
        except Exception:
            continue
    return "No encontrado"


def _ir_a_seccion_eudamed_rapido(driver, nombre_seccion):
    xpaths = [
        f"//a[normalize-space(text())='{nombre_seccion}']",
        f"//li[contains(normalize-space(.),'{nombre_seccion}')]//a",
        f"//a[contains(normalize-space(text()),'{nombre_seccion}')]",
        f"//*[@role='tab'][contains(normalize-space(.),'{nombre_seccion}')]",
    ]
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xp)))
            _clic_js(driver, el)
            time.sleep(0.6)
            return
        except Exception:
            continue
    raise TimeoutException(f"Sección '{nombre_seccion}' no encontrada")


def _extraer_todo_del_detalle(driver):
    codigo_udi = _obtener_valor_celda_detalle(driver, "UDI-DI code")
    agencia    = _obtener_valor_celda_detalle(driver, "Issuing entity")
    nombre     = "No encontrado"
    fabricante = "No encontrado"

    for etiqueta in ["Device name", "Trade/proprietary name", "Trade name",
                     "Commercial name", "Device trade name", "Name"]:
        val = _obtener_valor_celda_detalle(driver, etiqueta)
        if val != "No encontrado":
            nombre = val
            break

    for etiqueta in ["Organisation name", "Manufacturer name", "Company name",
                     "Actor name", "Legal manufacturer", "Name"]:
        val = _obtener_valor_celda_detalle(driver, etiqueta)
        if val != "No encontrado" and val != nombre:
            fabricante = val
            break

    if nombre == "No encontrado":
        try:
            _ir_a_seccion_eudamed_rapido(driver, "Basic UDI-DI")
            for etiqueta in ["Device name", "Trade/proprietary name", "Trade name", "Name"]:
                val = _obtener_valor_celda_detalle(driver, etiqueta)
                if val != "No encontrado":
                    nombre = val
                    break
        except Exception:
            pass

    if fabricante == "No encontrado":
        try:
            _ir_a_seccion_eudamed_rapido(driver, "Manufacturer")
            for etiqueta in ["Organisation name", "Manufacturer name", "Company name", "Name"]:
                val = _obtener_valor_celda_detalle(driver, etiqueta)
                if val != "No encontrado" and val != nombre:
                    fabricante = val
                    break
        except Exception:
            pass

    if agencia == "No encontrado":
        for etiqueta in ["Issuing entity code", "Issuing Agency", "Issuing Entity"]:
            val = _obtener_valor_celda_detalle(driver, etiqueta)
            if val != "No encontrado":
                agencia = val
                break

    if codigo_udi == "No encontrado":
        combinado = _obtener_valor_celda_detalle(driver, "UDI-DI code / Issuing entity")
        if combinado != "No encontrado" and "/" in combinado:
            partes = [p.strip() for p in combinado.split("/")]
            codigo_udi = partes[0]
            if agencia == "No encontrado" and len(partes) > 1:
                agencia = partes[-1]
        elif combinado != "No encontrado":
            codigo_udi = combinado

    return codigo_udi, agencia, nombre, fabricante


def _procesar_referencia_eudamed(driver, referencia, primera_vez):
    try:
        _iniciar_busqueda_eudamed(driver, referencia, primera_vez)
    except TimeoutException as e:
        raise RuntimeError(
            f"Tiempo de espera agotado iniciando la búsqueda de '{referencia}': "
            f"{_mensaje_error_limpio(e)}"
        ) from e

    total = _contar_resultados_eudamed(driver)
    if total == 0:
        return [{
            "Referencia_Original": referencia,
            "Codigo_UDI_DI":       "Sin resultados",
            "Agencia_Emisora":     "Sin resultados",
            "Nombre_Dispositivo":  "Sin resultados",
            "Fabricante":          "Sin resultados",
        }]

    cantidad_a_procesar = min(total, LIMITE_RESULTADOS_POR_REFERENCIA_EUDAMED)
    filas_resultado = []

    for indice in range(cantidad_a_procesar):
        try:
            filas_tabla = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//table//tbody/tr"))
            )
            if indice >= len(filas_tabla):
                break

            try:
                celda_ver = filas_tabla[indice].find_element(
                    By.XPATH,
                    ".//td[last()]//button | .//td[last()]//a"
                    " | .//button[contains(normalize-space(.),'View')]"
                    " | .//a[contains(normalize-space(.),'View')]"
                )
            except Exception:
                celda_ver = filas_tabla[indice]

            _clic_js(driver, celda_ver)

            WebDriverWait(driver, 12).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'UDI-DI')]")),
                    EC.presence_of_element_located((By.XPATH, "//table")),
                )
            )
            _aceptar_cookies_eudamed(driver, espera=2)
            time.sleep(0.35)

            codigo_udi, agencia, nombre_dispositivo, fabricante = _extraer_todo_del_detalle(driver)

            filas_resultado.append({
                "Referencia_Original": referencia,
                "Codigo_UDI_DI":       codigo_udi,
                "Agencia_Emisora":     agencia,
                "Nombre_Dispositivo":  nombre_dispositivo,
                "Fabricante":          fabricante,
            })

            try:
                driver.back()
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, "//table//tbody/tr"))
                )
            except Exception:
                try:
                    _iniciar_busqueda_eudamed(driver, referencia, primera_vez=False)
                except Exception:
                    break

        except Exception as e:
            filas_resultado.append({
                "Referencia_Original": referencia,
                "Codigo_UDI_DI":       "Error",
                "Agencia_Emisora":     "Error",
                "Nombre_Dispositivo":  "Error",
                "Fabricante":          f"Error: {_mensaje_error_limpio(e)}",
            })
            try:
                driver.back()
                time.sleep(0.4)
            except Exception:
                pass
            try:
                _iniciar_busqueda_eudamed(driver, referencia, primera_vez=False)
            except Exception:
                break

    return filas_resultado


# ==========================================================
# FUNCIONES DE IA (GEMINI) — más robustas: reintentan también
# ante errores de red (no solo 503/429), avisan si la respuesta
# viene vacía por el filtro de seguridad de Gemini, y usan más
# tokens de margen para que las respuestas no queden a la mitad.
# ==========================================================

MODELO_IA_RAPIDO  = "gemini-2.5-flash"
MODELO_IA_CALIDAD = "gemini-2.5-flash"


def _obtener_api_key_gemini():
    try:
        return st.secrets["gemini"]["api_key"]
    except Exception:
        try:
            return st.secrets["GEMINI_API_KEY"]
        except Exception:
            return None


def _llamar_gemini_api(system_prompt, mensajes, modelo=MODELO_IA_CALIDAD, max_tokens=900):
    """Llama a la API de Gemini. Reintenta automáticamente ante:
    - Errores de red/timeout (problemas de conexión transitorios)
    - 503 (modelo saturado) y 429 (límite de tasa)
    Y revisa explícitamente el motivo de finalización de la respuesta,
    para poder avisar con un mensaje claro si Gemini bloqueó la
    respuesta por su filtro de seguridad en vez de devolver texto vacío
    sin explicación (una de las causas de 'preguntas que fallan')."""
    api_key = _obtener_api_key_gemini()
    if not api_key:
        raise RuntimeError(
            "No hay una API key de Gemini configurada. Consíguela gratis en "
            "https://aistudio.google.com/apikey y agrégala en Settings → "
            "Secrets de Streamlit Cloud, así:\n"
            "[gemini]\napi_key = \"tu-clave-aqui\""
        )

    contenidos = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in mensajes
    ]

    cuerpo = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contenidos,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    headers = {"x-goog-api-key": api_key, "content-type": "application/json"}

    intentos = 4
    ultimo_error = None
    respuesta = None
    for intento in range(intentos):
        try:
            respuesta = requests.post(url, headers=headers, json=cuerpo, timeout=45)
        except requests.exceptions.RequestException as e:
            ultimo_error = e
            if intento < intentos - 1:
                time.sleep(2 * (intento + 1))
                continue
            raise RuntimeError(f"Error de red llamando a Gemini: {e}") from e

        if respuesta.status_code == 200:
            break
        if respuesta.status_code in (503, 429) and intento < intentos - 1:
            time.sleep(3 * (intento + 1))
            continue
        break

    if respuesta is None:
        raise RuntimeError(f"No se pudo contactar a Gemini: {ultimo_error}")

    if respuesta.status_code != 200:
        raise RuntimeError(
            f"Error de la API de Gemini (código {respuesta.status_code}): "
            f"{respuesta.text[:300]}"
        )

    datos = respuesta.json()
    candidatos = datos.get("candidates") or []
    if not candidatos:
        razon_bloqueo = (datos.get("promptFeedback") or {}).get("blockReason", "desconocida")
        raise RuntimeError(
            f"Gemini no devolvió respuesta (motivo: {razon_bloqueo}). "
            "Intenta reformular la pregunta."
        )

    finish_reason = candidatos[0].get("finishReason", "")
    partes = candidatos[0].get("content", {}).get("parts", [])
    texto = "".join(p.get("text", "") for p in partes).strip()

    if not texto and finish_reason == "SAFETY":
        raise RuntimeError("Gemini bloqueó esta respuesta por su filtro de seguridad.")
    if not texto and finish_reason == "MAX_TOKENS":
        raise RuntimeError("La respuesta quedó incompleta por límite de tokens. Intenta de nuevo.")

    return texto


def _traducir_gmdn_con_ia(texto_ingles):
    texto_ingles = (texto_ingles or "").strip()
    if not texto_ingles or texto_ingles.lower() == "no encontrado":
        return texto_ingles
    try:
        traduccion = _llamar_gemini_api(
            system_prompt=(
                "Eres un traductor especializado en terminología médica de "
                "dispositivos (nomenclatura GMDN). Traduce el siguiente texto "
                "del inglés al español de forma precisa y natural. Responde "
                "ÚNICAMENTE con la traducción, sin comillas ni comentarios."
            ),
            mensajes=[{"role": "user", "content": texto_ingles}],
            modelo=MODELO_IA_RAPIDO,
            max_tokens=400,
        )
        return traduccion if traduccion else texto_ingles
    except Exception:
        return texto_ingles


def _generar_resumen_ia(df, etiqueta_fuente):
    if df is None or df.empty:
        return "No hay datos para resumir."
    texto_datos = df.to_csv(index=False)
    if len(texto_datos) > 12000:
        texto_datos = texto_datos[:12000] + "\n... (datos truncados por espacio)"
    return _llamar_gemini_api(
        system_prompt=(
            f"Eres un analista que resume datos de dispositivos médicos "
            f"extraídos de {etiqueta_fuente}. Con la tabla en formato CSV que "
            "se te entrega a continuación, escribe un resumen breve en "
            "español (máximo 8 líneas, en viñetas) destacando: fabricantes "
            "más frecuentes, posibles duplicados o inconsistencias, y "
            "cuántos registros quedaron sin encontrar o con error. No "
            "inventes datos que no estén en la tabla."
        ),
        mensajes=[{"role": "user", "content": texto_datos}],
        modelo=MODELO_IA_CALIDAD,
        max_tokens=700,
    )


def _obtener_o_crear_hoja(nombre_hoja, encabezados):
    client = get_gspread_client()
    doc = client.open_by_key(SHEET_ID)
    try:
        hoja = doc.worksheet(nombre_hoja)
    except Exception:
        hoja = doc.add_worksheet(title=nombre_hoja, rows=2000, cols=len(encabezados) + 2)
        hoja.append_row(encabezados, value_input_option='RAW')
    return hoja


def guardar_resultados_accessgudid(usuario, filas):
    if not filas:
        return
    try:
        encabezados = ["Fecha", "Usuario", "Referencia_Original", "Primary_DI_Number",
                       "Nombre_Empresa_FDA", "Codigo_GMDN", "Definicion_GMDN",
                       "Estado_GMDN", "Issuing_Agency"]
        hoja = _obtener_o_crear_hoja("ResultadosAccessGudid", encabezados)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filas_excel = [
            [timestamp, usuario,
             f.get("Referencia_Original", ""), f.get("Primary_DI_Number", ""),
             f.get("Nombre_Empresa_FDA", ""), f.get("Codigo_GMDN", ""),
             f.get("Definicion_GMDN", ""), f.get("Estado_GMDN", ""),
             f.get("Issuing_Agency", "")]
            for f in filas
        ]
        hoja.append_rows(filas_excel, value_input_option='RAW')
    except Exception as e:
        st.warning(f"No se pudieron guardar los resultados en el histórico de Google Sheets: {e}")


def guardar_resultados_eudamed(usuario, filas):
    if not filas:
        return
    try:
        encabezados = ["Fecha", "Usuario", "Referencia_Original", "Codigo_UDI_DI",
                       "Agencia_Emisora", "Nombre_Dispositivo", "Fabricante"]
        hoja = _obtener_o_crear_hoja("ResultadosEudamed", encabezados)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filas_excel = [
            [timestamp, usuario,
             f.get("Referencia_Original", ""), f.get("Codigo_UDI_DI", ""),
             f.get("Agencia_Emisora", ""), f.get("Nombre_Dispositivo", ""),
             f.get("Fabricante", "")]
            for f in filas
        ]
        hoja.append_rows(filas_excel, value_input_option='RAW')
    except Exception as e:
        st.warning(f"No se pudieron guardar los resultados en el histórico de Google Sheets: {e}")


def _construir_contexto_chat_ia():
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        partes = []
        for nombre_hoja, max_filas in [("Logs", 150), ("ResultadosAccessGudid", 300), ("ResultadosEudamed", 300)]:
            try:
                hoja = doc.worksheet(nombre_hoja)
                datos = hoja.get_all_values()
                if len(datos) > 1:
                    encabezado, filas = datos[0], datos[1:][-max_filas:]
                    texto_tabla = " | ".join(encabezado) + "\n"
                    texto_tabla += "\n".join(" | ".join(f) for f in filas)
                    partes.append(f"### Hoja: {nombre_hoja} (mostrando {len(filas)} filas más recientes)\n{texto_tabla}")
            except Exception:
                continue
        return "\n\n".join(partes) if partes else "Todavía no hay datos históricos guardados."
    except Exception as e:
        return f"(No se pudo cargar el contexto desde Google Sheets: {e})"


def _responder_chat_ia(pregunta):
    if st.session_state.get("contexto_chat_ia") is None:
        with st.spinner("Cargando datos históricos..."):
            st.session_state["contexto_chat_ia"] = _construir_contexto_chat_ia()

    system_prompt = (
        "Eres el asistente de la plataforma 'Oficina Virtual de Dispositivos "
        "Médicos'. Ayudas a interpretar datos de dispositivos médicos "
        "extraídos de AccessGUDID (FDA) y Eudamed (UE). Responde siempre en "
        "español, de forma breve y concreta, basándote ÚNICAMENTE en los "
        "datos proporcionados a continuación. Si la respuesta no se puede "
        "deducir de estos datos, dilo claramente en vez de inventar.\n\n"
        f"DATOS DISPONIBLES:\n{st.session_state['contexto_chat_ia']}"
    )
    historial_reciente = st.session_state["historial_chat_ia"][-8:]
    mensajes = historial_reciente + [{"role": "user", "content": pregunta}]
    return _llamar_gemini_api(system_prompt, mensajes, modelo=MODELO_IA_CALIDAD, max_tokens=900)


# ==========================================================
# ASISTENTE IA — POPOVER CON BURBUJAS DE CHAT
# ==========================================================
def _renderizar_asistente_popover_ia():
    with st.popover("🤖 Asistente IA", use_container_width=True):
        st.caption("Pregunta sobre tu historial y resultados extraídos.")

        with st.container(height=300):
            if not st.session_state["historial_chat_ia"]:
                st.caption("👋 Aún no hay mensajes. ¡Hazme una pregunta!")
            for m in st.session_state["historial_chat_ia"]:
                if m["role"] == "user":
                    st.markdown(
                        f"""
                        <div style="display:flex;justify-content:flex-end;margin-bottom:10px;">
                            <div style="
                                background-color:#1a365d;
                                color:#ffffff;
                                border-radius:14px 14px 2px 14px;
                                padding:9px 14px;
                                max-width:85%;
                                font-size:13px;
                                line-height:1.5;
                                box-shadow:0 1px 3px rgba(0,0,0,0.18);">
                                <span style="
                                    font-size:10px;
                                    font-weight:700;
                                    opacity:0.80;
                                    display:block;
                                    margin-bottom:4px;
                                    text-align:right;
                                    letter-spacing:0.4px;">
                                    👤 TÚ
                                </span>
                                {m["content"]}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"""
                        <div style="display:flex;justify-content:flex-start;margin-bottom:10px;">
                            <div style="
                                background-color:#f1f5f9;
                                color:#1e293b;
                                border-radius:14px 14px 14px 2px;
                                padding:9px 14px;
                                max-width:85%;
                                font-size:13px;
                                line-height:1.5;
                                border:1px solid #e2e8f0;
                                box-shadow:0 1px 3px rgba(0,0,0,0.07);">
                                <span style="
                                    font-size:10px;
                                    font-weight:700;
                                    color:#1a365d;
                                    display:block;
                                    margin-bottom:4px;
                                    letter-spacing:0.4px;">
                                    🤖 ASISTENTE IA
                                </span>
                                {m["content"]}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

        with st.form(key="form_chat_ia", clear_on_submit=True):
            pregunta_ia = st.text_input(
                "Pregunta", key="txt_chat_ia", label_visibility="collapsed",
                placeholder="Ej: ¿qué fabricantes se repiten más?"
            )
            enviado_ia = st.form_submit_button("Enviar", use_container_width=True)

        if enviado_ia and pregunta_ia.strip():
            st.session_state["historial_chat_ia"].append({"role": "user", "content": pregunta_ia.strip()})
            try:
                with st.spinner("Pensando..."):
                    respuesta_ia = _responder_chat_ia(pregunta_ia.strip())
            except Exception as e:
                respuesta_ia = f"⚠️ No se pudo responder: {e}"
            st.session_state["historial_chat_ia"].append({"role": "assistant", "content": respuesta_ia})
            st.rerun()

# ==========================================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================================
st.set_page_config(page_title="Extractor AccessGUDID FDA", page_icon="🔬", layout="wide")

b64_gudid   = buscar_logo("logo_gudid")
b64_invima  = buscar_logo("logo_invima")
b64_eudamed = buscar_logo("logo_eudamed")
b64_gmdn    = buscar_logo("logo_gmdn")
b64_fda     = buscar_logo("logo_fda")

# ==========================================================
# INICIALIZACIÓN DE SESSION STATE
# ==========================================================
if "autenticado"             not in st.session_state: st.session_state["autenticado"]             = False
if "usuario_guardado"        not in st.session_state: st.session_state["usuario_guardado"]        = ""
if "usuario_activo_real"     not in st.session_state: st.session_state["usuario_activo_real"]     = ""
if "seccion_activa"          not in st.session_state: st.session_state["seccion_activa"]          = "Inicio"
if "lista_filtros_company"   not in st.session_state: st.session_state["lista_filtros_company"]   = [""]
if "mostrar_modal_perfil"    not in st.session_state: st.session_state["mostrar_modal_perfil"]    = False
if "historial_chat_ia"       not in st.session_state: st.session_state["historial_chat_ia"]       = []
if "contexto_chat_ia"        not in st.session_state: st.session_state["contexto_chat_ia"]        = None
if "eudamed_iniciar"         not in st.session_state: st.session_state["eudamed_iniciar"]         = False
if "eudamed_archivo_bytes"   not in st.session_state: st.session_state["eudamed_archivo_bytes"]   = None
if "eudamed_archivo_nombre"  not in st.session_state: st.session_state["eudamed_archivo_nombre"]  = ""

# ==========================================================
# CSS GLOBAL (LOGIN + INTERIOR)
# ==========================================================
CSS_GLOBAL = """
<style>
[data-testid="stSidebar"] {
    display: flex !important;
    visibility: visible !important;
    transform: none !important;
    min-width: 260px !important;
    width: 260px !important;
    margin-left: 0px !important;
    position: relative !important;
    background-color: #0b1d3a !important;
    border-right: 1px solid #061122 !important;
}
[data-testid="stSidebar"][aria-expanded="false"] {
    min-width: 260px !important;
    width: 260px !important;
    margin-left: 0px !important;
}
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
    display: flex !important;
    visibility: visible !important;
}
[data-testid="stSidebar"] *:not(button):not(button *) {
    color: #ffffff !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea {
    color: #1e293b !important;
    background-color: #ffffff !important;
}
[data-testid="stSidebar"] input::placeholder,
[data-testid="stSidebar"] textarea::placeholder {
    color: #94a3b8 !important;
}
[data-testid="stSidebar"] [data-baseweb="base-input"],
[data-testid="stSidebar"] [data-baseweb="base-input"] > div {
    background-color: #ffffff !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background-color: #f8fafc !important;
    border-radius: 8px !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] *:not(button):not(button *):not(input):not(textarea) {
    color: #1e293b !important;
}
[data-testid="stSidebar"] button {
    background-color: #1a365d !important;
    color: #ffffff !important;
    border: 1px solid #2a4d7c !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] button:hover { background-color: #2a4d7c !important; }
[data-testid="stSidebar"] button p,
[data-testid="stSidebar"] button span { color: #ffffff !important; }

.sidebar-header {
    text-align: center; padding: 15px 10px; margin-bottom: 20px;
    color: #ffffff; font-size: 19px; font-weight: 700;
    border-bottom: 1px solid rgba(255,255,255,0.15);
}

.stApp { background-color: #f0f4f8 !important; }
section.main { background-color: #f0f4f8 !important; }

footer, #MainMenu, [data-testid="stToolbar"] {
    visibility: hidden !important; display: none !important;
}
header[data-testid="stHeader"] {
    background-color: transparent !important;
    height: 3rem !important;
    box-shadow: none !important;
}

section.main p, section.main span, section.main label,
section.main h1, section.main h2, section.main h3,
section.main h4, section.main h5, section.main h6 {
    color: #1e293b !important;
}

.stButton > button,
.stDownloadButton > button,
section.main button {
    background-color: #1a365d !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
section.main button:hover { background-color: #2a4d7c !important; color: #ffffff !important; }
.stButton > button:active, section.main button:active { background-color: #0b1d3a !important; color: #ffffff !important; }
.stButton > button:focus, section.main button:focus { background-color: #1a365d !important; color: #ffffff !important; }
.stButton > button:disabled, section.main button:disabled {
    background-color: #94a3b8 !important; color: #e2e8f0 !important; opacity: 0.7 !important;
}
section.main button p, section.main button span,
.stButton > button p, .stButton > button span { color: #ffffff !important; }

section.main input[type="text"],
section.main input[type="password"],
section.main input[type="number"] {
    background-color: #ffffff !important; color: #1e293b !important;
    border: 1.5px solid #cbd5e1 !important; border-radius: 7px !important;
}
section.main [data-baseweb="base-input"],
section.main [data-baseweb="input"] > div {
    background-color: #ffffff !important; border-color: #cbd5e1 !important;
}
div[data-baseweb="base-input"] { background-color: white !important; }
div[data-baseweb="base-input"] > div { background-color: white !important; }
div[data-baseweb="base-input"] input { background-color: white !important; color: #1e293b !important; }
section.main input::placeholder { color: #94a3b8 !important; }
section.main label { color: #374151 !important; }

div[data-baseweb="select"] > div:first-child {
    background-color: white !important; border-color: #cbd5e1 !important;
}
div[data-baseweb="select"] div { background-color: white !important; color: #1e293b !important; }
div[data-baseweb="select"] span { color: #1e293b !important; }
[data-baseweb="select"] svg { fill: #374151 !important; }

[data-testid="stDateInput"] > div,
[data-testid="stDateInput"] > div > div,
[data-testid="stDateInput"] input {
    background-color: #ffffff !important; color: #1e293b !important; border-color: #cbd5e1 !important;
}

[data-baseweb="popover"] div, [data-baseweb="menu"] ul,
ul[role="listbox"] { background-color: white !important; }
li[role="option"] { background-color: white !important; color: #1e293b !important; }
li[role="option"]:hover { background-color: #eff6ff !important; }

section.main [data-baseweb="base-input"] button,
section.main [data-baseweb="input"] button {
    background-color: #1a365d !important; border: none !important;
    width: 42px !important; min-width: 42px !important; height: 100% !important;
    padding: 0 !important; margin: 0 !important; border-radius: 0 !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
}
section.main [data-baseweb="base-input"] button svg,
section.main [data-baseweb="input"] button svg { fill: #ffffff !important; width: 17px !important; height: 17px !important; }
section.main [data-baseweb="base-input"] button:hover,
section.main [data-baseweb="input"] button:hover { background-color: #2a4d7c !important; }

div[data-testid="stFileUploadDropzone"] {
    background-color: #eef2ff !important;
    border: 2px dashed #1a365d !important; border-radius: 8px !important;
}
div[data-testid="stFileUploadDropzone"] > div { background-color: #eef2ff !important; }
div[data-testid="stFileUploadDropzone"] * { color: #374151 !important; }
div[data-testid="stFileUploadDropzone"] button {
    background-color: #1a365d !important; color: white !important;
    border-radius: 6px !important; border: none !important;
}
div[data-testid="stFileUploadDropzone"] button * { color: white !important; }

[data-testid="stMetric"] {
    background-color: #ffffff !important; border-radius: 10px !important;
    padding: 14px 18px !important; border: 1px solid #dce4f5 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}
[data-testid="stMetricLabel"] p { color: #374151 !important; }
[data-testid="stMetricValue"] { color: #0b1d3a !important; }

.prog-wrap {
    width: 100%; background-color: #e2e8f0; border: 2px solid #1e40af;
    border-radius: 8px; padding: 3px; height: 30px; overflow: hidden; margin: 14px 0;
}
.prog-bar {
    height: 100%; border-radius: 5px;
    background-image: repeating-linear-gradient(-45deg, #1e40af, #1e40af 12px, #e2e8f0 12px, #e2e8f0 18px);
    transition: width 0.2s ease-in-out;
}

.header-box {
    background-color: #ffffff !important;
    padding: 12px 24px; border-radius: 10px;
    box-shadow: 0px 2px 8px rgba(0,0,0,0.07);
    margin-bottom: 22px;
    display: flex; justify-content: space-between; align-items: center; gap: 12px;
}
.header-titulo { color: #0b1d3a !important; font-size: 20px; font-weight: 700; margin: 0; }
.header-right { display: flex; align-items: center; gap: 10px; }
.user-pill {
    font-size: 13px; color: #0b1d3a !important;
    background-color: #eff6ff !important;
    padding: 7px 15px; border-radius: 20px;
    border: 1px solid #bfdbfe !important; font-weight: 500;
    white-space: nowrap; display: inline-flex; align-items: center; gap: 6px;
}
.badge-admin {
    font-size: 10px; color: #ffffff !important;
    background-color: #dc2626 !important;
    padding: 2px 8px; border-radius: 10px;
    font-weight: 700; letter-spacing: 0.4px;
}
.btn-perfil-header > button,
.btn-inicio-header > button {
    background-color: #0b1d3a !important;
    color: #ffffff !important;
    border: 2px solid #2a4d7c !important;
    border-radius: 20px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 6px 16px !important;
    white-space: nowrap !important;
}
.btn-perfil-header > button:hover,
.btn-inicio-header > button:hover { background-color: #1a365d !important; }
.btn-perfil-header > button p,
.btn-perfil-header > button span,
.btn-inicio-header > button p,
.btn-inicio-header > button span { color: #ffffff !important; }

.card-azul {
    background-color: #ffffff !important; padding: 22px; border-radius: 12px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.06); border-left: 5px solid #0b1d3a; margin-bottom: 16px;
}
.card-azul h4 { color: #0b1d3a !important; font-size: 15px !important; font-weight: 700 !important; margin: 0 0 6px 0 !important; }
.card-azul p  { color: #475569 !important; font-size: 13px !important; margin: 0 !important; }

.card-roja {
    background-color: #fff5f5 !important; padding: 22px; border-radius: 12px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.06); border-left: 5px solid #dc2626; margin-bottom: 16px;
}
.card-roja h4 { color: #991b1b !important; font-size: 15px !important; font-weight: 700 !important; margin: 0 0 6px 0 !important; }
.card-roja p  { color: #475569 !important; font-size: 13px !important; margin: 0 !important; }

.admin-card {
    background-color: #ffffff !important; border-radius: 12px !important;
    padding: 22px !important; box-shadow: 0 3px 10px rgba(0,0,0,0.07) !important;
    border-top: 4px solid #dc2626 !important; margin-bottom: 20px !important;
}
.admin-card-title { color: #991b1b !important; font-size: 15px !important; font-weight: 700 !important; margin: 0 0 16px 0 !important; display: block; }

.perfil-card {
    background-color: #ffffff !important; border-radius: 12px !important;
    padding: 22px !important; box-shadow: 0 3px 10px rgba(0,0,0,0.07) !important;
    border-top: 4px solid #0b1d3a !important; margin-bottom: 20px !important;
}
.perfil-card-title { color: #0b1d3a !important; font-size: 15px !important; font-weight: 700 !important; margin: 0 0 16px 0 !important; display: block; }

.tabla-usr {
    width: 100%; border-collapse: collapse; border-radius: 8px;
    overflow: hidden; border: 1px solid #e2e8f0; margin-top: 8px;
}
.tabla-usr th {
    background-color: #0b1d3a !important; color: #ffffff !important;
    padding: 10px 14px; font-size: 13px; text-align: left;
}
.tabla-usr td {
    padding: 9px 14px; font-size: 13px; color: #1e293b !important;
    border-bottom: 1px solid #e2e8f0; background-color: #ffffff !important;
}
.tabla-usr tr:last-child td { border-bottom: none; }
.tabla-usr tr:hover td { background-color: #eff6ff !important; }
.meta-txt { color: #64748b !important; font-size: 12px; margin-top: 8px; }

.footer-box {
    margin-top: 50px; padding: 22px 0;
    border-top: 1px solid #e2e8f0; text-align: center; font-size: 13px;
}
.footer-box p, .footer-box a, .footer-box span { color: #64748b !important; }
.footer-links { display: flex; justify-content: center; gap: 28px; margin-bottom: 8px; flex-wrap: wrap; }
.footer-links a { color: #0b1d3a !important; text-decoration: none; font-weight: 500; }

.col-extraccion-titulo {
    background-color: #ffffff !important; padding: 14px 18px; border-radius: 10px 10px 0 0;
    border-bottom: 3px solid #1a365d; margin-bottom: 14px; font-weight: 700; font-size: 16px;
    color: #0b1d3a !important; display:flex; align-items:center; gap:8px;
}
.col-extraccion-titulo.eudamed { border-bottom-color: #0e7490; }

@media (max-width: 768px) {
    .header-box { flex-direction: column !important; gap: 8px !important; padding: 12px !important; text-align: center !important; }
    .header-right { flex-wrap: wrap; justify-content: center; }
    .header-titulo { font-size: 15px !important; }
    .user-pill { font-size: 11px !important; }
    .card-azul, .card-roja, .admin-card, .perfil-card { padding: 14px !important; }
    [data-testid="stSidebar"] { min-width: 220px !important; width: 220px !important; }
}

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
"""

CSS_LOGIN = """
<style>
.stApp {
    background-image: linear-gradient(rgba(15,32,67,0.65), rgba(15,32,67,0.85)),
                      url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070');
    background-size: cover; background-position: center; background-attachment: fixed;
}
header, footer, [data-testid="stSidebar"], #MainMenu {
    visibility: hidden !important; display: none !important;
}
div[data-testid="stForm"] {
    background-color: #ffffff !important; border-radius: 16px !important;
    padding: 40px 36px !important; box-shadow: 0px 12px 40px rgba(0,0,0,0.35) !important;
    max-width: 480px !important; margin: 0 auto !important;
}
div[data-testid="stForm"] label,
div[data-testid="stForm"] p,
div[data-testid="stForm"] span:not([data-baseweb]) { color: #1a1a2e !important; }
div[data-testid="stForm"] input {
    background-color: #f8fafc !important; color: #1a1a2e !important;
    border: 1.5px solid #cbd5e1 !important; border-radius: 8px !important;
}
div[data-testid="stForm"] input::placeholder { color: #94a3b8 !important; }
div[data-testid="stForm"] [data-baseweb="base-input"] {
    border-radius: 8px !important; overflow: hidden !important;
    background-color: #f8fafc !important; border: 1.5px solid #cbd5e1 !important;
}
div[data-testid="stForm"] [data-baseweb="base-input"] > div { background-color: transparent !important; }
div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button,
div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button p,
div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button span {
    background-color: #1a365d !important; color: #ffffff !important; font-weight: 700 !important;
}
div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button:hover { background-color: #2a4d7c !important; }
div[data-testid="stForm"] [data-baseweb="checkbox"] p,
div[data-testid="stForm"] [data-baseweb="checkbox"] label { color: #374151 !important; }
div[data-testid="stPasswordInput"] button {
    background-color: #1a365d !important; border: none !important;
    width: 42px !important; height: 100% !important; padding: 0 !important; margin: 0 !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
}
div[data-testid="stPasswordInput"] button svg,
div[data-testid="stPasswordInput"] button svg path { fill: #ffffff !important; stroke: #ffffff !important; }
div[data-testid="stPasswordInput"] button:hover { background-color: #2a4d7c !important; }

.contenedor-logos-principales {
    display: flex; justify-content: center; align-items: center;
    gap: 20px; margin-bottom: 24px; height: 70px;
}
.logo-header-invima { height: 72px !important; width: auto !important; object-fit: contain; }
.logo-header-fda    { height: 46px !important; width: auto !important; object-fit: contain; }
.barra-sep { width: 3px; height: 55px; background-color: #00b4d8; border-radius: 2px; }
.login-title  { color: #0b1d3a !important; font-size: 22px; font-weight: 700; text-align: center; margin-bottom: 4px; }
.login-desc   { color: #64748b !important; font-size: 13px; text-align: center; margin-bottom: 20px; }
.soporte-inferior { border-top: 1px solid #e2e8f0; margin-top: 28px; padding-top: 20px; }
.soporte-titulo { font-size: 11px; font-weight: 700; color: #94a3b8 !important; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.5px; }
.fila-logos { display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 10px; }
.logo-gudid   { height: 126px !important; width: auto !important; object-fit: contain; max-width: 220px !important; }
.logo-eudamed { height: 126px !important; width: auto !important; object-fit: contain; max-width: 220px !important; }
.logo-gmdn    { height: 63px  !important; width: auto !important; object-fit: contain; max-width: 220px !important; }
@media (max-width: 768px) {
    div[data-testid="stForm"] { padding: 24px 16px !important; margin: 0 6px !important; }
    .logo-header-invima { height: 48px !important; }
    .logo-header-fda    { height: 30px !important; }
    .login-title { font-size: 18px !important; }
    .fila-logos { gap: 8px !important; }
    .logo-gudid, .logo-eudamed { height: 80px !important; }
    .logo-gmdn { height: 42px !important; }
}
</style>
"""

# ==========================================================
# PANTALLA DE LOGIN
# ==========================================================
if not st.session_state["autenticado"]:
    st.markdown(CSS_LOGIN, unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1.4, 1])

    with col_centro:
        with st.form("formulario_login", clear_on_submit=False):
            html_cab = '<div class="contenedor-logos-principales">'
            if b64_invima: html_cab += f'<img class="logo-header-invima" src="data:image/png;base64,{b64_invima}">'
            html_cab += '<div class="barra-sep"></div>'
            if b64_fda:    html_cab += f'<img class="logo-header-fda" src="data:image/png;base64,{b64_fda}">'
            html_cab += '</div>'
            st.markdown(html_cab, unsafe_allow_html=True)

            st.markdown("<div class='login-title'>Plataforma de Extracción</div>", unsafe_allow_html=True)
            st.markdown("<div class='login-desc'>Gestión Automatizada de Dispositivos Médicos</div>", unsafe_allow_html=True)

            usuario    = st.text_input("Nombre de usuario", value=st.session_state["usuario_guardado"], placeholder="Introduzca su usuario").strip()
            contraseña = st.text_input("Contraseña", type="password", placeholder="Introduzca su contraseña")
            recordar   = st.checkbox("Recordar mi usuario en este equipo", value=(st.session_state["usuario_guardado"] != ""))
            boton_ingresar = st.form_submit_button("Acceder", use_container_width=True)

            html_sop = '<div class="soporte-inferior"><div class="soporte-titulo">Bases de datos vinculadas</div><div class="fila-logos">'
            if b64_gudid:   html_sop += f'<img class="logo-gudid"   src="data:image/png;base64,{b64_gudid}">'
            if b64_eudamed: html_sop += f'<img class="logo-eudamed" src="data:image/png;base64,{b64_eudamed}">'
            if b64_gmdn:    html_sop += f'<img class="logo-gmdn"    src="data:image/png;base64,{b64_gmdn}">'
            html_sop += '</div></div>'
            st.markdown(html_sop, unsafe_allow_html=True)

            if boton_ingresar:
                if not usuario or not contraseña:
                    st.warning("Por favor complete todos los campos.")
                elif validar_usuario(usuario, contraseña):
                    st.session_state["autenticado"]         = True
                    st.session_state["usuario_activo_real"] = usuario
                    st.session_state["usuario_guardado"]    = usuario if recordar else ""
                    st.success("✔ Credenciales válidas. Accediendo...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
    st.stop()

# ==========================================================
# INTERFAZ INTERNA (usuario autenticado)
# ==========================================================
else:
    st.markdown(CSS_GLOBAL, unsafe_allow_html=True)

    es_admin = st.session_state["usuario_activo_real"].strip().lower() == ADMIN_USER.lower()
    usuario_sesion = st.session_state["usuario_activo_real"]

    # ── SIDEBAR ──────────────────────────────────────────
    with st.sidebar:
        st.markdown('<div class="sidebar-header">⚙️ Opciones del Sistema</div>', unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#94a3b8;font-size:10px;text-transform:uppercase;"
            "font-weight:700;margin:0 0 10px 5px;letter-spacing:0.5px;'>Navegación</p>",
            unsafe_allow_html=True
        )

        nav_items = [
            ("🏠 Menú Principal",       "Inicio"),
            ("🚀 Extracción Masiva",     "ExtraccionMasiva"),
            ("📋 Historiales y Reportes", "Historiales"),
        ]
        for label, seccion in nav_items:
            if st.button(label, key=f"nav_{seccion}", use_container_width=True):
                st.session_state["seccion_activa"] = seccion
                st.rerun()
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if es_admin:
            st.markdown(
                "<hr style='border-color:rgba(255,255,255,0.15);margin:16px 0 10px;'>",
                unsafe_allow_html=True
            )
            st.markdown(
                "<p style='color:#fca5a5;font-size:10px;text-transform:uppercase;"
                "font-weight:700;margin:0 0 8px 5px;'>Administración</p>",
                unsafe_allow_html=True
            )
            if st.button("👥 Panel de Administración", key="nav_Admin", use_container_width=True):
                st.session_state["seccion_activa"] = "Admin"
                st.rerun()

        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("🚪 Cerrar Sesión", key="btn_cerrar_sesion", use_container_width=True):
            st.session_state["autenticado"] = False
            st.rerun()

    # ── HEADER ──────────────────────────────────────────
    badge = '<span class="badge-admin">ADMIN</span>' if es_admin else ""

    col_titulo, col_inicio_btn, col_perfil_btn, col_ia_btn = st.columns([3.6, 1, 1, 1.3])
    with col_titulo:
        st.markdown(
            f'<div style="background:#ffffff;padding:12px 24px;border-radius:10px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,0.07);margin-bottom:22px;'
            f'display:flex;align-items:center;justify-content:space-between;">'
            f'<span class="header-titulo">Oficina Virtual de Dispositivos Médicos</span>'
            f'<span class="user-pill">👤 <b>{usuario_sesion}</b>{badge}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
    with col_inicio_btn:
        st.markdown('<div class="btn-inicio-header">', unsafe_allow_html=True)
        if st.button("🏠 Inicio", key="btn_header_inicio", use_container_width=True):
            st.session_state["seccion_activa"] = "Inicio"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with col_perfil_btn:
        st.markdown('<div class="btn-perfil-header">', unsafe_allow_html=True)
        if st.button("⚙️ Mi Perfil", key="btn_header_perfil", use_container_width=True):
            st.session_state["seccion_activa"] = "Perfil"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with col_ia_btn:
        _renderizar_asistente_popover_ia()

    # ==========================================================
    # VISTA 0: MI PERFIL
    # ==========================================================
    if st.session_state["seccion_activa"] == "Perfil":
        st.markdown("<h3 style='color:#0b1d3a;'>👤 Mi Perfil</h3>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#475569;'>Actualice sus datos personales y, si lo desea, "
            "su contraseña de acceso. Los cambios quedan reflejados de inmediato en el "
            "Panel de Administración.</p>",
            unsafe_allow_html=True
        )

        perfil_actual = obtener_perfil(usuario_sesion) or {}

        st.markdown('<div class="perfil-card"><span class="perfil-card-title">📝 Datos Personales</span>', unsafe_allow_html=True)
        st.text_input("Usuario", value=usuario_sesion, disabled=True, key="perfil_usuario_ro")
        nuevo_nombre = st.text_input(
            "Nombre completo",
            value=str(perfil_actual.get("nombre", "")),
            placeholder="Ej: Juan Pérez",
            key="perfil_nombre"
        )
        fecha_guardada = parsear_fecha(perfil_actual.get("fecha_nacimiento", ""))
        nueva_fecha = st.date_input(
            "Fecha de nacimiento",
            value=fecha_guardada if fecha_guardada else datetime.date(2000, 1, 1),
            min_value=datetime.date(1920, 1, 1),
            max_value=datetime.date.today(),
            key="perfil_fecha"
        )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="perfil-card"><span class="perfil-card-title">🔑 Cambiar mi Contraseña (opcional)</span>', unsafe_allow_html=True)
        st.caption("Deje estos dos campos vacíos si no desea cambiar su contraseña actual.")
        pwd_nueva     = st.text_input("Nueva contraseña",          type="password", key="perfil_pwd1", placeholder="Nueva contraseña")
        pwd_confirmar = st.text_input("Confirmar nueva contraseña", type="password", key="perfil_pwd2", placeholder="Repita la nueva contraseña")
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("💾 Guardar Cambios", key="btn_guardar_perfil", use_container_width=True):
            if (pwd_nueva or pwd_confirmar) and pwd_nueva != pwd_confirmar:
                st.error("Las contraseñas nuevas no coinciden.")
            elif pwd_nueva and len(pwd_nueva) < 4:
                st.warning("La nueva contraseña debe tener mínimo 4 caracteres.")
            else:
                ok, msg = actualizar_perfil(
                    usuario_sesion,
                    nuevo_nombre=nuevo_nombre,
                    nueva_fecha=nueva_fecha.strftime("%Y-%m-%d"),
                    nueva_password=pwd_nueva if pwd_nueva else None
                )
                if ok:
                    st.success(f"✔ {msg} (visible en el Panel de Administración al instante)")
                    registrar_log(usuario_sesion, "Actualizó su perfil", "-")
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    # ==========================================================
    # VISTA 1: MENÚ PRINCIPAL
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Inicio":
        st.markdown("<h3 style='color:#0b1d3a;margin-bottom:4px;'>Menú Principal</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569;margin-bottom:20px;'>Seleccione una de las siguientes opciones:</p>", unsafe_allow_html=True)

        st.markdown("""
            <div class="card-azul">
                <h4>1. Extracción Masiva (AccessGudid + Eudamed)</h4>
                <p>Carga masiva de archivos Excel para cruce con AccessGUDID (FDA) y Eudamed (UE), en una sola pantalla dividida.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("🚀 Ingresar al Módulo de Extracción Masiva", key="btn_ext", use_container_width=True):
            st.session_state["seccion_activa"] = "ExtraccionMasiva"; st.rerun()

        st.markdown("""
            <div class="card-azul" style="border-left-color:#0369a1;">
                <h4>2. Consulta de Historiales y Reportes</h4>
                <p>Consulta el historial de referencias buscadas por usuario, con fecha y cantidad de resultados obtenidos.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("📋 Ver Historiales y Reportes", key="btn_hist", use_container_width=True):
            st.session_state["seccion_activa"] = "Historiales"; st.rerun()

        st.markdown("""
            <div class="card-azul" style="border-left-color:#0b1d3a;">
                <h4>3. Mi Perfil</h4>
                <p>Edite su nombre, fecha de nacimiento y contraseña de acceso. Los cambios se reflejan en tiempo real.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("👤 Editar mi Perfil", key="btn_perfil_inicio", use_container_width=True):
            st.session_state["seccion_activa"] = "Perfil"; st.rerun()

        if es_admin:
            st.markdown("""
                <div class="card-roja">
                    <h4>🔐 4. Panel de Administración</h4>
                    <p>Gestión completa de usuarios: agregar, eliminar, ver/cambiar contraseñas y editar datos.</p>
                </div>""", unsafe_allow_html=True)
            if st.button("👥 Ir al Panel de Administración", key="btn_admin", use_container_width=True):
                st.session_state["seccion_activa"] = "Admin"; st.rerun()

    # ==========================================================
    # VISTA 2: EXTRACCIÓN MASIVA — PANTALLA DIVIDIDA
    # AccessGudid (izquierda) | Eudamed (derecha)
    # ==========================================================
    elif st.session_state["seccion_activa"] == "ExtraccionMasiva":
        st.markdown("<h3 style='color:#0b1d3a;margin-bottom:4px;'>🚀 Extracción Masiva</h3>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#475569;margin-bottom:18px;'>Trabaja con ambas fuentes en paralelo: "
            "AccessGUDID (FDA) a la izquierda, Eudamed (UE) a la derecha.</p>",
            unsafe_allow_html=True
        )

        col_gudid, col_eudamed = st.columns(2)

        # ──────────────────────────────────────────────
        # COLUMNA IZQUIERDA: ACCESSGUDID (FDA)
        # ──────────────────────────────────────────────
        with col_gudid:
            st.markdown('<div class="col-extraccion-titulo">🚀 AccessGudid (FDA)</div>', unsafe_allow_html=True)

            archivo_cargado = st.file_uploader(
                "Sube tu archivo de Excel (.xlsx)", type=["xlsx"], key="uploader_gudid"
            )

            with st.expander("⚙ Filtrar por fabricante (opcional)"):
                for i in range(len(st.session_state["lista_filtros_company"])):
                    col_campo, col_quitar = st.columns([5, 1])
                    with col_campo:
                        valor_actual = st.text_input(
                            f"Fabricante #{i+1}",
                            value=st.session_state["lista_filtros_company"][i],
                            key=f"company_filtro_{i}",
                            placeholder="Ej: MEDTRONIC",
                            label_visibility="collapsed"
                        )
                        st.session_state["lista_filtros_company"][i] = valor_actual
                    with col_quitar:
                        if len(st.session_state["lista_filtros_company"]) > 1:
                            if st.button("✖", key=f"quitar_company_{i}", use_container_width=True):
                                st.session_state["lista_filtros_company"].pop(i)
                                st.rerun()
                if st.button("➕ Agregar otro fabricante", key="btn_agregar_company", use_container_width=True):
                    st.session_state["lista_filtros_company"].append("")
                    st.rerun()

            company_names_filtro = [
                c.strip().upper() for c in st.session_state["lista_filtros_company"] if c.strip()
            ]

            conectar_boton = st.button(
                "🚀 Iniciar Extracción AccessGudid", disabled=(archivo_cargado is None),
                use_container_width=True, key="btn_iniciar_gudid"
            )

            contenedor_gudid = st.container()

            if archivo_cargado and conectar_boton:
                with contenedor_gudid:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    try:
                        bytes_data = archivo_cargado.read()
                        df = pd.read_excel(io.BytesIO(bytes_data), header=None, dtype=str)
                        df[0] = df[0].astype(str).str.strip()
                        referencias_totales = [r for r in df[0].tolist() if r and r != "nan"]
                        total_refs = len(referencias_totales)
                    except Exception as e:
                        st.error(f"Error al abrir el archivo de Excel: {e}"); st.stop()

                    st.success(f"📋 Referencias encontradas: {total_refs}")
                    if company_names_filtro:
                        st.info(f"🔎 Filtrando por: {', '.join(company_names_filtro)}")

                    texto_estado = st.empty()
                    barra_custom = st.empty()
                    tabla_viva   = st.empty()
                    lista_resultados = []
                    session = requests.Session()
                    inicio_tiempo = time.time()

                    # OPTIMIZACIÓN: hasta 5 referencias en paralelo (cada una hace
                    # sus propias peticiones HTTP independientes a AccessGUDID,
                    # así que paralelizar es seguro y acelera bastante el total).
                    MAX_HILOS_GUDID = 5

                    def actualizar_barra_gudid(pct):
                        barra_custom.markdown(
                            f'<div class="prog-wrap"><div class="prog-bar" style="width:{pct}%;"></div></div>',
                            unsafe_allow_html=True
                        )

                    completados = 0
                    with ThreadPoolExecutor(max_workers=MAX_HILOS_GUDID) as executor:
                        futuros = {
                            executor.submit(
                                _buscar_referencia_accessgudid, ref, session, headers, company_names_filtro
                            ): ref
                            for ref in referencias_totales
                        }
                        for futuro in as_completed(futuros):
                            ref_actual = futuros[futuro]
                            try:
                                filas_ref = futuro.result()
                            except Exception:
                                filas_ref = [{
                                    "Referencia_Original": ref_actual, "Primary_DI_Number": "Error",
                                    "Nombre_Empresa_FDA": "Error", "Codigo_GMDN": "Error",
                                    "Definicion_GMDN": "Error", "Estado_GMDN": "Error", "Issuing_Agency": "Error"
                                }]
                            lista_resultados.extend(filas_ref)
                            completados += 1

                            transcurrido = time.time() - inicio_tiempo
                            promedio = transcurrido / completados
                            restante = promedio * (total_refs - completados)
                            texto_estado.info(
                                f"⏳ {completados}/{total_refs} completadas | ⏱ ~{int(restante)}s restantes"
                            )
                            actualizar_barra_gudid(int(completados / total_refs * 100))
                            tabla_viva.dataframe(pd.DataFrame(lista_resultados), use_container_width=True, height=260)

                    texto_estado.empty(); barra_custom.empty()
                    st.success(f"✨ ¡Completado! ({int(time.time()-inicio_tiempo)}s)")
                    registrar_log(st.session_state["usuario_activo_real"], f"Extracción masiva AccessGudid ({total_refs} refs)", len(lista_resultados))
                    guardar_resultados_accessgudid(st.session_state["usuario_activo_real"], lista_resultados)
                    st.session_state["contexto_chat_ia"] = None

                    df_final = pd.DataFrame(lista_resultados)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_final.to_excel(writer, index=False)
                    st.download_button(
                        label="📥 Descargar Excel (AccessGudid)",
                        data=output.getvalue(),
                        file_name="resultados_fda.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key="dl_gudid"
                    )

                    if st.button("🤖 Resumen con IA", key="btn_resumen_ia_accessgudid", use_container_width=True):
                        with st.spinner("Generando resumen..."):
                            try:
                                st.info(_generar_resumen_ia(df_final, "AccessGUDID (FDA)"))
                            except Exception as e:
                                st.error(f"No se pudo generar el resumen: {e}")
            elif not archivo_cargado:
                st.info("👈 Sube un archivo para activar la monitorización.")

        # ──────────────────────────────────────────────
        # COLUMNA DERECHA: EUDAMED (UE)
        # ──────────────────────────────────────────────
        with col_eudamed:
            st.markdown('<div class="col-extraccion-titulo eudamed">🌍 Eudamed (Unión Europea)</div>', unsafe_allow_html=True)
            st.caption("Usa navegador automatizado: ~10-20s por referencia.")

            archivo_eudamed = st.file_uploader(
                "Sube tu archivo de Excel (.xlsx)", type=["xlsx"], key="uploader_eudamed"
            )

            if archivo_eudamed is not None:
                if archivo_eudamed.name != st.session_state.get("eudamed_archivo_nombre", ""):
                    st.session_state["eudamed_archivo_bytes"]  = archivo_eudamed.read()
                    st.session_state["eudamed_archivo_nombre"] = archivo_eudamed.name
                    st.session_state["eudamed_iniciar"]        = False

            hay_archivo_eu = st.session_state.get("eudamed_archivo_bytes") is not None

            if st.button(
                "🌍 Iniciar Extracción Eudamed",
                disabled=not hay_archivo_eu,
                use_container_width=True,
                key="btn_iniciar_eudamed"
            ):
                st.session_state["eudamed_iniciar"] = True
                st.rerun()

            contenedor_eudamed = st.container()

            if st.session_state.get("eudamed_iniciar") and hay_archivo_eu:
                st.session_state["eudamed_iniciar"] = False

                with contenedor_eudamed:
                    try:
                        bytes_data_eu = st.session_state["eudamed_archivo_bytes"]
                        df_eu = pd.read_excel(io.BytesIO(bytes_data_eu), header=None, dtype=str)
                        df_eu[0] = df_eu[0].astype(str).str.strip()
                        referencias_eu = [r for r in df_eu[0].tolist() if r and r != "nan"]
                        total_refs_eu  = len(referencias_eu)
                    except Exception as e:
                        st.error(f"Error al abrir el archivo de Excel: {e}")
                        st.stop()

                    st.success(f"📋 Referencias encontradas: {total_refs_eu}")

                    texto_estado_eu  = st.empty()
                    barra_eu         = st.empty()
                    tabla_viva_eu    = st.empty()
                    lista_resultados_eu = []
                    inicio_tiempo_eu = time.time()

                    def actualizar_barra_eu(pct):
                        barra_eu.markdown(
                            f'<div class="prog-wrap"><div class="prog-bar" style="width:{pct}%;"></div></div>',
                            unsafe_allow_html=True
                        )

                    driver_eu = None
                    try:
                        with st.spinner("Abriendo navegador automatizado..."):
                            driver_eu = _crear_driver_eudamed()
                    except Exception as e:
                        st.error("No se pudo iniciar el navegador automatizado para Eudamed.")
                        st.code(str(e))
                        st.info(
                            "Revisa que 'packages.txt' tenga 'chromium' y 'chromium-driver', "
                            "y que 'selenium' esté en requirements.txt."
                        )
                        st.stop()

                    try:
                        for idx, ref in enumerate(referencias_eu):
                            transcurrido = time.time() - inicio_tiempo_eu
                            if idx > 0:
                                promedio = transcurrido / idx
                                restante = promedio * (total_refs_eu - idx)
                                texto_tiempo = f" | ⏱ ~{int(restante)}s restantes"
                            else:
                                texto_tiempo = ""

                            texto_estado_eu.info(f"⏳ {idx+1}/{total_refs_eu} | 🔍 {ref}{texto_tiempo}")
                            actualizar_barra_eu(int(idx / total_refs_eu * 100))

                            try:
                                filas_ref = _procesar_referencia_eudamed(
                                    driver_eu, ref, primera_vez=(idx == 0)
                                )
                            except Exception as e:
                                filas_ref = [{
                                    "Referencia_Original": ref,
                                    "Codigo_UDI_DI":       "Error de navegador",
                                    "Agencia_Emisora":     "Error",
                                    "Nombre_Dispositivo":  "Error",
                                    "Fabricante":          f"Error: {_mensaje_error_limpio(e)}",
                                }]

                            lista_resultados_eu.extend(filas_ref)
                            actualizar_barra_eu(int((idx + 1) / total_refs_eu * 100))
                            tabla_viva_eu.dataframe(pd.DataFrame(lista_resultados_eu), use_container_width=True, height=260)

                    finally:
                        if driver_eu is not None:
                            try:
                                driver_eu.quit()
                            except Exception:
                                pass

                    texto_estado_eu.empty()
                    barra_eu.empty()
                    st.success(f"✨ ¡Completado! ({int(time.time()-inicio_tiempo_eu)}s)")

                    st.session_state["eudamed_archivo_bytes"]  = None
                    st.session_state["eudamed_archivo_nombre"] = ""

                    registrar_log(
                        st.session_state["usuario_activo_real"],
                        f"Extracción masiva Eudamed ({total_refs_eu} refs)",
                        len(lista_resultados_eu)
                    )
                    guardar_resultados_eudamed(st.session_state["usuario_activo_real"], lista_resultados_eu)
                    st.session_state["contexto_chat_ia"] = None

                    df_final_eu = pd.DataFrame(lista_resultados_eu)
                    output_eu   = io.BytesIO()
                    with pd.ExcelWriter(output_eu, engine='openpyxl') as writer:
                        df_final_eu.to_excel(writer, index=False)
                    st.download_button(
                        label="📥 Descargar Excel (Eudamed)",
                        data=output_eu.getvalue(),
                        file_name="resultados_eudamed.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key="dl_eudamed"
                    )

                    if st.button("🤖 Resumen con IA", key="btn_resumen_ia_eudamed", use_container_width=True):
                        with st.spinner("Generando resumen..."):
                            try:
                                st.info(_generar_resumen_ia(df_final_eu, "Eudamed (Unión Europea)"))
                            except Exception as e:
                                st.error(f"No se pudo generar el resumen: {e}")
            elif not hay_archivo_eu:
                st.info("👈 Sube un archivo para activar la monitorización.")

    # ==========================================================
    # VISTA 3: HISTORIALES
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Historiales":
        st.markdown("<h3 style='color:#0b1d3a;'>📋 Historiales y Reportes</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569;'>Registro de búsquedas realizadas en la plataforma.</p>", unsafe_allow_html=True)

        with st.spinner("Cargando historial..."):
            df_logs = obtener_logs()

        if df_logs.empty:
            st.info("No hay registros de búsquedas aún.")
        else:
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                usuarios_disp = ["Todos"] + sorted(df_logs["Usuario"].dropna().unique().tolist())
                filtro_usuario = st.selectbox("👤 Usuario", usuarios_disp)
            with col_f2:
                fecha_min = df_logs["Fecha"].min().date() if not df_logs["Fecha"].isna().all() else datetime.date.today()
                filtro_fecha_ini = st.date_input("📅 Desde", value=fecha_min)
            with col_f3:
                fecha_max = df_logs["Fecha"].max().date() if not df_logs["Fecha"].isna().all() else datetime.date.today()
                filtro_fecha_fin = st.date_input("📅 Hasta", value=fecha_max)

            df_fil = df_logs.copy()
            if filtro_usuario != "Todos":
                df_fil = df_fil[df_fil["Usuario"] == filtro_usuario]
            df_fil = df_fil[
                (df_fil["Fecha"].dt.date >= filtro_fecha_ini) &
                (df_fil["Fecha"].dt.date <= filtro_fecha_fin)
            ]

            st.markdown("<br>", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("📊 Total búsquedas", len(df_fil))
            m2.metric("👥 Usuarios activos", df_fil["Usuario"].nunique())
            total_res = pd.to_numeric(df_fil["Resultados"], errors="coerce").sum()
            m3.metric("🔬 Referencias procesadas", int(total_res) if not pd.isna(total_res) else 0)
            st.markdown("<br>", unsafe_allow_html=True)

            df_mostrar = df_fil.copy()
            df_mostrar["Fecha"] = df_mostrar["Fecha"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

            out_logs = io.BytesIO()
            with pd.ExcelWriter(out_logs, engine='openpyxl') as writer:
                df_mostrar.to_excel(writer, index=False)
            st.download_button(
                label="📥 Descargar Historial en Excel",
                data=out_logs.getvalue(),
                file_name=f"historial_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # ==========================================================
    # VISTA 4: PANEL ADMIN
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Admin":
        if not es_admin:
            st.error("🔒 Acceso denegado."); st.stop()

        st.markdown("<h3 style='color:#991b1b;'>👥 Panel de Administración de Usuarios</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569;'>Gestión completa de cuentas de acceso a la plataforma.</p>", unsafe_allow_html=True)

        col_lista, col_agregar = st.columns([1.4, 1])

        with col_lista:
            st.markdown('<div class="admin-card"><span class="admin-card-title">📋 Lista de Usuarios Registrados</span>', unsafe_allow_html=True)
            mostrar_pwds = st.checkbox("👁 Mostrar contraseñas", key="chk_mostrar_pwds")
            with st.spinner("Cargando usuarios..."):
                datos_usuarios, _ = obtener_usuarios()
            if datos_usuarios:
                filas = ""
                for u in datos_usuarios:
                    nom_usr    = str(u.get('usuario', '')).strip()
                    pwd_usr    = str(u.get('contraseña', '')).strip()
                    nombre_usr = str(u.get('nombre', '')).strip() or "—"
                    fecha_usr  = str(u.get('fecha_nacimiento', '')).strip() or "—"
                    rol        = "🔴 Admin" if nom_usr.lower() == ADMIN_USER.lower() else "🟢 Usuario"
                    pwd_mostrar = pwd_usr if mostrar_pwds else "•" * max(len(pwd_usr), 4)
                    filas += (
                        f"<tr><td>{nom_usr}</td><td>{pwd_mostrar}</td>"
                        f"<td>{nombre_usr}</td><td>{fecha_usr}</td><td>{rol}</td></tr>"
                    )
                st.markdown(
                    f'<table class="tabla-usr"><thead><tr>'
                    f'<th>Usuario</th><th>Contraseña</th><th>Nombre</th><th>Fecha Nac.</th><th>Rol</th>'
                    f'</tr></thead><tbody>{filas}</tbody></table>'
                    f'<p class="meta-txt">Total: {len(datos_usuarios)} usuario(s)</p>',
                    unsafe_allow_html=True
                )
            else:
                st.info("No se encontraron usuarios.")
            st.markdown('</div>', unsafe_allow_html=True)

        with col_agregar:
            st.markdown('<div class="admin-card"><span class="admin-card-title">➕ Agregar Nuevo Usuario</span>', unsafe_allow_html=True)
            nuevo_usr            = st.text_input("Nombre de usuario",            key="nu",        placeholder="Ej: usuario_nuevo")
            nuevo_nombre_cuenta  = st.text_input("Nombre completo (opcional)",   key="nu_nombre", placeholder="Ej: Juan Pérez")
            nuevo_pwd            = st.text_input("Contraseña",       type="password", key="np",   placeholder="Contraseña segura")
            nuevo_pwd2           = st.text_input("Confirmar contraseña", type="password", key="np2", placeholder="Repita la contraseña")
            if st.button("✅ Crear Usuario", key="btn_crear", use_container_width=True):
                if not nuevo_usr or not nuevo_pwd: st.warning("Complete todos los campos.")
                elif nuevo_pwd != nuevo_pwd2: st.error("Las contraseñas no coinciden.")
                elif len(nuevo_pwd) < 4: st.warning("Mínimo 4 caracteres.")
                else:
                    ok, msg = agregar_usuario(nuevo_usr, nuevo_pwd, nombre=nuevo_nombre_cuenta)
                    if ok:
                        st.success(f"✔ {msg}")
                        registrar_log(usuario_sesion, f"[ADMIN] Creó: {nuevo_usr}", "-")
                        time.sleep(0.5); st.rerun()
                    else:
                        st.error(f"❌ {msg}")
            st.markdown('</div>', unsafe_allow_html=True)

        col_elim, col_pwd = st.columns(2)

        with col_elim:
            st.markdown('<div class="admin-card"><span class="admin-card-title">🗑️ Eliminar Usuario</span>', unsafe_allow_html=True)
            no_admin = [
                str(u.get('usuario','')).strip()
                for u in datos_usuarios
                if str(u.get('usuario','')).strip().lower() != ADMIN_USER.lower()
            ] if datos_usuarios else []
            if no_admin:
                usr_elim = st.selectbox("Seleccionar usuario", no_admin, key="sel_e")
                confirmar = st.checkbox(f"Confirmo eliminar a **{usr_elim}**", key="chk_e")
                if st.button("🗑️ Eliminar Usuario", key="btn_e", use_container_width=True):
                    if not confirmar: st.warning("Marque la casilla de confirmación.")
                    else:
                        ok, msg = eliminar_usuario(usr_elim)
                        if ok:
                            st.success(f"✔ {msg}")
                            registrar_log(usuario_sesion, f"[ADMIN] Eliminó: {usr_elim}", "-")
                            time.sleep(0.5); st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            else:
                st.info("No hay usuarios para eliminar.")
            st.markdown('</div>', unsafe_allow_html=True)

        with col_pwd:
            st.markdown('<div class="admin-card"><span class="admin-card-title">✏️ Editar Usuario (nombre, fecha y/o contraseña)</span>', unsafe_allow_html=True)
            todos = [str(u.get('usuario','')).strip() for u in datos_usuarios] if datos_usuarios else []
            if todos:
                usr_editar   = st.selectbox("Seleccionar usuario", todos, key="sel_p")
                perfil_sel   = next((u for u in datos_usuarios if str(u.get('usuario','')).strip() == usr_editar), {})
                nombre_edit  = st.text_input("Nombre completo", value=str(perfil_sel.get('nombre','')), key="edit_nombre")
                fecha_edit_actual = parsear_fecha(perfil_sel.get('fecha_nacimiento',''))
                fecha_edit = st.date_input(
                    "Fecha de nacimiento",
                    value=fecha_edit_actual if fecha_edit_actual else datetime.date(2000, 1, 1),
                    min_value=datetime.date(1920, 1, 1),
                    max_value=datetime.date.today(),
                    key="edit_fecha"
                )
                npwd1 = st.text_input("Nueva contraseña (opcional)", type="password", key="np1", placeholder="Dejar en blanco para no cambiar")
                npwd2 = st.text_input("Confirmar contraseña",        type="password", key="np2b", placeholder="Repita la nueva contraseña")
                if st.button("💾 Guardar Cambios del Usuario", key="btn_p", use_container_width=True):
                    if npwd1 and npwd1 != npwd2:
                        st.error("Las contraseñas no coinciden.")
                    elif npwd1 and len(npwd1) < 4:
                        st.warning("Mínimo 4 caracteres.")
                    else:
                        ok, msg = actualizar_perfil(
                            usr_editar,
                            nuevo_nombre=nombre_edit,
                            nueva_fecha=fecha_edit.strftime("%Y-%m-%d"),
                            nueva_password=npwd1 if npwd1 else None
                        )
                        if ok:
                            st.success(f"✔ {msg}")
                            registrar_log(usuario_sesion, f"[ADMIN] Editó usuario: {usr_editar}", "-")
                            time.sleep(0.5); st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            else:
                st.info("No hay usuarios disponibles.")
            st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================
    # FOOTER
    # ==========================================================
    st.markdown("""
        <div class="footer-box">
            <div class="footer-links">
                <a href="#">Políticas de privacidad</a>
                <a href="#">Tratamiento de datos</a>
                <a href="#">Mesa de Ayuda</a>
            </div>
            <p>v 1.6.26 © Invima 2026. Todos los derechos reservados.</p>
        </div>""", unsafe_allow_html=True)
