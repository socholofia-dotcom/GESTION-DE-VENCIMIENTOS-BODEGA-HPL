from datetime import date

import streamlit as st

from src.auth import logout_button, require_login
from src.config import APP_TITLE, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
from src.database import initialize_database
from src.permissions import can_administer_users
from src.repositories import ensure_admin
from src.ui import render_audit, render_dashboard, render_import, render_step_management, render_users


st.set_page_config(page_title=APP_TITLE, page_icon="💊", layout="wide")
initialize_database()
ensure_admin(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
user = require_login()

st.sidebar.success(f"{user['full_name']}\n\n{user['role']}")
logout_button()

st.sidebar.title("Navegación")
pages = ["Dashboard", "Gestión por pasos", "Carga masiva", "Auditoría"]
if can_administer_users(user["role"]):
    pages.append("Usuarios")
page = st.sidebar.radio("Módulo", pages, label_visibility="collapsed")

today = date.today()
if today.day <= 15:
    st.info("Calendario operativo · Días 1 al 15: Jefatura debe completar el Paso 2 — gestión de canjes.")
else:
    st.warning("Calendario operativo · Día 16 al fin de mes: Área de Registro debe completar el Paso 3 — tramitación con proveedores.")

if page == "Dashboard": render_dashboard()
elif page == "Gestión por pasos": render_step_management(user)
elif page == "Carga masiva": render_import(user)
elif page == "Auditoría": render_audit()
elif page == "Usuarios": render_users(user)
