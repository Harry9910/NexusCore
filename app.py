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

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Plataforma de Extracción", layout="wide")

# --- FUNCIÓN DE LOGOS ---
def obtener_base64_logo(nombre_archivo):
    # Verifica si el archivo existe en la carpeta raíz del repo
    if os.path.exists(nombre_archivo):
        with open(nombre_archivo, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# Carga de logos (Asegúrate de que estos nombres coincidan con tus archivos en GitHub)
b64_invima = obtener_base64_logo("logo_invima.png")
b64_fda = obtener_base64_logo("logo_fda.png")

# --- LÓGICA DE VALIDACIÓN ---
def validar_usuario_sheets(usuario_ingresado, password_ingresado):
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    client = gspread.authorize(creds)
    datos = client.open("Usuarios_FDA").sheet1.get_all_records()
    for fila in datos:
        if str(fila.get('usuario', '')).strip() == usuario_ingresado.strip() and \
           str(fila.get('password', '')).strip() == password_ingresado.strip():
            return True
    return False

# --- CSS INTEGRADO ---
st.markdown("""
    <style>
    .stApp { background-image: linear-gradient(rgba(15, 32, 67, 0.65), rgba(15, 32, 67, 0.85)), url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070'); background-size: cover; }
    div[data-testid="stForm"] { background-color: rgba(255, 255, 255, 0.98); border-radius: 16px; padding: 40px; box-shadow: 0px 12px 40px rgba(0,0,0,0.35); max-width: 500px; margin: 0 auto; }
    .logo-container { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }
    .logo-img { height: 60px; }
    .login-title { color: #0f2043; font-size: 24px; font-weight: bold; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# --- SESIÓN E INTERFAZ ---
if "autenticado" not in st.session_state: st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    with st.form("login_estilo"):
        # Renderizado de logos
        cols = st.columns(2)
        if b64_invima: st.markdown(f'<div class="logo-container"><img class="logo-img" src="data:image/png;base64,{b64_invima}">', unsafe_allow_html=True)
        if b64_fda: st.markdown(f'<img class="logo-img" src="data:image/png;base64,{b64_fda}"></div>', unsafe_allow_html=True)
        
        st.markdown("<div class='login-title'>Plataforma de Extracción</div>", unsafe_allow_html=True)
        user = st.text_input("Nombre de usuario")
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Acceder", use_container_width=True):
            if validar_usuario_sheets(user, pwd):
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
else:
    st.title("Bienvenido al Sistema")
    if st.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.rerun()
