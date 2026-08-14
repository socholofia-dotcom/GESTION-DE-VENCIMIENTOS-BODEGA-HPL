"""Carga resiliente del catálogo institucional Reyimen."""

from __future__ import annotations

import base64
from io import StringIO
from pathlib import Path
import zlib

import pandas as pd

from .catalogo_base import CATALOGO_REYIMEN_ZLIB_BASE64


CATALOG_COLUMNS = ["codigo_reyimen", "descripcion", "unidad", "precio_unitario", "bodega"]
SOURCE_COLUMNS = {
    "CODIGO REYIMEN": "codigo_reyimen",
    "DESCRIPCION PRODUCTO": "descripcion",
    "UNIDAD MEDIDA": "unidad",
    "PRECIO UNITARIO": "precio_unitario",
    "BODEGA": "bodega",
}
PREFERRED_INVENTORY_NAMES = [
    "CONTROL_DE_INVENTARIO_POR_ESTABLECIMIENTO_Hospital Penco Lirquén - 2026-08-14T122914.040.xlsx",
    "CONTROL_DE_INVENTARIO_POR_ESTABLECIMIENTO_Hospital Penco Lirquén - 2026-08-14T122914.040.xls",
    "inventario.xlsx",
    "inventario.xls",
]


def _normalize_catalog(frame: pd.DataFrame) -> pd.DataFrame:
    normalized_headers = {str(column).strip().upper(): column for column in frame.columns}
    if set(SOURCE_COLUMNS).issubset(normalized_headers):
        frame = frame.rename(
            columns={normalized_headers[source]: target for source, target in SOURCE_COLUMNS.items()}
        )
    missing = set(CATALOG_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"faltan columnas requeridas: {', '.join(sorted(missing))}")

    catalog = frame[CATALOG_COLUMNS].copy()
    catalog = catalog[catalog["codigo_reyimen"].notna()]
    catalog["codigo_reyimen"] = (
        catalog["codigo_reyimen"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    )
    catalog = catalog[~catalog["codigo_reyimen"].str.upper().isin({"TOTAL", "TOTAL:"})]
    for column in ["descripcion", "unidad", "bodega"]:
        catalog[column] = catalog[column].fillna("").astype(str).str.strip()
    catalog["precio_unitario"] = pd.to_numeric(catalog["precio_unitario"], errors="coerce")
    catalog = catalog[
        catalog["codigo_reyimen"].ne("")
        & catalog["descripcion"].ne("")
        & catalog["unidad"].ne("")
        & catalog["bodega"].ne("")
    ]
    catalog = catalog.drop_duplicates(CATALOG_COLUMNS).sort_values(
        ["bodega", "descripcion", "codigo_reyimen"], kind="stable"
    )
    if catalog.empty:
        raise ValueError("el archivo no contiene productos válidos")
    return catalog.reset_index(drop=True)


def _find_header_row(path: Path) -> int:
    preview = pd.read_excel(path, sheet_name=0, header=None, nrows=30)
    for index, row in preview.iterrows():
        values = {str(value).strip().upper() for value in row if pd.notna(value)}
        if set(SOURCE_COLUMNS).issubset(values):
            return int(index)
    raise ValueError("no se encontró la fila de encabezados del inventario")


def _read_inventory(path: Path) -> pd.DataFrame:
    try:
        header_row = _find_header_row(path)
        return _normalize_catalog(pd.read_excel(path, sheet_name=0, header=header_row))
    except Exception as excel_error:
        # Algunos sistemas entregan un .xls que realmente es una tabla HTML.
        try:
            for table in pd.read_html(path):
                try:
                    return _normalize_catalog(table)
                except ValueError:
                    continue
        except Exception:
            pass
        raise ValueError(str(excel_error)) from excel_error


def _inventory_candidates(project_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in PREFERRED_INVENTORY_NAMES:
        candidate = project_root / name
        if candidate.exists():
            candidates.append(candidate)
    for pattern in ["CONTROL_DE_INVENTARIO*.xlsx", "CONTROL_DE_INVENTARIO*.xls", "*inventario*.xlsx", "*inventario*.xls"]:
        for candidate in sorted(project_root.glob(pattern)):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _embedded_catalog() -> pd.DataFrame:
    compressed = base64.b64decode(CATALOGO_REYIMEN_ZLIB_BASE64)
    csv_text = zlib.decompress(compressed).decode("utf-8")
    return _normalize_catalog(pd.read_csv(StringIO(csv_text), dtype={"codigo_reyimen": str}))


def load_catalog(project_root: Path) -> tuple[pd.DataFrame, str, list[str]]:
    """Devuelve catálogo, fuente utilizada y advertencias de lectura.

    Prioridad: inventario en la raíz, CSV normalizado y respaldo Python.
    """
    warnings: list[str] = []
    for candidate in _inventory_candidates(project_root):
        try:
            return _read_inventory(candidate), f"Inventario raíz: {candidate.name}", warnings
        except Exception as error:
            warnings.append(f"{candidate.name}: {error}")

    csv_path = project_root / "data" / "catalogo_reyimen.csv"
    if csv_path.exists():
        try:
            catalog = pd.read_csv(csv_path, dtype={"codigo_reyimen": str})
            return _normalize_catalog(catalog), "CSV normalizado del proyecto", warnings
        except Exception as error:
            warnings.append(f"{csv_path.name}: {error}")

    return _embedded_catalog(), "Catálogo base integrado en Python", warnings
