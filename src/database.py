import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash BLOB NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN (
        'Encargado de Bodega / Farmacia', 'Jefatura', 'Área de Registro',
        'Encargado Bodega de Excluidos', 'Administrador'
    )),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_status TEXT NOT NULL DEFAULT 'En revisión'
        CHECK (product_status IN ('En revisión', 'Concluido')),
    report_month TEXT NOT NULL,
    origin TEXT NOT NULL,
    product_type TEXT NOT NULL CHECK (product_type IN ('Fármaco', 'Insumo')),
    reyimen_code TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity >= 0),
    expiration_date TEXT NOT NULL,
    lot TEXT NOT NULL,
    report_reason TEXT NOT NULL,
    purchase_type TEXT NOT NULL CHECK (purchase_type IN ('CENABAST', 'Compra Propia')),

    exchange_policy TEXT CHECK (exchange_policy IN ('Con política', 'Sin política')),
    withdrawal_deadline TEXT,

    alert_status TEXT,
    procedure_status TEXT,
    document_number TEXT,
    document_type TEXT,
    supplier_name TEXT,
    supplier_contact TEXT,
    supplier_email TEXT,

    package_status TEXT CHECK (
        package_status IS NULL OR package_status IN ('Armado', 'Preparado', 'En bodega activa')
    ),
    physical_location TEXT,
    computer_location TEXT,

    final_resolution TEXT,
    observations TEXT,
    network_dissemination TEXT,
    stock_redistribution TEXT,
    successful_managed_quantity REAL NOT NULL DEFAULT 0 CHECK (successful_managed_quantity >= 0),
    estimated_unit_cost REAL NOT NULL DEFAULT 0 CHECK (estimated_unit_cost >= 0),

    created_by INTEGER NOT NULL REFERENCES users(id),
    updated_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (reyimen_code, lot, expiration_date, origin)
);

CREATE INDEX IF NOT EXISTS idx_products_expiration ON products(expiration_date);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(product_status);
CREATE INDEX IF NOT EXISTS idx_products_procedure ON products(procedure_status);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER NOT NULL REFERENCES users(id),
    username TEXT NOT NULL,
    record_type TEXT NOT NULL DEFAULT 'product',
    record_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    action TEXT NOT NULL CHECK (action IN ('CREATE', 'UPDATE', 'DEACTIVATE'))
);

CREATE INDEX IF NOT EXISTS idx_audit_record ON audit_log(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON audit_log(changed_at);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(db_path: Path = DB_PATH):
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: Path = DB_PATH) -> None:
    with transaction(db_path) as connection:
        connection.executescript(SCHEMA)

