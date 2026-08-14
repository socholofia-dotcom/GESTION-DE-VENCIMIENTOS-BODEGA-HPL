from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any
import math

import pandas as pd

from .repositories import create_product

TEMPLATE_COLUMNS = [
    "Estado del Producto", "Mes de informe", "Bodega/Farmacia origen", "Tipo de producto",
    "Código Reyimen", "Descripción", "Unidad", "Cantidad", "Vencimiento", "Lote",
    "Motivo de informe", "Tipo de compra", "Costo unitario estimado",
]

COLUMN_MAP = {
    "Estado del Producto": "product_status", "Mes de informe": "report_month",
    "Bodega/Farmacia origen": "origin", "Tipo de producto": "product_type",
    "Código Reyimen": "reyimen_code", "Descripción": "description", "Unidad": "unit",
    "Cantidad": "quantity", "Vencimiento": "expiration_date", "Lote": "lot",
    "Motivo de informe": "report_reason", "Tipo de compra": "purchase_type",
    "Costo unitario estimado": "estimated_unit_cost",
}

REQUIRED_COLUMNS = set(TEMPLATE_COLUMNS[:-1])


def template_bytes() -> bytes:
    example = pd.DataFrame([{
        "Estado del Producto": "En revisión", "Mes de informe": "2026-08",
        "Bodega/Farmacia origen": "Farmacia", "Tipo de producto": "Fármaco",
        "Código Reyimen": "100001052", "Descripción": "Producto de ejemplo",
        "Unidad": "AMPOLLA", "Cantidad": 100, "Vencimiento": date(2026, 12, 31),
        "Lote": "LOTE-001", "Motivo de informe": "Próximo vencimiento",
        "Tipo de compra": "CENABAST", "Costo unitario estimado": 0,
    }])
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        example.to_excel(writer, index=False, sheet_name="Carga Paso 1")
    return output.getvalue()


def read_upload(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, sep=None, engine="python")
    if name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file)
    raise ValueError("Formato no admitido. Use un archivo .xlsx o .csv.")


def _text(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _date_iso(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.date().isoformat()


def validate_rows(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        return [], [f"Faltan columnas obligatorias: {', '.join(sorted(missing))}"]
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, row in frame.iterrows():
        line = index + 2
        try:
            data = {target: _text(row[source]) for source, target in COLUMN_MAP.items() if source in frame.columns}
            data["quantity"] = float(row["Cantidad"])
            raw_cost = row.get("Costo unitario estimado", 0)
            data["estimated_unit_cost"] = 0.0 if pd.isna(raw_cost) else float(raw_cost)
            data["expiration_date"] = _date_iso(row["Vencimiento"])
            report_month = pd.to_datetime(row["Mes de informe"], errors="raise")
            data["report_month"] = report_month.strftime("%Y-%m")
            if data["product_status"] not in {"En revisión", "Concluido"}:
                raise ValueError("Estado del Producto inválido")
            if data["product_type"] not in {"Fármaco", "Insumo"}:
                raise ValueError("Tipo de producto inválido")
            if data["purchase_type"] not in {"CENABAST", "Compra Propia"}:
                raise ValueError("Tipo de compra inválido")
            if not math.isfinite(data["quantity"]) or not math.isfinite(data["estimated_unit_cost"]):
                raise ValueError("Cantidad y costo deben ser números válidos")
            if data["quantity"] < 0 or data["estimated_unit_cost"] < 0:
                raise ValueError("Cantidad y costo no pueden ser negativos")
            required_values = [data[COLUMN_MAP[column]] for column in REQUIRED_COLUMNS]
            if any(value == "" for value in required_values):
                raise ValueError("hay campos obligatorios vacíos")
            key = (data["reyimen_code"], data["lot"], data["expiration_date"], data["origin"])
            if key in seen:
                raise ValueError("registro duplicado dentro del archivo")
            seen.add(key)
            valid.append(data)
        except Exception as exc:
            errors.append(f"Fila {line}: {exc}")
    return valid, errors


def import_rows(rows: list[dict[str, Any]], user: dict[str, Any]) -> tuple[int, list[str]]:
    imported = 0
    errors: list[str] = []
    for index, data in enumerate(rows, start=2):
        try:
            create_product(data, user)
            imported += 1
        except Exception as exc:
            errors.append(f"Fila {index}: {exc}")
    return imported, errors
