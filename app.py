import streamlit as st
import json
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Plataforma de Extracción", layout="centered")

# --- LÓGICA DE CONEXIÓN ---
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

# --- INTERFAZ ÚNICA ---
if "autenticado" not in st.session_state: st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align: center;'>Plataforma de Extracción</h2>", unsafe_allow_html=True)
    with st.form("unico_login"):
        user = st.text_input("Nombre de usuario")
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Acceder"):
            if validar_usuario_sheets(user, pwd):
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
else:
    st.success("¡Bienvenido al sistema!")
    if st.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.rerun()
