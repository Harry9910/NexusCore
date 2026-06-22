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
import re
import json
from pypdf import PdfReader
import uuid
import zipfile
import mimetypes
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

def _obtener_credenciales_google():
    """Construye las credenciales de la cuenta de servicio. Se separó de
    get_gspread_client() para poder reutilizar las mismas credenciales con
    la API de Google Drive (Documentación Post-Venta) sin duplicar código."""
    creds_dict = dict(st.secrets["gcp"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)


def get_gspread_client():
    return gspread.authorize(_obtener_credenciales_google())


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
# GOOGLE DRIVE — DOCUMENTACIÓN POST-VENTA
# ==========================================================
# Reutiliza la misma cuenta de servicio que ya se usa para Google Sheets
# (el scope de Drive ya estaba incluido en SCOPE desde el principio).
# Se trabaja con la API REST de Drive directamente vía 'requests', igual
# que con Gemini, para no agregar dependencias nuevas.
#
# Estructura que se replica en Drive:
#   Carpeta raíz (la que tú compartiste, [drive] folder_id en Secrets)
#     └── Fabricante
#           └── Equipo
#                 └── Referencia
#                       └── (los archivos de esa referencia)

def _obtener_id_carpeta_raiz_postventa():
    """Lee el ID de la carpeta raíz desde Secrets. Si por error se pegó la
    URL completa de Drive (ej: '.../folders/ABC123?usp=drive_link') en vez
    del ID solo, lo extrae automáticamente en vez de fallar."""
    try:
        valor = st.secrets["drive"]["folder_id"]
    except Exception:
        return None
    if not valor:
        return None
    valor = valor.strip()
    coincidencia = re.search(r"/folders/([a-zA-Z0-9_-]+)", valor)
    if coincidencia:
        return coincidencia.group(1)
    # Si viene con parámetros tipo '?usp=drive_link' pegados al ID solo
    return valor.split("?")[0].strip("/")


def _obtener_token_drive():
    """Obtiene un token de acceso a Drive usando OAuth con la cuenta del
    USUARIO (no la cuenta de servicio). Esto es necesario porque las
    cuentas de servicio gratuitas de Google NO tienen cuota de
    almacenamiento propia y no pueden crear archivos con contenido real
    (ni subiéndolos de cero ni copiándolos) — solo pueden leer/listar.
    El token se renueva en cada llamada a partir del 'refresh_token'
    guardado en Secrets, que no caduca salvo que se revoque el acceso
    manualmente desde la cuenta de Google."""
    try:
        client_id = st.secrets["oauth_drive"]["client_id"]
        client_secret = st.secrets["oauth_drive"]["client_secret"]
        refresh_token = st.secrets["oauth_drive"]["refresh_token"]
    except Exception:
        raise RuntimeError(
            "No hay credenciales OAuth de Drive configuradas. Agrega en "
            "Settings → Secrets de Streamlit Cloud:\n\n"
            "[oauth_drive]\nclient_id = \"...\"\nclient_secret = \"...\"\n"
            "refresh_token = \"...\"\n\n"
            "(se consiguen siguiendo la guía paso a paso que te compartí)."
        )
    respuesta = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    respuesta.raise_for_status()
    return respuesta.json()["access_token"]


def _drive_listar_hijos(token, parent_id):
    """Devuelve un diccionario {nombre: {'id':..., 'mimeType':...}} con los
    hijos directos (carpetas y archivos) de una carpeta de Drive."""
    resultados = {}
    page_token = None
    while True:
        params = {
            "q": f"'{parent_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        respuesta = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        for f in datos.get("files", []):
            resultados[f["name"]] = {"id": f["id"], "mimeType": f["mimeType"]}
        page_token = datos.get("nextPageToken")
        if not page_token:
            break
    return resultados


def _drive_crear_carpeta(token, nombre, parent_id):
    respuesta = requests.post(
        "https://www.googleapis.com/drive/v3/files?fields=id,name",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": nombre, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        timeout=30,
    )
    respuesta.raise_for_status()
    return respuesta.json()["id"]


def _drive_obtener_o_crear_carpeta(token, nombre, parent_id, cache_hijos=None):
    """Busca una subcarpeta por nombre dentro de parent_id; si no existe,
    la crea. 'cache_hijos' (opcional) evita listar Drive repetidamente
    cuando se procesan muchas referencias del mismo fabricante/equipo."""
    hijos = cache_hijos if cache_hijos is not None else _drive_listar_hijos(token, parent_id)
    existente = hijos.get(nombre)
    if existente and existente["mimeType"] == "application/vnd.google-apps.folder":
        return existente["id"], False  # False = ya existía
    nuevo_id = _drive_crear_carpeta(token, nombre, parent_id)
    if cache_hijos is not None:
        cache_hijos[nombre] = {"id": nuevo_id, "mimeType": "application/vnd.google-apps.folder"}
    return nuevo_id, True  # True = se creó ahora


def _drive_subir_archivo(token, nombre, contenido_bytes, mimetype, parent_id):
    """Sube un archivo a Drive usando 'multipart upload' construido a mano
    (multipart/related), siguiendo el formato exacto que pide la API de
    Drive — los multipart automáticos de 'requests' usan un Content-Type
    distinto (multipart/form-data) que la API de Drive no garantiza
    aceptar, así que se arma el cuerpo manualmente para evitar sorpresas."""
    boundary = uuid.uuid4().hex
    metadata = json.dumps({"name": nombre, "parents": [parent_id]})
    cuerpo = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mimetype}\r\n\r\n"
    ).encode("utf-8") + contenido_bytes + f"\r\n--{boundary}--".encode("utf-8")

    respuesta = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=cuerpo,
        timeout=120,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def _procesar_zip_postventa(bytes_zip, token, carpeta_raiz_id):
    """Recorre el .zip subido (Fabricante/Equipo/Referencia/archivo) y:
    - Crea en Drive las carpetas que falten (Fabricante > Equipo > Referencia)
    - Sube los archivos que no existan todavía en esa referencia
    - Los archivos sueltos en la raíz del .zip (que no pertenecen a ningún
      fabricante) se guardan en una carpeta 'DOCUMENTOS GENERALES'.
    - NO sobrescribe ni renombra archivos que ya existan: los reporta como
      'conflicto pendiente' para que el usuario decida qué hacer.
    Devuelve una lista de filas (una por archivo procesado) con su estado."""
    filas = []
    cache_carpetas_fabricante = _drive_listar_hijos(token, carpeta_raiz_id)
    cache_carpetas_equipo = {}   # clave: id de carpeta fabricante -> dict hijos
    cache_carpetas_referencia = {}  # clave: id de carpeta equipo -> dict hijos
    cache_archivos_referencia = {}  # clave: id de carpeta referencia -> dict hijos
    id_carpeta_generales = None  # se crea/obtiene solo si hace falta

    with zipfile.ZipFile(io.BytesIO(bytes_zip)) as zf:
        nombres = [n for n in zf.namelist() if not n.endswith("/")]

        for nombre_entrada in nombres:
            ruta = nombre_entrada.strip("/")
            partes = ruta.split("/")

            # ── Archivo suelto en la raíz (no pertenece a ningún fabricante) ──
            if len(partes) == 1:
                nombre_archivo = partes[0]
                if not nombre_archivo:
                    continue
                if id_carpeta_generales is None:
                    id_carpeta_generales, _ = _drive_obtener_o_crear_carpeta(
                        token, "DOCUMENTOS GENERALES", carpeta_raiz_id, cache_carpetas_fabricante
                    )
                    cache_archivos_referencia[id_carpeta_generales] = _drive_listar_hijos(token, id_carpeta_generales)
                archivos_generales = cache_archivos_referencia[id_carpeta_generales]

                if nombre_archivo in archivos_generales:
                    filas.append({
                        "Fabricante": "(general)", "Equipo": "-", "Referencia": "-",
                        "Archivo": nombre_archivo, "Estado": "🟡 CONFLICTO: ya existe (no se subió, pendiente de decisión)"
                    })
                    continue
                try:
                    contenido = zf.read(nombre_entrada)
                    mimetype = mimetypes.guess_type(nombre_archivo)[0] or "application/octet-stream"
                    _drive_subir_archivo(token, nombre_archivo, contenido, mimetype, id_carpeta_generales)
                    archivos_generales[nombre_archivo] = {"id": "nuevo", "mimeType": mimetype}
                    filas.append({
                        "Fabricante": "(general)", "Equipo": "-", "Referencia": "-",
                        "Archivo": nombre_archivo, "Estado": "✅ Subido a DOCUMENTOS GENERALES"
                    })
                except Exception as e:
                    filas.append({
                        "Fabricante": "(general)", "Equipo": "-", "Referencia": "-",
                        "Archivo": nombre_archivo, "Estado": f"❌ Error: {e}"
                    })
                continue

            if len(partes) == 4:
                fabricante, equipo, referencia, nombre_archivo = partes
            elif len(partes) == 3:
                # Equipo sin subcarpeta de referencia: se usa el mismo nombre
                # del equipo como referencia, para mantener siempre 4 niveles
                # consistentes dentro de Drive (Fabricante/Equipo/Equipo/archivo).
                fabricante, equipo, nombre_archivo = partes
                referencia = equipo
            else:
                filas.append({
                    "Fabricante": "?", "Equipo": "?", "Referencia": "?",
                    "Archivo": ruta, "Estado": f"⚠ Ignorado (se esperaban 1, 3 o 4 niveles, tiene {len(partes)})"
                })
                continue

            if not nombre_archivo:
                continue

            # Carpeta del fabricante
            id_fabricante, _ = _drive_obtener_o_crear_carpeta(
                token, fabricante, carpeta_raiz_id, cache_carpetas_fabricante
            )

            # Carpeta del equipo
            if id_fabricante not in cache_carpetas_equipo:
                cache_carpetas_equipo[id_fabricante] = _drive_listar_hijos(token, id_fabricante)
            id_equipo, _ = _drive_obtener_o_crear_carpeta(
                token, equipo, id_fabricante, cache_carpetas_equipo[id_fabricante]
            )

            # Carpeta de la referencia
            if id_equipo not in cache_carpetas_referencia:
                cache_carpetas_referencia[id_equipo] = _drive_listar_hijos(token, id_equipo)
            id_referencia, _ = _drive_obtener_o_crear_carpeta(
                token, referencia, id_equipo, cache_carpetas_referencia[id_equipo]
            )

            # Archivos ya existentes en esa referencia
            if id_referencia not in cache_archivos_referencia:
                cache_archivos_referencia[id_referencia] = _drive_listar_hijos(token, id_referencia)
            archivos_existentes = cache_archivos_referencia[id_referencia]

            if nombre_archivo in archivos_existentes:
                filas.append({
                    "Fabricante": fabricante, "Equipo": equipo, "Referencia": referencia,
                    "Archivo": nombre_archivo, "Estado": "🟡 CONFLICTO: ya existe (no se subió, pendiente de decisión)"
                })
                continue

            try:
                contenido = zf.read(nombre_entrada)
                mimetype = mimetypes.guess_type(nombre_archivo)[0] or "application/octet-stream"
                _drive_subir_archivo(token, nombre_archivo, contenido, mimetype, id_referencia)
                archivos_existentes[nombre_archivo] = {"id": "nuevo", "mimeType": mimetype}
                filas.append({
                    "Fabricante": fabricante, "Equipo": equipo, "Referencia": referencia,
                    "Archivo": nombre_archivo, "Estado": "✅ Subido"
                })
            except Exception as e:
                filas.append({
                    "Fabricante": fabricante, "Equipo": equipo, "Referencia": referencia,
                    "Archivo": nombre_archivo, "Estado": f"❌ Error: {e}"
                })

    return filas


# ==========================================================
# PROCESAMIENTO DE REMISIONES → CARPETAS FINALES POST-VENTA
# ==========================================================
# Flujo: PDF de remisión -> texto -> IA extrae pedido/remisión/cliente y
# los equipos de la tabla -> IA cruza cada equipo con el árbol de carpetas
# (Fabricante/Equipo/Referencia) ya existente en Drive -> se copian esos
# documentos (sin moverlos del original) dentro de una carpeta nueva por
# cliente, en 'CARPETA FINAL POST-VENTA'.

NOMBRE_CARPETA_FINAL_POSTVENTA = "CARPETA FINAL POST-VENTA"
NOMBRE_CARPETA_GENERALES = "DOCUMENTOS GENERALES"


def _extraer_texto_pdf(bytes_pdf):
    """Extrae el texto de un PDF de remisión. Si el PDF es una imagen
    escaneada sin texto seleccionable, el resultado vendrá vacío o muy
    corto (eso se detecta más adelante para avisar en vez de fallar)."""
    try:
        lector = PdfReader(io.BytesIO(bytes_pdf))
        texto = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
        return texto.strip()
    except Exception:
        return ""


def _mensaje_error_drive(e):
    """Extrae el mensaje de error real que devuelve la API de Drive
    (viene en el cuerpo de la respuesta como JSON), en vez de solo el
    genérico '404 Client Error' / '403 Client Error' que da 'requests'."""
    respuesta = getattr(e, "response", None)
    if respuesta is not None:
        try:
            datos_error = respuesta.json()
            return datos_error.get("error", {}).get("message", respuesta.text[:200])
        except Exception:
            return (respuesta.text or str(e))[:200]
    return str(e)


def _drive_descargar_archivo(token, file_id):
    """Descarga el contenido (bytes) de un archivo de Drive. Se usa en vez
    de 'files.copy' (que falla porque las cuentas de servicio no tienen
    cuota propia: ver _mensaje_error_drive más abajo) — descargando y
    subiendo de nuevo el archivo (como una subida normal) sí funciona,
    porque ese consumo de cuota se atribuye al dueño de la carpeta
    destino, no a la cuenta de servicio."""
    respuesta = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    respuesta.raise_for_status()
    return respuesta.content


def _drive_listar_archivos_de_carpeta(token, folder_id):
    """Como _drive_listar_hijos, pero se queda solo con los archivos
    (descarta subcarpetas)."""
    hijos = _drive_listar_hijos(token, folder_id)
    return {n: i for n, i in hijos.items() if i["mimeType"] != "application/vnd.google-apps.folder"}


def _construir_arbol_referencias_drive(token, carpeta_raiz_id):
    """Recorre todo el árbol Fabricante > Equipo > [Referencia] ya
    organizado en Drive y devuelve una lista plana de combinaciones
    encontradas, cada una con el id de la carpeta donde están sus
    documentos (la de Referencia, o la del Equipo si no tiene
    subcarpetas de referencia — mismo criterio usado al subir)."""
    arbol = []
    fabricantes = _drive_listar_hijos(token, carpeta_raiz_id)
    for nombre_fab, info_fab in fabricantes.items():
        if info_fab["mimeType"] != "application/vnd.google-apps.folder":
            continue
        if nombre_fab in (NOMBRE_CARPETA_GENERALES, NOMBRE_CARPETA_FINAL_POSTVENTA):
            continue
        equipos = _drive_listar_hijos(token, info_fab["id"])
        for nombre_equipo, info_equipo in equipos.items():
            if info_equipo["mimeType"] != "application/vnd.google-apps.folder":
                continue
            hijos_equipo = _drive_listar_hijos(token, info_equipo["id"])
            subcarpetas = {
                n: i for n, i in hijos_equipo.items()
                if i["mimeType"] == "application/vnd.google-apps.folder"
            }
            if subcarpetas:
                for nombre_ref, info_ref in subcarpetas.items():
                    arbol.append({
                        "fabricante": nombre_fab, "equipo": nombre_equipo,
                        "referencia": nombre_ref, "folder_id": info_ref["id"]
                    })
            else:
                arbol.append({
                    "fabricante": nombre_fab, "equipo": nombre_equipo,
                    "referencia": nombre_equipo, "folder_id": info_equipo["id"]
                })
    return arbol


