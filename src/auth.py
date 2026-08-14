import streamlit as st

from .repositories import get_user_by_username, verify_password


def login_form() -> bool:
    st.title("Gestión de productos con pronto vencimiento")
    st.caption("Acceso institucional")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)
    if submitted:
        user = get_user_by_username(username)
        if user and user["active"] and verify_password(password, user["password_hash"]):
            st.session_state.user = {
                "id": user["id"], "username": user["username"],
                "full_name": user["full_name"], "role": user["role"],
            }
            st.rerun()
        st.error("Usuario o contraseña incorrectos, o cuenta desactivada.")
    return False


def require_login() -> dict:
    if "user" not in st.session_state:
        login_form()
        st.stop()
    return st.session_state.user


def logout_button() -> None:
    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

