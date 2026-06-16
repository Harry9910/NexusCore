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

# 1. Configuración Única
st.set_page_config(page_title="Extractor AccessGUDID FDA", page_icon="🔬", layout="wide")

# 2. Función de Validación
def validar_usuario_sheets(usuario_ingresado, password_ingresado):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Usuarios_FDA").sheet1
    datos = sheet.get_all_records()
    for fila in datos:
        if str(fila.get('usuario', '')).strip() == usuario_ingresado.strip() and \
           str(fila.get('password', '')).strip() == password_ingresado.strip():
            return True
    return False

# 3. Inicialización
if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if "usuario_activo_real" not in st.session_state: st.session_state["usuario_activo_real"] = ""
if "seccion_activa" not in st.session_state: st.session_state["seccion_activa"] = "Inicio"

# 4. Login (Si no está autenticado)
if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align: center;'>Plataforma de Extracción</h2>", unsafe_allow_html=True)
    with st.form("login_unico"):
        user = st.text_input("Nombre de usuario")
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Acceder"):
            if validar_usuario_sheets(user, pwd):
                st.session_state["autenticado"] = True
                st.session_state["usuario_activo_real"] = user
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop() # Detenemos aquí si no hay login

# 5. Interfaz Interna (Solo visible si autenticado)
st.markdown("""<style>
    .header-oficina-virtual { background-color: #ffffff; padding: 15px 30px; border-radius: 10px; box-shadow: 0px 2px 8px rgba(0,0,0,0.05); margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; }
    .header-title { color: #0b1d3a; font-size: 22px; font-weight: bold; }
    .user-tag { font-size: 13.5px; color: #0b1d3a; background-color: #eff6ff; padding: 8px 16px; border-radius: 20px; border: 1px solid #bfdbfe; }
</style>""", unsafe_allow_html=True)

st.markdown(f"""
    <div class="header-oficina-virtual">
        <div class="header-title">Oficina Virtual de Dispositivos Médicos</div>
        <div class="user-tag">👤 <b>Usuario:</b> {st.session_state["usuario_activo_real"]}</div>
    </div>
""", unsafe_allow_html=True)

# Barra Lateral
with st.sidebar:
    if st.button("🏠 Menú Principal"): st.session_state["seccion_activa"] = "Inicio"; st.rerun()
    if st.button("🚀 Panel de Extracción"): st.session_state["seccion_activa"] = "Extraccion"; st.rerun()
    if st.button("🚪 Cerrar Sesión"): st.session_state["autenticado"] = False; st.rerun()

# Vistas
if st.session_state["seccion_activa"] == "Inicio":
    st.title("Menú Principal")
    st.write("Seleccione una opción de la barra lateral.")
elif st.session_state["seccion_activa"] == "Extraccion":
    st.title("Panel de Extracción")
    st.write("Lógica de extracción aquí...")