def _analizar_remision_con_ia(texto_pdf, arbol_referencias, pdf_bytes=None):
    """Le pide a Gemini que extraiga pedido/remisión/cliente y la lista de
    equipos de la tabla, y que cruce cada equipo con la lista de carpetas
    (Fabricante/Equipo/Referencia) que ya existen en Drive. Devuelve un
    dict ya parseado desde el JSON de la respuesta.

    Si 'pdf_bytes' viene informado (remisión escaneada, sin texto
    extraíble), se adjunta el PDF directamente para que Gemini lo lea
    como imagen."""
    lista_candidatos = "\n".join(
        f"{e['fabricante']} | {e['equipo']} | {e['referencia']}" for e in arbol_referencias
    )
    system_prompt = (
        "Eres un asistente que extrae información de documentos de remisión/entrega "
        "en español, y la cruza con una lista de carpetas de documentación técnica "
        "ya organizadas por Fabricante, Equipo y Referencia.\n\n"
        "El documento puede venir como texto extraído de un PDF (el orden de las "
        "líneas puede salir un poco desordenado por la extracción automática), o "
        "como el archivo PDF adjunto directamente (cuando es una remisión "
        "escaneada, en cuyo caso debes leerla visualmente como si fuera una "
        "imagen). Interpreta el contenido de todas formas.\n\n"
        "Identifica cada línea de la tabla que corresponda a un EQUIPO/DISPOSITIVO "
        "MÉDICO real (ignora líneas de garantías, mantenimientos, servicios, fletes, "
        "descuentos u otros conceptos que no sean un equipo físico).\n\n"
        "Para cada equipo identificado, busca en la siguiente lista de combinaciones "
        "(Fabricante | Equipo | Referencia) cuál es la que mejor corresponde a la "
        "descripción de ese equipo en la remisión (la descripción puede no coincidir "
        "exactamente en palabras; usa tu criterio semántico, por ejemplo 'MONITOR DE "
        "SIGNOS VITALES UMEC 100' corresponde a Equipo='MONITORES DE SIGNOS' y "
        "Referencia='UMEC 100'). Si no encuentras ninguna coincidencia razonablemente "
        "confiable, indícalo como sin coincidencia en vez de adivinar.\n\n"
        f"LISTA DE COMBINACIONES EXISTENTES EN DRIVE:\n{lista_candidatos}\n\n"
        "Responde ÚNICAMENTE con un JSON con este formato exacto, sin texto adicional, "
        "sin comentarios y sin marcado markdown (sin ```):\n"
        '{"numero_pedido": "", "numero_remision": "", "cliente": "", "items": '
        '[{"descripcion_original": "", "fabricante": "", "equipo": "", "referencia": "", '
        '"coincidencia": "alta|baja|sin_coincidencia"}]}\n'
        "Si algún campo no se encuentra en el documento, usa cadena vacía. Si "
        "'coincidencia' es 'sin_coincidencia', deja fabricante/equipo/referencia vacíos."
    )
    mensaje_usuario = texto_pdf[:15000] if texto_pdf else (
        "(Esta remisión no tiene texto extraíble por métodos normales — "
        "probablemente está escaneada como imagen. Léela directamente del "
        "archivo PDF adjunto.)"
    )
    respuesta_texto = _llamar_gemini_api(
        system_prompt=system_prompt,
        mensajes=[{"role": "user", "content": mensaje_usuario}],
        modelo=MODELO_IA_CALIDAD,
        max_tokens=1500,
        pdf_bytes=pdf_bytes,
    )
    texto_json = respuesta_texto.strip()
    if texto_json.startswith("```"):
        texto_json = texto_json.strip("`")
        if texto_json.lower().startswith("json"):
            texto_json = texto_json[4:]
    inicio = texto_json.find("{")
    fin = texto_json.rfind("}")
    if inicio != -1 and fin != -1:
        texto_json = texto_json[inicio:fin + 1]
    return json.loads(texto_json)


# ==========================================================
# CREACIÓN DE DOSSIER — (DM) DISPOSITIVOS MÉDICOS
# ==========================================================
# Checklist tomado de la pestaña "(DM)DISPOSITIVOS MÉDICOS" del formato
# ASS-RSA-FM007 v.17 (filas ~63-100), basado en el Decreto 4725 de 2005.
# 'riesgos' indica para qué clasificación de riesgo aplica cada ítem,
# según la nota "OTROS ELEMENTOS DE TRÁMITE" del mismo formato:
#   Riesgo I:        ítems 1-14, 17, 18
#   Riesgo IIa:      ítems 1-18
#   Riesgo IIb y III: todos los ítems (1-20)
# NOTA: el ítem 1 (Formulario debidamente diligenciado en medio digital) se
# omite a propósito — se refiere al mismo formulario ASS-RSA-FM007 que ya
# es la base de esta herramienta, así que no hace falta pedirlo como PDF
# aparte. Los demás ítems conservan su número original del Excel.
CHECKLIST_DM = [
    {"item": 2,  "articulo": "Art.19 lit. b", "titulo": "Poder (si aplica)",
     "sigla": "PODER",
     "descripcion": "Poder para tramitar el registro sanitario, cuando la solicitud sea presentada por un apoderado. Puede ser especial (nombre del poderdante, nombre del abogado titulado, trámites para los que está facultado) o general (escritura pública o certificado de existencia y representación legal). Si fue otorgado en el extranjero debe estar consularizado/legalizado o apostillado.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 3,  "articulo": "",              "titulo": "Comprobante de pago",
     "sigla": "PAGO",
     "descripcion": "Debe corresponder al concepto del trámite por la tarifa legal correspondiente.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 4,  "articulo": "Art.29 lit. b", "titulo": "Certificado de Venta Libre — CVL (productos importados)",
     "sigla": "CVL",
     "descripcion": "Emitido por la autoridad sanitaria del país de origen o de referencia (Canadá, Japón, Australia, Unión Europea o EE.UU.). Debe indicar el fabricante y el nombre del dispositivo con sus referencias. Vigencia de 1 año si no se declara otra. Debe estar consularizado/legalizado o apostillado, y acompañado de traducción oficial.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 5,  "articulo": "Art.29 lit. d", "titulo": "Autorización del fabricante (productos importados)",
     "sigla": "AUT FABRICANTE",
     "descripcion": "Debe indicar el nombre e domicilio del importador, los roles/actividades que desempeñará, y estar firmada y autorizada por el titular del registro sanitario y/o permiso de comercialización.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 6,  "articulo": "Art.29 lit. c", "titulo": "Existencia y Representación Legal",
     "sigla": "ERL",
     "descripcion": "Empresas nacionales: se valida en RUES (rues.org.co). Empresas extranjeras: prueba de constitución, existencia y representación legal del titular y del fabricante, expedida por el organismo competente del país de origen.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 7,  "articulo": "Art.18 lit. b", "titulo": "Certificado de Capacidad de Almacenamiento (CCAA) o BPM / Condiciones Técnico Sanitarias",
     "sigla": "CCAA",
     "descripcion": "Fabricantes nacionales: indicar fecha y número de radicado del CCAA/BPM/Condiciones Técnico Sanitarias. Producto importado para uso propio: certificación de que no se comercializará. Producto importado para comercializar: la línea debe estar aprobada dentro del CCAA vigente del importador.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 8,  "articulo": "Art.18 lit. c", "titulo": "Descripción del dispositivo médico",
     "sigla": "DESCRIPCION DM",
     "descripcion": "Debe contener indicaciones, contraindicaciones, advertencias, componentes principales, accesorios, relación con pacientes, todo en español, y la presentación comercial (unidades/contenido por empaque).",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 9,  "articulo": "Art.18 lit. d", "titulo": "Estudios técnicos y comprobaciones analíticas",
     "sigla": "ESTUDIOS TECNICOS",
     "descripcion": "Resumen de los documentos de verificación y validación del diseño (pruebas durante fabricación), y certificado de análisis del producto terminado con especificaciones y rangos de aceptación.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 10, "articulo": "Art.18 lit. i", "titulo": "Declaración de conformidad emitida por el fabricante",
     "sigla": "DECL CONFORMIDAD",
     "descripcion": "Emitida por el fabricante: razón social y domicilio, nombre del producto, referencias/códigos/modelos, y normas empleadas en diseño y fabricación. No reemplaza el CVL.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 11, "articulo": "Art.18 lit. e", "titulo": "Método de esterilización",
     "sigla": "MET ESTERILIZACION",
     "descripcion": "Indicar el o los métodos empleados, procedimiento, norma de referencia y estudios/resultados/conclusiones. Si usa óxido de etileno, adjuntar estudio de residuos (EO/ECH). Debe coincidir con inserto y etiqueta.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 12, "articulo": "Art.18 lit. f", "titulo": "Método de desecho o disposición final",
     "sigla": "MET DESECHO",
     "descripcion": "Documento emitido por el fabricante describiendo el método de desecho/disposición final, junto con el inserto donde se especifique.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 13, "articulo": "Art.18 lit. d", "titulo": "Vida útil (cuando aplique)",
     "sigla": "VIDA UTIL",
     "descripcion": "Estudios de estabilidad (esterilidad, envejecimiento natural/acelerado o almacenamiento) que validen la vida útil declarada, con resumen del método, verificación, validación y conclusión.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 14, "articulo": "Art.18 lit. g", "titulo": "Artes originales de etiquetas e insertos",
     "sigla": "ETIQUETAS INSERTOS",
     "descripcion": "Etiquetas originales del fabricante (nombre/referencia, fabricante, símbolos de seguridad), sticker del importador (producto, modelo/referencia, importador, número de registro sanitario), e inserto (IFU) en castellano con uso, presentación comercial, precauciones, disposición final, limpieza/desinfección/esterilización, almacenamiento.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 15, "articulo": "Art.18 lit. j", "titulo": "Información científica que respalde la seguridad (riesgo IIa, IIb, III)",
     "sigla": "INFO CIENTIFICA",
     "descripcion": "Pruebas de evaluación biológica (citotoxicidad, toxicidad sistémica, pirogenicidad, sensibilización, irritación, genotoxicidad, alergenicidad, hemocompatibilidad, carcinogenicidad) para productos en contacto con el paciente. Para dispositivos activos: pruebas eléctricas y de compatibilidad electromagnética (ej. normas IEC).",
     "riesgos": ["IIA", "IIB", "III"]},
    {"item": 16, "articulo": "Art.18 lit. j", "titulo": "Análisis de riesgos emitido por el fabricante (clase IIa, IIb, III)",
     "sigla": "ANALISIS RIESGOS",
     "descripcion": "Riesgos detectados en diseño y manufactura: causas, severidad, ocurrencia, detectabilidad, soluciones de mitigación (ej. norma ISO 14971).",
     "riesgos": ["IIA", "IIB", "III"]},
    {"item": 17, "articulo": "Art.18 lit. j", "titulo": "Lista de normas empleadas",
     "sigla": "LISTA NORMAS",
     "descripcion": "Listado de las normas de referencia internacional aplicadas total o parcialmente.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 18, "articulo": "Art.29 lit. a", "titulo": "Historial comercial del dispositivo médico (productos importados)",
     "sigla": "HIST COMERCIAL",
     "descripcion": "Países en los que se vende el dispositivo, indicando si ha presentado alertas sanitarias asociadas, expedido por el fabricante.",
     "riesgos": ["I", "IIA", "IIB", "III"]},
    {"item": 19, "articulo": "Art.18 lit. k", "titulo": "Estudios clínicos (clase IIb, III)",
     "sigla": "ESTUDIOS CLINICOS",
     "descripcion": "Realizados en pacientes para demostrar seguridad y efectividad, o estudios publicados de tecnologías similares/equivalentes.",
     "riesgos": ["IIB", "III"]},
    {"item": 20, "articulo": "Art.40",         "titulo": "Tarjeta implantable",
     "sigla": "TARJETA IMPLANTABLE",
     "descripcion": "Arte con nombre y modelo del dispositivo, lote, serie, dirección del fabricante, institución donde se implantó, fecha e identificación del paciente. Aplica para implantables que duran más de 30 días en el cuerpo, riesgo IIb y III.",
     "riesgos": ["IIB", "III"]},
]


def _obtener_items_aplicables_dm(riesgo):
    """Filtra el checklist según la clasificación de riesgo elegida."""
    return [it for it in CHECKLIST_DM if riesgo in it["riesgos"]]


def _analizar_documento_dossier_dm(texto_pdf, items_aplicables, pdf_bytes=None):
    """Le pide a Gemini que determine a cuál ítem del checklist corresponde
    un documento (por su contenido), y si parece cumplir lo que exige ese
    ítem o si encuentra algo claramente mal/faltante. Devuelve un dict ya
    parseado desde el JSON de la respuesta.

    Si 'pdf_bytes' viene informado (PDF escaneado, sin texto extraíble),
    se le adjunta el archivo directamente a Gemini para que lo lea como
    imagen, en vez de descartarlo."""
    lista_items = "\n".join(
        f"{it['item']}. {it['titulo']} ({it['articulo']}): {it['descripcion']}"
        for it in items_aplicables
    )
    system_prompt = (
        "Eres un experto en trámites regulatorios del INVIMA (Colombia) para "
        "dispositivos médicos, con base en el Decreto 4725 de 2005 y el Formato "
        "Único ASS-RSA-FM007.\n\n"
        "Te doy una lista de documentos requeridos para este trámite (número de "
        "ítem, título y los requisitos exactos que debe cumplir cada uno), y un "
        "documento que el usuario subió — puede venir como texto extraído de un "
        "PDF (el orden de las líneas puede salir un poco desordenado por la "
        "extracción automática), o como el archivo PDF adjunto directamente "
        "(cuando es un documento escaneado, en cuyo caso debes leerlo "
        "visualmente como si fuera una imagen).\n\n"
        "1. Determina a cuál ítem de la lista corresponde este documento, según "
        "su CONTENIDO (no el nombre del archivo). Si no corresponde claramente a "
        "ninguno, indica null.\n"
        "2. Evalúa si el documento, según lo que se puede leer, CUMPLE lo exigido "
        "para ese ítem (fechas de vigencia, firmas, datos exigidos, etc., en la "
        "medida en que el contenido lo permita determinar). Si encuentras algo que "
        "claramente falta o está mal (ej: vigencia vencida, falta firma o sello, "
        "no menciona un dato exigido), indícalo en el comentario.\n"
        "3. Si el contenido es muy corto, está en blanco, o no se puede "
        "interpretar bien (incluso como imagen), dilo en el comentario y usa "
        "conforme='no_determinable'.\n\n"
        f"LISTA DE DOCUMENTOS REQUERIDOS PARA ESTE TRÁMITE:\n{lista_items}\n\n"
        "Responde ÚNICAMENTE con un JSON con este formato exacto, sin texto "
        "adicional, sin comentarios y sin marcado markdown (sin ```):\n"
        '{"item": numero_o_null, "confianza": "alta|media|baja", '
        '"conforme": true_o_false_o_"no_determinable", "comentario": "explicación breve en español, máximo 3 líneas"}'
    )
    mensaje_usuario = texto_pdf[:15000] if texto_pdf else (
        "(Este documento no tiene texto extraíble por métodos normales — "
        "probablemente está escaneado como imagen. Léelo directamente del "
        "archivo PDF adjunto.)"
    )
    respuesta_texto = _llamar_gemini_api(
        system_prompt=system_prompt,
        mensajes=[{"role": "user", "content": mensaje_usuario}],
        modelo=MODELO_IA_CALIDAD,
        max_tokens=500,
        pdf_bytes=pdf_bytes,
    )
    texto_json = respuesta_texto.strip()
    if texto_json.startswith("```"):
        texto_json = texto_json.strip("`")
        if texto_json.lower().startswith("json"):
            texto_json = texto_json[4:]
    inicio = texto_json.find("{")
    fin = texto_json.rfind("}")
    if inicio != -1 and fin != -1:
        texto_json = texto_json[inicio:fin + 1]
    return json.loads(texto_json)


