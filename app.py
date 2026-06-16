import streamlit as st
import pandas as pd
import requests
import json
import gspread
import base64
import os
import time
import io
import urllib.parse
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials

# 1. CONFIGURACIÓN ÚNICA
st.set_page_config(page_title="Extractor AccessGUDID FDA", page_icon="🔬", layout="wide")

# 2. FUNCIONES BASE (LOGOS Y AUTH)
def obtener_base64_logo(nombre_archivo):
    if os.path.exists(nombre_archivo):
        with open(nombre_archivo, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

def validar_usuario_sheets(user, pwd):
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    client = gspread.authorize(creds)
    datos = client.open("Usuarios_FDA").sheet1.get_all_records()
    for fila in datos:
        if str(fila.get('usuario', '')).strip() == user.strip() and str(fila.get('password', '')).strip() == pwd.strip():
            return True
    return False

# 3. ESTADOS DE SESIÓN
if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if "usuario_activo_real" not in st.session_state: st.session_state["usuario_activo_real"] = ""
if "seccion_activa" not in st.session_state: st.session_state["seccion_activa"] = "Inicio"

# 4. CSS GLOBAL (ÚNICO)
st.markdown("""<style>
    .stApp { background-image: linear-gradient(rgba(15, 32, 67, 0.65), rgba(15, 32, 67, 0.85)), url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070'); background-size: cover; }
    div[data-testid="stForm"] { background-color: rgba(255, 255, 255, 0.98); border-radius: 16px; padding: 40px; box-shadow: 0px 12px 40px rgba(0,0,0,0.35); }
    .logo-container { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }
    .logo-img { height: 60px; }
</style>""", unsafe_allow_html=True)

# 5. FLUJO LÓGICO
if not st.session_state["autenticado"]:
    # --- PANTALLA DE LOGIN ---
    st.markdown("<br><br>", unsafe_allow_html=True)
    with st.form("login_unico"):
        # (Aquí iría la lógica de tus logos si los archivos están en la raíz)
        user = st.text_input("Usuario")
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Acceder", use_container_width=True):
            if validar_usuario_sheets(user, pwd):
                st.session_state["autenticado"] = True
                st.session_state["usuario_activo_real"] = user
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
else:
    # --- PANTALLA PRINCIPAL (AQUÍ PEGA TUS 700 LÍNEAS) ---
    # Al estar dentro de este 'else', todo tu código de extracción 
    # solo se ejecutará cuando el usuario haya iniciado sesión.
    
    # PEGA TU LÓGICA DE EXTRACCIÓN, SIDEBAR, Y TABLAS AQUÍ:
    st.write(f"Bienvenido {st.session_state['usuario_activo_real']}")
    # ... RESTO DE TU CÓDIGO ...
