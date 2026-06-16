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
SHEET_ID = "1SSAS4NLafr3p8K3nllBoHp0AKklO5JNfWwQbSfNdbGU"

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

            /* ── RESPONSIVE MÓVIL ── */
            @media (max-width: 768px) {
                div[data-testid="stForm"] {
                    padding: 25px 18px !important;
                    margin: 0 8px !important;
                }
                .contenedor-logos-principales { gap: 12px !important; height: 55px !important; }
                .logo-header-invima { height: 42px !important; }
                .logo-header-fda    { height: 32px !important; }
                .login-title { font-size: 20px !important; }
                .fila-logos-soporte {
                    flex-direction: column !important;
                    gap: 12px !important;
                    align-items: center !important;
                }
                .logo-gudid-libre, .logo-eudamed-libre, .logo-gmdn-libre {
                    width: 100px !important;
                }
            }
        </style>""", unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1.2, 1])

    with col_centro:
        with st.form("formulario_login", clear_on_submit=False):
            # Logos superiores
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

            # Logos inferiores
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
    st.markdown("""
        <style>
            .stApp { background-image: none !important; background-color: #f4f6f9 !important; }
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
            .custom-progress-container {
                width: 100%; background-color: #ffffff; border: 2px solid #1e40af;
                border-radius: 8px; padding: 3px; height: 32px; overflow: hidden; margin: 15px 0;
            }
            .custom-progress-bar {
                height: 100%; border-radius: 4px;
                background-image: repeating-linear-gradient(-45deg, #1e40af, #1e40af 12px, #ffffff 12px, #ffffff 18px);
                transition: width 0.2s ease-in-out;
            }

            /* ── HEADER ── */
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

            /* ── CARDS MENÚ ── */
            .card-menu-principal {
                background-color: #ffffff !important;
                padding: 25px; border-radius: 12px;
                box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
                border-left: 5px solid #0b1d3a;
                margin-bottom: 20px;
            }
            .card-menu-principal h4 {
                color: #0b1d3a !important;
                font-size: 16px !important;
                margin: 0 0 8px 0 !important;
                font-weight: 700 !important;
            }
            .card-menu-principal p {
                color: #374151 !important;
                font-size: 14px !important;
                margin: 0 !important;
            }
            .card-menu-secundaria {
                background-color: #ffffff !important;
                padding: 25px; border-radius: 12px;
                box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
                border-left: 5px solid #6b7280;
                margin-bottom: 20px;
                opacity: 0.65;
            }
            .card-menu-secundaria h4 {
                color: #4b5563 !important;
                font-size: 16px !important;
                margin: 0 0 8px 0 !important;
                font-weight: 700 !important;
            }
            .card-menu-secundaria p {
                color: #4b5563 !important;
                font-size: 14px !important;
                margin: 0 !important;
            }

            /* ── FOOTER ── */
            .footer-institucional {
                margin-top: 60px; padding: 25px 0;
                border-top: 1px solid #e5e7eb;
                text-align: center; font-size: 13px; color: #4b5563 !important;
            }
            .footer-links { display: flex; justify-content: center; gap: 30px; margin-bottom: 10px; flex-wrap: wrap; }
            .footer-links a { color: #0b1d3a !important; text-decoration: none; font-weight: 500; }

            /* ── RESPONSIVE MÓVIL ── */
            @media (max-width: 768px) {
                .header-oficina-virtual {
                    flex-direction: column !important;
                    gap: 8px !important;
                    text-align: center !important;
                    padding: 12px 15px !important;
                }
                .header-title { font-size: 16px !important; }
                .user-tag { font-size: 12px !important; padding: 6px 12px !important; }
                .card-menu-principal, .card-menu-secundaria { padding: 15px !important; }
                .card-menu-principal h4, .card-menu-secundaria h4 { font-size: 14px !important; }
                .card-menu-principal p,  .card-menu-secundaria p  { font-size: 12px !important; }
                .footer-links { gap: 15px !important; }
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
        st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)
        if st.sidebar.button("🚪 Cerrar Sesión Segura", use_container_width=True):
            st.session_state["autenticado"] = False; st.rerun()

    # --- ENCABEZADO ---
    usuario_sesion = st.session_state["usuario_activo_real"]
    st.markdown(f"""
        <div class="header-oficina-virtual">
            <div class="header-title">Oficina Virtual de Dispositivos Médicos</div>
            <div class="user-tag">👤 <b>Usuario activo:</b> {usuario_sesion}</div>
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
            <div class="card-menu-secundaria">
                <h4>2. Consulta de Historiales y Reportes</h4>
                <p>Módulo de auditoría — Próximamente disponible.</p>
            </div>""", unsafe_allow_html=True)

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

                                    # Company Name
                                    company = "No encontrado"
                                    for i, l in enumerate(lineas):
                                        if "Company Name" in l:
                                            company = lineas[i+1] if l.replace(":","").strip() == "Company Name" and i+1 < len(lineas) else l.replace("Company Name","").replace(":","").strip()
                                            break
                                    company = " ".join(company.split()).strip() or "No encontrado"

                                    if company_name_filtro and company_name_filtro.upper() not in company.upper():
                                        continue

                                    # GMDN Code
                                    gmdn_code = "No encontrado"
                                    for p in texto.replace(':',' ').replace('(',' ').replace(')',' ').split():
                                        if p.isdigit() and len(p) == 5:
                                            gmdn_code = p; break

                                    # GMDN Definition & Status
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

                                    # Traducción GMDN Definition
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

                                    # Issuing Agency
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

                # --- FINALIZACIÓN ---
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
    # PIE DE PÁGINA
    # ==========================================================
    st.markdown("""
        <div class="footer-institucional">
            <div class="footer-links">
                <a href="#">Políticas de privacidad</a>
                <a href="#">Tratamiento de datos</a>
                <a href="#">Mesa de Ayuda</a>
            </div>
            <div>v 1.0.26 © Invima 2026. Todos los derechos reservados.</div>
        </div>""", unsafe_allow_html=True)