def _procesar_documentos_dossier_dm(archivos_con_bytes, items_aplicables, callback_progreso=None,
                                     segundos_pausa=1.5):
    """Analiza cada PDF, lo asigna al ítem del checklist que mejor le
    corresponde, y arma: (1) una tabla de resultados por archivo, (2) un
    resumen de cobertura del checklist completo (qué falta), y (3) los
    nombres finales sugeridos ('{item}. {SIGLA}.pdf'), manejando duplicados
    cuando dos archivos caen en el mismo ítem.

    'archivos_con_bytes' es una lista de tuplas (nombre, bytes) — así se
    puede llamar tanto con archivos recién subidos como con archivos ya
    leídos en memoria (por ejemplo, al reintentar solo los que fallaron
    por límite de cuota de Gemini, sin tener que volver a subirlos).

    'segundos_pausa' espacía las llamadas a Gemini entre un documento y
    el siguiente, para reducir el riesgo de chocar con el límite de
    peticiones por minuto de la cuota gratuita."""
    resultados_archivos = []  # uno por PDF subido
    asignaciones_por_item = {}  # item -> lista de nombres finales ya usados (para numerar duplicados)
    archivos_para_zip = []  # (nombre_final, bytes)

    total = len(archivos_con_bytes)
    for idx, (nombre_archivo, bytes_pdf) in enumerate(archivos_con_bytes):
        if callback_progreso:
            callback_progreso(idx, total, nombre_archivo)
        if idx > 0 and segundos_pausa:
            time.sleep(segundos_pausa)

        try:
            texto_pdf = _extraer_texto_pdf(bytes_pdf)
            if len(texto_pdf) < 30:
                # Probablemente escaneado: en vez de descartarlo, se le manda
                # el PDF directo a Gemini para que lo lea como imagen.
                analisis = _analizar_documento_dossier_dm("", items_aplicables, pdf_bytes=bytes_pdf)
            else:
                analisis = _analizar_documento_dossier_dm(texto_pdf, items_aplicables)
        except Exception as e:
            resultados_archivos.append({
                "Archivo_Original": nombre_archivo, "Item": "-", "Documento": "-",
                "Conforme": "-", "Comentario": f"❌ Error analizando con IA: {e}",
                "Nombre_Final": None
            })
            continue

        item_num = analisis.get("item")
        conforme = analisis.get("conforme")
        comentario = (analisis.get("comentario") or "").strip()

        item_info = next((it for it in items_aplicables if it["item"] == item_num), None)

        if item_info is None:
            resultados_archivos.append({
                "Archivo_Original": nombre_archivo, "Item": "-", "Documento": "Sin clasificar",
                "Conforme": "-", "Comentario": comentario or "No se identificó a qué ítem del checklist corresponde.",
                "Nombre_Final": None
            })
            archivos_para_zip.append((f"SIN CLASIFICAR - {nombre_archivo}", bytes_pdf))
            continue

        # Nombre final, manejando duplicados (dos archivos para el mismo ítem)
        base_nombre = f"{item_info['item']}. {item_info['sigla']}"
        usados = asignaciones_por_item.setdefault(item_info["item"], [])
        if not usados:
            nombre_final = base_nombre
        else:
            nombre_final = f"{base_nombre} ({len(usados) + 1})"
        usados.append(nombre_final)

        if conforme is True:
            estado_conforme = "✅ Conforme"
        elif conforme is False:
            estado_conforme = "⚠ Con observación"
        else:
            estado_conforme = "❓ No determinable"

        resultados_archivos.append({
            "Archivo_Original": nombre_archivo, "Item": item_info["item"], "Documento": item_info["titulo"],
            "Conforme": estado_conforme, "Comentario": comentario or "-",
            "Nombre_Final": f"{nombre_final}.pdf"
        })
        archivos_para_zip.append((f"{nombre_final}.pdf", bytes_pdf))

    # Resumen de cobertura: qué ítems del checklist aplicable quedaron cubiertos
    items_cubiertos = set(asignaciones_por_item.keys())
    resumen_cobertura = []
    for it in items_aplicables:
        cubierto = it["item"] in items_cubiertos
        resumen_cobertura.append({
            "Item": it["item"], "Documento": it["titulo"], "Sigla": it["sigla"],
            "Estado": "✅ Subido" if cubierto else "❌ FALTA"
        })

    return resultados_archivos, resumen_cobertura, archivos_para_zip


# ==========================================================
# CREACIÓN DE DOSSIER — MODIFICACIONES AUTOMÁTICAS
# ==========================================================
# Estructura tomada de la pestaña "MODIFICACIONES AUTOMATICAS" del formato
# ASS-RSA-FM007 v.17 (filas 13-189). A diferencia de (DM), aquí no hay una
# numeración única 1-20: cada código (o grupo de códigos que comparten
# requisitos) tiene su propio bloque de documentos. El ítem "Formulario
# debidamente diligenciado" (aplica a todas las modificaciones) se omite
# por la misma razón que en (DM). Los otros 2 documentos universales
# (Comprobante de pago, Poder si aplica) sí se mantienen.

CODIGOS_MOD_LEGAL = [
    ("TITULAR",         [("A", "Cambio"), ("B", "Cambio de Razón Social"), ("C", "Adición"), ("D", "Cambio de Domicilio")]),
    ("FABRICANTE",      [("E", "Cambio"), ("F", "Cambio de Razón Social"), ("G", "Cambio de Domicilio"), ("H", "Adición"), ("I", "Exclusión")]),
    ("IMPORTADOR",      [("J", "Cambio"), ("K", "Cambio de Razón Social"), ("L", "Cambio de Domicilio"), ("M", "Adición"), ("N", "Exclusión")]),
    ("ACONDICIONADOR",  [("Ñ1", "Cambio"), ("Ñ2", "Cambio de Razón Social"), ("Ñ3", "Cambio de Domicilio"), ("Ñ4", "Adición"), ("Ñ5", "Exclusión")]),
]

CODIGOS_MOD_TECNICO = [
    ("O1", "Cambio del Nombre del Producto"),
    ("O2", "Cambio de Nombre Genérico"),
    ("P1", "Presentación Comercial — Adición"),
    ("P2", "Presentación Comercial — Cambio"),
    ("P3", "Presentación Comercial — Exclusión"),
    ("Q1", "Sistemas y Subsistemas — Adición"),
    ("Q2", "Sistemas y Subsistemas — Exclusión"),
    ("R1", "Material de Envase — Adición"),
    ("R2", "Material de Envase — Cambio"),
    ("R3", "Material de Envase — Exclusión"),
    ("S1", "Etiquetas/Insertos/Stickers — Adición"),
    ("S2", "Etiquetas/Insertos/Stickers — Cambio"),
    ("S3", "Etiquetas/Insertos/Stickers — Exclusión"),
    ("T1", "Vida Útil — Adición"),
    ("T2", "Vida Útil — Cambio"),
    ("T3", "Vida Útil — Exclusión"),
    ("U1", "Marca — Adición"),
    ("U2", "Marca — Cambio"),
    ("U3", "Marca — Exclusión"),
    ("V",  "Cambio de la Modalidad"),
    ("W1", "Indicaciones de Uso — Adición"),
    ("W2", "Indicaciones de Uso — Cambio"),
    ("W3", "Indicaciones de Uso — Exclusión"),
    ("X",  "Cambio de la Clasificación de Riesgo"),
    ("Y1", "Adición de Referencias"),
    ("Y2", "Exclusión de Referencias"),
    ("Z1", "Observaciones/Advertencias — Adición"),
    ("Z2", "Observaciones/Advertencias — Cambio"),
    ("Z3", "Observaciones/Advertencias — Exclusión"),
]

DOCS_UNIVERSALES_MOD = [
    {"sigla": "PAGO",  "documento": "Comprobante de pago",
     "descripcion": "Comprobante de pago por concepto del trámite en original por la tarifa legal correspondiente."},
    {"sigla": "PODER", "documento": "Poder (si aplica)",
     "descripcion": "Si la solicitud es presentada por un apoderado: poder especial (poderdante, abogado, trámites facultados) o general (escritura pública o certificado de existencia/representación legal). Si fue otorgado en el extranjero debe estar consularizado/legalizado o apostillado."},
]

