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
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================================
# CONFIGURACIÓN GLOBAL
# ==========================================================
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SHEET_ID = "1SSAS4NLafR3p8K3nIlBoHp0AKklO5JNfWwQbSfNdbGU"
ADMIN_USER = "admin"

# ==========================================================
# FUNCIONES DE CONEXIÓN Y AUTENTICACIÓN
# ==========================================================

def get_gspread_client():
    creds_dict = dict(st.secrets["gcp"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    return gspread.authorize(creds)

def validar_usuario(usuario, password):
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos_usuarios = sheet_users.get_all_records()
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
        sheet_logs.append_row([timestamp, usuario, busqueda, cantidad_resultados])
    except Exception as e:
        st.error(f"Error al guardar log: {e}")

def obtener_usuarios():
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_records()
        return datos, sheet_users
    except Exception as e:
        st.error(f"Error al obtener usuarios: {e}")
        return [], None

def agregar_usuario(nuevo_usuario, nueva_password):
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_records()
        for fila in datos:
            if str(fila.get('usuario', '')).strip().lower() == nuevo_usuario.strip().lower():
                return False, "El usuario ya existe."
        sheet_users.append_row([nuevo_usuario.strip(), nueva_password.strip()])
        return True, "Usuario creado correctamente."
    except Exception as e:
        return False, f"Error: {e}"

def eliminar_usuario(usuario_a_eliminar):
    try:
        if usuario_a_eliminar.strip().lower() == ADMIN_USER.lower():
            return False, "No se puede eliminar al administrador."
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_values()
        for i, fila in enumerate(datos):
            if len(fila) > 0 and str(fila[0]).strip() == usuario_a_eliminar.strip():
                sheet_users.delete_rows(i + 1)
                return True, f"Usuario '{usuario_a_eliminar}' eliminado."
        return False, "Usuario no encontrado."
    except Exception as e:
        return False, f"Error: {e}"

def cambiar_password(usuario_objetivo, nueva_password):
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_values()
        for i, fila in enumerate(datos):
            if len(fila) > 0 and str(fila[0]).strip() == usuario_objetivo.strip():
                sheet_users.update_cell(i + 1, 2, nueva_password.strip())
                return True, f"Contraseña actualizada para '{usuario_objetivo}'."
        return False, "Usuario no encontrado."
    except Exception as e:
        return False, f"Error: {e}"

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
if "autenticado"         not in st.session_state: st.session_state["autenticado"]         = False
if "usuario_guardado"    not in st.session_state: st.session_state["usuario_guardado"]    = ""
if "usuario_activo_real" not in st.session_state: st.session_state["usuario_activo_real"] = ""
if "seccion_activa"      not in st.session_state: st.session_state["seccion_activa"]      = "Inicio"

# ==========================================================
# PANTALLA DE LOGIN
# ==========================================================
if not st.session_state["autenticado"]:
    st.markdown("""
    <style>
        /* ── Fondo login ── */
        .stApp {
            background-image: linear-gradient(rgba(15,32,67,0.65), rgba(15,32,67,0.85)),
                              url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070');
            background-size: cover; background-position: center; background-attachment: fixed;
        }
        header, footer, [data-testid="stSidebar"], #MainMenu {
            visibility: hidden !important; display: none !important;
        }

        /* ── Tarjeta del formulario ── */
        div[data-testid="stForm"] {
            background-color: #ffffff !important;
            border-radius: 16px !important;
            padding: 40px 36px !important;
            box-shadow: 0px 12px 40px rgba(0,0,0,0.35) !important;
            max-width: 480px !important;
            margin: 0 auto !important;
        }

        /* ── Texto dentro del formulario ── */
        div[data-testid="stForm"] label,
        div[data-testid="stForm"] p,
        div[data-testid="stForm"] span:not([data-baseweb]) {
            color: #1a1a2e !important;
        }

        /* ── Inputs del login ── */
        div[data-testid="stForm"] input {
            background-color: #f8fafc !important;
            color: #1a1a2e !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stForm"] input::placeholder { color: #94a3b8 !important; }
        div[data-testid="stForm"] [data-baseweb="base-input"],
        div[data-testid="stForm"] [data-baseweb="input"] > div {
            background-color: #f8fafc !important;
            border-color: #cbd5e1 !important;
        }

        /* ════════════════════════════════════════════════
           BOTÓN OJO — base-input limpio, sin fondo negro
        ════════════════════════════════════════════════ */
        div[data-testid="stForm"] [data-baseweb="base-input"] {
            border-radius: 8px !important;
            overflow: hidden !important;
            background-color: #f8fafc !important;
            border: 1.5px solid #cbd5e1 !important;
        }
        div[data-testid="stForm"] [data-baseweb="base-input"] > div {
            background-color: transparent !important;
        }

        /* ════════════════════════════════════════════════
           BOTÓN ACCEDER — azul oscuro, texto BLANCO
        ════════════════════════════════════════════════ */
        div[data-testid="stForm"] button[kind="primaryFormSubmit"],
        div[data-testid="stForm"] button[data-testid="baseButton-primaryFormSubmit"],
        div[data-testid="stForm"] > div button:not([data-baseweb]) {
            background-color: #1a365d !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            padding: 10px 24px !important;
        }
        /* Forzar blanco en cualquier hijo del botón Acceder */
        div[data-testid="stForm"] button[kind="primaryFormSubmit"] *,
        div[data-testid="stForm"] button[kind="primaryFormSubmit"] p,
        div[data-testid="stForm"] button[kind="primaryFormSubmit"] span,
        div[data-testid="stForm"] button[data-testid="baseButton-primaryFormSubmit"] *,
        div[data-testid="stForm"] button[data-testid="baseButton-primaryFormSubmit"] p,
        div[data-testid="stForm"] button[data-testid="baseButton-primaryFormSubmit"] span {
            color: #ffffff !important;
        }
        /* Selector nuclear de último recurso para el botón submit */
        div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button,
        div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button p,
        div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button span {
            background-color: #1a365d !important;
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #2a4d7c !important;
        }

        /* ════════════════════════════════════════════════
           CHECKBOX — fondo BLANCO, borde AZUL
        ════════════════════════════════════════════════ */

        /* El cuadrito del checkbox — todos los selectores posibles */
        div[data-testid="stForm"] [data-baseweb="checkbox"] [data-testid="stCheckbox"] span,
        div[data-testid="stForm"] [data-baseweb="checkbox"] label span:first-of-type,
        div[data-testid="stForm"] [data-baseweb="checkbox"] > label > div,
        div[data-testid="stForm"] [data-baseweb="checkbox"] > label > div:first-child,
        div[data-testid="stForm"] [data-baseweb="checkbox"] div[role="checkbox"],
        div[data-testid="stForm"] [data-baseweb="checkbox"] span[role="checkbox"],
        div[data-testid="stCheckbox"] label span:first-child,
        div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > label > span:first-child {
            background-color: #ffffff !important;
            background: #ffffff !important;
            border: 2px solid #1a365d !important;
            border-radius: 4px !important;
        }
        /* Marcado → azul */
        div[data-testid="stForm"] [data-baseweb="checkbox"] input[type="checkbox"]:checked + label span:first-of-type,
        div[data-testid="stForm"] [data-baseweb="checkbox"] [aria-checked="true"] > div,
        div[data-testid="stForm"] [data-baseweb="checkbox"] [aria-checked="true"] span:first-child {
            background-color: #1a365d !important;
            border-color: #1a365d !important;
        }
        div[data-testid="stForm"] [data-baseweb="checkbox"] p,
        div[data-testid="stForm"] [data-baseweb="checkbox"] label {
            color: #374151 !important;
        }

        /* ── Clases custom login ── */
        .contenedor-logos-principales {
            display: flex; justify-content: center; align-items: center;
            gap: 20px; margin-bottom: 24px; height: 70px;
        }
        .logo-header-invima { height: 60px !important; width: auto !important; object-fit: contain; }
        .logo-header-fda    { height: 46px !important; width: auto !important; object-fit: contain; }
        .barra-sep { width: 3px; height: 55px; background-color: #00b4d8; border-radius: 2px; }
        .login-title {
            color: #0b1d3a !important; font-size: 22px; font-weight: 700;
            text-align: center; margin-bottom: 4px;
        }
        .login-desc {
            color: #64748b !important; font-size: 13px;
            text-align: center; margin-bottom: 20px;
        }
        .soporte-inferior { border-top: 1px solid #e2e8f0; margin-top: 28px; padding-top: 20px; }
        .soporte-titulo {
            font-size: 11px; font-weight: 700; color: #94a3b8 !important;
            margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.5px;
        }
        .fila-logos { display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 10px; }
        .logo-soporte { height: 90px !important; width: auto !important; object-fit: contain; max-width: 220px !important; }

        /* ── Responsive móvil ── */
        @media (max-width: 768px) {
            div[data-testid="stForm"] { padding: 24px 16px !important; margin: 0 6px !important; }
            .logo-header-invima { height: 40px !important; }
            .logo-header-fda    { height: 30px !important; }
            .login-title { font-size: 18px !important; }
            .fila-logos { gap: 8px !important; }
            .logo-soporte { height: 26px !important; }
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1.4, 1])

    with col_centro:
        with st.form("formulario_login", clear_on_submit=False):
            # Logos superiores
            html_cab = '<div class="contenedor-logos-principales">'
            if b64_invima: html_cab += f'<img class="logo-header-invima" src="data:image/png;base64,{b64_invima}">'
            html_cab += '<div class="barra-sep"></div>'
            if b64_fda: html_cab += f'<img class="logo-header-fda" src="data:image/png;base64,{b64_fda}">'
            html_cab += '</div>'
            st.markdown(html_cab, unsafe_allow_html=True)

            st.markdown("<div class='login-title'>Plataforma de Extracción</div>", unsafe_allow_html=True)
            st.markdown("<div class='login-desc'>Gestión Automatizada de Dispositivos Médicos</div>", unsafe_allow_html=True)

            usuario    = st.text_input("Nombre de usuario", value=st.session_state["usuario_guardado"], placeholder="Introduzca su usuario").strip()
            contraseña = st.text_input("Contraseña", type="password", placeholder="Introduzca su contraseña")
            recordar   = st.checkbox("Recordar mi usuario en este equipo", value=(st.session_state["usuario_guardado"] != ""))
            boton_ingresar = st.form_submit_button("Acceder", use_container_width=True)

            # ── CSS nuclear: checkbox sin borde en texto + ojo blanco sin negro ──
            st.markdown("""
            <style>
            /* ══ CHECKBOX ══ solo el cuadrito tiene borde, el texto NO */
            div[data-testid="stForm"] [data-baseweb="checkbox"] label > div:first-child {
                background-color: #ffffff !important;
                background: #ffffff !important;
                border: 2px solid #1a365d !important;
                border-radius: 4px !important;
                min-width: 16px !important;
                min-height: 16px !important;
                width: 16px !important;
                height: 16px !important;
                flex-shrink: 0 !important;
                outline: none !important;
                box-shadow: none !important;
            }
            div[data-testid="stForm"] [data-baseweb="checkbox"] label,
            div[data-testid="stForm"] [data-baseweb="checkbox"] label > div:not(:first-child),
            div[data-testid="stForm"] [data-baseweb="checkbox"] p,
            div[data-testid="stForm"] [data-baseweb="checkbox"] span {
                border: none !important;
                outline: none !important;
                box-shadow: none !important;
                background: transparent !important;
            }

            /* ══ OJO ══ botón azul + quitar negro con width 0 en el div extra */
            div[data-testid="stPasswordInput"] [data-baseweb="base-input"] {
                overflow: hidden !important;
                border-radius: 8px !important;
                background-color: #f8fafc !important;
                display: flex !important;
                align-items: stretch !important;
            }
            /* input ocupa todo el espacio disponible */
            div[data-testid="stPasswordInput"] [data-baseweb="base-input"] input {
                flex: 1 !important;
                background-color: #f8fafc !important;
                min-width: 0 !important;
            }
            /* div contenedor del botón: sin padding/margin extra */
            div[data-testid="stPasswordInput"] [data-baseweb="base-input"] > div:not(:first-child) {
                background-color: #f8fafc !important;
                padding: 0 !important;
                margin: 0 !important;
                border: none !important;
                width: auto !important;
                flex-shrink: 0 !important;
            }
            /* El div negro extra que aparece DESPUÉS del botón → ancho 0 */
            div[data-testid="stPasswordInput"] [data-baseweb="base-input"] > div:last-child:not(:has(button)) {
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                padding: 0 !important;
                margin: 0 !important;
                overflow: hidden !important;
                background-color: #f8fafc !important;
            }
            /* El botón del ojo */
            div[data-testid="stPasswordInput"] button {
                background-color: #1a365d !important;
                border-radius: 0 !important;
                width: 42px !important;
                min-width: 42px !important;
                height: 100% !important;
                min-height: 36px !important;
                border: none !important;
                padding: 0 !important;
                margin: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            div[data-testid="stPasswordInput"] button:hover {
                background-color: #2a4d7c !important;
            }
            div[data-testid="stPasswordInput"] button svg,
            div[data-testid="stPasswordInput"] button > svg,
            div[data-testid="stPasswordInput"] button span svg {
                fill: #ffffff !important;
                color: #ffffff !important;
                stroke: #ffffff !important;
                width: 18px !important;
                height: 18px !important;
                display: block !important;
                opacity: 1 !important;
                visibility: visible !important;
            }
            div[data-testid="stPasswordInput"] button svg path,
            div[data-testid="stPasswordInput"] button svg circle,
            div[data-testid="stPasswordInput"] button svg line,
            div[data-testid="stPasswordInput"] button svg polyline {
                fill: #ffffff !important;
                stroke: #ffffff !important;
            }
            div[data-testid="stPasswordInput"] button span {
                background: transparent !important;
                display: flex !important;
                align-items: center !important;
            }
            </style>
            """, unsafe_allow_html=True)

            # Logos inferiores
            html_sop = '<div class="soporte-inferior"><div class="soporte-titulo">Bases de datos vinculadas</div><div class="fila-logos">'
            if b64_gudid:   html_sop += f'<img class="logo-soporte" src="data:image/png;base64,{b64_gudid}">'
            if b64_eudamed: html_sop += f'<img class="logo-soporte" src="data:image/png;base64,{b64_eudamed}">'
            if b64_gmdn:    html_sop += f'<img class="logo-soporte" src="data:image/png;base64,{b64_gmdn}">'
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
# INTERFAZ INTERNA
# ==========================================================
else:
    es_admin = st.session_state["usuario_activo_real"].strip().lower() == ADMIN_USER.lower()

    st.markdown("""
    <style>
        /* ── Base ── */
        .stApp { background-color: #f0f4f8 !important; }
        section.main { background-color: #f0f4f8 !important; }
        header, footer, #MainMenu { visibility: hidden !important; display: none !important; }

        /* ── Todo el texto del contenido principal en oscuro ── */
        section.main p,
        section.main span,
        section.main label,
        section.main h1, section.main h2, section.main h3,
        section.main h4, section.main h5, section.main h6 {
            color: #1e293b !important;
        }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            background-color: #0b1d3a !important;
            border-right: 1px solid #061122 !important;
        }
        [data-testid="stSidebar"] *:not(button):not(button *) {
            color: #ffffff !important;
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

        /* ── Botones del contenido principal — NUNCA NEGROS ── */
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
        section.main button:hover {
            background-color: #2a4d7c !important;
            color: #ffffff !important;
        }
        .stButton > button:active,
        section.main button:active {
            background-color: #0b1d3a !important;
            color: #ffffff !important;
        }
        .stButton > button:focus,
        section.main button:focus {
            background-color: #1a365d !important;
            color: #ffffff !important;
        }
        .stButton > button:disabled,
        section.main button:disabled {
            background-color: #94a3b8 !important;
            color: #e2e8f0 !important;
            opacity: 0.7 !important;
        }
        section.main button p,
        section.main button span,
        .stButton > button p,
        .stButton > button span { color: #ffffff !important; }

        /* ── Botón OJO en contenido principal — azul solo en su celda ── */
        section.main [data-baseweb="base-input"] {
            overflow: hidden !important;
            border-radius: 7px !important;
        }
        section.main [data-baseweb="base-input"] button,
        section.main [data-baseweb="input"] button {
            background-color: #1a365d !important;
            background: #1a365d !important;
            border: none !important;
            box-shadow: none !important;
            width: 42px !important;
            min-width: 42px !important;
            max-width: 42px !important;
            height: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            border-radius: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        section.main [data-baseweb="base-input"] button svg,
        section.main [data-baseweb="input"] button svg {
            fill: #ffffff !important;
            width: 17px !important;
            height: 17px !important;
        }
        section.main [data-baseweb="base-input"] button *,
        section.main [data-baseweb="input"] button * { color: #ffffff !important; }
        section.main [data-baseweb="base-input"] button:hover,
        section.main [data-baseweb="input"] button:hover {
            background-color: #2a4d7c !important;
        }

        /* ── Inputs contenido principal ── */
        section.main input[type="text"],
        section.main input[type="password"],
        section.main input[type="number"] {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 7px !important;
        }
        section.main [data-baseweb="base-input"],
        section.main [data-baseweb="input"] > div {
            background-color: #ffffff !important;
            border-color: #cbd5e1 !important;
        }
        section.main input::placeholder { color: #94a3b8 !important; }
        section.main label { color: #374151 !important; }

        /* ── Selectbox ── */
        section.main [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border-color: #cbd5e1 !important;
        }
        [data-baseweb="popover"] li,
        [data-baseweb="menu"] li {
            background-color: #ffffff !important;
            color: #1e293b !important;
        }

        /* ── Date input ── */
        [data-testid="stDateInput"] input { background-color: #ffffff !important; color: #1e293b !important; }

        /* ── Checkbox ── */
        section.main [data-baseweb="checkbox"] p { color: #374151 !important; }

        /* ── Alertas (info, warning, success, error) ── */
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] span { color: #1e293b !important; }

        /* ── File uploader ── */
        [data-testid="stFileUploadDropzone"] {
            background-color: #eef2ff !important;
            border: 2px dashed #1a365d !important;
            border-radius: 8px !important;
        }
        [data-testid="stFileUploadDropzone"] p,
        [data-testid="stFileUploadDropzone"] span { color: #374151 !important; }

        /* ── Métricas ── */
        [data-testid="stMetric"] {
            background-color: #ffffff !important;
            border-radius: 10px !important;
            padding: 14px 18px !important;
            border: 1px solid #dce4f5 !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
        }
        [data-testid="stMetricLabel"] p { color: #374151 !important; }
        [data-testid="stMetricValue"]   { color: #0b1d3a !important; }

        /* ── Progreso ── */
        .prog-wrap {
            width: 100%; background-color: #e2e8f0; border: 2px solid #1e40af;
            border-radius: 8px; padding: 3px; height: 30px; overflow: hidden; margin: 14px 0;
        }
        .prog-bar {
            height: 100%; border-radius: 5px;
            background-image: repeating-linear-gradient(-45deg, #1e40af, #1e40af 12px, #e2e8f0 12px, #e2e8f0 18px);
            transition: width 0.2s ease-in-out;
        }

        /* ── Header ── */
        .header-box {
            background-color: #ffffff !important;
            padding: 14px 28px; border-radius: 10px;
            box-shadow: 0px 2px 8px rgba(0,0,0,0.07);
            margin-bottom: 22px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .header-titulo { color: #0b1d3a !important; font-size: 20px; font-weight: 700; margin: 0; }
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

        /* ── Cards menú ── */
        .card-azul {
            background-color: #ffffff !important;
            padding: 22px; border-radius: 12px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.06);
            border-left: 5px solid #0b1d3a;
            margin-bottom: 16px;
        }
        .card-azul h4 { color: #0b1d3a !important; font-size: 15px !important; font-weight: 700 !important; margin: 0 0 6px 0 !important; }
        .card-azul p  { color: #475569 !important; font-size: 13px !important; margin: 0 !important; }

        .card-roja {
            background-color: #fff5f5 !important;
            padding: 22px; border-radius: 12px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.06);
            border-left: 5px solid #dc2626;
            margin-bottom: 16px;
        }
        .card-roja h4 { color: #991b1b !important; font-size: 15px !important; font-weight: 700 !important; margin: 0 0 6px 0 !important; }
        .card-roja p  { color: #475569 !important; font-size: 13px !important; margin: 0 !important; }

        /* ── Cards panel admin ── */
        .admin-card {
            background-color: #ffffff !important;
            border-radius: 12px !important;
            padding: 22px !important;
            box-shadow: 0 3px 10px rgba(0,0,0,0.07) !important;
            border-top: 4px solid #dc2626 !important;
            margin-bottom: 20px !important;
        }
        .admin-card-title {
            color: #991b1b !important;
            font-size: 15px !important;
            font-weight: 700 !important;
            margin: 0 0 16px 0 !important;
            display: block;
        }

        /* ── Tabla usuarios ── */
        .tabla-usr {
            width: 100%; border-collapse: collapse;
            border-radius: 8px; overflow: hidden;
            border: 1px solid #e2e8f0; margin-top: 8px;
        }
        .tabla-usr th {
            background-color: #0b1d3a !important; color: #ffffff !important;
            padding: 10px 14px; font-size: 13px; text-align: left;
        }
        .tabla-usr td {
            padding: 9px 14px; font-size: 13px;
            color: #1e293b !important;
            border-bottom: 1px solid #e2e8f0;
            background-color: #ffffff !important;
        }
        .tabla-usr tr:last-child td { border-bottom: none; }
        .tabla-usr tr:hover td { background-color: #eff6ff !important; }
        .meta-txt { color: #64748b !important; font-size: 12px; margin-top: 8px; }

        /* ── Footer ── */
        .footer-box {
            margin-top: 50px; padding: 22px 0;
            border-top: 1px solid #e2e8f0;
            text-align: center; font-size: 13px;
        }
        .footer-box p, .footer-box a, .footer-box span { color: #64748b !important; }
        .footer-links { display: flex; justify-content: center; gap: 28px; margin-bottom: 8px; flex-wrap: wrap; }
        .footer-links a { color: #0b1d3a !important; text-decoration: none; font-weight: 500; }

        /* ── Responsive móvil ── */
        @media (max-width: 768px) {
            .header-box { flex-direction: column !important; gap: 8px !important; padding: 12px !important; text-align: center !important; }
            .header-titulo { font-size: 15px !important; }
            .user-pill { font-size: 11px !important; }
            .card-azul, .card-roja, .admin-card { padding: 14px !important; }
        }

        /* ── Scrollbar ── */
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }

        /* ══ FORZAR FONDO BLANCO EN TODOS LOS INPUTS / SELECTS / DATES ══ */
        [data-testid="stTextInput"] > div,
        [data-testid="stTextInput"] > div > div,
        [data-testid="stTextInput"] input {
            background-color: #ffffff !important;
            color: #1e293b !important;
        }
        [data-testid="stTextInput"] input::placeholder { color: #94a3b8 !important; }

        [data-testid="stSelectbox"],
        [data-testid="stSelectbox"] > div,
        [data-testid="stSelectbox"] > div > div,
        [data-testid="stSelectbox"] > div > div > div,
        [data-testid="stSelectbox"] > div > div > div > div {
            background-color: #ffffff !important;
            color: #1e293b !important;
        }
        [data-baseweb="select"],
        [data-baseweb="select"] > div,
        [data-baseweb="select"] > div > div,
        [data-baseweb="select"] div[role="combobox"],
        [data-baseweb="select"] div[role="option"],
        [data-baseweb="select"] input {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border-color: #cbd5e1 !important;
        }
        [data-baseweb="select"] svg { fill: #374151 !important; }

        [data-testid="stDateInput"] > div,
        [data-testid="stDateInput"] > div > div,
        [data-testid="stDateInput"] input {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border-color: #cbd5e1 !important;
        }

        [data-baseweb="base-input"],
        [data-baseweb="base-input"] > div,
        [data-baseweb="input"],
        [data-baseweb="input"] > div {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border-color: #cbd5e1 !important;
        }
        [data-baseweb="base-input"] input,
        [data-baseweb="input"] input {
            background-color: #ffffff !important;
            color: #1e293b !important;
        }

        [data-baseweb="popover"],
        [data-baseweb="popover"] > div,
        [data-baseweb="menu"],
        [data-baseweb="menu"] ul,
        [data-baseweb="menu"] li {
            background-color: #ffffff !important;
            color: #1e293b !important;
        }
        [data-baseweb="option"]:hover {
            background-color: #eff6ff !important;
        }

        [data-testid="stFileUploadDropzone"],
        [data-testid="stFileUploadDropzone"] > div,
        [data-testid="stFileUploaderDropzoneInstructions"],
        section.main [data-testid="stFileUploader"] > div,
        section.main [data-testid="stFileUploader"] > label + div {
            background-color: #eef2ff !important;
            border: 2px dashed #1a365d !important;
            border-radius: 8px !important;
            color: #374151 !important;
        }
        [data-testid="stFileUploadDropzone"] button,
        [data-testid="stFileUploadDropzone"] button:hover,
        section.main [data-testid="stFileUploader"] button,
        [data-testid="baseButton-secondary"],
        [kind="secondary"] {
            background-color: #1a365d !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 6px !important;
        }
        [data-testid="stFileUploadDropzone"] p,
        [data-testid="stFileUploadDropzone"] span,
        [data-testid="stFileUploadDropzone"] small {
            color: #374151 !important;
        }

        [data-baseweb="checkbox"] > div:first-child {
            background-color: #ffffff !important;
            border-color: #94a3b8 !important;
        }
        [data-baseweb="checkbox"] [data-checked="true"] > div:first-child {
            background-color: #1a365d !important;
            border-color: #1a365d !important;
        }

        [data-testid="stTextInput"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stDateInput"] label,
        [data-testid="stFileUploader"] label {
            color: #374151 !important;
            font-weight: 500 !important;
        }

    </style>
    """, unsafe_allow_html=True)

    # CSS nuclear para inputs, selects, file uploader
    st.markdown("""
    <style>
    /* ===== NUCLEAR OVERRIDE — FONDO BLANCO EN TODO ===== */
    div[data-baseweb="base-input"] {
        background-color: white !important;
    }
    div[data-baseweb="base-input"] > div {
        background-color: white !important;
    }
    div[data-baseweb="base-input"] input {
        background-color: white !important;
        color: #1e293b !important;
    }

    div[data-baseweb="select"] > div:first-child {
        background-color: white !important;
        border-color: #cbd5e1 !important;
    }
    div[data-baseweb="select"] div {
        background-color: white !important;
        color: #1e293b !important;
    }
    div[data-baseweb="select"] span {
        color: #1e293b !important;
    }

    div[data-testid="stFileUploadDropzone"] {
        background-color: #eef2ff !important;
        border: 2px dashed #1a365d !important;
    }
    div[data-testid="stFileUploadDropzone"] > div {
        background-color: #eef2ff !important;
    }
    div[data-testid="stFileUploadDropzone"] * {
        color: #374151 !important;
    }
    div[data-testid="stFileUploadDropzone"] button {
        background-color: #1a365d !important;
        color: white !important;
        border-radius: 6px !important;
        border: none !important;
    }
    div[data-testid="stFileUploadDropzone"] button * {
        color: white !important;
    }

    div[data-testid="stDateInput"] > div {
        background-color: white !important;
    }
    div[data-testid="stDateInput"] input {
        background-color: white !important;
        color: #1e293b !important;
    }

    .tabla-usr td {
        background-color: white !important;
        color: #1e293b !important;
    }

    div[data-baseweb="popover"] div {
        background-color: white !important;
        color: #1e293b !important;
    }
    ul[role="listbox"] {
        background-color: white !important;
    }
    li[role="option"] {
        background-color: white !important;
        color: #1e293b !important;
    }
    li[role="option"]:hover {
        background-color: #eff6ff !important;
    }

    label[data-baseweb="checkbox"] > div:first-child {
        background-color: white !important;
        border-color: #94a3b8 !important;
    }

    </style>
    """, unsafe_allow_html=True)

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown('<div class="sidebar-header">⚙️ Opciones del Sistema</div>', unsafe_allow_html=True)
        st.markdown("<p style='color:#94a3b8; font-size:10px; text-transform:uppercase; font-weight:700; margin:0 0 10px 5px; letter-spacing:0.5px;'>Navegación</p>", unsafe_allow_html=True)

        if st.sidebar.button("🏠 Menú Principal", use_container_width=True):
            st.session_state["seccion_activa"] = "Inicio"; st.rerun()
        st.sidebar.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        if st.sidebar.button("🚀 Extracción Masiva", use_container_width=True):
            st.session_state["seccion_activa"] = "Extraccion"; st.rerun()
        st.sidebar.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        if st.sidebar.button("📋 Historiales y Reportes", use_container_width=True):
            st.session_state["seccion_activa"] = "Historiales"; st.rerun()

        if es_admin:
            st.sidebar.markdown("<hr style='border-color:rgba(255,255,255,0.15); margin:16px 0 10px;'>", unsafe_allow_html=True)
            st.sidebar.markdown("<p style='color:#fca5a5; font-size:10px; text-transform:uppercase; font-weight:700; margin:0 0 8px 5px;'>Administración</p>", unsafe_allow_html=True)
            if st.sidebar.button("👥 Panel de Administración", use_container_width=True):
                st.session_state["seccion_activa"] = "Admin"; st.rerun()

        st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
        if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state["autenticado"] = False; st.rerun()

    # --- HEADER ---
    usuario_sesion = st.session_state["usuario_activo_real"]
    badge = '<span class="badge-admin">ADMIN</span>' if es_admin else ""
    st.markdown(f"""
        <div class="header-box">
            <div class="header-titulo">Oficina Virtual de Dispositivos Médicos</div>
            <div class="user-pill">👤 <b>{usuario_sesion}</b>{badge}</div>
        </div>""", unsafe_allow_html=True)

    # ==========================================================
    # VISTA 1: MENÚ PRINCIPAL
    # ==========================================================
    if st.session_state["seccion_activa"] == "Inicio":
        st.markdown("<h3 style='color:#0b1d3a; margin-bottom:4px;'>Menú Principal</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569; margin-bottom:20px;'>Seleccione una de las siguientes opciones:</p>", unsafe_allow_html=True)

        st.markdown("""
            <div class="card-azul">
                <h4>1. Módulo Automatizado de Extracción Masiva</h4>
                <p>Carga masiva de archivos Excel para cruce con AccessGUDID (FDA), identificación de códigos GMDN y agencias emisoras.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("🚀 Ingresar al Módulo de Extracción", key="btn_ext", use_container_width=True):
            st.session_state["seccion_activa"] = "Extraccion"; st.rerun()

        st.markdown("""
            <div class="card-azul" style="border-left-color:#0369a1;">
                <h4>2. Consulta de Historiales y Reportes</h4>
                <p>Consulta el historial de referencias buscadas por usuario, con fecha y cantidad de resultados obtenidos.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("📋 Ver Historiales y Reportes", key="btn_hist", use_container_width=True):
            st.session_state["seccion_activa"] = "Historiales"; st.rerun()

        if es_admin:
            st.markdown("""
                <div class="card-roja">
                    <h4>🔐 3. Panel de Administración</h4>
                    <p>Gestión completa de usuarios: agregar, eliminar, cambiar contraseñas y visualizar lista de accesos.</p>
                </div>""", unsafe_allow_html=True)
            if st.button("👥 Ir al Panel de Administración", key="btn_admin", use_container_width=True):
                st.session_state["seccion_activa"] = "Admin"; st.rerun()

    # ==========================================================
    # VISTA 2: EXTRACCIÓN MASIVA
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Extraccion":
        st.markdown("<h3 style='color:#0b1d3a;'>🚀 Extracción Automatizada AccessGUDID (FDA)</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569;'>Suba su archivo, aplique filtros opcionales e inicie la consulta.</p>", unsafe_allow_html=True)

        col_izq, col_der = st.columns([1, 2])

        with col_izq:
            st.info("⚙ Configuración de Parámetros")
            archivo_cargado     = st.file_uploader("Sube tu archivo de Excel (.xlsx)", type=["xlsx"])
            st.markdown('''<style>
            [data-testid="stFileUploader"] > div:last-child,
            [data-testid="stFileUploader"] > div:last-child > div,
            [data-testid="stFileUploadDropzone"] {
                background: #eef2ff !important;
                background-color: #eef2ff !important;
                border: 2px dashed #1a365d !important;
            }
            [data-testid="stFileUploadDropzone"] * { color: #374151 !important; }
            [data-testid="stFileUploadDropzone"] button {
                background-color: #1a365d !important;
                color: white !important;
                border-radius: 6px !important;
            }
            [data-testid="stFileUploadDropzone"] button * { color: white !important; }
            [data-baseweb="checkbox"] span:first-child {
                background-color: white !important;
                border-color: #94a3b8 !important;
                border-width: 2px !important;
                border-style: solid !important;
            }
            </style>''', unsafe_allow_html=True)
            company_name_filtro = st.text_input("Filtrar por Company Name (Opcional)", "").strip()
            conectar_boton      = st.button("🚀 Iniciar Extracción Masiva", disabled=(archivo_cargado is None), use_container_width=True)

        with col_der:
            st.warning("📊 Monitor de Procesamiento en Tiempo Real")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            if archivo_cargado and conectar_boton:
                try:
                    bytes_data = archivo_cargado.read()
                    df = pd.read_excel(io.BytesIO(bytes_data), header=None, dtype=str)
                    df[0] = df[0].astype(str).str.strip()
                    referencias_totales = [r for r in df[0].tolist() if r and r != "nan"]
                    total_refs = len(referencias_totales)
                except Exception as e:
                    st.error(f"Error al abrir el archivo de Excel: {e}"); st.stop()

                st.success(f"📋 Referencias encontradas: {total_refs}")
                texto_estado = st.empty(); barra_custom = st.empty(); tabla_viva = st.empty()
                lista_resultados = []; session = requests.Session()

                def actualizar_barra(pct):
                    barra_custom.markdown(f'<div class="prog-wrap"><div class="prog-bar" style="width:{pct}%;"></div></div>', unsafe_allow_html=True)

                for idx, ref in enumerate(referencias_totales):
                    base_pct = (idx / total_refs) * 100
                    paso_pct = (1 / total_refs) * 100
                    texto_estado.info(f"⏳ Fila {idx+1} de {total_refs} | 🔍 Buscando: {ref}...")
                    actualizar_barra(int(base_pct + paso_pct * 0.33))
                    url_busqueda = f"https://accessgudid.nlm.nih.gov/devices/search?query={urllib.parse.quote(ref)}"
                    try:
                        response = session.get(url_busqueda, headers=headers, timeout=15)
                        actualizar_barra(int(base_pct + paso_pct * 0.66)); time.sleep(0.4)
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, 'html.parser')
                            enlaces = list(dict.fromkeys([a['href'] for a in soup.find_all('a', href=True) if '/devices/' in a['href'] and 'search' not in a['href']]))
                            coincidencias = []
                            for href in enlaces:
                                try:
                                    res = session.get(f"https://accessgudid.nlm.nih.gov{href}", headers=headers, timeout=15)
                                    if res.status_code != 200: continue
                                    soup2 = BeautifulSoup(res.text, 'html.parser')
                                    texto = soup2.get_text()
                                    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
                                    company = "No encontrado"
                                    for i, l in enumerate(lineas):
                                        if "Company Name" in l:
                                            company = lineas[i+1] if l.replace(":","").strip() == "Company Name" and i+1 < len(lineas) else l.replace("Company Name","").replace(":","").strip()
                                            break
                                    company = " ".join(company.split()).strip() or "No encontrado"
                                    if company_name_filtro and company_name_filtro.upper() not in company.upper(): continue
                                    gmdn_code = "No encontrado"
                                    for p in texto.replace(':',' ').replace('(',' ').replace(')',' ').split():
                                        if p.isdigit() and len(p) == 5: gmdn_code = p; break
                                    gmdn_def, gmdn_status = "No encontrado", "No encontrado"
                                    for i, l in enumerate(lineas):
                                        if "GMDN Term Definition" in l:
                                            candidatos = [x.replace("[?]","").strip() for x in lineas[i:] if x.replace("[?]","").strip() and not any(h in x for h in ["GMDN Term Code","GMDN Term Name","GMDN Term Definition","GMDN Term Status","Implantable?"]) and not (x.strip().isdigit() and len(x.strip())==5)]
                                            if len(candidatos) >= 2: gmdn_def, gmdn_status = candidatos[1], candidatos[2] if len(candidatos)>2 else candidatos[1]
                                            elif len(candidatos) == 1: gmdn_def = candidatos[0]
                                            break
                                    diccionario_estados = {"active":"Activo","obsolete":"Obsoleto","no encontrado":"No encontrado"}
                                    gmdn_status = diccionario_estados.get(gmdn_status.lower(), gmdn_status)
                                    if gmdn_def and gmdn_def.lower() != "no encontrado":
                                        try:
                                            texto_url = gmdn_def.replace('"','').replace("'","")
                                            partes, pedazos_trad = [], []
                                            palabras, parte_actual, cuenta = texto_url.split(), [], 0
                                            for palabra in palabras:
                                                if cuenta + len(palabra) + 1 > 450: partes.append(" ".join(parte_actual)); parte_actual=[palabra]; cuenta=len(palabra)
                                                else: parte_actual.append(palabra); cuenta += len(palabra)+1
                                            if parte_actual: partes.append(" ".join(parte_actual))
                                            for parte in partes:
                                                r_t = requests.get(f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(parte)}&langpair=en|es", timeout=5)
                                                if r_t.status_code == 200:
                                                    trad = r_t.json().get("responseData",{}).get("translatedText","")
                                                    pedazos_trad.append(trad if trad and "MYMEMORY" not in trad else parte)
                                                else: pedazos_trad.append(parte)
                                            gmdn_def = " ".join(pedazos_trad).strip()
                                        except: pass
                                    issuing = "No encontrado"
                                    for i, l in enumerate(lineas):
                                        if "Issuing Agency" in l:
                                            issuing = lineas[i+1] if l.replace(":","").strip() == "Issuing Agency" and i+1 < len(lineas) else l.replace("Issuing Agency","").replace(":","").strip()
                                            break
                                    issuing = " ".join(issuing.split()).strip() or "No encontrado"
                                    coincidencias.append({"Referencia_Original":ref,"Primary_DI_Number":href.split('/')[-1].strip(),"Nombre_Empresa_FDA":company,"Codigo_GMDN":gmdn_code,"Definicion_GMDN":" ".join(str(gmdn_def).split()).strip(),"Estado_GMDN":" ".join(str(gmdn_status).split()).strip(),"Issuing_Agency":issuing})
                                except: continue
                            if coincidencias: lista_resultados.extend(coincidencias)
                            else: lista_resultados.append({"Referencia_Original":ref,"Primary_DI_Number":"Filtrado","Nombre_Empresa_FDA":"No coincide","Codigo_GMDN":"Filtrado","Definicion_GMDN":"Filtrado","Estado_GMDN":"Filtrado","Issuing_Agency":"Filtrado"})
                        elif response.status_code == 429:
                            st.warning("⏳ Servidor saturado. Esperando 15 segundos..."); time.sleep(15)
                        else:
                            lista_resultados.append({"Referencia_Original":ref,"Primary_DI_Number":"No encontrado","Nombre_Empresa_FDA":"No encontrado","Codigo_GMDN":"No encontrado","Definicion_GMDN":"No encontrado","Estado_GMDN":"No encontrado","Issuing_Agency":"No encontrado"})
                    except Exception:
                        lista_resultados.append({"Referencia_Original":ref,"Primary_DI_Number":"Error de Red","Nombre_Empresa_FDA":"Error","Codigo_GMDN":"Error","Definicion_GMDN":"Error","Estado_GMDN":"Error","Issuing_Agency":"Error"})
                    actualizar_barra(int((idx+1)/total_refs*100))
                    tabla_viva.dataframe(pd.DataFrame(lista_resultados), use_container_width=True)
                    time.sleep(0.8)

                texto_estado.empty(); barra_custom.empty()
                st.success("✨ ¡Extracción completada al 100%!")
                registrar_log(st.session_state["usuario_activo_real"], f"Extracción masiva ({total_refs} refs)", len(lista_resultados))
                df_final = pd.DataFrame(lista_resultados)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False)
                st.download_button(label="📥 Descargar Excel con Resultados", data=output.getvalue(), file_name="resultados_fda.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            elif not archivo_cargado:
                st.info("👈 Cargue un archivo en el panel izquierdo para activar la monitorización.")

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
            df_fil = df_fil[(df_fil["Fecha"].dt.date >= filtro_fecha_ini) & (df_fil["Fecha"].dt.date <= filtro_fecha_fin)]

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
            st.download_button(label="📥 Descargar Historial en Excel", data=out_logs.getvalue(), file_name=f"historial_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

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
            with st.spinner("Cargando usuarios..."):
                datos_usuarios, _ = obtener_usuarios()
            if datos_usuarios:
                filas = ""
                for u in datos_usuarios:
                    nom = str(u.get('usuario', '')).strip()
                    rol = "🔴 Admin" if nom.lower() == ADMIN_USER.lower() else "🟢 Usuario"
                    filas += f"<tr><td>{nom}</td><td>{rol}</td></tr>"
                st.markdown(f'<table class="tabla-usr"><thead><tr><th>Usuario</th><th>Rol</th></tr></thead><tbody>{filas}</tbody></table><p class="meta-txt">Total: {len(datos_usuarios)} usuario(s)</p>', unsafe_allow_html=True)
            else:
                st.info("No se encontraron usuarios.")
            st.markdown('</div>', unsafe_allow_html=True)

        with col_agregar:
            st.markdown('<div class="admin-card"><span class="admin-card-title">➕ Agregar Nuevo Usuario</span>', unsafe_allow_html=True)
            nuevo_usr  = st.text_input("Nombre de usuario", key="nu", placeholder="Ej: usuario_nuevo")
            nuevo_pwd  = st.text_input("Contraseña", type="password", key="np", placeholder="Contraseña segura")
            nuevo_pwd2 = st.text_input("Confirmar contraseña", type="password", key="np2", placeholder="Repita la contraseña")
            if st.button("✅ Crear Usuario", key="btn_crear", use_container_width=True):
                if not nuevo_usr or not nuevo_pwd: st.warning("Complete todos los campos.")
                elif nuevo_pwd != nuevo_pwd2: st.error("Las contraseñas no coinciden.")
                elif len(nuevo_pwd) < 4: st.warning("Mínimo 4 caracteres.")
                else:
                    ok, msg = agregar_usuario(nuevo_usr, nuevo_pwd)
                    if ok: st.success(f"✔ {msg}"); registrar_log(usuario_sesion, f"[ADMIN] Creó: {nuevo_usr}", "-"); time.sleep(0.5); st.rerun()
                    else: st.error(f"❌ {msg}")
            st.markdown('</div>', unsafe_allow_html=True)

        col_elim, col_pwd = st.columns(2)

        with col_elim:
            st.markdown('<div class="admin-card"><span class="admin-card-title">🗑️ Eliminar Usuario</span>', unsafe_allow_html=True)
            no_admin = [str(u.get('usuario','')).strip() for u in datos_usuarios if str(u.get('usuario','')).strip().lower() != ADMIN_USER.lower()] if datos_usuarios else []
            if no_admin:
                usr_elim = st.selectbox("Seleccionar usuario", no_admin, key="sel_e")
                confirmar = st.checkbox(f"Confirmo eliminar a **{usr_elim}**", key="chk_e")
                if st.button("🗑️ Eliminar Usuario", key="btn_e", use_container_width=True):
                    if not confirmar: st.warning("Marque la casilla de confirmación.")
                    else:
                        ok, msg = eliminar_usuario(usr_elim)
                        if ok: st.success(f"✔ {msg}"); registrar_log(usuario_sesion, f"[ADMIN] Eliminó: {usr_elim}", "-"); time.sleep(0.5); st.rerun()
                        else: st.error(f"❌ {msg}")
            else:
                st.info("No hay usuarios para eliminar.")
            st.markdown('</div>', unsafe_allow_html=True)

        with col_pwd:
            st.markdown('<div class="admin-card"><span class="admin-card-title">🔑 Cambiar Contraseña</span>', unsafe_allow_html=True)
            todos = [str(u.get('usuario','')).strip() for u in datos_usuarios] if datos_usuarios else []
            if todos:
                usr_pwd = st.selectbox("Seleccionar usuario", todos, key="sel_p")
                npwd1   = st.text_input("Nueva contraseña", type="password", key="np1", placeholder="Nueva contraseña")
                npwd2   = st.text_input("Confirmar contraseña", type="password", key="np2b", placeholder="Repita la contraseña")
                if st.button("🔑 Actualizar Contraseña", key="btn_p", use_container_width=True):
                    if not npwd1: st.warning("Ingrese la nueva contraseña.")
                    elif npwd1 != npwd2: st.error("Las contraseñas no coinciden.")
                    elif len(npwd1) < 4: st.warning("Mínimo 4 caracteres.")
                    else:
                        ok, msg = cambiar_password(usr_pwd, npwd1)
                        if ok: st.success(f"✔ {msg}"); registrar_log(usuario_sesion, f"[ADMIN] Cambió pwd de: {usr_pwd}", "-"); time.sleep(0.5); st.rerun()
                        else: st.error(f"❌ {msg}")
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
            <p>v 1.1.26 © Invima 2026. Todos los derechos reservados.</p>
        </div>""", unsafe_allow_html=True)
