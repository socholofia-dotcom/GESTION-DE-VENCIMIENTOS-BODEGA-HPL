from __future__ import annotations

from datetime import date, datetime
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from .importer import import_rows, read_upload, template_bytes, validate_rows
from .permissions import Role, can_administer_users, can_edit_step
from .repositories import (
    create_product, create_user, get_product, list_audit, list_products, list_users,
    set_user_active, update_product,
)
from .risk import months_until, risk_state


RISK_COLORS = {
    "Crítico / Urgente": "#dc2626", "Advertencia": "#facc15",
    "Seguro": "#16a34a", "Vencido / Retirar": "#111827", "Retirado": "#6b7280",
}


def _products_frame() -> pd.DataFrame:
    rows = [dict(row) for row in list_products()]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    expiry = pd.to_datetime(frame["expiration_date"])
    frame["meses_para_vencer"] = expiry.map(lambda value: months_until(value.date()))
    frame["riesgo"] = expiry.map(lambda value: risk_state(value.date()))
    frame.loc[frame["final_resolution"] == "Retirado/Baja", "riesgo"] = "Retirado"
    frame["monto_evitado"] = frame["successful_managed_quantity"].fillna(0) * frame["estimated_unit_cost"].fillna(0)
    return frame


def render_dashboard() -> None:
    st.header("Dashboard ejecutivo")
    frame = _products_frame()
    if frame.empty:
        st.info("Aún no existen productos. Registre uno en Gestión por pasos o use la carga masiva.")
        return
    successful = frame["successful_managed_quantity"].fillna(0).sum()
    amount = frame["monto_evitado"].sum()
    critical = int((frame["riesgo"] == "Crítico / Urgente").sum())
    open_items = int((frame["product_status"] == "En revisión").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cantidad de merma evitada", f"{successful:,.0f}")
    c2.metric("Monto estimado evitado", f"${amount:,.0f}")
    c3.metric("Productos críticos", critical)
    c4.metric("Gestiones abiertas", open_items)

    left, right = st.columns(2)
    risk_counts = frame["riesgo"].value_counts().rename_axis("Riesgo").reset_index(name="Productos")
    left.plotly_chart(px.pie(
        risk_counts, names="Riesgo", values="Productos", hole=.45,
        color="Riesgo", color_discrete_map=RISK_COLORS, title="Distribución por riesgo",
    ), use_container_width=True)
    procedure = frame["procedure_status"].fillna("Sin iniciar").replace("", "Sin iniciar")
    procedure_counts = procedure.value_counts().rename_axis("Estado").reset_index(name="Productos")
    right.plotly_chart(px.bar(
        procedure_counts, x="Productos", y="Estado", orientation="h",
        title="Estado de tramitación con proveedores", color="Productos",
        color_continuous_scale="Blues",
    ), use_container_width=True)

    completed = int((frame["product_status"] == "Concluido").sum())
    progress = completed / len(frame) if len(frame) else 0
    st.subheader("Avance global de gestiones")
    st.progress(progress, text=f"{completed} de {len(frame)} registros concluidos ({progress:.0%})")

    st.subheader("Alertas urgentes: vencimiento dentro de 2 meses")
    urgent = frame[frame["riesgo"].isin(["Crítico / Urgente", "Vencido / Retirar"])].copy()
    if urgent.empty:
        st.success("No existen productos urgentes o vencidos.")
    else:
        st.dataframe(urgent[[
            "id", "reyimen_code", "description", "origin", "quantity", "lot",
            "expiration_date", "meses_para_vencer", "riesgo", "procedure_status",
        ]], hide_index=True, use_container_width=True)


def _selector(frame: pd.DataFrame, key: str) -> int | None:
    if frame.empty:
        st.info("No existen productos registrados.")
        return None
    labels = {
        int(row.id): f"#{int(row.id)} · {row.reyimen_code} · {row.description} · Lote {row.lot}"
        for row in frame.itertuples()
    }
    return st.selectbox("Seleccione un producto", list(labels), format_func=labels.get, key=key)


def render_step_management(user: dict, catalog: pd.DataFrame) -> None:
    st.header("Gestión por pasos")
    frame = _products_frame()
    tabs = st.tabs(["Paso 1 · Informe", "Paso 2 · Canje", "Paso 3 · Proveedor", "Paso 4 · Bulto", "Paso 5 · Resolución"])
    with tabs[0]:
        _step_1(user, frame, catalog)
    with tabs[1]:
        _step_2(user, frame)
    with tabs[2]:
        _step_3(user, frame)
    with tabs[3]:
        _step_4(user, frame)
    with tabs[4]:
        _step_5(user, frame)


def _read_only_notice(user: dict, step: int) -> bool:
    allowed = can_edit_step(user["role"], step)
    if not allowed:
        st.info(f"Su rol puede consultar este paso, pero no modificarlo.")
    return allowed


def _step_1(user: dict, frame: pd.DataFrame, catalog: pd.DataFrame) -> None:
    allowed = _read_only_notice(user, 1)
    mode = st.radio("Acción", ["Crear producto", "Editar producto"], horizontal=True, key="s1_mode")
    record = None
    if mode == "Editar producto":
        record_id = _selector(frame, "s1_record")
        record = dict(get_product(record_id)) if record_id else None
    defaults = record or {}
    record_token = record["id"] if record else "new"
    catalog_match = pd.DataFrame()
    if record and not catalog.empty:
        catalog_match = catalog[
            (catalog["codigo_reyimen"] == str(record["reyimen_code"]))
            & (catalog["bodega"] == str(record["origin"]))
        ]
    manual_default = catalog.empty or (record is not None and catalog_match.empty)
    manual_entry = st.checkbox(
        "Ingreso manual de un producto que no está en el catálogo",
        value=manual_default,
        key=f"s1_manual_{record_token}",
        disabled=not allowed or catalog.empty,
    )

    if not catalog.empty:
        warehouses = sorted(catalog["bodega"].dropna().unique().tolist(), key=str.casefold)
        current_origin = str(defaults.get("origin", ""))
        if current_origin and current_origin not in warehouses:
            warehouses.append(current_origin)
        warehouse_index = warehouses.index(current_origin) if current_origin in warehouses else 0
        origin = st.selectbox(
            "Bodega/Farmacia origen *",
            warehouses,
            index=warehouse_index,
            key=f"s1_warehouse_{record_token}",
            disabled=not allowed,
        )
        if not manual_entry:
            warehouse_catalog = catalog[catalog["bodega"] == origin].drop_duplicates("codigo_reyimen")
            code_labels = {
                row.codigo_reyimen: f"{row.codigo_reyimen} — {row.descripcion}"
                for row in warehouse_catalog.itertuples()
            }
            codes = list(code_labels)
            current_code = str(defaults.get("reyimen_code", ""))
            code_index = codes.index(current_code) if current_code in codes else 0
            selected_code = st.selectbox(
                "Buscar código Reyimen o descripción *",
                codes,
                index=code_index,
                format_func=code_labels.get,
                key=f"s1_code_{record_token}_{origin}",
                disabled=not allowed,
                help="Escriba parte del código o de la descripción para filtrar la lista.",
            )
            catalog_row = warehouse_catalog[warehouse_catalog["codigo_reyimen"] == selected_code].iloc[0]
            defaults = {
                **defaults,
                "origin": origin,
                "reyimen_code": str(catalog_row["codigo_reyimen"]),
                "description": str(catalog_row["descripcion"]),
                "unit": str(catalog_row["unidad"]),
                "estimated_unit_cost": 0 if pd.isna(catalog_row["precio_unitario"]) else float(catalog_row["precio_unitario"]),
            }
            st.caption("Descripción, unidad de medida y precio fueron completados desde el inventario institucional.")
            if pd.isna(catalog_row["precio_unitario"]):
                st.warning("El precio de este producto aparece oculto como ######## en la planilla fuente. Active el ingreso manual para incorporarlo.")
    else:
        origin = str(defaults.get("origin", ""))

    with st.form("step1_form"):
        c1, c2, c3 = st.columns(3)
        status = c1.selectbox("Estado del producto", ["En revisión", "Concluido"], index=0 if defaults.get("product_status", "En revisión") == "En revisión" else 1)
        report_date = c2.date_input("Mes de informe", value=pd.to_datetime(defaults.get("report_month", date.today().strftime("%Y-%m"))).date())
        c3.text_input("Bodega seleccionada", origin, disabled=True)
        c1, c2, c3 = st.columns(3)
        product_type = c1.selectbox("Tipo de producto", ["Fármaco", "Insumo"], index=0 if defaults.get("product_type", "Fármaco") == "Fármaco" else 1)
        code = c2.text_input("Código Reyimen *", defaults.get("reyimen_code", ""), disabled=not manual_entry, key=f"s1_code_field_{record_token}_{defaults.get('reyimen_code', '')}")
        unit = c3.text_input("Unidad *", defaults.get("unit", ""), disabled=not manual_entry, key=f"s1_unit_{record_token}_{defaults.get('reyimen_code', '')}")
        description = st.text_input("Descripción *", defaults.get("description", ""), disabled=not manual_entry, key=f"s1_description_{record_token}_{defaults.get('reyimen_code', '')}")
        c1, c2, c3 = st.columns(3)
        quantity = c1.number_input("Cantidad", min_value=0.0, value=float(defaults.get("quantity", 0)))
        expiration = c2.date_input("Vencimiento", value=pd.to_datetime(defaults.get("expiration_date", date.today())).date())
        lot = c3.text_input("Lote *", defaults.get("lot", ""))
        reason = st.text_area("Motivo de informe *", defaults.get("report_reason", ""))
        c1, c2 = st.columns(2)
        purchase = c1.selectbox("Tipo de compra", ["CENABAST", "Compra Propia"], index=0 if defaults.get("purchase_type", "CENABAST") == "CENABAST" else 1)
        cost = c2.number_input("Precio unitario ($)", min_value=0.0, value=float(defaults.get("estimated_unit_cost", 0)), disabled=not manual_entry, key=f"s1_cost_{record_token}_{defaults.get('reyimen_code', '')}")
        submitted = st.form_submit_button("Guardar Paso 1", disabled=not allowed, use_container_width=True)
    if submitted:
        if not all([origin.strip(), code.strip(), unit.strip(), description.strip(), lot.strip(), reason.strip()]):
            st.error("Complete todos los campos marcados con *.")
            return
        data = {"product_status": status, "report_month": report_date.strftime("%Y-%m"), "origin": origin.strip(),
                "product_type": product_type, "reyimen_code": code.strip(), "description": description.strip(),
                "unit": unit.strip(), "quantity": quantity, "expiration_date": expiration.isoformat(), "lot": lot.strip(),
                "report_reason": reason.strip(), "purchase_type": purchase, "estimated_unit_cost": cost}
        try:
            if record:
                update_product(record["id"], data, user)
                st.success("Paso 1 actualizado y registrado en auditoría.")
            else:
                create_product(data, user)
                st.success("Producto creado y registrado en auditoría.")
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("Ya existe un registro con el mismo código, lote, vencimiento y origen.")


def _step_2(user: dict, frame: pd.DataFrame) -> None:
    allowed = _read_only_notice(user, 2)
    record_id = _selector(frame, "s2_record")
    if not record_id: return
    record = dict(get_product(record_id))
    expiry = date.fromisoformat(record["expiration_date"])
    st.metric("Meses por vencer (automático)", months_until(expiry), risk_state(expiry))
    with st.form("step2_form"):
        current = record.get("exchange_policy") or "Con política"
        policy = st.selectbox("Carta de canje", ["Con política", "Sin política"], index=0 if current == "Con política" else 1)
        deadline = st.date_input("Fecha límite de retiro de stock utilizable", value=pd.to_datetime(record.get("withdrawal_deadline") or expiry).date())
        submitted = st.form_submit_button("Guardar Paso 2", disabled=not allowed, use_container_width=True)
    if submitted:
        update_product(record_id, {"exchange_policy": policy, "withdrawal_deadline": deadline.isoformat()}, user)
        st.success("Paso 2 actualizado."); st.rerun()


def _step_3(user: dict, frame: pd.DataFrame) -> None:
    allowed = _read_only_notice(user, 3)
    record_id = _selector(frame, "s3_record")
    if not record_id: return
    r = dict(get_product(record_id))
    with st.form("step3_form"):
        c1, c2 = st.columns(2)
        alert = c1.selectbox("Estado de alerta", ["Sin iniciar", "Notificado", "Urgente", "Cerrado"], index=_option_index(["Sin iniciar", "Notificado", "Urgente", "Cerrado"], r.get("alert_status")))
        statuses = ["Sin iniciar", "Correo enviado", "En espera de respuesta", "Canje aceptado", "Canje rechazado", "Nota de crédito recibida", "Producto retirado", "Trámite cerrado"]
        procedure = c2.selectbox("Estado del trámite", statuses, index=_option_index(statuses, r.get("procedure_status")))
        c1, c2 = st.columns(2)
        doc_number = c1.text_input("N° documento", r.get("document_number") or "")
        doc_type = c2.text_input("Tipo de documento", r.get("document_type") or "")
        supplier = st.text_input("Nombre del proveedor", r.get("supplier_name") or "")
        c1, c2 = st.columns(2)
        contact = c1.text_input("Contacto del proveedor", r.get("supplier_contact") or "")
        email = c2.text_input("Correo del proveedor", r.get("supplier_email") or "")
        submitted = st.form_submit_button("Guardar Paso 3", disabled=not allowed, use_container_width=True)
    if submitted:
        update_product(record_id, {"alert_status": alert, "procedure_status": procedure, "document_number": doc_number.strip(),
            "document_type": doc_type.strip(), "supplier_name": supplier.strip(), "supplier_contact": contact.strip(), "supplier_email": email.strip()}, user)
        st.success("Paso 3 actualizado."); st.rerun()


def _step_4(user: dict, frame: pd.DataFrame) -> None:
    allowed = _read_only_notice(user, 4)
    record_id = _selector(frame, "s4_record")
    if not record_id: return
    r = dict(get_product(record_id)); statuses = ["Armado", "Preparado", "En bodega activa"]
    with st.form("step4_form"):
        package = st.selectbox("Estado del bulto", statuses, index=_option_index(statuses, r.get("package_status")))
        physical = st.text_input("Ubicación física", r.get("physical_location") or "")
        computer = st.text_input("Ubicación computacional", r.get("computer_location") or "")
        submitted = st.form_submit_button("Guardar Paso 4", disabled=not allowed, use_container_width=True)
    if submitted:
        update_product(record_id, {"package_status": package, "physical_location": physical.strip(), "computer_location": computer.strip()}, user)
        st.success("Paso 4 actualizado."); st.rerun()


def _step_5(user: dict, frame: pd.DataFrame) -> None:
    allowed = _read_only_notice(user, 5)
    record_id = _selector(frame, "s5_record")
    if not record_id: return
    r = dict(get_product(record_id))
    resolutions = ["Pendiente", "Canje exitoso", "Sin carta de canje", "Redistribuido", "Retirado/Baja", "Otra"]
    with st.form("step5_form"):
        resolution = st.selectbox("Resolución final", resolutions, index=_option_index(resolutions, r.get("final_resolution")))
        observations = st.text_area("Observaciones", r.get("observations") or "")
        c1, c2 = st.columns(2)
        dissemination = c1.text_area("Difusión a la Red", r.get("network_dissemination") or "")
        redistribution = c2.text_area("Redistribución de stock", r.get("stock_redistribution") or "")
        successful_qty = st.number_input("Cantidad gestionada exitosamente", min_value=0.0, max_value=float(r["quantity"]), value=min(float(r.get("successful_managed_quantity") or 0), float(r["quantity"])))
        close = st.checkbox("Marcar producto como Concluido", value=r["product_status"] == "Concluido")
        submitted = st.form_submit_button("Guardar Paso 5", disabled=not allowed, use_container_width=True)
    if submitted:
        update_product(record_id, {"final_resolution": resolution, "observations": observations.strip(),
            "network_dissemination": dissemination.strip(), "stock_redistribution": redistribution.strip(),
            "successful_managed_quantity": successful_qty, "product_status": "Concluido" if close else "En revisión"}, user)
        st.success("Resolución actualizada."); st.rerun()


def _option_index(options: list[str], current: str | None) -> int:
    return options.index(current) if current in options else 0


def render_import(user: dict) -> None:
    st.header("Carga masiva del Paso 1")
    if not can_edit_step(user["role"], 1):
        st.warning("Solo Encargado de Bodega/Farmacia o Administrador puede importar el Paso 1.")
        return
    st.download_button("Descargar plantilla Excel", template_bytes(), "plantilla_carga_paso_1.xlsx", use_container_width=True)
    uploaded = st.file_uploader("Seleccione archivo Excel o CSV", type=["xlsx", "csv"])
    if uploaded:
        try:
            frame = read_upload(uploaded)
            st.dataframe(frame.head(50), hide_index=True, use_container_width=True)
            rows, errors = validate_rows(frame)
            if errors:
                st.error(f"Se encontraron {len(errors)} errores. No se importará mientras existan errores.")
                st.code("\n".join(errors[:100]))
            else:
                st.success(f"Validación correcta: {len(rows)} filas listas para importar.")
                if st.button("Confirmar importación", type="primary", use_container_width=True):
                    count, import_errors = import_rows(rows, user)
                    if import_errors:
                        st.warning(f"Se importaron {count} filas; {len(import_errors)} no pudieron guardarse.")
                        st.code("\n".join(import_errors[:100]))
                    else:
                        st.success(f"Se importaron correctamente {count} productos.")
        except Exception as exc:
            st.error(f"No fue posible leer el archivo: {exc}")


def render_users(user: dict) -> None:
    st.header("Administración de usuarios")
    if not can_administer_users(user["role"]):
        st.warning("Módulo disponible solo para Jefatura y Administrador.")
        return
    with st.expander("Crear nuevo usuario", expanded=False):
        with st.form("create_user_form"):
            c1, c2 = st.columns(2)
            username = c1.text_input("Usuario *")
            full_name = c2.text_input("Nombre completo *")
            password = st.text_input("Contraseña temporal *", type="password", help="Mínimo 10 caracteres.")
            role = st.selectbox("Rol", [r.value for r in Role])
            submitted = st.form_submit_button("Crear usuario", use_container_width=True)
        if submitted:
            if not username.strip() or not full_name.strip() or len(password) < 10:
                st.error("Complete los datos y use una contraseña de al menos 10 caracteres.")
            else:
                try:
                    create_user(username, password, full_name, role)
                    st.success("Usuario creado correctamente."); st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ese nombre de usuario ya existe.")
    users = pd.DataFrame([dict(row) for row in list_users()])
    users["Estado"] = users["active"].map({1: "Activo", 0: "Desactivado"})
    st.dataframe(users[["id", "username", "full_name", "role", "Estado", "created_at"]], hide_index=True, use_container_width=True)
    labels = {int(row.id): f"{row.full_name} ({row.username}) · {row.Estado}" for row in users.itertuples()}
    target = st.selectbox("Usuario a activar/desactivar", list(labels), format_func=labels.get)
    desired = st.radio("Nuevo estado", ["Activo", "Desactivado"], horizontal=True)
    if st.button("Aplicar cambio de estado", use_container_width=True):
        try:
            set_user_active(target, desired == "Activo", user)
            st.success("Estado actualizado."); st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def render_audit() -> None:
    st.header("Bincard / Historial de cambios")
    rows = pd.DataFrame([dict(row) for row in list_audit()])
    if rows.empty:
        st.info("Aún no existen cambios registrados.")
        return
    c1, c2 = st.columns(2)
    users = ["Todos"] + sorted(rows["username"].unique().tolist())
    selected_user = c1.selectbox("Filtrar por usuario", users)
    record_types = ["Todos"] + sorted(rows["record_type"].unique().tolist())
    selected_type = c2.selectbox("Filtrar por tipo de registro", record_types)
    filtered = rows.copy()
    if selected_user != "Todos": filtered = filtered[filtered["username"] == selected_user]
    if selected_type != "Todos": filtered = filtered[filtered["record_type"] == selected_type]
    st.dataframe(filtered[["changed_at", "username", "record_type", "record_id", "field_name", "old_value", "new_value", "action"]], hide_index=True, use_container_width=True)
