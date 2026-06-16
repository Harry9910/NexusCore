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

# 1. ESTO DEBE IR AL PRINCIPIO
@st.cache_resource
def conectar_google():
    creds = Credentials.from_service_account_info(st.secrets["gcp"])
    return gspread.authorize(creds)

# 2. Creamos el cliente una sola vez
client = conectar_google()

# 1. Configuración de conexión (una sola vez)
@st.cache_resource
def conectar_google():
    creds = Credentials.from_service_account_info(st.secrets["gcp"])
    return gspread.authorize(creds)

client = conectar_google()

# 2. ÚNICA DEFINICIÓN DE LA FUNCIÓN (Sin duplicados, sin diagnóstico)
def validar_usuario(usuario, password):
    try:
        sheet_users = client.open("Usuarios_FDA").worksheet("Usuarios")
        datos_usuarios = sheet_users.get_all_records()
        
        for fila in datos_usuarios:
            usuario_db = str(fila.get('usuario', '')).strip()
            pass_db = str(fila.get('contraseña', '')).strip()
            
            if usuario_db == usuario.strip() and pass_db == password.strip():
                return True
        return False
    except Exception as e:
        st.error(f"Error al conectar con la hoja: {e}")
        return False

# 3. AQUÍ VA EL RESTO DE TU LÓGICA (Formulario, botones, etc.)
# Ejemplo de donde llamas a la función:
# if st.button("Ingresar"):
#     if validar_usuario(usuario, contraseña):
#         ...

