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

# --- FUNCIONES DE APOYO ---
def obtener_base64_imagen(ruta_archivo):
    if os.path.exists(ruta_archivo):
        with open(ruta_archivo, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    return ""

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

# --- CSS Y ESTILOS (El corazón del diseño) ---
st.markdown("""
    <style>
    .stApp { background-image: linear-gradient(rgba(15, 32, 67, 0.65), rgba(15, 32, 67, 0.85)), url('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?q=80&w=2070'); background-size: cover; }
    div[data-testid="stForm"] { background-color: rgba(255, 255, 255, 0.98); border-radius: 16px; padding: 40px; box-shadow: 0px 12px 40px rgba(0,0,0,0.35); max-width: 500px; margin: 0 auto; }
    .login-title { color: #0f2043; font-size: 24px; font-weight: bold; text-align: center; }
    .login-desc { color: #555555; font-size: 14px; text-align: center; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

# --- LÓGICA DE SESIÓN ---
if "autenticado" not in st.session_state: st.session_state["autenticado"] = False

# --- INTERFAZ ---
if not st.session_state["autenticado"]:
    # Espaciado para centrar
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    with st.form("login_estilo"):
        st.markdown("<div class='login-title'>Plataforma de Extracción</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-desc'>Gestión Automatizada de Dispositivos Médicos</div>", unsafe_allow_html=True)
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