BLOQUES_MOD = {
    "A": {"titulo": "Cambio de Titular", "codigos": ["A"], "documentos": [
        {"sigla": "CESION", "documento": "Documento de Cesión",
         "descripcion": "Debe indicar (conjunta o separadamente) la intención de transferir y aceptar la cesión. Solo el titular del registro puede cederlo. Debe identificar plenamente el registro (número, expediente, nombre del producto, marca) y estar firmado por el representante legal del cedente y del cesionario."},
        {"sigla": "AUT FABRICANTE", "documento": "Autorización del Fabricante o su Autorizado",
         "descripcion": "Documento expedido por el fabricante o su autorizado, estableciendo la relación entre el cesionario y el fabricante responsable."},
        {"sigla": "ERL", "documento": "Existencia y Representación Legal",
         "descripcion": "Nacionales: validar en RUES (rues.org.co). Extranjeras: documento de autoridad competente del país de origen (no vale uno emitido por el mismo titular/fabricante)."},
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "En el ítem 2.2: señalar la letra del motivo, qué figura actualmente en el registro, y cómo debe quedar en la resolución."},
    ]},
    "BFKÑ2": {"titulo": "Cambio de Razón Social (Titular/Fabricante/Importador/Acondicionador)", "codigos": ["B", "F", "K", "Ñ2"], "documentos": [
        {"sigla": "ERL", "documento": "Existencia y Representación Legal",
         "descripcion": "Nacionales: validar cambio de razón social en RUES. Extranjeras: documento de autoridad competente del país de origen, o en su defecto CVL que refleje el nuevo nombre, acompañado de declaración del fabricante."},
        {"sigla": "ETIQUETA STICKER", "documento": "Etiqueta del Fabricante y/o Sticker del Importador",
         "descripcion": "Evidenciar el cambio de razón social en las etiquetas del fabricante, o en el sticker del importador (nombre, domicilio, número de registro). No se aceptan etiquetas con cambios distintos a los ya autorizados."},
    ]},
    "C": {"titulo": "Adición de Titular", "codigos": ["C"], "documentos": [
        {"sigla": "CESION", "documento": "Documento de Cesión",
         "descripcion": "Mismos requisitos que para Cambio de Titular: intención de transferir/aceptar, identificación plena del registro, firmado por representantes legales de cedente y cesionario."},
        {"sigla": "AUT FABRICANTE", "documento": "Autorización del Fabricante o su Autorizado",
         "descripcion": "Documento expedido por el fabricante o su autorizado, estableciendo la relación entre el cesionario y el fabricante responsable."},
        {"sigla": "ERL", "documento": "Existencia y Representación Legal",
         "descripcion": "Nacionales: validar en RUES. Extranjeras: documento de autoridad competente del país de origen."},
    ]},
    "DGLÑ3": {"titulo": "Cambio de Domicilio (Titular/Fabricante/Importador/Acondicionador)", "codigos": ["D", "G", "L", "Ñ3"], "documentos": [
        {"sigla": "ERL", "documento": "Existencia y Representación Legal",
         "descripcion": "Nacionales: validar cambio de domicilio en RUES. Extranjeras: documento de autoridad competente, o CVL con el nuevo domicilio acompañado de declaración del fabricante/titular."},
        {"sigla": "ETIQUETA STICKER", "documento": "Etiqueta del Fabricante y/o Sticker del Importador",
         "descripcion": "Evidenciar la nueva dirección en las etiquetas (fabricante) o rótulo/sticker (importador)."},
        {"sigla": "CCAA", "documento": "Certificado de Capacidad de Almacenamiento y/o Acondicionamiento",
         "descripcion": "Para cambio de domicilio de importador y acondicionador. Debe estar vigente; se valida con las bases de la Dirección de Dispositivos Médicos."},
    ]},
    "E": {"titulo": "Cambio de Fabricante", "codigos": ["E"], "documentos": [
        {"sigla": "CERT FABRICANTE", "documento": "Certificación del Fabricante",
         "descripcion": "Indicar el nombre del producto, precisar que mantiene sus características autorizadas, y estar rotulado y firmado por el fabricante."},
        {"sigla": "BPM SGC", "documento": "Certificación del Sistema de Gestión de Calidad / BPM o equivalente",
         "descripcion": "Nacionales: validar en RUES / bases de Certificaciones. Extranjeras: certificado de calidad (ISO 13485, ISO 9001, etc.) de autoridad competente, no emitido por el mismo titular/fabricante."},
        {"sigla": "CVL", "documento": "Certificado de Venta Libre",
         "descripcion": "Expedido por entidad competente, indicando el fabricante a cambiar y el producto con referencias/modelos autorizados. Vigencia 1 año si no se declara otra. Consularizado/legalizado o apostillado, con traducción oficial."},
        {"sigla": "ETIQUETA FABRICANTE", "documento": "Etiqueta del Fabricante",
         "descripcion": "Tal como provienen del país de origen: nombre y domicilio del fabricante, nombre del producto con referencias/modelos autorizados."},
        {"sigla": "INSERTOS", "documento": "Insertos Originales",
         "descripcion": "Nombre del producto, indicaciones, contraindicaciones y advertencias autorizadas; idioma original y castellano; información del fabricante con domicilio."},
        {"sigla": "REL COMERCIAL FABR", "documento": "Documento de relación comercial entre el fabricante autorizado y el nuevo",
         "descripcion": "Nacionales: contrato de maquila entre ambos fabricantes. Extranjeras: contrato de maquila, certificado de casa matriz (filiales/subsidiarias), o CVL que consigne fabricante legal y planta."},
    ]},
    "H": {"titulo": "Adición de Fabricante", "codigos": ["H"], "documentos": [
        {"sigla": "ERL", "documento": "Existencia y Representación Legal",
         "descripcion": "Nacionales: validar en RUES. Extranjeras: documento de autoridad competente del país de origen."},
        {"sigla": "BPM SGC", "documento": "Certificación del Sistema de Gestión de Calidad / BPM o equivalente",
         "descripcion": "Nacionales: validar en bases de Certificaciones. Extranjeras: certificado de calidad (ISO 13485, ISO 9001, etc.) de autoridad competente."},
        {"sigla": "CERT FABRICANTE", "documento": "Certificación del Fabricante",
         "descripcion": "Indicar el nombre del producto, precisar que mantiene sus características autorizadas, y estar rotulado y firmado por el fabricante."},
        {"sigla": "CVL", "documento": "Certificado de Venta Libre",
         "descripcion": "Expedido por entidad competente, indicando el fabricante y producto con referencias/modelos autorizados. Vigencia 1 año si no declara otra, consularizado/legalizado/apostillado con traducción."},
        {"sigla": "ETIQUETA FABRICANTE", "documento": "Etiqueta del Fabricante",
         "descripcion": "Tal como provienen del país de origen, con nombre/domicilio del fabricante y producto con referencias/modelos autorizados."},
        {"sigla": "REL COMERCIAL FABR", "documento": "Documento de relación comercial entre el fabricante autorizado y el nuevo a adicionar",
         "descripcion": "Nacionales: contrato de maquila. Extranjeras: contrato de maquila, certificado de casa matriz, o CVL que consigne fabricante legal y planta."},
    ]},
    "INÑ5": {"titulo": "Exclusión de Fabricante/Importador/Acondicionador", "codigos": ["I", "N", "Ñ5"], "documentos": [
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "En el ítem 2.2: señalar la letra del motivo, qué figura actualmente en el registro, y cómo debe quedar en la resolución."},
    ]},
    "JMÑ1Ñ4": {"titulo": "Adición o Cambio de Importador/Acondicionador", "codigos": ["J", "M", "Ñ1", "Ñ4"], "documentos": [
        {"sigla": "AUT TITULAR", "documento": "Autorización del Titular",
         "descripcion": "Indicar nombre y domicilio del importador, roles/actividades que desempeñará, firmada y autorizada por el titular del registro/permiso."},
        {"sigla": "ERL", "documento": "Existencia y Representación Legal",
         "descripcion": "Nacionales: validar en RUES."},
        {"sigla": "CCAA", "documento": "Certificado de Capacidad de Almacenamiento y/o Acondicionamiento",
         "descripcion": "Debe estar vigente, validado con las bases de la Dirección de Dispositivos Médicos."},
        {"sigla": "STICKER IMPORTADOR", "documento": "Sticker o Rótulo Importador",
         "descripcion": "Datos del nuevo importador con domicilio, nombre del producto, modelo/referencias, número de registro/permiso. No puede tapar información del fabricante."},
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente, y cómo debe quedar en la resolución. Diligenciar dirección/domicilio completo del importador y acondicionador."},
    ]},
    "O": {"titulo": "Cambio del Nombre del Producto / Nombre Genérico", "codigos": ["O1", "O2"], "documentos": [
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, el nombre actual autorizado, y cómo debe quedar en la resolución. Aclarar si el cambio es de nombre del producto o nombre genérico."},
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Carta del titular evidenciando la justificación del cambio de nombre del producto."},
        {"sigla": "CVL DECL CONFORMIDAD", "documento": "Certificado de Venta Libre y Declaración de Conformidad",
         "descripcion": "Importados: el nombre debe coincidir con el CVL o la Declaración de Conformidad del fabricante. Nacionales: Declaración de Conformidad del Fabricante Nacional. CVL: expedido por entidad competente, vigencia 1 año si no declara otra, consularizado/legalizado/apostillado con traducción."},
        {"sigla": "INSERTOS", "documento": "Insertos Originales",
         "descripcion": "Nuevo nombre del producto, indicaciones, contraindicaciones y advertencias autorizadas; idioma original y castellano; información del fabricante con domicilio."},
        {"sigla": "ETIQUETAS STICKER", "documento": "Etiquetas y/o Sticker",
         "descripcion": "Etiquetas del fabricante y sticker del importador con el nuevo nombre, manteniendo las demás condiciones autorizadas."},
    ]},
    "P": {"titulo": "Presentación Comercial (Adición/Cambio/Exclusión)", "codigos": ["P1", "P2", "P3"], "documentos": [
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente, y la cantidad con unidades como se comercializa (caja por unidad, blíster, set, etc.). Si incluye muestras gratis, especificarlo."},
        {"sigla": "INSERTOS", "documento": "Insertos Originales",
         "descripcion": "Nombre del producto con sus presentaciones comerciales, indicaciones/contraindicaciones/advertencias autorizadas, idioma original y castellano, información del fabricante."},
        {"sigla": "ETIQUETA ORIGINAL", "documento": "Etiqueta Original",
         "descripcion": "Etiquetas del fabricante con las nuevas presentaciones comerciales, manteniendo las demás condiciones autorizadas."},
    ]},
    "Q": {"titulo": "Sistemas y Subsistemas (partes de Equipos Biomédicos)", "codigos": ["Q1", "Q2"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Motivo de la adición de sistemas/subsistemas, precisando diferencias entre lo autorizado y lo que se quiere adicionar."},
        {"sigla": "CATALOGOS", "documento": "Catálogos",
         "descripcion": "Deben relacionar los subsistemas (partes) a adicionar, indicando el folio donde se evidencian."},
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente, y cómo debe quedar en la resolución."},
    ]},
    "R": {"titulo": "Material de Envase Primario/Secundario/Empaque", "codigos": ["R1", "R2", "R3"], "documentos": [
        {"sigla": "ESTUDIOS TECNICOS", "documento": "Estudios Técnicos",
         "descripcion": "Emitidos por el fabricante, justificando el cambio de envase y garantizando integridad del producto: parámetros, especificaciones y rangos de aceptabilidad (certificado de análisis o informe de pruebas)."},
        {"sigla": "ESTUDIOS ESTABILIDAD", "documento": "Estudios de Estabilidad",
         "descripcion": "Si la vida útil depende del empaque que se cambia: estudios que demuestren la vida útil aprobada dentro del nuevo empaque (metodología, resultados, conclusiones)."},
        {"sigla": "ESPEC TECNICAS", "documento": "Especificaciones Técnicas",
         "descripcion": "Documento del fabricante con las especificaciones de los nuevos materiales de envase, o declaración certificando dichas especificaciones."},
        {"sigla": "ETIQUETA ORIGINAL", "documento": "Etiqueta Original",
         "descripcion": "Etiquetas del fabricante con el nuevo material de envase primario/secundario o empaque."},
    ]},
    "S": {"titulo": "Etiquetas, Stickers e Insertos (Adición/Cambio/Exclusión)", "codigos": ["S1", "S2", "S3"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Justificación descriptiva del cambio, adición y/o exclusión de etiquetas, stickers o insertos."},
        {"sigla": "INSERTOS MANUALES", "documento": "Insertos o Manuales",
         "descripcion": "Para adición o cambio: inserto/manual donde se evidencien los cambios (si aplica)."},
        {"sigla": "ETIQUETA STICKER", "documento": "Etiqueta o Sticker",
         "descripcion": "Debe evidenciar lo descrito en el documento justificativo."},
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente, y descripción de los cambios (no citar folios ni incluir imágenes)."},
    ]},
    "T": {"titulo": "Vida Útil (Adición/Cambio/Exclusión)", "codigos": ["T1", "T2", "T3"], "documentos": [
        {"sigla": "ESTUDIOS ESTABILIDAD", "documento": "Estudios de Estabilidad (Dispositivos Médicos)",
         "descripcion": "Estudios que validen la vida útil atribuida: resumen del método, verificación, validación y resultado final."},
        {"sigla": "DECL FABR ESTABILIDAD", "documento": "Declaración del Fabricante y Estudios de Estabilidad (Equipos Biomédicos)",
         "descripcion": "Estudios de estabilidad que validen la vida útil; si no se puede sustentar, declaración del fabricante certificando la vida útil del equipo (también aplica a accesorios/DM estériles usados con el equipo)."},
    ]},
    "U": {"titulo": "Marca (Adición/Cambio/Exclusión)", "codigos": ["U1", "U2", "U3"], "documentos": [
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente, y cómo debe quedar en la resolución."},
        {"sigla": "ETIQUETA ORIGINAL", "documento": "Etiqueta Original",
         "descripcion": "Etiquetas originales donde se evidencie el cambio o adición de marca."},
    ]},
    "V": {"titulo": "Cambio de la Modalidad del Registro Sanitario", "codigos": ["V"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Justificación del cambio de modalidad. Solo se permite cambiar de 'importar y vender' a 'importar, empacar y vender'; para otras modalidades se requiere registro/permiso nuevo."},
        {"sigla": "CCAA CONDICIONES", "documento": "Certificado de Capacidad de Almacenamiento/Acondicionamiento o Condiciones Sanitarias",
         "descripcion": "Validado con las bases del Instituto; aportar el radicado del documento."},
    ]},
    "W": {"titulo": "Indicaciones de Uso (Adición/Cambio/Exclusión)", "codigos": ["W1", "W2", "W3"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Justificación de la adición, cambio o exclusión de indicaciones de uso. No puede afectar diseño/seguridad ya autorizados (de lo contrario se requiere registro nuevo)."},
        {"sigla": "INSERTO MANUALES", "documento": "Inserto o Manuales",
         "descripcion": "El uso debe estar acorde con el inserto/manual de los modelos/referencias aprobadas."},
        {"sigla": "ETIQUETA ORIGINAL", "documento": "Etiqueta Original",
         "descripcion": "Si la indicación de uso está en las etiquetas, deben actualizarse también."},
    ]},
    "X": {"titulo": "Cambio de la Clasificación de Riesgo", "codigos": ["X"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Justificación del cambio de clasificación de riesgo, expedida por el titular del registro/permiso."},
        {"sigla": "DOC TECNICOS", "documento": "Documentos Técnicos",
         "descripcion": "DM riesgo I→IIA: información científica de seguridad (evaluación biológica) y análisis de riesgos del fabricante. DM IIA→IIB/III: estudios clínicos. EB I→IIA: pruebas eléctricas/compatibilidad electromagnética, evaluación biológica de accesorios en contacto con paciente, análisis de riesgos. EB IIA→IIB/III: estudios clínicos, certificado de estándares de calidad, datos de la IPS donde se instalará, declaración del fabricante/representante (no en experimentación, usos, soporte de insumos/mantenimiento 5 años, capacitación, manuales en español)."},
        {"sigla": "ETIQUETA INSERTO", "documento": "Etiqueta Original e Inserto",
         "descripcion": "Para EB que cambian de IIA a IIB/III: sticker del importador indicando Permiso de Comercialización y nomenclatura EBC."},
    ]},
    "Y1": {"titulo": "Adición de Referencias y/o Modelos", "codigos": ["Y1"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Justificación de la adición de referencias, destacando diferencias con las ya registradas, manteniendo misma indicación de uso y principio de funcionamiento."},
        {"sigla": "CVL", "documento": "Certificado de Venta Libre",
         "descripcion": "Importados: debe evidenciar las nuevas referencias/modelos, nombre del producto, fabricante. Vigencia 1 año si no declara otra, consularizado/legalizado/apostillado con traducción."},
        {"sigla": "DECL CONFORMIDAD", "documento": "Declaración de Conformidad",
         "descripcion": "DM: si el CVL solo declara familias, declaración del fabricante indicando que las subfamilias coinciden con las referencias a adicionar. EB: declaración de cumplimiento de normas internacionales con el nombre del equipo y modelos/referencias a adicionar."},
        {"sigla": "CATALOGOS", "documento": "Catálogos",
         "descripcion": "Deben contener las referencias/modelos a adicionar, con la misma indicación de uso autorizada."},
        {"sigla": "ESTUDIOS TECNICOS", "documento": "Estudios Técnicos y Comprobaciones Analíticas",
         "descripcion": "Certificado de análisis del producto terminado (especificaciones, rangos de aceptación) o resumen de verificación/validación del diseño, para las referencias a adicionar."},
        {"sigla": "ETIQUETA INSERTO", "documento": "Etiqueta Original e Inserto",
         "descripcion": "Etiquetas del fabricante con nombre del producto, referencias/modelos, fabricante, para las referencias que se desean adicionar."},
    ]},
    "Y2": {"titulo": "Exclusión de Referencias y/o Modelos", "codigos": ["Y2"], "documentos": [
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente en el registro, y cómo debe quedar en la resolución."},
    ]},
    "Z": {"titulo": "Observaciones, Advertencias, Contraindicaciones y Precauciones", "codigos": ["Z1", "Z2", "Z3"], "documentos": [
        {"sigla": "DOC JUSTIFICATIVO", "documento": "Documento Justificativo",
         "descripcion": "Justificación de la adición de observaciones/advertencias, destacando diferencias con lo ya registrado."},
        {"sigla": "DILIG FORMULARIO", "documento": "Diligenciamiento del Formulario",
         "descripcion": "Señalar la letra del motivo, qué figura actualmente, y cómo debe quedar en la resolución."},
        {"sigla": "ETIQUETA INSERTO", "documento": "Etiqueta Original e Inserto",
         "descripcion": "De las observaciones/advertencias a adicionar. No aplica para exclusión."},
    ]},
}


def _obtener_bloques_desde_codigos(codigos_elegidos):
    """Dado un conjunto de códigos elegidos por el usuario (ej: ['Y1','H']),
    devuelve la lista de bloques únicos que se activan (un código puede
    pertenecer a un bloque compartido con otros, ej. 'B' activa el mismo
    bloque que 'F','K','Ñ2')."""
    bloques_activados = []
    ids_ya_incluidos = set()
    for bloque_id, info in BLOQUES_MOD.items():
        if any(c in codigos_elegidos for c in info["codigos"]) and bloque_id not in ids_ya_incluidos:
            bloques_activados.append({"bloque_id": bloque_id, **info})
            ids_ya_incluidos.add(bloque_id)
    return bloques_activados


def _analizar_documento_modificacion(texto_pdf, candidatos, pdf_bytes=None):
    """Análogo a _analizar_documento_dossier_dm pero para Modificaciones
    Automáticas, donde los candidatos vienen identificados por un id
    compuesto (bloque + documento) en vez de un número de ítem único.

    Si 'pdf_bytes' viene informado (PDF escaneado, sin texto extraíble),
    se adjunta el archivo directamente para que Gemini lo lea como imagen."""
    lista_candidatos = "\n".join(
        f"{c['id']}. [{c['bloque_titulo']}] {c['documento']}: {c['descripcion']}" for c in candidatos
    )
    system_prompt = (
        "Eres un experto en trámites regulatorios del INVIMA (Colombia) para "
        "modificaciones automáticas de registros sanitarios de dispositivos "
        "médicos, con base en el Decreto 4725 de 2005 y el Formato Único "
        "ASS-RSA-FM007.\n\n"
        "Te doy una lista de documentos requeridos (con un identificador único, "
        "el bloque/tipo de modificación al que pertenecen, y los requisitos "
        "exactos que deben cumplir), y un documento que el usuario subió — puede "
        "venir como texto extraído de un PDF (el orden de las líneas puede salir "
        "desordenado por la extracción automática), o como el archivo PDF "
        "adjunto directamente (cuando está escaneado, en cuyo caso debes leerlo "
        "visualmente como si fuera una imagen).\n\n"
        "1. Determina a cuál identificador de la lista corresponde este documento, "
        "según su CONTENIDO (no el nombre del archivo). Si no corresponde "
        "claramente a ninguno, indica null.\n"
        "2. Evalúa si el documento CUMPLE lo exigido para ese ítem (vigencias, "
        "firmas, datos exigidos, etc., en la medida en que el contenido lo "
        "permita determinar). Si encuentras algo claramente mal o faltante, "
        "indícalo.\n"
        "3. Si el contenido es muy corto, está en blanco, o no se puede "
        "interpretar bien (incluso como imagen), dilo y usa "
        "conforme='no_determinable'.\n\n"
        f"LISTA DE DOCUMENTOS REQUERIDOS:\n{lista_candidatos}\n\n"
        "Responde ÚNICAMENTE con un JSON con este formato exacto, sin texto "
        "adicional, sin comentarios y sin marcado markdown (sin ```):\n"
        '{"id": "id_o_null", "confianza": "alta|media|baja", '
        '"conforme": true_o_false_o_"no_determinable", "comentario": "explicación breve en español, máximo 3 líneas"}'
    )
    mensaje_usuario = texto_pdf[:15000] if texto_pdf else (
        "(Este documento no tiene texto extraíble por métodos normales — "
        "probablemente está escaneado como imagen. Léelo directamente del "
        "archivo PDF adjunto.)"
    )
    respuesta_texto = _llamar_gemini_api(
        system_prompt=system_prompt,
        mensajes=[{"role": "user", "content": mensaje_usuario}],
        modelo=MODELO_IA_CALIDAD,
        max_tokens=500,
        pdf_bytes=pdf_bytes,
    )
    texto_json = respuesta_texto.strip()
    if texto_json.startswith("```"):
        texto_json = texto_json.strip("`")
        if texto_json.lower().startswith("json"):
            texto_json = texto_json[4:]
    inicio = texto_json.find("{")
    fin = texto_json.rfind("}")
    if inicio != -1 and fin != -1:
        texto_json = texto_json[inicio:fin + 1]
    return json.loads(texto_json)


def _procesar_documentos_modificacion(archivos_con_bytes, bloques_activados, callback_progreso=None,
                                       segundos_pausa=1.5):
    """Analiza cada PDF y lo asigna al documento que mejor le corresponde,
    entre TODOS los documentos de los bloques activados más los 2
    documentos universales (Pago, Poder). Organiza el resultado en
    carpetas por código dentro del .zip final.

    'archivos_con_bytes' es una lista de tuplas (nombre, bytes) — permite
    reintentar solo los archivos que fallaron por límite de cuota de
    Gemini sin tener que volver a subirlos. 'segundos_pausa' espacía las
    llamadas a Gemini para reducir el riesgo de chocar con el límite de
    peticiones por minuto."""
    candidatos = []
    for bloque in bloques_activados:
        nombre_carpeta_bloque = f"{'-'.join(bloque['codigos'])} {bloque['titulo']}"
        for idx_doc, doc in enumerate(bloque["documentos"]):
            candidatos.append({
                "id": f"{bloque['bloque_id']}::{idx_doc}",
                "bloque_id": bloque["bloque_id"], "bloque_titulo": bloque["titulo"],
                "carpeta": nombre_carpeta_bloque,
                "documento": doc["documento"], "sigla": doc["sigla"], "descripcion": doc["descripcion"],
            })
    for idx_doc, doc in enumerate(DOCS_UNIVERSALES_MOD):
        candidatos.append({
            "id": f"UNIVERSAL::{idx_doc}",
            "bloque_id": "UNIVERSAL", "bloque_titulo": "Documentos para todas las modificaciones",
            "carpeta": "DOCUMENTOS GENERALES",
            "documento": doc["documento"], "sigla": doc["sigla"], "descripcion": doc["descripcion"],
        })

    resultados_archivos = []
    asignaciones_por_id = {}
    archivos_para_zip = []

    total = len(archivos_con_bytes)
    for idx, (nombre_archivo, bytes_pdf) in enumerate(archivos_con_bytes):
        if callback_progreso:
            callback_progreso(idx, total, nombre_archivo)
        if idx > 0 and segundos_pausa:
            time.sleep(segundos_pausa)

        try:
            texto_pdf = _extraer_texto_pdf(bytes_pdf)
            if len(texto_pdf) < 30:
                # Probablemente escaneado: se manda el PDF directo a Gemini
                # para que lo lea como imagen, en vez de descartarlo.
                analisis = _analizar_documento_modificacion("", candidatos, pdf_bytes=bytes_pdf)
            else:
                analisis = _analizar_documento_modificacion(texto_pdf, candidatos)
        except Exception as e:
            resultados_archivos.append({
                "Archivo_Original": nombre_archivo, "Bloque": "-", "Documento": "-",
                "Conforme": "-", "Comentario": f"❌ Error analizando con IA: {e}",
                "Nombre_Final": None
            })
            continue

        id_match = analisis.get("id")
        conforme = analisis.get("conforme")
        comentario = (analisis.get("comentario") or "").strip()
        candidato_info = next((c for c in candidatos if c["id"] == id_match), None)

        if candidato_info is None:
            resultados_archivos.append({
                "Archivo_Original": nombre_archivo, "Bloque": "-", "Documento": "Sin clasificar",
                "Conforme": "-", "Comentario": comentario or "No se identificó a qué documento corresponde.",
                "Nombre_Final": f"SIN CLASIFICAR - {nombre_archivo}"
            })
            archivos_para_zip.append((f"SIN CLASIFICAR - {nombre_archivo}", bytes_pdf))
            continue

        base_nombre = f"{candidato_info['carpeta']}/{candidato_info['sigla']}"
        usados = asignaciones_por_id.setdefault(id_match, [])
        nombre_final = base_nombre if not usados else f"{base_nombre} ({len(usados) + 1})"
        usados.append(nombre_final)

        if conforme is True:
            estado_conforme = "✅ Conforme"
        elif conforme is False:
            estado_conforme = "⚠ Con observación"
        else:
            estado_conforme = "❓ No determinable"

        resultados_archivos.append({
            "Archivo_Original": nombre_archivo, "Bloque": candidato_info["bloque_titulo"],
            "Documento": candidato_info["documento"], "Conforme": estado_conforme, "Comentario": comentario or "-",
            "Nombre_Final": f"{nombre_final}.pdf"
        })
        archivos_para_zip.append((f"{nombre_final}.pdf", bytes_pdf))

    ids_cubiertos = set(asignaciones_por_id.keys())
    resumen_cobertura = []
    for c in candidatos:
        resumen_cobertura.append({
            "Carpeta": c["carpeta"], "Documento": c["documento"], "Sigla": c["sigla"],
            "Estado": "✅ Subido" if c["id"] in ids_cubiertos else "❌ FALTA"
        })

    return resultados_archivos, resumen_cobertura, archivos_para_zip