# --- CONFIGURACIÓN DE CONEXIÓN A GOOGLE SHEETS ---
try:
    creds_dict = dict(st.secrets["gcp"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # Abre tu hoja por nombre
    sheet = client.open("Usuarios_FDA").worksheet("Logs")
except Exception as e:
    st.error(f"Error en la conexión con Google: {e}")


from oauth2client.service_account import ServiceAccountCredentials # ESTA LÍNEA ES LA QUE FALTA

# Configuración de credenciales desde Secrets de Streamlit (para la nube)
creds_dict = dict(st.secrets["gcp"])
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

def registrar_log(usuario, busqueda, resultados_obtenidos):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Crear un DataFrame con la nueva fila
    nueva_entrada = pd.DataFrame([{
        "Fecha/Hora": timestamp,
        "Usuario": usuario,
        "Consulta": busqueda,
        "Registros Encontrados": len(resultados_obtenidos)
    }])
    
    try:
        # Usamos 'append' si tu versión de la librería lo permite, 
        # o leemos y concatenamos como estabas haciendo, 
        # pero asegurándonos de que la conexión esté bien instanciada.
        
        # FORMA SEGURA (Leer, Concat, Sobreescribir)
        df_existente = conn.read(worksheet="Logs", usecols=[0,1,2,3]) # Ajusta las columnas
        df_actualizado = pd.concat([df_existente, nueva_entrada], ignore_index=True)
        
        # Si .update() falla, usa el método write:
        conn.write(worksheet="Logs", data=df_actualizado) 
        
    except Exception as e:
        st.error(f"Error al guardar log: {e}")

# --- NUEVAS FUNCIONES ---

@st.cache_data(ttl=3600)
def realizar_busqueda_fda(query):
    # Aquí mueves la lógica que ya tienes para hacer el request y el parsing
    url = f"https://accessgudid.nlm.nih.gov/results?query={urllib.parse.quote(query)}"
    # ... tu código actual de request y beautifulsoup ...
    return data_frame_resultados

def registrar_log(usuario, busqueda, resultados_obtenidos):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nueva_entrada = pd.DataFrame([{
        "Fecha/Hora": timestamp,
        "Usuario": usuario,
        "Consulta": busqueda,
        "Registros Encontrados": len(resultados_obtenidos)
    }])
    
    # Obtener los datos existentes y añadir la fila nueva
    try:
        df_existente = conn.read(worksheet="Logs")
        df_actualizado = pd.concat([df_existente, nueva_entrada], ignore_index=True)
        conn.update(worksheet="Logs", data=df_actualizado)
    except Exception as e:
        st.error(f"Error al guardar log en Google Sheets: {e}")





# Configuración de la página web con layout expandido
st.set_page_config(page_title="Extractor AccessGUDID FDA", page_icon="🔬", layout="wide")

# ==========================================================
# CONFIGURACIÓN DE CREDENCIALES Y MEMORIA DE USUARIO
# ==========================================================


if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if "usuario_guardado" not in st.session_state:
    st.session_state["usuario_guardado"] = ""

if "usuario_activo_real" not in st.session_state:
    st.session_state["usuario_activo_real"] = ""

if "seccion_activa" not in st.session_state:
    st.session_state["seccion_activa"] = "Inicio"

# ==========================================================
# FUNCIÓN TRUCO: CARGAR IMÁGENES LOCALES EN HTML (BASE64)
# ==========================================================

# --- Lógica de Login ---
if not st.session_state["autenticado"]:
    # Aquí está tu código actual del formulario de login
    # Asegúrate de que al hacer clic en el botón, hagas: st.session_state["autenticado"] = True
    pass 
else:
    # --- AQUÍ VA TU NUEVA LÓGICA DE BÚSQUEDA ---
    # Al estar dentro del 'else', solo se mostrará si el login fue exitoso
    
    st.title("Bienvenido al Extractor FDA")
    busqueda_input = st.text_input("Ingrese su criterio de búsqueda:")
    
    if st.button("Buscar"):
        with st.spinner("Consultando AccessGUDID..."):
            try:
                # 1. Llamada a la función con caché
                resultados = realizar_busqueda_fda(busqueda_input)
                
                # 2. Mostrar los resultados
                st.dataframe(resultados)
                
                # 3. Registrar el log de auditoría
                registrar_log(st.session_state["usuario_activo_real"], busqueda_input, resultados)
            
            except Exception as e:
                st.error(f"Error al conectar con la FDA: {e}")


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

# Cargar los logos locales procesados
b64_gudid = buscar_logo("logo_gudid")
b64_invima = buscar_logo("logo_invima")
b64_eudamed = buscar_logo("logo_eudamed")
b64_gmdn = buscar_logo("logo_gmdn")
b64_fda = buscar_logo("logo_fda")

# ==========================================================
# PANTALLA DE LOGIN REPLICADA LITERAL
# ==========================================================
if not st.session_state["autenticado"]:
    st.markdown(
        """
        <style>
            .stApp {
                background-image: linear-gradient(rgba(15, 32, 67, 0.65), rgba(15, 32, 67, 0.85)), 
                                  url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070');
                background-size: cover;
                background-position: center;
                background-attachment: fixed;
            }
            header, footer, [data-testid="stSidebar"], #MainMenu { 
                visibility: hidden !important; 
                display: none !important;
            }
            [data-testid="stTextInput"] json, 
            [data-testid="stTextInput"] div[data-testid="stWidgetInstructions"] p { display: none !important; visibility: hidden !important; height: 0px !important; }
            .st-emotion-cache-1wivp7d, [data-testid="InputInstructions"] { display: none !important; visibility: hidden !important; }
            div[data-testid="stForm"] {
                background-color: rgba(255, 255, 255, 0.98) !important;
                border: none !important;
                border-radius: 16px !important;
                padding: 45px 40px !important;
                box-shadow: 0px 12px 40px rgba(0, 0, 0, 0.35) !important;
                max-width: 540px; margin: 0 auto;
            }
            .contenedor-logos-principales { display: flex; flex-direction: row; justify-content: center; align-items: center; width: 100%; gap: 25px; margin-bottom: 30px; height: 75px; overflow: hidden; }
            .logo-header-invima { height: 65px !important; width: auto !important; object-fit: contain; }
            .logo-header-fda { height: 50px !important; width: auto !important; object-fit: contain; }
            .barra-separadora-vertical-azul { width: 3px; height: 60px; background-color: #00b4d8; margin: 0 10px; }
            .login-title { color: #0f2043 !important; font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 6px; font-family: 'Segoe UI', sans-serif; }
            .login-desc { color: #555555 !important; font-size: 14px; text-align: center; margin-bottom: 25px; }
            div[data-testid="stForm"] button { background-color: #000c66 !important; color: white !important; width: 120px; border-radius: 6px; border: none; padding: 10px 20px; font-size: 16px; font-weight: 500; margin-top: 5px; transition: 0.3s ease; }
            div[data-testid="stForm"] button:hover { background-color: #000533 !important; box-shadow: 0px 4px 10px rgba(0,0,0,0.2); }
            .contenedor-soporte-inferior { border-top: 1px solid #eef0f4; margin-top: 35px; padding-top: 25px; width: 100%; }
            .titulo-soporte { font-size: 12.5px; font-weight: 600; color: #6c757d !important; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.5px; }
            .fila-logos-soporte { display: flex; flex-direction: row; justify-content: space-between; align-items: center; width: 100%; }
            .logo-gudid-libre { width: 130px !important; height: auto !important; object-fit: contain; }
            .logo-eudamed-libre { width: 120px !important; height: auto !important; object-fit: contain; }
            .logo-gmdn-libre { width: 135px !important; height: auto !important; object-fit: contain; }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1.2, 1]) 

    with col_centro:
        with st.form("formulario_login", clear_on_submit=False):
            html_cabecera = '<div class="contenedor-logos-principales">'
            if b64_invima: html_cabecera += f'<img class="logo-header-invima" src="data:image/png;base64,{b64_invima}">'
            html_cabecera += '<div class="barra-separadora-vertical-azul"></div>'
            if b64_fda: html_cabecera += f'<img class="logo-header-fda" src="data:image/png;base64,{b64_fda}">'
            html_cabecera += '</div>'
            st.markdown(html_cabecera, unsafe_allow_html=True)
            
            st.markdown("<div class='login-title'>Plataforma de Extracción</div>", unsafe_allow_html=True)
            st.markdown("<div class='login-desc'>Gestión Automatizada de Dispositivos Médicos</div>", unsafe_allow_html=True)
            
            usuario = st.text_input("Nombre de usuario", value=st.session_state["usuario_guardado"], placeholder="Introduzca su usuario").strip()
            contraseña = st.text_input("Contraseña", type="password", placeholder="Introduzca su contraseña")
            recordar = st.checkbox("Recordar mi usuario en este equipo", value=(st.session_state["usuario_guardado"] != ""))
            boton_ingresar = st.form_submit_button("Acceder")
            
            html_soporte = '<div class="contenedor-soporte-inferior">'
            html_soporte += '<div class="titulo-soporte">Bases de datos vinculadas:</div>'
            html_soporte += '<div class="fila-logos-soporte">'
            if b64_gudid: html_soporte += f'<img class="logo-gudid-libre" src="data:image/png;base64,{b64_gudid}">'
            if b64_eudamed: html_soporte += f'<img class="logo-eudamed-libre" src="data:image/png;base64,{b64_eudamed}">'
            if b64_gmdn: html_soporte += f'<img class="logo-gmdn-libre" src="data:image/png;base64,{b64_gmdn}">'
            html_soporte += '</div>'
            html_soporte += '</div>'
            st.markdown(html_soporte, unsafe_allow_html=True)
            
            if boton_ingresar:
                # --- ESTO ES LO QUE DEBES CAMBIAR ---
                # ESTA ERA TU LÓGICA ANTIGUA (BORRA LA COMPARACIÓN VIEJA)
                # if usuario == USUARIO_CORRECTO and contraseña == CONTRASEÑA_CORRECTA:
    

# ==========================================================
# INTERFAZ INTERNA: MONITOR CON CONTENEDOR SEGMENTADO CUSTOM
# ==========================================================
else:
    st.markdown(
        """
        <style>
            .stApp {
                background-image: none !important;
                background-color: #f4f6f9 !important;
            }
            
            header, footer, #MainMenu {
                visibility: hidden !important;
                display: none !important;
            }
            
            [data-testid="stSidebar"] {
                visibility: visible !important;
                background-color: #0b1d3a !important; 
                border-right: 1px solid #061122 !important;
            }
            
            .sidebar-text-header {
                text-align: center;
                padding: 15px 10px;
                margin-bottom: 20px;
                color: #ffffff !important;
                font-family: 'Segoe UI', sans-serif;
                font-size: 20px;
                font-weight: 700;
                letter-spacing: 0.5px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.15);
            }

            [data-testid="stSidebar"] button {
                background-color: #1a365d !important; 
                color: #ffffff !important; 
                font-weight: 600 !important;
                border: 1px solid #2a4d7c !important;
                border-radius: 6px !important;
                padding: 10px !important;
                transition: 0.2s;
            }
            [data-testid="stSidebar"] button:hover {
                background-color: #2a4d7c !important;
                border-color: #3b629b !important;
                box-shadow: 0px 4px 10px rgba(0,0,0,0.3) !important;
            }

            [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button {
                color: #ffffff !important;
                background-color: transparent !important;
                border: none !important;
            }

            .custom-progress-container {
                width: 100%;
                background-color: #ffffff;
                border: 2px solid #1e40af; 
                border-radius: 8px;
                padding: 3px;
                height: 32px;
                box-sizing: border-box;
                overflow: hidden;
                margin: 15px 0;
                box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
            }
            
            .custom-progress-bar {
                height: 100%;
                border-radius: 4px;
                background-image: repeating-linear-gradient(
                    -45deg,
                    #1e40af,
                    #1e40af 12px,
                    #ffffff 12px,
                    #ffffff 18px
                );
                transition: width 0.2s ease-in-out;
            }

            .header-oficina-virtual {
                background-color: #ffffff !important;
                padding: 15px 30px;
                border-radius: 10px;
                box-shadow: 0px 2px 8px rgba(0,0,0,0.05);
                margin-bottom: 25px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header-title { color: #0b1d3a !important; font-size: 22px; font-weight: bold; margin: 0; }
            .user-tag { font-size: 13.5px; color: #0b1d3a !important; background-color: #eff6ff !important; padding: 8px 16px; border-radius: 20px; border: 1px solid #bfdbfe !important; font-weight: 500; }
            .menu-principal-titulo-seccion { color: #0b1d3a !important; font-weight: bold !important; }
            .menu-principal-desc-seccion { color: #374151 !important; }
            .card-menu-principal { background-color: #ffffff !important; padding: 25px; border-radius: 12px; box-shadow: 0px 4px 12px rgba(0,0,0,0.05); border-left: 5px solid #0b1d3a; margin-bottom: 20px; }
            [data-testid="stBlock"] p, [data-testid="stBlock"] label { color: #0b1d3a !important; font-weight: 500; }

            .footer-institucional { margin-top: 60px; padding: 25px 0; border-top: 1px solid #e5e7eb; text-align: center; font-size: 13px; color: #4b5563 !important; width: 100%; }
            .footer-links { display: flex; justify-content: center; gap: 30px; margin-bottom: 10px; }
            .footer-links a { color: #0b1d3a !important; text-decoration: none; font-weight: 500; }
            .footer-links a:hover { text-decoration: underline; }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ==========================================================
    # BARRA LATERAL (SIDEBAR DE TEXTO PREMIUM)
    # ==========================================================
    with st.sidebar:
        st.markdown('<div class="sidebar-text-header">⚙️ Opciones del Sistema</div>', unsafe_allow_html=True)
        st.sidebar.markdown("<p style='color:#ffffff; font-size:11px; text-transform:uppercase; font-weight:bold; margin-left:5px; margin-bottom:12px; letter-spacing:0.5px;'>Navegación del Portal</p>", unsafe_allow_html=True)
        
        if st.sidebar.button("🏠 Menú Principal / Inicio", use_container_width=True):
            st.session_state["seccion_activa"] = "Inicio"
            st.rerun()
            
        st.sidebar.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        if st.sidebar.button("🚀 Panel de Extracción Masiva", use_container_width=True):
            st.session_state["seccion_activa"] = "Extraccion"
            st.rerun()
            
        st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)
        if st.sidebar.button("🚪 Cerrar Sesión Segura", use_container_width=True):
            st.session_state["autenticado"] = False
            st.rerun()

    # ==========================================================
    # ENCABEZADO DINÁMICO
    # ==========================================================
    usuario_sesion = st.session_state["usuario_activo_real"]
    st.markdown(
        f"""
        <div class="header-oficina-virtual">
            <div class="header-title">Oficina Virtual de Dispositivos Médicos</div>
            <div class="user-tag">👤 <b>Usuario activo:</b> {usuario_sesion}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ==========================================================
    # VISTA 1: MENÚ PRINCIPAL
    # ==========================================================
    if st.session_state["seccion_activa"] == "Inicio":
        st.markdown("<h3 class='menu-principal-titulo-seccion'>Menú Principal</h3>", unsafe_allow_html=True)
        st.markdown("<p class='menu-principal-desc-seccion'>Seleccione una de las siguientes opciones del sistema para iniciar la gestión:</p>", unsafe_allow_html=True)
        
        with st.container():
            st.markdown(
                """
                <div class="card-menu-principal">
                    <h4 style="margin:0 0 8px 0; color:#0b1d3a !important;">1. Módulo Automatizado de Extracción Masiva</h4>
                    <p style="margin:0; color:#374151 !important; font-size:14px;">Carga masiva de archivos de Excel para el cruce de referencias contra la base de datos de AccessGUDID de la FDA, identificación de códigos GMDN y agencias emisoras.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Ingresar al Módulo de Extracción", key="btn_ir_ext"):
                st.session_state["seccion_activa"] = "Extraccion"
                st.rerun()

        st.markdown(
            """
            <div class="card-menu-principal" style="border-left-color: #6b7280; opacity: 0.65;">
                <h4 style="margin:0 0 8px 0; color:#4b5563 !important;">2. Consulta de Historiales y Reportes Anteriores</h4>
                <p style="margin:0; color:#4b5563 !important; font-size:14px;">Módulo de auditoría para la revisión de bases de datos generadas en consultas previas (Próximamente disponible).</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # ==========================================================
    # VISTA 2: PANEL DE EXTRACCIÓN MASIVA (LÓGICA ORIGINAL RESTAURADA)
    # ==========================================================
    elif st.session_state["seccion_activa"] == "Extraccion":
        st.markdown("<h3 class='menu-principal-titulo-seccion'>🚀 Extracción Automatizada AccessGUDID (FDA)</h3>", unsafe_allow_html=True)
        st.markdown("<p class='menu-principal-desc-seccion'>Suba su archivo, aplique filtros opcionales de validación corporativa e inicie la consulta del robot.</p>", unsafe_allow_html=True)
        
        col_izq, col_der = st.columns([1, 2])
        
        with col_izq:
            st.info("⚙ Configuración de Parámetros")
            archivo_cargado = st.file_uploader("Sube tu archivo de Excel (.xlsx)", type=["xlsx"])
            company_name_filtro = st.text_input("Filtrar por Company Name (Opcional)", "").strip()
            conectar_boton = st.button("🚀 Iniciar Extracción Masiva", disabled=(archivo_cargado is None), use_container_width=True)
            
        with col_der:
            st.warning("📊 Monitor de Procesamiento en Tiempo Real")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            if archivo_cargado and conectar_boton:
                try:
                    df = pd.read_excel(archivo_cargado, header=None, dtype=str)
                    df[0] = df[0].astype(str).str.strip()
                    referencias_totales = df[0].tolist()
                    total_refs = len(referencias_totales)
                except Exception as e:
                    st.error(f"Error al abrir el archivo de Excel: {e}")
                    st.stop()

                st.success(f"📋 Referencias encontradas en el archivo: {total_refs}")
                texto_estado = st.empty() 
                barra_custom_dinamica = st.empty() 
                tabla_viva = st.empty() 
                
                lista_resultados_finales = []
                session = requests.Session()

                def actualizar_barra_en_vivo(porcentaje_exacto):
                    html_barra = f"""
                    <div class="custom-progress-container">
                        <div class="custom-progress-bar" style="width: {porcentaje_exacto}%;"></div>
                    </div>
                    """
                    barra_custom_dinamica.markdown(html_barra, unsafe_allow_html=True)

                for idx, ref in enumerate(referencias_totales):
                    if not ref or ref == "nan" or ref == "":
                        continue
                    
                    base_progreso = (idx / total_refs) * 100
                    paso_por_fila = (1 / total_refs) * 100
                    
                    # Micro-Etapa 1: Buscando
                    porcentaje_etapa_1 = int(base_progreso + (paso_por_fila * 0.33))
                    texto_estado.info(f"⏳ Fila {idx + 1} de {total_refs} | 🔍 Buscando referencia en FDA: {ref}...")
                    actualizar_barra_en_vivo(porcentaje_etapa_1)
                    
                    query_codificada = urllib.parse.quote(ref)
                    url_busqueda = f"https://accessgudid.nlm.nih.gov/devices/search?query={query_codificada}"
                    
                    try:
                        response = session.get(url_busqueda, headers=headers, timeout=15)
                        
                        # Micro-Etapa 2: Descargando
                        porcentaje_etapa_2 = int(base_progreso + (paso_por_fila * 0.66))
                        texto_estado.info(f"⏳ Fila {idx + 1} de {total_refs} | 📄 Extrayendo estructura HTML y campos regulatorios...")
                        actualizar_barra_en_vivo(porcentaje_etapa_2)
                        time.sleep(0.4)

                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, 'html.parser')
                            enlaces_candidatos = [a['href'] for a in soup.find_all('a', href=True) if '/devices/' in a['href'] and not 'search' in a['href']]
                            enlaces_candidatos = list(dict.fromkeys(enlaces_candidatos))
                            
                            coincidencias_validas = []
                            
                            if enlaces_candidatos:
                                for href_candidato in enlaces_candidatos:
                                    url_verificacion = f"https://accessgudid.nlm.nih.gov{href_candidato}"
                                    try:
                                        res_verif = session.get(url_verificacion, headers=headers, timeout=15)
                                        if res_verif.status_code == 200:
                                            soup_verif = BeautifulSoup(res_verif.text, 'html.parser')
                                            texto_completo_pagina = soup_verif.get_text()
                                            
                                            # 🏢 LÓGICA DE EXTRACCIÓN DE COMPANY NAME
                                            company_name_detectado = "No encontrado"
                                            lineas_html = [l.strip() for l in texto_completo_pagina.split('\n') if l.strip()]
                                            for i, linea in enumerate(lineas_html):
                                                if "Company Name" in linea:
                                                    if linea.replace(":", "").strip() == "Company Name" and i + 1 < len(lineas_html):
                                                        company_name_detectado = lineas_html[i+1]
                                                    else:
                                                        company_name_detectado = linea.replace("Company Name", "").replace(":", "").strip()
                                                    break
                                            company_name_detectado = " ".join(company_name_detectado.split()).strip()
                                            if not company_name_detectado:
                                                company_name_detectado = "No encontrado"
                                            
                                            pasar_filtro = False
                                            if company_name_filtro:
                                                if company_name_filtro.upper() in company_name_detectado.upper():
                                                    pasar_filtro = True
                                            else:
                                                pasar_filtro = True
                                            
                                            if pasar_filtro:
                                                primary_di = href_candidato.split('/')[-1].strip()
                                                
                                                # 🔬 LÓGICA DE EXTRACCIÓN DE CÓDIGO GMDN NUMÉRICO
                                                gmdn_code = "No encontrado"
                                                if "GMDN" in texto_completo_pagina or "gmdn" in texto_completo_pagina.lower():
                                                    palabras = texto_completo_pagina.replace(':', ' ').replace('(', ' ').replace(')', ' ').split()
                                                    for p in palabras:
                                                        if p.isdigit() and len(p) == 5:
                                                            gmdn_code = p
                                                            break
                                                
                                                # ==========================================================
                                                # 🛠️ PASO 1: EXTRACCIÓN HORIZONTAL (TU CÓDIGO BUENO)
                                                # ==========================================================
                                                gmdn_definition = "No encontrado"
                                                gmdn_status = "No encontrado"
                                                
                                                # Buscamos la línea exacta donde inicia la tabla de encabezados GMDN
                                                for idx_linea, linea in enumerate(lineas_html):
                                                    if "GMDN Term Definition" in linea:
                                                        
                                                        # Creamos un sub-bloque con las líneas siguientes para analizar la fila de valores
                                                        lineas_siguientes = lineas_html[idx_linea:]
                                                        
                                                        # 1. Filtramos títulos o textos de la interfaz que queden en el medio
                                                        valores_candidatos = []
                                                        for l in lineas_siguientes:
                                                            texto_limpio = l.replace("[?]", "").strip()
                                                            # Saltamos los nombres de las columnas conocidas
                                                            if any(header in texto_limpio for header in ["GMDN Term Code", "GMDN Term Name", "GMDN Term Definition", "GMDN Term Status", "Implantable?"]):
                                                                continue
                                                            # Saltamos el código numérico (ya lo extraes arriba) para no duplicarlo
                                                            if texto_limpio.isdigit() and len(texto_limpio) == 5:
                                                                continue
                                                            if texto_limpio:
                                                                valores_candidatos.append(texto_limpio)
                                                        
                                                        # 2. Asignación por orden de aparición en la fila de datos
                                                        if len(valores_candidatos) >= 3:
                                                            gmdn_definition = valores_candidatos[1]
                                                            gmdn_status = valores_candidatos[2]
                                                        elif len(valores_candidatos) == 2:
                                                            gmdn_definition = valores_candidatos[0]
                                                            gmdn_status = valores_candidatos[1]
                                                        
                                                        break # Salimos del ciclo principal una vez procesada la tabla

                                                # Formateo y limpieza inicial estándar de textos
                                                gmdn_definition = " ".join(gmdn_definition.split()).strip()
                                                gmdn_status = " ".join(gmdn_status.split()).strip()

                                                # ==========================================================
                                                # 🌎 PASO 2: TRADUCCIÓN AUTOMÁTICA CON SEGMENTACIÓN (< 500 CHARS)
                                                # ==========================================================
                                                gmdn_status_esp = "No encontrado"
                                                gmdn_definition_esp = "No encontrado"

                                                # Traducir el Estado GMDN usando el diccionario local (Seguro y Rápido)
                                                diccionario_estados = {
                                                    "active": "Activo",
                                                    "obsolete": "Obsoleto",
                                                    "no encontrado": "No encontrado",
                                                    "filtrado": "Filtrado"
                                                }
                                                gmdn_status_esp = diccionario_estados.get(gmdn_status.lower(), gmdn_status)

                                                # Traducir la Definición GMDN manejando el límite de tamaño de MyMemory
                                                if gmdn_definition and gmdn_definition.lower() not in ["no encontrado", "filtrado"]:
                                                    try:
                                                        # Limpiamos comillas que dañen la URL
                                                        texto_limpio_url = gmdn_definition.replace('"', '').replace("'", "")
                                                        
                                                        # Segmentamos el texto si supera los 450 caracteres para no rozar el límite de la API
                                                        limite_caracteres = 450
                                                        pedazos = []
                                                        
                                                        if len(texto_limpio_url) > limite_caracteres:
                                                            # Divide el texto de forma limpia buscando espacios para no cortar palabras a la mitad
                                                            palabras = texto_limpio_url.split(' ')
                                                            pedazo_actual = []
                                                            cuenta_caracteres = 0
                                                            
                                                            for palabra in palabras:
                                                                if cuenta_caracteres + len(palabra) + 1 > limite_caracteres:
                                                                    pedazos.append(" ".join(pedazo_actual))
                                                                    pedazo_actual = [palabra]
                                                                    cuenta_caracteres = len(palabra)
                                                                else:
                                                                    pedazo_actual.append(palabra)
                                                                    cuenta_caracteres += len(palabra) + 1
                                                            if pedazo_actual:
                                                                pedazos.append(" ".join(pedazo_actual))
                                                        else:
                                                            pedazos = [texto_limpio_url]
                                                        
                                                        # Traducimos cada segmento individualmente
                                                        pedazos_traducidos = []
                                                        for pedazo in pedazos:
                                                            if pedazo.strip():
                                                                query_segura = urllib.parse.quote(pedazo.strip())
                                                                url_traductor = f"https://api.mymemory.translated.net/get?q={query_segura}&langpair=en|es"
                                                                respuesta_traduccion = requests.get(url_traductor, timeout=5)
                                                                
                                                                if respuesta_traduccion.status_code == 200:
                                                                    datos_traduccion = respuesta_traduccion.json()
                                                                    texto_traducido = datos_traduccion.get("responseData", {}).get("translatedText", "")
                                                                    
                                                                    if texto_traducido and "MYMEMORY" not in texto_traducido:
                                                                        pedazos_traducidos.append(texto_traducido.strip())
                                                                    else:
                                                                        pedazos_traducidos.append(pedazo)  # Conserva fragmento original si falla
                                                                else:
                                                                    pedazos_traducidos.append(pedazo)
                                                        
                                                        # Reconstruimos el texto completo traducido
                                                        gmdn_definition_esp = " ".join(pedazos_traducidos).strip()
                                                        
                                                    except Exception:
                                                        # Si hay fallo general, conserva el texto original en inglés
                                                        gmdn_definition_esp = gmdn_definition
                                                else:
                                                    gmdn_definition_esp = gmdn_definition

                                                # Sobreescribimos las variables originales con el resultado final en español
                                                gmdn_definition = gmdn_definition_esp
                                                gmdn_status = gmdn_status_esp
                                                
                                                if not gmdn_definition: gmdn_definition = "No encontrado"
                                                if not gmdn_status: gmdn_status = "No encontrado"
                                                
                                                # 🔬 LÓGICA DE EXTRACCIÓN DE ISSUING AGENCY
                                                issuing_agency_detectado = "No encontrado"
                                                if "Issuing Agency" in texto_completo_pagina:
                                                    for i, linea in enumerate(lineas_html):
                                                        if "Issuing Agency" in linea:
                                                            if linea.replace(":", "").strip() == "Issuing Agency" and i + 1 < len(lineas_html):
                                                                issuing_agency_detectado = lineas_html[i+1]
                                                            else:
                                                                issuing_agency_detectado = linea.replace("Issuing Agency", "").replace(":", "").strip()
                                                            break
                                                issuing_agency_detectado = " ".join(issuing_agency_detectado.split()).strip()
                                                
                                                coincidencias_validas.append({
                                                    "Referencia_Original": ref,
                                                    "Primary_DI_Number": primary_di,
                                                    "Nombre_Empresa_FDA": company_name_detectado,
                                                    "Codigo_GMDN": gmdn_code,
                                                    "Definicion_GMDN": " ".join(str(gmdn_definition).split()).strip(),
                                                    "Estado_GMDN": " ".join(str(gmdn_status).split()).strip(),
                                                    "Issuing_Agency": issuing_agency_detectado
                                                })
                                    except:
                                        continue
                                
                                if coincidencias_validas:
                                    lista_resultados_finales.extend(coincidencias_validas)
                                else:
                                    lista_resultados_finales.append({
                                        "Referencia_Original": ref, "Primary_DI_Number": "Filtrado", 
                                        "Nombre_Empresa_FDA": "No coincide", "Codigo_GMDN": "Filtrado",
                                        "Definicion_GMDN": "Filtrado", "Estado_GMDN": "Filtrado", "Issuing_Agency": "Filtrado"
                                    })
                            else:
                                lista_resultados_finales.append({
                                    "Referencia_Original": ref, "Primary_DI_Number": "No encontrado",
                                    "Nombre_Empresa_FDA": "No encontrado", "Codigo_GMDN": "No encontrado",
                                    "Definicion_GMDN": "No encontrado", "Estado_GMDN": "No encontrado", "Issuing_Agency": "No encontrado"
                                })
                        elif response.status_code == 429:
                            st.warning("⏳ Servidor saturado (429). Esperando 15 segundos...")
                            time.sleep(15)
                    except:
                        # En caso de caída de red de la máquina cliente, añade una fila de error en lugar de congelar la app
                        lista_resultados_finales.append({
                            "Referencia_Original": ref, "Primary_DI_Number": "Error de Red",
                            "Nombre_Empresa_FDA": "Error de Conexión", "Codigo_GMDN": "Error",
                            "Definicion_GMDN": "Error", "Estado_GMDN": "Error", "Issuing_Agency": "Error"
                        })
                    
                    # Micro-Etapa 3: Consolidado
                    porcentaje_etapa_3 = int((idx + 1) / total_refs * 100)
                    actualizar_barra_en_vivo(porcentaje_etapa_3)
                    
                    df_temporal = pd.DataFrame(lista_resultados_finales)
                    tabla_viva.dataframe(df_temporal, use_container_width=True)
                    time.sleep(0.8)

                texto_estado.empty()
                barra_custom_dinamica.empty() 
                st.success("✨ ¡Extracción masiva completada con éxito al 100%!")
                
                df_final = pd.DataFrame(lista_resultados_finales)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False)
                datos_excel = output.getvalue()
                
                st.download_button(
                    label="📥 Descargar Excel con Resultados",
                    data=datos_excel,
                    file_name="resultados_fda_interactivo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            elif not archivo_cargado:
                st.info("👈 Cargue un archivo en el panel izquierdo para activar la monitorización.")

    # ==========================================================
    # PIE DE PÁGINA CORPORATIVO INVARIANTE
    # ==========================================================
    st.markdown(
        """
        <div class="footer-institucional">
            <div class="footer-links">
                <a href="#">Políticas de privacidad y condiciones de uso del sitio</a>
                <a href="#">Política de tratamiento de datos personales</a>
                <a href="#">Mesa de Ayuda</a>
            </div>
            <div>v 1.0.26 © Invima 2026. Todos los derechos reservados.</div>
        </div>
        """,
        unsafe_allow_html=True
    )
