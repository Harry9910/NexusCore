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
ADMIN_USER = "admin"  # Usuario con privilegios de administrador

# ==========================================================
# FUNCIONES DE CONEXIÓN Y AUTENTICACIÓN
# ==========================================================

def get_gspread_client():
    """Crea y retorna un cliente de gspread autenticado."""
    creds_dict = dict(st.secrets["gcp"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    return gspread.authorize(creds)

def validar_usuario(usuario, password):
    """Valida usuario y contraseña contra la hoja 'Usuarios' de Google Sheets."""
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
    """Obtiene todos los logs desde la hoja 'Logs' de Google Sheets."""
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
    """Registra una búsqueda en la hoja 'Logs' de Google Sheets."""
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_logs = doc.worksheet("Logs")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet_logs.append_row([timestamp, usuario, busqueda, cantidad_resultados])
    except Exception as e:
        st.error(f"Error al guardar log: {e}")

# ==========================================================
# FUNCIONES DE GESTIÓN DE USUARIOS (SOLO ADMIN)
# ==========================================================

def obtener_usuarios():
    """Obtiene la lista de usuarios desde Google Sheets."""
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
    """Agrega un nuevo usuario a la hoja 'Usuarios'."""
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_records()
        # Verificar que no exista
        for fila in datos:
            if str(fila.get('usuario', '')).strip().lower() == nuevo_usuario.strip().lower():
                return False, "El usuario ya existe."
        sheet_users.append_row([nuevo_usuario.strip(), nueva_password.strip()])
        return True, "Usuario creado correctamente."
    except Exception as e:
        return False, f"Error: {e}"

def eliminar_usuario(usuario_a_eliminar):
    """Elimina un usuario de la hoja 'Usuarios'."""
    try:
        if usuario_a_eliminar.strip().lower() == ADMIN_USER.lower():
            return False, "No se puede eliminar al administrador."
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_values()  # incluye cabecera
        for i, fila in enumerate(datos):
            if len(fila) > 0 and str(fila[0]).strip() == usuario_a_eliminar.strip():
                sheet_users.delete_rows(i + 1)
                return True, f"Usuario '{usuario_a_eliminar}' eliminado."
        return False, "Usuario no encontrado."
    except Exception as e:
        return False, f"Error: {e}"

def cambiar_password(usuario_objetivo, nueva_password):
    """Cambia la contraseña de un usuario."""
    try:
        client = get_gspread_client()
        doc = client.open_by_key(SHEET_ID)
        sheet_users = doc.worksheet("Usuarios")
        datos = sheet_users.get_all_values()  # incluye cabecera
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
# CSS GLOBAL (compartido login + app)
# ==========================================================
CSS_GLOBAL = """
<style>
/* ── TABLAS / DATAFRAMES: fondo gris muy claro, texto oscuro ── */
[data-testid="stDataFrame"] div,
[data-testid="stDataFrame"] table,
[data-testid="stDataFrame"] thead,
[data-testid="stDataFrame"] tbody,
[data-testid="stDataFrame"] tr,
[data-testid="stDataFrame"] td,
[data-testid="stDataFrame"] th {
    background-color: #f8f9fb !important;
    color: #1a1a2e !important;
}
/* ── SELECTBOX / INPUTS: fondo claro ── */
div[data-baseweb="select"] > div,
div[data-baseweb="input"]  > div,
input, textarea {
    background-color: #f8f9fb !important;
    color: #1a1a2e !important;
}
/* ── DATE INPUT ── */
div[data-testid="stDateInput"] input {
    background-color: #f8f9fb !important;
    color: #1a1a2e !important;
}
/* ── MÉTRICAS ── */
[data-testid="stMetric"] {
    background-color: #f0f4ff !important;
    border-radius: 10px;
    padding: 14px 18px !important;
    border: 1px solid #dce4f5 !important;
}
[data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"]   { color: #0b1d3a !important; }
/* ── FILE UPLOADER ── */
[data-testid="stFileUploadDropzone"] {
    background-color: #f0f4ff !important;
    border: 2px dashed #1e40af !important;
    color: #1a1a2e !important;
}
/* ── INFO / WARNING / SUCCESS / ERROR boxes ── */
div[data-testid="stAlert"] {
    background-color: #f0f4ff !important;
    color: #1a1a2e !important;
}
</style>
"""
st.markdown(CSS_GLOBAL, unsafe_allow_html=True)

# ==========================================================
# PANTALLA DE LOGIN
# ==========================================================
if not st.session_state["autenticado"]:
    st.markdown("""
        <style>
            .stApp {
                background-image: linear-gradient(rgba(15,32,67,0.65), rgba(15,32,67,0.85)),
                                  url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070');
                background-size: cover; background-position: center; background-attachment: fixed;
            }
            header, footer, [data-testid="stSidebar"], #MainMenu { visibility: hidden !important; display: none !important; }
            div[data-testid="stForm"] {
                background-color: rgba(255,255,255,0.98) !important;
                border-radius: 16px !important;
                padding: 45px 40px !important;
                box-shadow: 0px 12px 40px rgba(0,0,0,0.35) !important;
                max-width: 540px;
                margin: 0 auto;
            }
            .contenedor-logos-principales {
                display: flex; justify-content: center; align-items: center;
                gap: 25px; margin-bottom: 30px; height: 75px;
            }
            .logo-header-invima { height: 65px !important; width: auto !important; object-fit: contain; }
            .logo-header-fda    { height: 50px !important; width: auto !important; object-fit: contain; }
            .barra-separadora-vertical-azul { width: 3px; height: 60px; background-color: #00b4d8; margin: 0 10px; }
            .login-title { color: #0f2043 !important; font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 6px; }
            .login-desc  { color: #555555 !important; font-size: 14px; text-align: center; margin-bottom: 25px; }
            div[data-testid="stForm"] button {
                background-color: #000c66 !important; color: white !important;
                width: 120px; border-radius: 6px; padding: 10px 20px;
                font-size: 16px; font-weight: 500;
            }
            .contenedor-soporte-inferior { border-top: 1px solid #eef0f4; margin-top: 35px; padding-top: 25px; }
            .titulo-soporte { font-size: 12.5px; font-weight: 600; color: #6c757d !important; margin-bottom: 20px; text-transform: uppercase; }
            .fila-logos-soporte { display: flex; justify-content: space-between; align-items: center; }
            .logo-gudid-libre   { width: 130px !important; height: auto !important; object-fit: contain; }
            .logo-eudamed-libre { width: 120px !important; height: auto !important; object-fit: contain; }
            .logo-gmdn-libre    { width: 135px !important; height: auto !important; object-fit: contain; }
            @media (max-width: 768px) {
                div[data-testid="stForm"] { padding: 25px 18px !important; margin: 0 8px !important; }
                .contenedor-logos-principales { gap: 12px !important; height: 55px !important; }
                .logo-header-invima { height: 42px !important; }
                .logo-header-fda    { height: 32px !important; }
                .login-title { font-size: 20px !important; }
                .fila-logos-soporte { flex-direction: column !important; gap: 12px !important; align-items: center !important; }
                .logo-gudid-libre, .logo-eudamed-libre, .logo-gmdn-libre { width: 100px !important; }
            }
        </style>""", unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1.2, 1])

    with col_centro:
        with st.form("formulario_login", clear_on_submit=False):
            html_cabecera = '<div class="contenedor-logos-principales">'
            if b64_invima: html_cabecera += f'<img class="logo-header-invima" src="data:image/png;base64,{b64_invima}">'
            html_cabecera += '<div class="barra-separadora-vertical-azul"></div>'
            if b64_fda:    html_cabecera += f'<img class="logo-header-fda" src="data:image/png;base64,{b64_fda}">'
            html_cabecera += '</div>'
            st.markdown(html_cabecera, unsafe_allow_html=True)

            st.markdown("<div class='login-title'>Plataforma de Extracción</div>", unsafe_allow_html=True)
            st.markdown("<div class='login-desc'>Gestión Automatizada de Dispositivos Médicos</div>", unsafe_allow_html=True)

            usuario    = st.text_input("Nombre de usuario", value=st.session_state["usuario_guardado"], placeholder="Introduzca su usuario").strip()
            contraseña = st.text_input("Contraseña", type="password", placeholder="Introduzca su contraseña")
            recordar   = st.checkbox("Recordar mi usuario en este equipo", value=(st.session_state["usuario_guardado"] != ""))
            boton_ingresar = st.form_submit_button("Acceder")

            html_soporte = '<div class="contenedor-soporte-inferior"><div class="titulo-soporte">Bases de datos vinculadas:</div><div class="fila-logos-soporte">'
            if b64_gudid:   html_soporte += f'<img class="logo-gudid-libre"   src="data:image/png;base64,{b64_gudid}">'
            if b64_eudamed: html_soporte += f'<img class="logo-eudamed-libre" src="data:image/png;base64,{b64_eudamed}">'
            if b64_gmdn:    html_soporte += f'<img class="logo-gmdn-libre"    src="data:image/png;base64,{b64_gmdn}">'
            html_soporte += '</div></div>'
            st.markdown(html_soporte, unsafe_allow_html=True)

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
    es_admin = st.session_state["usuario_activo_real"].strip().lower() == ADMIN_USER.lower()

    st.markdown("""
        <style>
            .stApp { background-image: none !important; background-color: #f0f2f6 !important; }
            header, footer, #MainMenu { visibility: hidden !important; display: none !important; }
            [data-testid="stSidebar"] {
                visibility: visible !important;
                background-color: #0b1d3a !important;
                border-right: 1px solid #061122 !important;
            }
            .sidebar-text-header {
                text-align: center; padding: 15px 10px; margin-bottom: 20px;
                color: #ffffff !important; font-size: 20px; font-weight: 700;
                border-bottom: 1px solid rgba(255,255,255,0.15);
            }
            [data-testid="stSidebar"] button {
                background-color: #1a365d !important; color: #ffffff !important;
                font-weight: 600 !important; border: 1px solid #2a4d7c !important;
                border-radius: 6px !important; padding: 10px !important;
            }
            [data-testid="stSidebar"] button:hover { background-color: #2a4d7c !important; }
            /* barra de progreso */
            .custom-progress-container {
                width: 100%; background-color: #e8ecf4; border: 2px solid #1e40af;
                border-radius: 8px; padding: 3px; height: 32px; overflow: hidden; margin: 15px 0;
            }
            .custom-progress-bar {
                height: 100%; border-radius: 4px;
                background-image: repeating-linear-gradient(-45deg, #1e40af, #1e40af 12px, #e8ecf4 12px, #e8ecf4 18px);
                transition: width 0.2s ease-in-out;
            }
            /* header */
            .header-oficina-virtual {
                background-color: #ffffff !important;
                padding: 15px 30px; border-radius: 10px;
                box-shadow: 0px 2px 8px rgba(0,0,0,0.05);
                margin-bottom: 25px;
                display: flex; justify-content: space-between; align-items: center;
            }
            .header-title { color: #0b1d3a !important; font-size: 22px; font-weight: bold; margin: 0; }
            .user-tag {
                font-size: 13.5px; color: #0b1d3a !important;
                background-color: #eff6ff !important; padding: 8px 16px;
                border-radius: 20px; border: 1px solid #bfdbfe !important; font-weight: 500;
                white-space: nowrap;
            }
            .admin-badge {
                font-size: 11px; color: #ffffff !important;
                background-color: #dc2626 !important; padding: 3px 10px;
                border-radius: 12px; font-weight: 700; margin-left: 8px;
                vertical-align: middle; letter-spacing: 0.5px;
            }
            /* cards menú */
            .card-menu-principal {
                background-color: #ffffff !important;
                padding: 25px; border-radius: 12px;
                box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
                border-left: 5px solid #0b1d3a;
                margin-bottom: 20px;
            }
            .card-menu-principal h4 { color: #0b1d3a !important; font-size: 16px !important; margin: 0 0 8px 0 !important; font-weight: 700 !important; }
            .card-menu-principal p  { color: #374151 !important; font-size: 14px !important; margin: 0 !important; }
            .card-menu-admin {
                background-color: #fff5f5 !important;
                padding: 25px; border-radius: 12px;
                box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
                border-left: 5px solid #dc2626;
                margin-bottom: 20px;
            }
            .card-menu-admin h4 { color: #991b1b !important; font-size: 16px !important; margin: 0 0 8px 0 !important; font-weight: 700 !important; }
            .card-menu-admin p  { color: #374151 !important; font-size: 14px !important; margin: 0 !important; }
            /* panel admin */
            .admin-section-card {
                background-color: #ffffff !important;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0px 3px 10px rgba(0,0,0,0.07);
                border-top: 4px solid #dc2626;
                margin-bottom: 24px;
            }
            .admin-section-card h4 { color: #991b1b !important; font-size: 15px !important; font-weight: 700 !important; margin-bottom: 16px !important; }
            /* tabla usuarios */
            .tabla-usuarios {
                width: 100%; border-collapse: collapse; margin-top: 8px;
                background-color: #f8f9fb !important;
                border-radius: 8px; overflow: hidden;
            }
            .tabla-usuarios th {
                background-color: #0b1d3a !important; color: #ffffff !important;
                padding: 10px 14px; font-size: 13px; text-align: left;
            }
            .tabla-usuarios td {
                padding: 9px 14px; font-size: 13px; color: #1a1a2e !important;
                border-bottom: 1px solid #e5e7eb; background-color: #f8f9fb !important;
            }
            .tabla-usuarios tr:last-child td { border-bottom: none; }
            /* footer */
            .footer-institucional {
                margin-top: 60px; padding: 25px 0;
                border-top: 1px solid #e5e7eb;
                text-align: center; font-size: 13px; color: #4b5563 !important;
            }
            .footer-links { display: flex; justify-content: center; gap: 30px; margin-bottom: 10px; flex-wrap: wrap; }
            .footer-links a { color: #0b1d3a !important; text-decoration: none; font-weight: 500; }
            /* responsive */
            @media (max-width: 768px) {
                .header-oficina-virtual { flex-direction: column !important; gap: 8px !important; text-align: center !important; padding: 12px 15px !important; }
                .header-title { font-size: 16px !important; }
                .user-tag { font-size: 12px !important; padding: 6px 12px !important; }
                .card-menu-principal, .card-menu-admin { padding: 15px !important; }
            }
        </style>""", unsafe_allow_html=True)

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown('<div class="sidebar-text-header">⚙️ Opciones del Sistema</div>', unsafe_allow_html=True)
        st.markdown("<p style='color:#ffffff; font-size:11px; text-transform:uppercase; font-weight:bold; margin-left:5px; margin-bottom:12px;'>Navegación del Portal</p>", unsafe_allow_html=True)
        if st.sidebar.button("🏠 Menú Principal / Inicio", use_container_width=True):
            st.session_state["seccion_activa"] = "Inicio"; st.rerun()
        st.sidebar.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        if st.sidebar.button("🚀 Panel de Extracción Masiva", use_container_width=True):
            st.session_state["seccion_activa"] = "Extraccion"; st.rerun()
        st.sidebar.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        if st.sidebar.button("📋 Historiales y Reportes", use_container_width=True):
            st.session_state["seccion_activa"] = "Historiales"; st.rerun()

        # Botón admin solo visible para admin
        if es_admin:
            st.sidebar.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
            st.sidebar.markdown("<p style='color:#fca5a5; font-size:11px; text-transform:uppercase; font-weight:bold; margin-left:5px; margin-bottom:8px;'>Administración</p>", unsafe_allow_html=True)
            if st.sidebar.button("👥 Panel de Administración", use_container_width=True):
                st.session_state["seccion_activa"] = "Admin"; st.rerun()

        st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)
        if st.sidebar.button("🚪 Cerrar Sesión Segura", use_container_width=True):
            st.session_state["autenticado"] = False; st.rerun()

    # --- ENCABEZADO ---
    usuario_sesion = st.session_state["usuario_activo_real"]
    badge_admin = '<span class="admin-badge">ADMIN</span>' if es_admin else ""
    st.markdown(f"""
        <div class="header-oficina-virtual">
            <div class="header-title">Oficina Virtual de Dispositivos Médicos</div>
            <div class="user-tag">👤 <b>Usuario activo:</b> {usuario_sesion}{badge_admin}</div>
        </div>""", unsafe_allow_html=True)

    # ==========================================================
    # VISTA 1: MENÚ PRINCIPAL
    # ==========================================================
    if st.session_state["seccion_activa"] == "Inicio":
        st.markdown("<h3 style='color:#0b1d3a;'>Menú Principal</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#374151;'>Seleccione una de las siguientes opciones:</p>", unsafe_allow_html=True)

        st.markdown("""
            <div class="card-menu-principal">
                <h4>1. Módulo Automatizado de Extracción Masiva</h4>
                <p>Carga masiva de archivos Excel para cruce con AccessGUDID (FDA), identificación de códigos GMDN y agencias emisoras.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("🚀 Ingresar al Módulo de Extracción", key="btn_ir_ext", use_container_width=True):
            st.session_state["seccion_activa"] = "Extraccion"; st.rerun()

        st.markdown("""
            <div class="card-menu-principal" style="border-left-color:#0369a1;">
                <h4>2. Consulta de Historiales y Reportes</h4>
                <p>Consulta el historial de referencias buscadas por usuario, con fecha y cantidad de resultados obtenidos.</p>
            </div>""", unsafe_allow_html=True)
        if st.button("📋 Ver Historiales y Reportes", key="btn_ir_hist", use_container_width=True):
            st.session_state["seccion_activa"] = "Historiales"; st.rerun()

        if es_admin:
            st.markdown("""
                <div class="card-menu-admin">
                    <h4>🔐 3. Panel de Administración (Solo Admin)</h4>
                    <p>Gestión completa de usuarios: agregar, eliminar, cambiar contraseñas y visualizar lista de accesos.</p>
                </div>""", unsafe_allow_html=True)
            if st.button("👥 Ir al Panel de Administración", key="btn_ir_admin", use_container_width=True):
                st.session_state["seccion_activa"] = "Admin"; st.rerun()

    # ==========================================================
    # VISTA 2: PANEL DE EXTRACCIÓN MASIVA
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Extraccion":
        st.markdown("<h3 style='color:#0b1d3a;'>🚀 Extracción Automatizada AccessGUDID (FDA)</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#374151;'>Suba su archivo, aplique filtros opcionales e inicie la consulta.</p>", unsafe_allow_html=True)

        col_izq, col_der = st.columns([1, 2])

        with col_izq:
            st.info("⚙ Configuración de Parámetros")
            archivo_cargado     = st.file_uploader("Sube tu archivo de Excel (.xlsx)", type=["xlsx"])
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
                    st.error(f"Error al abrir el archivo de Excel: {e}")
                    st.stop()

                st.success(f"📋 Referencias encontradas: {total_refs}")
                texto_estado     = st.empty()
                barra_custom     = st.empty()
                tabla_viva       = st.empty()
                lista_resultados = []
                session          = requests.Session()

                def actualizar_barra(pct):
                    barra_custom.markdown(f"""
                        <div class="custom-progress-container">
                            <div class="custom-progress-bar" style="width:{pct}%;"></div>
                        </div>""", unsafe_allow_html=True)

                for idx, ref in enumerate(referencias_totales):
                    base_pct = (idx / total_refs) * 100
                    paso_pct = (1 / total_refs) * 100

                    texto_estado.info(f"⏳ Fila {idx+1} de {total_refs} | 🔍 Buscando: {ref}...")
                    actualizar_barra(int(base_pct + paso_pct * 0.33))

                    url_busqueda = f"https://accessgudid.nlm.nih.gov/devices/search?query={urllib.parse.quote(ref)}"

                    try:
                        response = session.get(url_busqueda, headers=headers, timeout=15)
                        actualizar_barra(int(base_pct + paso_pct * 0.66))
                        time.sleep(0.4)

                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, 'html.parser')
                            enlaces = list(dict.fromkeys([
                                a['href'] for a in soup.find_all('a', href=True)
                                if '/devices/' in a['href'] and 'search' not in a['href']
                            ]))
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

                                    if company_name_filtro and company_name_filtro.upper() not in company.upper():
                                        continue

                                    gmdn_code = "No encontrado"
                                    for p in texto.replace(':',' ').replace('(',' ').replace(')',' ').split():
                                        if p.isdigit() and len(p) == 5:
                                            gmdn_code = p; break

                                    gmdn_def, gmdn_status = "No encontrado", "No encontrado"
                                    for i, l in enumerate(lineas):
                                        if "GMDN Term Definition" in l:
                                            candidatos = [
                                                x.replace("[?]","").strip() for x in lineas[i:]
                                                if x.replace("[?]","").strip()
                                                and not any(h in x for h in ["GMDN Term Code","GMDN Term Name","GMDN Term Definition","GMDN Term Status","Implantable?"])
                                                and not (x.strip().isdigit() and len(x.strip())==5)
                                            ]
                                            if len(candidatos) >= 2:
                                                gmdn_def, gmdn_status = candidatos[1], candidatos[2] if len(candidatos)>2 else candidatos[1]
                                            elif len(candidatos) == 1:
                                                gmdn_def = candidatos[0]
                                            break

                                    diccionario_estados = {"active":"Activo","obsolete":"Obsoleto","no encontrado":"No encontrado"}
                                    gmdn_status = diccionario_estados.get(gmdn_status.lower(), gmdn_status)

                                    if gmdn_def and gmdn_def.lower() != "no encontrado":
                                        try:
                                            texto_url = gmdn_def.replace('"','').replace("'","")
                                            partes, pedazos_trad = [], []
                                            palabras, parte_actual, cuenta = texto_url.split(), [], 0
                                            for palabra in palabras:
                                                if cuenta + len(palabra) + 1 > 450:
                                                    partes.append(" ".join(parte_actual)); parte_actual=[palabra]; cuenta=len(palabra)
                                                else:
                                                    parte_actual.append(palabra); cuenta += len(palabra)+1
                                            if parte_actual: partes.append(" ".join(parte_actual))
                                            for parte in partes:
                                                r_t = requests.get(f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(parte)}&langpair=en|es", timeout=5)
                                                if r_t.status_code == 200:
                                                    trad = r_t.json().get("responseData",{}).get("translatedText","")
                                                    pedazos_trad.append(trad if trad and "MYMEMORY" not in trad else parte)
                                                else:
                                                    pedazos_trad.append(parte)
                                            gmdn_def = " ".join(pedazos_trad).strip()
                                        except:
                                            pass

                                    issuing = "No encontrado"
                                    for i, l in enumerate(lineas):
                                        if "Issuing Agency" in l:
                                            issuing = lineas[i+1] if l.replace(":","").strip() == "Issuing Agency" and i+1 < len(lineas) else l.replace("Issuing Agency","").replace(":","").strip()
                                            break
                                    issuing = " ".join(issuing.split()).strip() or "No encontrado"

                                    coincidencias.append({
                                        "Referencia_Original": ref,
                                        "Primary_DI_Number":   href.split('/')[-1].strip(),
                                        "Nombre_Empresa_FDA":  company,
                                        "Codigo_GMDN":         gmdn_code,
                                        "Definicion_GMDN":     " ".join(str(gmdn_def).split()).strip(),
                                        "Estado_GMDN":         " ".join(str(gmdn_status).split()).strip(),
                                        "Issuing_Agency":      issuing
                                    })
                                except:
                                    continue

                            if coincidencias:
                                lista_resultados.extend(coincidencias)
                            else:
                                lista_resultados.append({"Referencia_Original":ref,"Primary_DI_Number":"Filtrado","Nombre_Empresa_FDA":"No coincide","Codigo_GMDN":"Filtrado","Definicion_GMDN":"Filtrado","Estado_GMDN":"Filtrado","Issuing_Agency":"Filtrado"})

                        elif response.status_code == 429:
                            st.warning("⏳ Servidor saturado. Esperando 15 segundos..."); time.sleep(15)
                        else:
                            lista_resultados.append({"Referencia_Original":ref,"Primary_DI_Number":"No encontrado","Nombre_Empresa_FDA":"No encontrado","Codigo_GMDN":"No encontrado","Definicion_GMDN":"No encontrado","Estado_GMDN":"No encontrado","Issuing_Agency":"No encontrado"})

                    except Exception:
                        lista_resultados.append({"Referencia_Original":ref,"Primary_DI_Number":"Error de Red","Nombre_Empresa_FDA":"Error","Codigo_GMDN":"Error","Definicion_GMDN":"Error","Estado_GMDN":"Error","Issuing_Agency":"Error"})

                    actualizar_barra(int((idx+1)/total_refs*100))
                    tabla_viva.dataframe(pd.DataFrame(lista_resultados), use_container_width=True)
                    time.sleep(0.8)

                texto_estado.empty()
                barra_custom.empty()
                st.success("✨ ¡Extracción completada al 100%!")
                registrar_log(st.session_state["usuario_activo_real"], f"Extracción masiva ({total_refs} refs)", len(lista_resultados))

                df_final = pd.DataFrame(lista_resultados)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False)

                st.download_button(
                    label="📥 Descargar Excel con Resultados",
                    data=output.getvalue(),
                    file_name="resultados_fda.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            elif not archivo_cargado:
                st.info("👈 Cargue un archivo en el panel izquierdo para activar la monitorización.")

    # ==========================================================
    # VISTA 3: HISTORIALES Y REPORTES
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Historiales":
        st.markdown("<h3 style='color:#0b1d3a;'>📋 Historiales y Reportes</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#374151;'>Consulta el registro de búsquedas realizadas en la plataforma.</p>", unsafe_allow_html=True)

        with st.spinner("Cargando historial..."):
            df_logs = obtener_logs()

        if df_logs.empty:
            st.info("No hay registros de búsquedas aún.")
        else:
            col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
            with col_f1:
                usuarios_disponibles = ["Todos"] + sorted(df_logs["Usuario"].dropna().unique().tolist())
                filtro_usuario = st.selectbox("👤 Filtrar por usuario", usuarios_disponibles)
            with col_f2:
                fecha_min = df_logs["Fecha"].min().date() if not df_logs["Fecha"].isna().all() else datetime.date.today()
                fecha_max = df_logs["Fecha"].max().date() if not df_logs["Fecha"].isna().all() else datetime.date.today()
                filtro_fecha_ini = st.date_input("📅 Desde", value=fecha_min)
            with col_f3:
                filtro_fecha_fin = st.date_input("📅 Hasta", value=fecha_max)

            df_filtrado = df_logs.copy()
            if filtro_usuario != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Usuario"] == filtro_usuario]
            df_filtrado = df_filtrado[
                (df_filtrado["Fecha"].dt.date >= filtro_fecha_ini) &
                (df_filtrado["Fecha"].dt.date <= filtro_fecha_fin)
            ]

            st.markdown("<br>", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("📊 Total de búsquedas", len(df_filtrado))
            m2.metric("👥 Usuarios activos", df_filtrado["Usuario"].nunique())
            total_resultados = pd.to_numeric(df_filtrado["Resultados"], errors="coerce").sum()
            m3.metric("🔬 Referencias procesadas", int(total_resultados) if not pd.isna(total_resultados) else 0)
            st.markdown("<br>", unsafe_allow_html=True)

            df_mostrar = df_filtrado.copy()
            df_mostrar["Fecha"] = df_mostrar["Fecha"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

            output_logs = io.BytesIO()
            with pd.ExcelWriter(output_logs, engine='openpyxl') as writer:
                df_mostrar.to_excel(writer, index=False)

            st.download_button(
                label="📥 Descargar Historial en Excel",
                data=output_logs.getvalue(),
                file_name=f"historial_busquedas_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # ==========================================================
    # VISTA 4: PANEL DE ADMINISTRACIÓN (solo admin)
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Admin":
        if not es_admin:
            st.error("🔒 Acceso denegado. Solo el administrador puede ver esta sección.")
            st.stop()

        st.markdown("<h3 style='color:#991b1b;'>👥 Panel de Administración de Usuarios</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color:#374151;'>Gestión completa de cuentas de acceso a la plataforma.</p>", unsafe_allow_html=True)

        # ── FILA SUPERIOR: Lista de usuarios + Agregar usuario ──
        col_lista, col_agregar = st.columns([1.4, 1])

        # --- LISTA DE USUARIOS ---
        with col_lista:
            st.markdown('<div class="admin-section-card">', unsafe_allow_html=True)
            st.markdown("<h4>📋 Lista de Usuarios Registrados</h4>", unsafe_allow_html=True)

            with st.spinner("Cargando usuarios..."):
                datos_usuarios, _ = obtener_usuarios()

            if datos_usuarios:
                filas_html = ""
                for u in datos_usuarios:
                    nombre = str(u.get('usuario', '')).strip()
                    es_adm = "🔴 Admin" if nombre.lower() == ADMIN_USER.lower() else "🟢 Usuario"
                    filas_html += f"<tr><td>{nombre}</td><td>{es_adm}</td></tr>"

                st.markdown(f"""
                    <table class="tabla-usuarios">
                        <thead><tr><th>Usuario</th><th>Rol</th></tr></thead>
                        <tbody>{filas_html}</tbody>
                    </table>""", unsafe_allow_html=True)
                st.markdown(f"<p style='color:#6b7280; font-size:12px; margin-top:10px;'>Total: {len(datos_usuarios)} usuario(s) registrado(s)</p>", unsafe_allow_html=True)
            else:
                st.info("No se encontraron usuarios.")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- AGREGAR USUARIO ---
        with col_agregar:
            st.markdown('<div class="admin-section-card">', unsafe_allow_html=True)
            st.markdown("<h4>➕ Agregar Nuevo Usuario</h4>", unsafe_allow_html=True)

            nuevo_usr = st.text_input("Nombre de usuario", key="nuevo_usr", placeholder="Ej: usuario_nuevo")
            nuevo_pwd = st.text_input("Contraseña", type="password", key="nuevo_pwd", placeholder="Contraseña segura")
            nuevo_pwd2 = st.text_input("Confirmar contraseña", type="password", key="nuevo_pwd2", placeholder="Repita la contraseña")

            if st.button("✅ Crear Usuario", key="btn_crear", use_container_width=True):
                if not nuevo_usr or not nuevo_pwd:
                    st.warning("Complete todos los campos.")
                elif nuevo_pwd != nuevo_pwd2:
                    st.error("Las contraseñas no coinciden.")
                elif len(nuevo_pwd) < 4:
                    st.warning("La contraseña debe tener al menos 4 caracteres.")
                else:
                    ok, msg = agregar_usuario(nuevo_usr, nuevo_pwd)
                    if ok:
                        st.success(f"✔ {msg}")
                        registrar_log(usuario_sesion, f"[ADMIN] Creó usuario: {nuevo_usr}", "-")
                        time.sleep(0.5); st.rerun()
                    else:
                        st.error(f"❌ {msg}")
            st.markdown('</div>', unsafe_allow_html=True)

        # ── FILA INFERIOR: Eliminar usuario + Cambiar contraseña ──
        col_elim, col_pwd = st.columns(2)

        # --- ELIMINAR USUARIO ---
        with col_elim:
            st.markdown('<div class="admin-section-card">', unsafe_allow_html=True)
            st.markdown("<h4>🗑️ Eliminar Usuario</h4>", unsafe_allow_html=True)

            nombres_disponibles = [
                str(u.get('usuario', '')).strip()
                for u in datos_usuarios
                if str(u.get('usuario', '')).strip().lower() != ADMIN_USER.lower()
            ] if datos_usuarios else []

            if nombres_disponibles:
                usuario_a_eliminar = st.selectbox("Seleccionar usuario a eliminar", nombres_disponibles, key="sel_eliminar")
                confirmar_elim = st.checkbox(f"Confirmo que deseo eliminar a **{usuario_a_eliminar}**", key="chk_elim")
                if st.button("🗑️ Eliminar Usuario", key="btn_eliminar", use_container_width=True):
                    if not confirmar_elim:
                        st.warning("Marque la casilla de confirmación antes de eliminar.")
                    else:
                        ok, msg = eliminar_usuario(usuario_a_eliminar)
                        if ok:
                            st.success(f"✔ {msg}")
                            registrar_log(usuario_sesion, f"[ADMIN] Eliminó usuario: {usuario_a_eliminar}", "-")
                            time.sleep(0.5); st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            else:
                st.info("No hay usuarios disponibles para eliminar.")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- CAMBIAR CONTRASEÑA ---
        with col_pwd:
            st.markdown('<div class="admin-section-card">', unsafe_allow_html=True)
            st.markdown("<h4>🔑 Cambiar Contraseña de Usuario</h4>", unsafe_allow_html=True)

            todos_usuarios = [
                str(u.get('usuario', '')).strip()
                for u in datos_usuarios
            ] if datos_usuarios else []

            if todos_usuarios:
                usuario_cambio_pwd = st.selectbox("Seleccionar usuario", todos_usuarios, key="sel_pwd")
                nueva_pwd_1 = st.text_input("Nueva contraseña", type="password", key="npwd1", placeholder="Nueva contraseña")
                nueva_pwd_2 = st.text_input("Confirmar nueva contraseña", type="password", key="npwd2", placeholder="Repita la contraseña")

                if st.button("🔑 Actualizar Contraseña", key="btn_cambiar_pwd", use_container_width=True):
                    if not nueva_pwd_1:
                        st.warning("Ingrese la nueva contraseña.")
                    elif nueva_pwd_1 != nueva_pwd_2:
                        st.error("Las contraseñas no coinciden.")
                    elif len(nueva_pwd_1) < 4:
                        st.warning("La contraseña debe tener al menos 4 caracteres.")
                    else:
                        ok, msg = cambiar_password(usuario_cambio_pwd, nueva_pwd_1)
                        if ok:
                            st.success(f"✔ {msg}")
                            registrar_log(usuario_sesion, f"[ADMIN] Cambió contraseña de: {usuario_cambio_pwd}", "-")
                            time.sleep(0.5); st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            else:
                st.info("No hay usuarios disponibles.")
            st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================
    # PIE DE PÁGINA
    # ==========================================================
    st.markdown("""
        <div class="footer-institucional">
            <div class="footer-links">
                <a href="#">Políticas de privacidad</a>
                <a href="#">Tratamiento de datos</a>
                <a href="#">Mesa de Ayuda</a>
            </div>
            <div>v 1.1.26 © Invima 2026. Todos los derechos reservados.</div>
        </div>""", unsafe_allow_html=True)