def _recalcular_cobertura_modificacion(resultados, bloques_activados):
    """Recalcula la tabla de cobertura del checklist a partir de una lista
    de resultados (por ejemplo, después de fusionar un reintento de los
    archivos que fallaron), sin necesidad de volver a llamar a la IA."""
    cubiertos = set(
        (r.get("Bloque"), r.get("Documento")) for r in resultados
        if r.get("Documento") and r.get("Documento") not in ("-", "Sin clasificar")
    )
    resumen = []
    for bloque in bloques_activados:
        carpeta = f"{'-'.join(bloque['codigos'])} {bloque['titulo']}"
        for doc in bloque["documentos"]:
            clave = (bloque["titulo"], doc["documento"])
            resumen.append({
                "Carpeta": carpeta, "Documento": doc["documento"], "Sigla": doc["sigla"],
                "Estado": "✅ Subido" if clave in cubiertos else "❌ FALTA"
            })
    for doc in DOCS_UNIVERSALES_MOD:
        clave = ("Documentos para todas las modificaciones", doc["documento"])
        resumen.append({
            "Carpeta": "DOCUMENTOS GENERALES", "Documento": doc["documento"], "Sigla": doc["sigla"],
            "Estado": "✅ Subido" if clave in cubiertos else "❌ FALTA"
        })
    return resumen


def _recalcular_cobertura_dm(resultados, items_aplicables):
    """Análogo a _recalcular_cobertura_modificacion pero para (DM), donde
    la cobertura se identifica por número de ítem en vez de (bloque,
    documento)."""
    items_cubiertos = set(
        r.get("Item") for r in resultados
        if r.get("Item") not in (None, "-") and r.get("Documento") not in (None, "-", "Sin clasificar")
    )
    resumen = []
    for it in items_aplicables:
        resumen.append({
            "Item": it["item"], "Documento": it["titulo"], "Sigla": it["sigla"],
            "Estado": "✅ Subido" if it["item"] in items_cubiertos else "❌ FALTA"
        })
    return resumen


def _construir_zip_desde_resultados(resultados, bytes_por_archivo):
    """Reconstruye la lista de (nombre_final, bytes) a partir de una lista
    de resultados ya fusionada (original + reintentos), usando el campo
    'Nombre_Final' de cada fila y los bytes originales cacheados por
    nombre de archivo. Evita tener que hacer cirugía manual sobre listas
    de tuplas al fusionar un reintento con los resultados anteriores."""
    archivos_zip = []
    for r in resultados:
        nombre_final = r.get("Nombre_Final")
        nombre_original = r.get("Archivo_Original")
        if nombre_final and nombre_original in bytes_por_archivo:
            archivos_zip.append((nombre_final, bytes_por_archivo[nombre_original]))
    return archivos_zip


def _analizar_zip_remisiones(bytes_zip, token, carpeta_raiz_id, callback_progreso=None):
    """FASE 1: analiza el .zip de remisiones con IA y arma la lista de
    'grupos' (remisión + equipo encontrado, con sus archivos disponibles
    en Drive), SIN COPIAR nada todavía. El usuario revisa y marca/desmarca
    qué archivos quiere antes de confirmar la copia real (ver
    _ejecutar_copia_seleccionada más abajo). 'callback_progreso(indice,
    total, nombre_archivo)' se llama antes de procesar cada PDF."""
    grupos = []
    informativas = []  # casos sin coincidencia, sin texto, o con error (no requieren selección)

    arbol_referencias = _construir_arbol_referencias_drive(token, carpeta_raiz_id)
    if not arbol_referencias:
        return {"grupos": [], "informativas": [{
            "Remision": "-", "Cliente": "-", "Equipo": "-", "Referencia": "-",
            "Estado": "⚠ No se encontró ningún equipo documentado en Drive todavía. "
                      "Sube primero la documentación de los fabricantes."
        }]}

    with zipfile.ZipFile(io.BytesIO(bytes_zip)) as zf:
        nombres_pdf = [n for n in zf.namelist() if n.lower().endswith(".pdf") and not n.endswith("/")]
        total = len(nombres_pdf)

        for idx, nombre_entrada in enumerate(nombres_pdf):
            nombre_archivo_pdf = nombre_entrada.split("/")[-1]
            if callback_progreso:
                callback_progreso(idx, total, nombre_archivo_pdf)

            try:
                bytes_pdf = zf.read(nombre_entrada)
                texto_pdf = _extraer_texto_pdf(bytes_pdf)
                if len(texto_pdf) < 30:
                    # Probablemente escaneada: se manda el PDF directo a
                    # Gemini para que lo lea como imagen, en vez de descartarla.
                    analisis = _analizar_remision_con_ia("", arbol_referencias, pdf_bytes=bytes_pdf)
                else:
                    analisis = _analizar_remision_con_ia(texto_pdf, arbol_referencias)
            except Exception as e:
                informativas.append({
                    "Remision": nombre_archivo_pdf, "Cliente": "-", "Equipo": "-", "Referencia": "-",
                    "Estado": f"❌ Error analizando con IA: {e}"
                })
                continue

            numero_pedido = (analisis.get("numero_pedido") or "").strip()
            numero_remision = (analisis.get("numero_remision") or "").strip()
            cliente = (analisis.get("cliente") or "").strip()
            items = analisis.get("items") or []

            nombre_carpeta_cliente = " ".join(p for p in [numero_pedido, numero_remision, cliente] if p)
            if not nombre_carpeta_cliente:
                nombre_carpeta_cliente = nombre_archivo_pdf

            if not items:
                informativas.append({
                    "Remision": nombre_archivo_pdf, "Cliente": cliente or "-",
                    "Equipo": "-", "Referencia": "-",
                    "Estado": "⚠ No se identificaron equipos en la tabla de esta remisión"
                })
                continue

            for idx_item, item in enumerate(items):
                descripcion = (item.get("descripcion_original") or "").strip()
                fabricante_m = (item.get("fabricante") or "").strip()
                equipo_m = (item.get("equipo") or "").strip()
                referencia_m = (item.get("referencia") or "").strip()
                coincidencia = (item.get("coincidencia") or "").strip().lower()

                if coincidencia == "sin_coincidencia" or not equipo_m or not referencia_m:
                    informativas.append({
                        "Remision": nombre_archivo_pdf, "Cliente": cliente or "-",
                        "Equipo": descripcion or "-", "Referencia": "-",
                        "Estado": "🟠 PENDIENTE: no se encontró carpeta de Drive correspondiente"
                    })
                    continue

                entrada_arbol = next(
                    (e for e in arbol_referencias
                     if e["equipo"].strip().lower() == equipo_m.lower()
                     and e["referencia"].strip().lower() == referencia_m.lower()
                     and (not fabricante_m or e["fabricante"].lower() == fabricante_m.lower())),
                    None
                )
                if entrada_arbol is None:
                    informativas.append({
                        "Remision": nombre_archivo_pdf, "Cliente": cliente or "-",
                        "Equipo": descripcion or f"{equipo_m} {referencia_m}", "Referencia": referencia_m,
                        "Estado": "🟠 PENDIENTE: la IA sugirió una carpeta que no coincide exactamente"
                    })
                    continue

                archivos_origen = _drive_listar_archivos_de_carpeta(token, entrada_arbol["folder_id"])
                if not archivos_origen:
                    informativas.append({
                        "Remision": nombre_archivo_pdf, "Cliente": cliente or "-",
                        "Equipo": equipo_m, "Referencia": referencia_m,
                        "Estado": "🟠 PENDIENTE: la carpeta de ese equipo no tiene archivos"
                    })
                    continue

                grupos.append({
                    "id_grupo": f"{idx}_{idx_item}",
                    "remision": nombre_archivo_pdf,
                    "cliente": cliente or "-",
                    "nombre_carpeta_cliente": nombre_carpeta_cliente,
                    "equipo": equipo_m,
                    "referencia": referencia_m,
                    "archivos_disponibles": [
                        {"nombre": nombre, "id": info["id"], "mimeType": info.get("mimeType", "")}
                        for nombre, info in archivos_origen.items()
                    ],
                })

    return {"grupos": grupos, "informativas": informativas}


def _ejecutar_copia_seleccionada(token, carpeta_raiz_id, grupos, obtener_seleccion_archivo):
    """FASE 2: ya con la selección de archivos confirmada por el usuario
    ('obtener_seleccion_archivo(id_grupo, id_archivo) -> bool'), crea las
    carpetas que falten y copia (descarga + sube) solo los archivos que
    quedaron marcados."""
    filas = []
    id_carpeta_final, _ = _drive_obtener_o_crear_carpeta(
        token, NOMBRE_CARPETA_FINAL_POSTVENTA, carpeta_raiz_id
    )
    cache_carpetas_cliente = {}

    for grupo in grupos:
        archivos_seleccionados = [
            a for a in grupo["archivos_disponibles"]
            if obtener_seleccion_archivo(grupo["id_grupo"], a["id"])
        ]
        if not archivos_seleccionados:
            filas.append({
                "Remision": grupo["remision"], "Cliente": grupo["cliente"],
                "Equipo": grupo["equipo"], "Referencia": grupo["referencia"],
                "Estado": "⏭ Omitido (no se seleccionó ningún archivo de este equipo)"
            })
            continue

        nombre_carpeta_cliente = grupo["nombre_carpeta_cliente"]
        if nombre_carpeta_cliente not in cache_carpetas_cliente:
            id_cliente, _ = _drive_obtener_o_crear_carpeta(token, nombre_carpeta_cliente, id_carpeta_final)
            cache_carpetas_cliente[nombre_carpeta_cliente] = id_cliente
        id_carpeta_cliente = cache_carpetas_cliente[nombre_carpeta_cliente]

        nombre_subcarpeta_equipo = f"{grupo['equipo']} - {grupo['referencia']}"
        id_subcarpeta_equipo, _ = _drive_obtener_o_crear_carpeta(
            token, nombre_subcarpeta_equipo, id_carpeta_cliente
        )

        copiados = 0
        errores_copia = []
        for archivo in archivos_seleccionados:
            try:
                contenido = _drive_descargar_archivo(token, archivo["id"])
                mimetype = archivo.get("mimeType") or mimetypes.guess_type(archivo["nombre"])[0] or "application/octet-stream"
                _drive_subir_archivo(token, archivo["nombre"], contenido, mimetype, id_subcarpeta_equipo)
                copiados += 1
            except Exception as e:
                errores_copia.append(f"{archivo['nombre']}: {_mensaje_error_drive(e)}")

        if copiados == 0 and errores_copia:
            estado_fila = f"❌ No se pudo copiar ningún archivo. Detalle: {errores_copia[0]}"
        else:
            estado_fila = (
                f"✅ {copiados}/{len(archivos_seleccionados)} documento(s) copiado(s) a "
                f"'{NOMBRE_CARPETA_FINAL_POSTVENTA}/{nombre_carpeta_cliente}/{nombre_subcarpeta_equipo}'"
            )
            if errores_copia:
                estado_fila += f" (⚠ {len(errores_copia)} fallaron: {errores_copia[0]})"

        filas.append({
            "Remision": grupo["remision"], "Cliente": grupo["cliente"],
            "Equipo": grupo["equipo"], "Referencia": grupo["referencia"],
            "Estado": estado_fila
        })

    return filas


# ==========================================================
# ACCESSGUDID — FUNCIÓN DE BÚSQUEDA POR REFERENCIA (extraída
# para poder paralelizarla con ThreadPoolExecutor y así acelerar
# la extracción masiva sin perder ninguna lógica existente)
# ==========================================================

def _procesar_detalle_accessgudid(href, ref, session, headers, company_names_filtro):
    """Descarga y procesa la ficha de detalle de UN dispositivo. Se separó
    de _buscar_referencia_accessgudid para poder pedir varios detalles de
    la misma referencia en paralelo (antes se pedían uno por uno, lo cual
    era lento cuando una referencia tenía varios dispositivos coincidentes)."""
    try:
        res = session.get(f"https://accessgudid.nlm.nih.gov{href}", headers=headers, timeout=15)
        if res.status_code != 200:
            return None
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
            return None

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

        # NOTA: la traducción con IA ya NO se hace aquí. Se hace después,
        # una sola vez para todas las definiciones únicas encontradas, para
        # no saturar el límite de peticiones por minuto de Gemini.
        if gmdn_def and gmdn_def.lower() != "no encontrado":
            gmdn_def = gmdn_def.replace('"', '').replace("'", "")

        issuing = "No encontrado"
        for i2, l in enumerate(lineas):
            if "Issuing Agency" in l:
                issuing = lineas[i2+1] if l.replace(":", "").strip() == "Issuing Agency" and i2+1 < len(lineas) else l.replace("Issuing Agency", "").replace(":", "").strip()
                break
        issuing = " ".join(issuing.split()).strip() or "No encontrado"

        return {
            "Referencia_Original": ref,
            "Primary_DI_Number": href.split('/')[-1].strip(),
            "Nombre_Empresa_FDA": company,
            "Codigo_GMDN": gmdn_code,
            "Definicion_GMDN": " ".join(str(gmdn_def).split()).strip(),
            "Estado_GMDN": " ".join(str(gmdn_status).split()).strip(),
            "Issuing_Agency": issuing
        }
    except Exception:
        return None


