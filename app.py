"""Punto de entrada de la aplicación Streamlit."""

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from src.auth import logout_button, require_login
from src.config import APP_TITLE, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, PROJECT_ROOT
from src.database import initialize_database
from src.permissions import can_administer_users
from src.repositories import ensure_admin
from src.ui import render_audit, render_dashboard, render_import, render_step_management, render_users


CATALOG_PATH = PROJECT_ROOT / "data" / "catalogo_reyimen.csv"
CATALOG_COLUMNS = {"codigo_reyimen", "descripcion", "unidad", "precio_unitario", "bodega"}


@st.cache_data(show_spinner=False)
def load_catalog(path: Path) -> pd.DataFrame:
    """Carga y valida el catálogo extraído del inventario institucional."""
    if not path.exists():
        return pd.DataFrame(columns=sorted(CATALOG_COLUMNS))
    catalog = pd.read_csv(path, dtype={"codigo_reyimen": str}, keep_default_na=True)
    missing = CATALOG_COLUMNS - set(catalog.columns)
    if missing:
        raise ValueError(f"El catálogo no contiene las columnas: {', '.join(sorted(missing))}")
    for column in ["codigo_reyimen", "descripcion", "unidad", "bodega"]:
        catalog[column] = catalog[column].fillna("").astype(str).str.strip()
    catalog["precio_unitario"] = pd.to_numeric(catalog["precio_unitario"], errors="coerce")
    return catalog.sort_values(["bodega", "descripcion", "codigo_reyimen"], kind="stable")


st.set_page_config(page_title=APP_TITLE, page_icon="💊", layout="wide")
initialize_database()
ensure_admin(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
user = require_login()

try:
    catalog = load_catalog(CATALOG_PATH)
except Exception as error:
    st.error(f"No fue posible cargar el catálogo Reyimen: {error}")
    catalog = pd.DataFrame(columns=sorted(CATALOG_COLUMNS))

st.sidebar.success(f"{user['full_name']}\n\n{user['role']}")
if not catalog.empty:
    st.sidebar.caption(
        f"Catálogo institucional: {catalog['codigo_reyimen'].nunique():,} códigos · "
        f"{catalog['bodega'].nunique()} bodegas"
    )
else:
    st.sidebar.warning("Catálogo Reyimen no disponible")
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

if page == "Dashboard":
    render_dashboard()
elif page == "Gestión por pasos":
    render_step_management(user, catalog)
elif page == "Carga masiva":
    render_import(user)
elif page == "Auditoría":
    render_audit()
elif page == "Usuarios":
    render_users(user)