def _buscar_referencia_accessgudid(ref, session, headers, company_names_filtro):
    """Busca una referencia en AccessGUDID y devuelve la lista de filas
    encontradas (puede ser más de un dispositivo, o una fila de aviso si
    no hay coincidencias / hubo error). Las fichas de detalle de los
    dispositivos encontrados se piden en paralelo (hasta 4 a la vez) para
    acelerar referencias con muchas coincidencias."""
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
        if enlaces:
            with ThreadPoolExecutor(max_workers=min(4, len(enlaces))) as executor_detalle:
                futuros_detalle = [
                    executor_detalle.submit(_procesar_detalle_accessgudid, href, ref, session, headers, company_names_filtro)
                    for href in enlaces
                ]
                for futuro_detalle in futuros_detalle:
                    resultado = futuro_detalle.result()
                    if resultado is not None:
                        coincidencias.append(resultado)

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
    # OPTIMIZACIÓN DE VELOCIDAD:
    # - 'eager': Selenium considera la página "cargada" en cuanto el HTML
    #   está listo, sin esperar a que terminen de cargar imágenes/CSS/fuentes
    #   de terceros — en un sitio pesado como Eudamed esto ahorra varios
    #   segundos por navegación.
    # - Bloquear imágenes: no las necesitamos para leer texto, y cada una
    #   que no se descarga es tiempo de red que se ahorra.
    opciones.page_load_strategy = "eager"
    opciones.add_experimental_option(
        "prefs",
        {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
        },
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


def _procesar_referencia_eudamed(driver, referencia, primera_vez, limite_resultados=LIMITE_RESULTADOS_POR_REFERENCIA_EUDAMED):
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

    cantidad_a_procesar = min(total, limite_resultados)
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

    if total > cantidad_a_procesar:
        filas_resultado.append({
            "Referencia_Original": referencia,
            "Codigo_UDI_DI":       f"⚠ {total - cantidad_a_procesar} resultados más sin procesar",
            "Agencia_Emisora":     f"(de {total} encontrados, solo se procesaron {cantidad_a_procesar})",
            "Nombre_Dispositivo":  "Sube el límite en 'Configuración' si necesitas todos",
            "Fabricante":          "",
        })

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


def _llamar_gemini_api(system_prompt, mensajes, modelo=MODELO_IA_CALIDAD, max_tokens=900, pdf_bytes=None):
    """Llama a la API de Gemini. Reintenta automáticamente ante:
    - Errores de red/timeout (problemas de conexión transitorios)
    - 503 (modelo saturado) y 429 (límite de tasa)
    Y revisa explícitamente el motivo de finalización de la respuesta,
    para poder avisar con un mensaje claro si Gemini bloqueó la
    respuesta por su filtro de seguridad en vez de devolver texto vacío
    sin explicación (una de las causas de 'preguntas que fallan').

    Si se pasa 'pdf_bytes', se adjunta el PDF directamente como archivo al
    último mensaje (Gemini puede 'leer' PDFs escaneados como imagen, sin
    necesidad de instalar un motor de OCR aparte) — útil cuando la
    extracción de texto normal no encuentra nada (PDF escaneado)."""
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
    if pdf_bytes is not None and contenidos:
        b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
        contenidos[-1]["parts"].insert(0, {
            "inline_data": {"mime_type": "application/pdf", "data": b64_pdf}
        })

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
            time.sleep((6 if respuesta.status_code == 429 else 3) * (intento + 1))
            continue
        break

    if respuesta is None:
        raise RuntimeError(f"No se pudo contactar a Gemini: {ultimo_error}")

    if respuesta.status_code != 200:
        mensaje_limpio = respuesta.text[:300]
        try:
            mensaje_limpio = respuesta.json().get("error", {}).get("message", mensaje_limpio)
        except Exception:
            pass
        if respuesta.status_code == 429:
            raise RuntimeError(
                "Se alcanzó el límite de uso gratuito de Gemini por ahora (pasa al analizar "
                "muchos documentos seguidos, sobre todo si son pesados). Espera unos minutos "
                f"y reintenta solo los pendientes. Detalle: {mensaje_limpio}"
            )
        raise RuntimeError(
            f"Error de la API de Gemini (código {respuesta.status_code}): {mensaje_limpio}"
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


def _obtener_o_crear_hoja(nombre_hoja, encabezados):
    client = get_gspread_client()
    doc = client.open_by_key(SHEET_ID)
    try:
        hoja = doc.worksheet(nombre_hoja)
    except Exception:
        hoja = doc.add_worksheet(title=nombre_hoja, rows=2000, cols=len(encabezados) + 2)
        hoja.append_row(encabezados, value_input_option='RAW')
    return hoja


# ==========================================================
# SEMÁFORO DE USO DE EUDAMED — evita que dos personas corran la
# extracción de Eudamed (la más pesada, abre un navegador completo) al
# mismo tiempo y saturen la memoria del servidor compartido. Se guarda
# en una fila fija de una hoja de Google Sheets, visible para todos los
# usuarios de la app sin importar en qué sesión estén.
# ==========================================================
NOMBRE_HOJA_ESTADO_EUDAMED = "EstadoEudamed"
LIMITE_MINUTOS_LOCK_EUDAMED = 20  # si lleva más de esto "en uso", se considera abandonado (ej: sesión cerrada a la fuerza)


def _obtener_estado_eudamed():
    """Devuelve (en_uso, usuario, hora_inicio). Si algo falla al leer
    (ej: problema de red puntual), se devuelve 'no en uso' para no
    bloquear a nadie por un error de lectura."""
    try:
        hoja = _obtener_o_crear_hoja(NOMBRE_HOJA_ESTADO_EUDAMED, ["En_Uso", "Usuario", "Hora_Inicio"])
        valores = hoja.get_all_values()
        if len(valores) < 2:
            return False, None, None
        fila = valores[1]
        en_uso = (fila[0].strip().upper() == "TRUE") if len(fila) > 0 and fila[0] else False
        usuario = fila[1] if len(fila) > 1 and fila[1] else None
        hora_texto = fila[2] if len(fila) > 2 and fila[2] else None
        hora_inicio = None
        if hora_texto:
            try:
                hora_inicio = datetime.datetime.strptime(hora_texto, "%Y-%m-%d %H:%M:%S")
            except Exception:
                hora_inicio = None
        if en_uso and hora_inicio:
            minutos_transcurridos = (datetime.datetime.now() - hora_inicio).total_seconds() / 60
            if minutos_transcurridos > LIMITE_MINUTOS_LOCK_EUDAMED:
                return False, None, None  # se considera abandonado, no bloquea
        return en_uso, usuario, hora_inicio
    except Exception:
        return False, None, None


def _marcar_estado_eudamed(en_uso, usuario=""):
    """Actualiza el semáforo. Si falla (ej: problema de red puntual), no
    interrumpe el flujo principal de la extracción por esto."""
    try:
        hoja = _obtener_o_crear_hoja(NOMBRE_HOJA_ESTADO_EUDAMED, ["En_Uso", "Usuario", "Hora_Inicio"])
        if en_uso:
            hora_texto = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hoja.update("A2:C2", [["TRUE", usuario, hora_texto]])
        else:
            hoja.update("A2:C2", [["FALSE", "", ""]])
    except Exception:
        pass


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
            ("📄 Documentación Post-Venta", "DocumentacionPostVenta"),
            ("🔢 Codificación",          "Codificacion"),
            ("📁 Creación de Dossier",   "CreacionDossier"),
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

    col_titulo, col_inicio_btn, col_perfil_btn = st.columns([4.6, 1, 1])
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

            with st.expander("⚙ Configuración"):
                limite_eudamed = st.number_input(
                    "Máximo de resultados a procesar por referencia",
                    min_value=1, max_value=200, value=15, step=5,
                    key="limite_eudamed",
                    help="Si una referencia tiene muchas coincidencias (ej: 'mg1' con 94 resultados), "
                         "procesar todas puede tardar mucho (cada una toma ~10-20s). Si necesitas todas, "
                         "sube este número, pero la extracción será más lenta."
                )
                st.caption(
                    "Si una referencia tiene más resultados que este límite, se te avisará "
                    "en la tabla cuántos quedaron sin procesar."
                )

            if archivo_eudamed is not None:
                if archivo_eudamed.name != st.session_state.get("eudamed_archivo_nombre", ""):
                    st.session_state["eudamed_archivo_bytes"]  = archivo_eudamed.read()
                    st.session_state["eudamed_archivo_nombre"] = archivo_eudamed.name
                    st.session_state["eudamed_iniciar"]        = False

            hay_archivo_eu = st.session_state.get("eudamed_archivo_bytes") is not None

            en_uso_eu, usuario_en_uso_eu, hora_inicio_eu = _obtener_estado_eudamed()
            if en_uso_eu:
                minutos_en_uso = int((datetime.datetime.now() - hora_inicio_eu).total_seconds() / 60) if hora_inicio_eu else 0
                st.warning(
                    f"🔴 Eudamed está siendo usado ahora mismo por **{usuario_en_uso_eu or 'otro usuario'}** "
                    f"(empezó hace ~{minutos_en_uso} min). Para no saturar el servidor, espera a que termine "
                    "antes de iniciar otra extracción."
                )

            if st.button(
                "🌍 Iniciar Extracción Eudamed",
                disabled=(not hay_archivo_eu) or en_uso_eu,
                use_container_width=True,
                key="btn_iniciar_eudamed"
            ):
                st.session_state["eudamed_iniciar"] = True
                st.rerun()

            contenedor_eudamed = st.container()

            if st.session_state.get("eudamed_iniciar") and hay_archivo_eu:
                st.session_state["eudamed_iniciar"] = False

                with contenedor_eudamed:
                    # Re-chequeo del semáforo justo antes de empezar (por si dos
                    # personas le dieron clic casi al mismo tiempo, antes de que
                    # el botón se deshabilitara para la otra persona).
                    en_uso_eu_check, usuario_en_uso_eu_check, _ = _obtener_estado_eudamed()
                    if en_uso_eu_check:
                        st.error(
                            f"🔴 {usuario_en_uso_eu_check or 'Otro usuario'} acaba de iniciar una extracción "
                            "de Eudamed justo ahora. Espera a que termine antes de intentar de nuevo."
                        )
                        st.stop()

                    try:
                        bytes_data_eu = st.session_state["eudamed_archivo_bytes"]
                        df_eu = pd.read_excel(io.BytesIO(bytes_data_eu), header=None, dtype=str)
                        df_eu[0] = df_eu[0].astype(str).str.strip()
                        referencias_eu = [r for r in df_eu[0].tolist() if r and r != "nan"]
                        total_refs_eu  = len(referencias_eu)
                    except Exception as e:
                        st.error(f"Error al abrir el archivo de Excel: {e}")
                        st.stop()

                    _marcar_estado_eudamed(True, usuario=st.session_state["usuario_activo_real"])

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
                        _marcar_estado_eudamed(False)
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
                                    driver_eu, ref, primera_vez=(idx == 0),
                                    limite_resultados=limite_eudamed
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
                        _marcar_estado_eudamed(False)

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
            elif not hay_archivo_eu:
                st.info("👈 Sube un archivo para activar la monitorización.")

    # ==========================================================
    # VISTA 2-C: DOCUMENTACIÓN POST-VENTA
    # ==========================================================
    elif st.session_state["seccion_activa"] == "DocumentacionPostVenta":
        st.markdown("<h3 style='color:#0b1d3a;'>📄 Documentación Post-Venta</h3>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#475569;'>Sube un archivo .zip con la estructura "
            "<b>Fabricante / Equipo / Referencia / archivos</b>. Las carpetas que no "
            "existan en tu Google Drive se crean automáticamente; las que ya existan "
            "se reutilizan (así puedes ir alimentando esto con nuevos fabricantes, "
            "equipos o referencias sin duplicar nada).</p>",
            unsafe_allow_html=True
        )

        carpeta_raiz_id = _obtener_id_carpeta_raiz_postventa()
        if not carpeta_raiz_id:
            st.error(
                "No hay una carpeta de Google Drive configurada todavía. Agrega en "
                "Settings → Secrets de Streamlit Cloud:\n\n"
                "[drive]\nfolder_id = \"el-id-de-tu-carpeta-de-drive\""
            )
            st.info(
                "Recuerda compartir esa carpeta (permiso Editor) con el correo de la "
                "cuenta de servicio que aparece en tus Secrets, dentro de [gcp] → client_email."
            )
        else:
            archivo_zip = st.file_uploader(
                "Sube el archivo .zip con la documentación", type=["zip"], key="uploader_postventa"
            )

            if archivo_zip and st.button(
                "📤 Procesar y subir a Drive", use_container_width=True, key="btn_procesar_postventa"
            ):
                try:
                    bytes_zip = archivo_zip.read()
                except Exception as e:
                    st.error(f"No se pudo leer el archivo .zip: {e}")
                    st.stop()

                with st.spinner("Conectando con Google Drive..."):
                    try:
                        token = _obtener_token_drive()
                    except Exception as e:
                        st.error(f"No se pudo obtener acceso a Google Drive: {e}")
                        st.stop()

                with st.spinner("Procesando carpetas y subiendo archivos... esto puede tardar varios minutos si hay muchos documentos."):
                    try:
                        filas_resultado = _procesar_zip_postventa(bytes_zip, token, carpeta_raiz_id)
                    except zipfile.BadZipFile:
                        st.error("El archivo subido no es un .zip válido.")
                        st.stop()
                    except Exception as e:
                        st.error(f"Ocurrió un error procesando el .zip: {e}")
                        st.stop()

                df_resultado = pd.DataFrame(filas_resultado)
                total_subidos = (df_resultado["Estado"] == "✅ Subido").sum() if not df_resultado.empty else 0
                total_conflictos = df_resultado["Estado"].str.contains("CONFLICTO", na=False).sum() if not df_resultado.empty else 0
                total_errores = df_resultado["Estado"].str.contains("❌", na=False).sum() if not df_resultado.empty else 0
                total_ignorados = df_resultado["Estado"].str.contains("Ignorado", na=False).sum() if not df_resultado.empty else 0

                st.success(
                    f"✨ Proceso terminado: {total_subidos} archivo(s) subido(s), "
                    f"{total_conflictos} en conflicto, {total_errores} con error, "
                    f"{total_ignorados} ignorado(s)."
                )

                if total_conflictos > 0:
                    st.warning(
                        f"⚠ Hay {total_conflictos} archivo(s) que ya existían en su referencia "
                        "y NO se subieron (para no sobrescribir nada sin tu autorización). "
                        "Revísalos en la tabla de abajo (estado 'CONFLICTO') y avísame cómo "
                        "quieres que proceda con ellos."
                    )

                st.dataframe(df_resultado, use_container_width=True, height=350)

                output_resumen = io.BytesIO()
                with pd.ExcelWriter(output_resumen, engine='openpyxl') as writer:
                    df_resultado.to_excel(writer, index=False)
                st.download_button(
                    label="📥 Descargar resumen en Excel",
                    data=output_resumen.getvalue(),
                    file_name="resumen_documentacion_postventa.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

                registrar_log(
                    st.session_state["usuario_activo_real"],
                    f"Carga de documentación post-venta ({total_subidos} archivos subidos, {total_conflictos} conflictos)",
                    len(filas_resultado)
                )
            elif not archivo_zip:
                st.info("👈 Sube tu archivo .zip para comenzar.")

            st.markdown("<hr style='margin:32px 0;'>", unsafe_allow_html=True)
            st.markdown(
                "<h4 style='color:#0b1d3a;'>📋 Procesar Remisiones → Generar Carpetas Post-Venta</h4>",
                unsafe_allow_html=True
            )
            st.markdown(
                "<p style='color:#475569;'>Sube un .zip con tu carpeta de remisiones (PDF). Por cada "
                "una, la IA extrae el pedido, la remisión y el cliente, e identifica los equipos de la "
                "tabla. Antes de copiar nada, vas a poder revisar y desmarcar los documentos que NO "
                "quieras incluir. Los archivos originales no se mueven ni se modifican, solo se copian "
                f"dentro de una carpeta nueva por cliente, en <b>{NOMBRE_CARPETA_FINAL_POSTVENTA}</b>.</p>",
                unsafe_allow_html=True
            )

            if "analisis_remisiones" not in st.session_state:
                st.session_state["analisis_remisiones"] = None

            archivo_zip_remisiones = st.file_uploader(
                "Sube el .zip con las remisiones (PDF)", type=["zip"], key="uploader_remisiones"
            )

            if archivo_zip_remisiones and st.button(
                "🔍 Analizar Remisiones", use_container_width=True, key="btn_analizar_remisiones"
            ):
                try:
                    bytes_zip_rem = archivo_zip_remisiones.read()
                except Exception as e:
                    st.error(f"No se pudo leer el .zip: {e}")
                    st.stop()

                with st.spinner("Conectando con Google Drive..."):
                    try:
                        token_rem = _obtener_token_drive()
                    except Exception as e:
                        st.error(f"No se pudo obtener acceso a Google Drive: {e}")
                        st.stop()

                texto_estado_rem = st.empty()

                def _avisar_progreso_remision(idx, total, nombre_archivo):
                    texto_estado_rem.info(f"⏳ Analizando {idx+1}/{total}: {nombre_archivo}...")

                with st.spinner("Analizando remisiones con IA (puede tardar varios minutos)..."):
                    try:
                        resultado_analisis = _analizar_zip_remisiones(
                            bytes_zip_rem, token_rem, carpeta_raiz_id,
                            callback_progreso=_avisar_progreso_remision
                        )
                    except zipfile.BadZipFile:
                        st.error("El archivo subido no es un .zip válido.")
                        st.stop()
                    except Exception as e:
                        st.error(f"Ocurrió un error analizando las remisiones: {e}")
                        st.stop()

                texto_estado_rem.empty()
                st.session_state["analisis_remisiones"] = resultado_analisis
                st.rerun()

            elif not archivo_zip_remisiones:
                st.info("👈 Sube tu .zip con las remisiones para comenzar.")

            # ── Revisión de la selección (después de analizar, antes de copiar) ──
            datos_analisis = st.session_state.get("analisis_remisiones")
            if datos_analisis is not None:
                grupos_rem = datos_analisis["grupos"]
                informativas_rem = datos_analisis["informativas"]

                if informativas_rem:
                    st.warning(
                        f"⚠ {len(informativas_rem)} caso(s) sin coincidencia o sin texto legible "
                        "(no requieren selección, no se les puede copiar nada):"
                    )
                    st.dataframe(pd.DataFrame(informativas_rem), use_container_width=True)

                if grupos_rem:
                    st.markdown("##### ✅ Revisa qué documentos copiar por cada equipo encontrado")
                    st.caption(
                        "Por defecto están todos marcados. Desmarca los que NO quieras incluir en "
                        "la carpeta final de ese cliente."
                    )
                    for grupo_rem in grupos_rem:
                        with st.expander(
                            f"📦 {grupo_rem['remision']} — {grupo_rem['cliente']} — "
                            f"{grupo_rem['equipo']} ({grupo_rem['referencia']}) "
                            f"· {len(grupo_rem['archivos_disponibles'])} documento(s)",
                            expanded=True
                        ):
                            for archivo_rem in grupo_rem["archivos_disponibles"]:
                                key_chk = f"chk_rem_{grupo_rem['id_grupo']}_{archivo_rem['id']}"
                                if key_chk not in st.session_state:
                                    st.session_state[key_chk] = True
                                st.checkbox(archivo_rem["nombre"], key=key_chk)

                    if st.button(
                        "✅ Confirmar selección y copiar a Drive",
                        use_container_width=True, key="btn_confirmar_copia_remisiones"
                    ):
                        with st.spinner("Conectando con Google Drive..."):
                            try:
                                token_copia_rem = _obtener_token_drive()
                            except Exception as e:
                                st.error(f"No se pudo obtener acceso a Google Drive: {e}")
                                st.stop()

                        with st.spinner("Copiando los documentos seleccionados..."):
                            filas_copiados = _ejecutar_copia_seleccionada(
                                token_copia_rem, carpeta_raiz_id, grupos_rem,
                                obtener_seleccion_archivo=lambda gid, fid: st.session_state.get(
                                    f"chk_rem_{gid}_{fid}", True
                                )
                            )

                        filas_finales_rem = filas_copiados + informativas_rem
                        df_rem = pd.DataFrame(filas_finales_rem)
                        total_ok = df_rem["Estado"].str.contains("✅", na=False).sum() if not df_rem.empty else 0
                        total_omitidos = df_rem["Estado"].str.contains("⏭", na=False).sum() if not df_rem.empty else 0
                        total_pendientes = df_rem["Estado"].str.contains("PENDIENTE", na=False).sum() if not df_rem.empty else 0
                        total_err = df_rem["Estado"].str.contains("❌", na=False).sum() if not df_rem.empty else 0

                        st.success(
                            f"✨ Proceso terminado: {total_ok} equipo(s) copiado(s), "
                            f"{total_omitidos} omitido(s) por selección, "
                            f"{total_pendientes} pendiente(s), {total_err} error(es)."
                        )
                        st.dataframe(df_rem, use_container_width=True, height=350)

                        output_rem = io.BytesIO()
                        with pd.ExcelWriter(output_rem, engine='openpyxl') as writer:
                            df_rem.to_excel(writer, index=False)
                        st.download_button(
                            label="📥 Descargar resumen en Excel",
                            data=output_rem.getvalue(),
                            file_name="resumen_remisiones_postventa.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )

                        registrar_log(
                            st.session_state["usuario_activo_real"],
                            f"Procesamiento de remisiones post-venta ({total_ok} copiados, {total_pendientes} pendientes)",
                            len(filas_finales_rem)
                        )
                        st.session_state["analisis_remisiones"] = None
                elif not informativas_rem:
                    st.info("No se encontraron remisiones para procesar en ese .zip.")

    # ==========================================================
    # VISTA 2-D: CODIFICACIÓN — COMPARAR REFERENCIAS ENTRE ARCHIVOS
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Codificacion":
        st.markdown("<h3 style='color:#0b1d3a;'>🔢 Codificación — Comparar Referencias entre Archivos</h3>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#475569;'>Sube dos archivos de Excel (una sola columna de referencias, "
            "sin encabezado, igual que en Extracción Masiva). Te muestro cuáles referencias del "
            "<b>Archivo 1</b> NO están en el <b>Archivo 2</b>.</p>",
            unsafe_allow_html=True
        )

        col_arch1, col_arch2 = st.columns(2)
        with col_arch1:
            st.markdown("**📄 Archivo 1** (el que quieres revisar)")
            archivo_cod_1 = st.file_uploader("Sube el Archivo 1", type=["xlsx"], key="uploader_cod_1")
        with col_arch2:
            st.markdown("**📄 Archivo 2** (donde se busca si ya están)")
            archivo_cod_2 = st.file_uploader("Sube el Archivo 2", type=["xlsx"], key="uploader_cod_2")

        ignorar_mayusculas_cod = st.checkbox(
            "Ignorar mayúsculas/minúsculas y espacios extra al comparar (recomendado)",
            value=True, key="chk_cod_ignorar_mayus"
        )

        if archivo_cod_1 and archivo_cod_2 and st.button(
            "🔍 Comparar Referencias", use_container_width=True, key="btn_comparar_codificacion"
        ):
            with st.spinner("Leyendo y comparando archivos (si son muy grandes puede tardar un poco)..."):
                try:
                    df_cod_1 = pd.read_excel(archivo_cod_1, header=None, dtype=str)
                    df_cod_2 = pd.read_excel(archivo_cod_2, header=None, dtype=str)
                except Exception as e:
                    st.error(f"No se pudo leer alguno de los archivos: {e}")
                    st.stop()

                refs_1 = [r for r in df_cod_1[0].astype(str).str.strip().tolist() if r and r.lower() != "nan"]
                refs_2 = [r for r in df_cod_2[0].astype(str).str.strip().tolist() if r and r.lower() != "nan"]

                if ignorar_mayusculas_cod:
                    _normalizar_cod = lambda r: r.strip().upper()
                else:
                    _normalizar_cod = lambda r: r.strip()

                mapa_normalizado_a_original = {}
                for r in refs_1:
                    clave = _normalizar_cod(r)
                    mapa_normalizado_a_original.setdefault(clave, r)

                set_2_normalizado = set(_normalizar_cod(r) for r in refs_2)

                # Índice del Archivo 2 quitando TODO lo que no sea letra o número
                # (puntos, espacios, guiones, etc.) — para sugerir posibles
                # coincidencias cuando la referencia es casi la misma pero con
                # un formato ligeramente distinto.
                _normalizar_alfanumerico_cod = lambda r: re.sub(r'[^A-Za-z0-9]', '', r).upper()
                indice_super_normalizado_2 = {}
                for r in refs_2:
                    clave_super = _normalizar_alfanumerico_cod(r)
                    indice_super_normalizado_2.setdefault(clave_super, []).append(r)

                filas_faltantes_cod = []
                for clave in mapa_normalizado_a_original:
                    if clave in set_2_normalizado:
                        continue
                    referencia_original = mapa_normalizado_a_original[clave]
                    clave_super = _normalizar_alfanumerico_cod(referencia_original)
                    posibles = sorted(set(indice_super_normalizado_2.get(clave_super, [])))
                    filas_faltantes_cod.append({
                        "Referencia_No_Encontrada": referencia_original,
                        "Posibles_Coincidencias_Archivo2": ", ".join(posibles) if posibles else "-"
                    })

                faltantes = [f["Referencia_No_Encontrada"] for f in filas_faltantes_cod]
                total_con_posible = sum(1 for f in filas_faltantes_cod if f["Posibles_Coincidencias_Archivo2"] != "-")

            st.success(
                f"✨ Archivo 1: {len(refs_1)} referencias ({len(mapa_normalizado_a_original)} únicas) · "
                f"Archivo 2: {len(refs_2)} referencias · "
                f"**{len(faltantes)} referencias del Archivo 1 no están en el Archivo 2**"
            )
            if faltantes and total_con_posible:
                st.info(
                    f"🔎 De esas {len(faltantes)}, **{total_con_posible}** tienen una posible coincidencia "
                    "en el Archivo 2 (probablemente la misma referencia con formato distinto — un punto, "
                    "espacio, guion, etc.). Revísalas en la columna 'Posibles_Coincidencias_Archivo2'."
                )

            if faltantes:
                df_faltantes_cod = pd.DataFrame(filas_faltantes_cod)
                st.dataframe(df_faltantes_cod, use_container_width=True, height=400)

                output_cod = io.BytesIO()
                with pd.ExcelWriter(output_cod, engine='openpyxl') as writer:
                    df_faltantes_cod.to_excel(writer, index=False)
                st.download_button(
                    label="📥 Descargar referencias faltantes en Excel",
                    data=output_cod.getvalue(),
                    file_name="referencias_faltantes.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

                registrar_log(
                    st.session_state["usuario_activo_real"],
                    f"Codificación: comparación de referencias ({len(faltantes)} faltantes de {len(refs_1)})",
                    len(faltantes)
                )
            else:
                st.info("🎉 Todas las referencias del Archivo 1 están presentes en el Archivo 2.")

        elif not archivo_cod_1 or not archivo_cod_2:
            st.info("👈 Sube ambos archivos para activar la comparación.")

    # ==========================================================
    # VISTA 2-E: CREACIÓN DE DOSSIER
    # ==========================================================
    elif st.session_state["seccion_activa"] == "CreacionDossier":
        st.markdown("<h3 style='color:#0b1d3a;'>📁 Creación de Dossier</h3>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#475569;'>Elige el trámite que vas a realizar (numeral 1.3 del Formato Único "
            "ASS-RSA-FM007). Según el trámite y la clasificación de riesgo, te muestro qué documentos "
            "necesitas, y la IA revisa los PDF que subas para indicarte a cuál ítem corresponde cada uno "
            "y si parece estar conforme — basado en el Decreto 4725 de 2005.</p>",
            unsafe_allow_html=True
        )

        OPCIONES_TRAMITE = [
            "(DM) Expedición de Registro Sanitario para Dispositivos Médicos",
            "(DM) Renovación para Dispositivos Médicos",
            "(EB) Expedición de Registro/Permiso de Comercialización Equipos Biomédicos",
            "(EB) Renovación para Equipos Biomédicos",
            "Modificaciones Automáticas",
            "(AUT 32) Autorización de Agotamiento de Existencia",
            "(AUT EB) Autorización Equipos Biomédicos (usado/repotenciado/reparado)",
            "(AUT VUCE) Accesorios, Partes y Repuestos (RS-PC) VUCE",
            "(CERT. CON RS) Certificación con Registro Sanitario (CVL)",
            "(CERT. SIN RS) Certificación sin Registro Sanitario",
            "(DESG) Desglose",
            "(CPFE) Pérdida de Fuerza Ejecutoria",
            "(AUT 46) Autorización Art.46",
        ]
        tramite_elegido = st.selectbox(
            "1.3 — Tipo de trámite que desea realizar", OPCIONES_TRAMITE, key="select_tramite_dossier"
        )

        if tramite_elegido not in (OPCIONES_TRAMITE[0], OPCIONES_TRAMITE[4]):
            st.info(
                "🚧 Este trámite todavía no está construido — por ahora tenemos "
                "**(DM) Expedición de Registro Sanitario** y **Modificaciones Automáticas**. "
                "Cuéntame cuándo quieres que sigamos con los demás."
            )
        elif tramite_elegido == OPCIONES_TRAMITE[0]:
            st.markdown("##### Datos del trámite")
            col_equipo_doss, col_riesgo_doss = st.columns([2.5, 1.4])
            with col_equipo_doss:
                equipo_dossier = st.text_input("Nombre del equipo", key="txt_equipo_dossier")
            with col_riesgo_doss:
                riesgo_dossier = st.selectbox(
                    "Clasificación de riesgo", ["I", "IIA", "IIB", "III"], key="select_riesgo_dossier"
                )

            st.markdown("**Referencias** (opcional)")
            modo_referencias_dm = st.radio(
                "¿Cómo vas a indicar las referencias?",
                ["✍️ Escribir manualmente (1-2 referencias)", "📄 Subir Excel (muchas referencias)"],
                horizontal=True, key="modo_referencias_dm", label_visibility="collapsed"
            )
            lista_referencias_dossier = []
            if modo_referencias_dm.startswith("✍️"):
                texto_referencias_dm = st.text_area(
                    "Escribe una referencia por línea", key="txt_referencias_manual_dm",
                    placeholder="Ej:\nIMEC10\nIMEC12"
                )
                lista_referencias_dossier = [
                    r.strip() for r in texto_referencias_dm.split("\n") if r.strip()
                ]
            else:
                archivo_referencias_dossier = st.file_uploader(
                    "Sube el Excel de referencias (una sola columna, sin encabezado)",
                    type=["xlsx"], key="uploader_referencias_dossier"
                )
                if archivo_referencias_dossier is not None:
                    try:
                        df_refs_dossier = pd.read_excel(archivo_referencias_dossier, header=None, dtype=str)
                        lista_referencias_dossier = [
                            r for r in df_refs_dossier[0].astype(str).str.strip().tolist()
                            if r and r.lower() != "nan"
                        ]
                        st.success(f"✅ {len(lista_referencias_dossier)} referencia(s) cargada(s).")
                    except Exception as e:
                        st.error(f"No se pudo leer el archivo de referencias: {e}")

            items_aplicables_dm = _obtener_items_aplicables_dm(riesgo_dossier)

            with st.expander(
                f"📋 Ver los {len(items_aplicables_dm)} documentos requeridos para riesgo {riesgo_dossier}",
                expanded=False
            ):
                df_checklist_dm = pd.DataFrame([
                    {"Ítem": it["item"], "Documento": it["titulo"], "Sigla": it["sigla"], "Artículo": it["articulo"]}
                    for it in items_aplicables_dm
                ])
                st.dataframe(df_checklist_dm, use_container_width=True, hide_index=True)

            st.markdown("##### Sube los documentos (PDF)")
            archivos_dossier_dm = st.file_uploader(
                "Puedes subir varios PDF a la vez", type=["pdf"], accept_multiple_files=True,
                key="uploader_dossier_dm"
            )

            if archivos_dossier_dm and st.button(
                "🔍 Analizar y Organizar Documentos", use_container_width=True, key="btn_analizar_dossier_dm"
            ):
                archivos_con_bytes_dm = [(f.name, f.read()) for f in archivos_dossier_dm]

                texto_estado_dossier = st.empty()

                def _avisar_progreso_dossier(idx, total, nombre_archivo):
                    texto_estado_dossier.info(f"⏳ Analizando {idx+1}/{total}: {nombre_archivo}...")

                with st.spinner("Analizando documentos con IA..."):
                    resultados_dm, _cobertura_inicial_dm, _zip_inicial_dm = _procesar_documentos_dossier_dm(
                        archivos_con_bytes_dm, items_aplicables_dm,
                        callback_progreso=_avisar_progreso_dossier
                    )
                texto_estado_dossier.empty()

                # Se guarda en sesión (incluyendo los bytes) para poder
                # reintentar solo los archivos que fallen por límite de
                # cuota de Gemini, sin tener que volver a subirlos.
                st.session_state["dm_cache"] = {
                    "resultados": resultados_dm,
                    "bytes_por_archivo": {n: b for n, b in archivos_con_bytes_dm},
                    "equipo": equipo_dossier,
                    "referencias": lista_referencias_dossier,
                    "items_aplicables": items_aplicables_dm,
                    "riesgo": riesgo_dossier,
                }

            cache_dm = st.session_state.get("dm_cache")
            if cache_dm and cache_dm.get("riesgo") == riesgo_dossier:
                resultados_dm = cache_dm["resultados"]
                bytes_por_archivo_dm = cache_dm["bytes_por_archivo"]

                df_resultados_dm = pd.DataFrame(resultados_dm)
                filas_fallidas_dm = df_resultados_dm[
                    df_resultados_dm["Comentario"].astype(str).str.contains("❌", na=False)
                ] if not df_resultados_dm.empty else df_resultados_dm

                if len(filas_fallidas_dm) > 0:
                    st.warning(
                        f"⚠ {len(filas_fallidas_dm)} archivo(s) no se pudieron analizar (por ejemplo, "
                        "por límite de cuota de Gemini). Espera un par de minutos y reintenta solo esos, "
                        "sin gastar cuota de nuevo en los que ya salieron bien."
                    )
                    if st.button(
                        "🔄 Reintentar solo los que fallaron", use_container_width=True, key="btn_reintentar_dm"
                    ):
                        nombres_fallidos_dm = filas_fallidas_dm["Archivo_Original"].tolist()
                        archivos_reintento_dm = [
                            (n, bytes_por_archivo_dm[n]) for n in nombres_fallidos_dm if n in bytes_por_archivo_dm
                        ]

                        texto_estado_retry_dm = st.empty()

                        def _avisar_progreso_retry_dm(idx, total, nombre_archivo):
                            texto_estado_retry_dm.info(f"⏳ Reintentando {idx+1}/{total}: {nombre_archivo}...")

                        with st.spinner("Reintentando los documentos pendientes..."):
                            resultados_retry_dm, _, _ = _procesar_documentos_dossier_dm(
                                archivos_reintento_dm, cache_dm["items_aplicables"],
                                callback_progreso=_avisar_progreso_retry_dm
                            )
                        texto_estado_retry_dm.empty()

                        resultados_por_nombre_dm = {r["Archivo_Original"]: r for r in resultados_dm}
                        for r in resultados_retry_dm:
                            resultados_por_nombre_dm[r["Archivo_Original"]] = r
                        resultados_dm = list(resultados_por_nombre_dm.values())

                        cache_dm["resultados"] = resultados_dm
                        st.session_state["dm_cache"] = cache_dm
                        st.rerun()

                archivos_zip_dm = _construir_zip_desde_resultados(resultados_dm, bytes_por_archivo_dm)
                df_cobertura_dm = pd.DataFrame(_recalcular_cobertura_dm(resultados_dm, cache_dm["items_aplicables"]))
                total_faltan = (df_cobertura_dm["Estado"] == "❌ FALTA").sum() if not df_cobertura_dm.empty else 0
                df_resultados_dm = pd.DataFrame(resultados_dm)
                total_observacion = (df_resultados_dm["Conforme"] == "⚠ Con observación").sum() if not df_resultados_dm.empty else 0

                if total_faltan == 0:
                    st.success("✨ ¡Checklist completo! Todos los documentos requeridos para este riesgo están cubiertos.")
                else:
                    st.warning(f"⚠ Faltan {total_faltan} documento(s) del checklist para este riesgo.")
                if total_observacion > 0:
                    st.warning(f"🔎 {total_observacion} documento(s) tienen alguna observación — revísalos antes de radicar.")

                st.markdown("###### Cobertura del checklist")
                st.dataframe(df_cobertura_dm, use_container_width=True, hide_index=True)

                st.markdown("###### Resultado por cada archivo subido")
                st.dataframe(
                    df_resultados_dm.drop(columns=["Nombre_Final"], errors="ignore"),
                    use_container_width=True, hide_index=True
                )

                if archivos_zip_dm:
                    output_zip_dossier = io.BytesIO()
                    with zipfile.ZipFile(output_zip_dossier, "w") as zf_out:
                        for nombre_final, bytes_archivo in archivos_zip_dm:
                            zf_out.writestr(f"{nombre_final}", bytes_archivo)
                        output_resumen_dm = io.BytesIO()
                        with pd.ExcelWriter(output_resumen_dm, engine='openpyxl') as writer:
                            df_cobertura_dm.to_excel(writer, sheet_name="Cobertura", index=False)
                            df_resultados_dm.drop(columns=["Nombre_Final"], errors="ignore").to_excel(
                                writer, sheet_name="Detalle por archivo", index=False
                            )
                            if cache_dm["referencias"]:
                                pd.DataFrame({"Referencia": cache_dm["referencias"]}).to_excel(
                                    writer, sheet_name="Referencias", index=False
                                )
                        zf_out.writestr("Resumen_Dossier.xlsx", output_resumen_dm.getvalue())

                    st.download_button(
                        label="📥 Descargar Dossier Organizado (.zip)",
                        data=output_zip_dossier.getvalue(),
                        file_name=f"Dossier_DM_{cache_dm['equipo'] or 'equipo'}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )

                registrar_log(
                    st.session_state["usuario_activo_real"],
                    f"Creación de Dossier (DM) - {cache_dm['equipo']} ({len(cache_dm['referencias'])} referencias) "
                    f"riesgo {riesgo_dossier} ({len(resultados_dm)} documentos, {total_faltan} faltantes)",
                    len(resultados_dm)
                )
            elif not archivos_dossier_dm:
                st.info("👈 Sube los documentos PDF para comenzar el análisis.")

        elif tramite_elegido == OPCIONES_TRAMITE[4]:
            st.markdown("##### Datos del trámite")
            equipo_mod = st.text_input("Nombre del equipo / producto", key="txt_equipo_mod")

            st.markdown("**Referencias relacionadas** (opcional — útil sobre todo para Y1/Y2)")
            modo_referencias_mod = st.radio(
                "¿Cómo vas a indicar las referencias?",
                ["✍️ Escribir manualmente (1-2 referencias)", "📄 Subir Excel (muchas referencias)"],
                horizontal=True, key="modo_referencias_mod", label_visibility="collapsed"
            )
            lista_referencias_mod = []
            if modo_referencias_mod.startswith("✍️"):
                texto_referencias_mod = st.text_area(
                    "Escribe una referencia por línea", key="txt_referencias_manual_mod",
                    placeholder="Ej:\nIMEC10\nIMEC12"
                )
                lista_referencias_mod = [
                    r.strip() for r in texto_referencias_mod.split("\n") if r.strip()
                ]
            else:
                archivo_referencias_mod = st.file_uploader(
                    "Sube el Excel de referencias (una sola columna, sin encabezado)",
                    type=["xlsx"], key="uploader_referencias_mod"
                )
                if archivo_referencias_mod is not None:
                    try:
                        df_refs_mod = pd.read_excel(archivo_referencias_mod, header=None, dtype=str)
                        lista_referencias_mod = [
                            r for r in df_refs_mod[0].astype(str).str.strip().tolist()
                            if r and r.lower() != "nan"
                        ]
                        st.success(f"✅ {len(lista_referencias_mod)} referencia(s) cargada(s).")
                    except Exception as e:
                        st.error(f"No se pudo leer el archivo de referencias: {e}")

            st.markdown("##### 2. Tipo(s) de modificación a realizar")
            st.caption("Marca todos los códigos que apliquen — puedes combinar legales y técnicos en el mismo trámite.")

            codigos_elegidos_mod = []

            col_legal_mod, col_tecnico_mod = st.columns(2)
            with col_legal_mod:
                st.markdown("**MODIFICACIÓN DE TIPO LEGAL**")
                for rol, opciones in CODIGOS_MOD_LEGAL:
                    st.markdown(f"*{rol}*")
                    for codigo, descripcion in opciones:
                        if st.checkbox(f"{codigo} — {descripcion}", key=f"chk_mod_{codigo}"):
                            codigos_elegidos_mod.append(codigo)
            with col_tecnico_mod:
                st.markdown("**MODIFICACIÓN DE TIPO TÉCNICO**")
                for codigo, descripcion in CODIGOS_MOD_TECNICO:
                    if st.checkbox(f"{codigo} — {descripcion}", key=f"chk_mod_{codigo}"):
                        codigos_elegidos_mod.append(codigo)

            if not codigos_elegidos_mod:
                st.info("👈 Marca al menos un código de modificación para continuar.")
            else:
                bloques_activados_mod = _obtener_bloques_desde_codigos(codigos_elegidos_mod)
                total_docs_mod = sum(len(b["documentos"]) for b in bloques_activados_mod) + len(DOCS_UNIVERSALES_MOD)

                with st.expander(f"📋 Ver los {total_docs_mod} documentos requeridos para tu selección", expanded=False):
                    st.markdown("**Documentos para todas las modificaciones**")
                    st.dataframe(
                        pd.DataFrame([{"Documento": d["documento"], "Sigla": d["sigla"]} for d in DOCS_UNIVERSALES_MOD]),
                        use_container_width=True, hide_index=True
                    )
                    for bloque in bloques_activados_mod:
                        st.markdown(f"**{'/'.join(bloque['codigos'])} — {bloque['titulo']}**")
                        st.dataframe(
                            pd.DataFrame([{"Documento": d["documento"], "Sigla": d["sigla"]} for d in bloque["documentos"]]),
                            use_container_width=True, hide_index=True
                        )

                st.markdown("##### Sube los documentos (PDF)")
                archivos_mod = st.file_uploader(
                    "Puedes subir varios PDF a la vez", type=["pdf"], accept_multiple_files=True,
                    key="uploader_mod"
                )

                if archivos_mod and st.button(
                    "🔍 Analizar y Organizar Documentos", use_container_width=True, key="btn_analizar_mod"
                ):
                    archivos_con_bytes_mod = [(f.name, f.read()) for f in archivos_mod]

                    texto_estado_mod = st.empty()

                    def _avisar_progreso_mod(idx, total, nombre_archivo):
                        texto_estado_mod.info(f"⏳ Analizando {idx+1}/{total}: {nombre_archivo}...")

                    with st.spinner("Analizando documentos con IA..."):
                        resultados_mod, _cobertura_inicial, _archivos_zip_inicial = _procesar_documentos_modificacion(
                            archivos_con_bytes_mod, bloques_activados_mod, callback_progreso=_avisar_progreso_mod
                        )
                    texto_estado_mod.empty()

                    # Se guarda todo en sesión (incluyendo los bytes de cada
                    # archivo) para poder reintentar solo los que fallen por
                    # límite de cuota de Gemini, sin tener que volver a subirlos.
                    st.session_state["mod_cache"] = {
                        "resultados": resultados_mod,
                        "bytes_por_archivo": {n: b for n, b in archivos_con_bytes_mod},
                        "equipo": equipo_mod,
                        "referencias": lista_referencias_mod,
                        "bloques_activados": bloques_activados_mod,
                        "codigos_elegidos": codigos_elegidos_mod,
                    }

                cache_mod = st.session_state.get("mod_cache")
                if cache_mod and cache_mod.get("codigos_elegidos") == codigos_elegidos_mod:
                    resultados_mod = cache_mod["resultados"]
                    bytes_por_archivo_mod = cache_mod["bytes_por_archivo"]

                    df_resultados_mod = pd.DataFrame(resultados_mod)
                    filas_fallidas_mod = df_resultados_mod[
                        df_resultados_mod["Comentario"].astype(str).str.contains("❌", na=False)
                    ] if not df_resultados_mod.empty else df_resultados_mod

                    if len(filas_fallidas_mod) > 0:
                        st.warning(
                            f"⚠ {len(filas_fallidas_mod)} archivo(s) no se pudieron analizar (por ejemplo, "
                            "por límite de cuota de Gemini). Espera un par de minutos y reintenta solo esos, "
                            "sin gastar cuota de nuevo en los que ya salieron bien."
                        )
                        if st.button(
                            "🔄 Reintentar solo los que fallaron", use_container_width=True, key="btn_reintentar_mod"
                        ):
                            nombres_fallidos = filas_fallidas_mod["Archivo_Original"].tolist()
                            archivos_reintento = [
                                (n, bytes_por_archivo_mod[n]) for n in nombres_fallidos if n in bytes_por_archivo_mod
                            ]

                            texto_estado_retry = st.empty()

                            def _avisar_progreso_retry(idx, total, nombre_archivo):
                                texto_estado_retry.info(f"⏳ Reintentando {idx+1}/{total}: {nombre_archivo}...")

                            with st.spinner("Reintentando los documentos pendientes..."):
                                resultados_retry, _, _ = _procesar_documentos_modificacion(
                                    archivos_reintento, cache_mod["bloques_activados"],
                                    callback_progreso=_avisar_progreso_retry
                                )
                            texto_estado_retry.empty()

                            # Fusionar: reemplazar las filas viejas (fallidas) por
                            # los resultados nuevos del reintento, conservando las
                            # que ya estaban bien.
                            resultados_por_nombre = {r["Archivo_Original"]: r for r in resultados_mod}
                            for r in resultados_retry:
                                resultados_por_nombre[r["Archivo_Original"]] = r
                            resultados_mod = list(resultados_por_nombre.values())

                            cache_mod["resultados"] = resultados_mod
                            st.session_state["mod_cache"] = cache_mod
                            st.rerun()

                    archivos_zip_mod = _construir_zip_desde_resultados(resultados_mod, bytes_por_archivo_mod)
                    df_cobertura_mod = pd.DataFrame(_recalcular_cobertura_modificacion(
                        resultados_mod, cache_mod["bloques_activados"]
                    ))
                    total_faltan_mod = (df_cobertura_mod["Estado"] == "❌ FALTA").sum() if not df_cobertura_mod.empty else 0
                    df_resultados_mod = pd.DataFrame(resultados_mod)
                    total_obs_mod = (df_resultados_mod["Conforme"] == "⚠ Con observación").sum() if not df_resultados_mod.empty else 0

                    if total_faltan_mod == 0:
                        st.success("✨ ¡Checklist completo! Todos los documentos requeridos están cubiertos.")
                    else:
                        st.warning(f"⚠ Faltan {total_faltan_mod} documento(s) del checklist para tu selección.")
                    if total_obs_mod > 0:
                        st.warning(f"🔎 {total_obs_mod} documento(s) tienen alguna observación — revísalos antes de radicar.")

                    st.markdown("###### Cobertura del checklist")
                    st.dataframe(df_cobertura_mod, use_container_width=True, hide_index=True)

                    st.markdown("###### Resultado por cada archivo subido")
                    st.dataframe(
                        df_resultados_mod.drop(columns=["Nombre_Final"], errors="ignore"),
                        use_container_width=True, hide_index=True
                    )

                    if archivos_zip_mod:
                        output_zip_mod = io.BytesIO()
                        with zipfile.ZipFile(output_zip_mod, "w") as zf_out:
                            for nombre_final, bytes_archivo in archivos_zip_mod:
                                zf_out.writestr(nombre_final, bytes_archivo)
                            output_resumen_mod = io.BytesIO()
                            with pd.ExcelWriter(output_resumen_mod, engine='openpyxl') as writer:
                                df_cobertura_mod.to_excel(writer, sheet_name="Cobertura", index=False)
                                df_resultados_mod.drop(columns=["Nombre_Final"], errors="ignore").to_excel(
                                    writer, sheet_name="Detalle por archivo", index=False
                                )
                                if cache_mod["referencias"]:
                                    pd.DataFrame({"Referencia": cache_mod["referencias"]}).to_excel(
                                        writer, sheet_name="Referencias", index=False
                                    )
                            zf_out.writestr("Resumen_Modificacion.xlsx", output_resumen_mod.getvalue())

                        st.download_button(
                            label="📥 Descargar Dossier Organizado (.zip)",
                            data=output_zip_mod.getvalue(),
                            file_name=f"Modificacion_{cache_mod['equipo'] or 'equipo'}.zip",
                            mime="application/zip",
                            use_container_width=True
                        )

                    registrar_log(
                        st.session_state["usuario_activo_real"],
                        f"Creación de Dossier (Modificaciones) - {cache_mod['equipo']} "
                        f"({len(cache_mod['referencias'])} referencias) "
                        f"({'/'.join(codigos_elegidos_mod)}) ({len(resultados_mod)} documentos, {total_faltan_mod} faltantes)",
                        len(resultados_mod)
                    )
                elif not archivos_mod:
                    st.info("👈 Sube los documentos PDF para comenzar el análisis.")

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
