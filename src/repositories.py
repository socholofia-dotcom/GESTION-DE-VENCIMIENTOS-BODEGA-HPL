from typing import Any
import hashlib
import hmac
import os

from .database import transaction

PRODUCT_FIELDS = {
    "product_status", "report_month", "origin", "product_type", "reyimen_code",
    "description", "unit", "quantity", "expiration_date", "lot", "report_reason",
    "purchase_type", "exchange_policy", "withdrawal_deadline", "alert_status",
    "procedure_status", "document_number", "document_type", "supplier_name",
    "supplier_contact", "supplier_email", "package_status", "physical_location",
    "computer_location", "final_resolution", "observations", "network_dissemination",
    "stock_redistribution", "successful_managed_quantity", "estimated_unit_cost",
}


def hash_password(password: str) -> bytes:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return b"pbkdf2_sha256$600000$" + salt.hex().encode() + b"$" + digest.hex().encode()


def verify_password(password: str, password_hash: bytes) -> bool:
    algorithm, iterations, salt_hex, digest_hex = bytes(password_hash).split(b"$")
    if algorithm != b"pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex.decode()), int(iterations)
    )
    return hmac.compare_digest(candidate, bytes.fromhex(digest_hex.decode()))


def create_user(username: str, password: str, full_name: str, role: str) -> int:
    with transaction() as connection:
        cursor = connection.execute(
            "INSERT INTO users(username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (username.strip(), hash_password(password), full_name.strip(), role),
        )
        return int(cursor.lastrowid)


def list_users():
    with transaction() as connection:
        return connection.execute(
            "SELECT id, username, full_name, role, active, created_at, updated_at FROM users ORDER BY full_name"
        ).fetchall()


def set_user_active(user_id: int, active: bool, actor: dict[str, Any]) -> None:
    if user_id == actor["id"] and not active:
        raise ValueError("No puede desactivar su propia cuenta durante la sesión.")
    with transaction() as connection:
        target = connection.execute("SELECT username, active FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ValueError("El usuario no existe.")
        connection.execute(
            "UPDATE users SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (int(active), user_id)
        )
        connection.execute(
            """INSERT INTO audit_log
               (user_id, username, record_type, record_id, field_name, old_value, new_value, action)
               VALUES (?, ?, 'user', ?, 'active', ?, ?, ?)""",
            (actor["id"], actor["username"], user_id, str(target["active"]), str(int(active)),
             "UPDATE" if active else "DEACTIVATE"),
        )


def get_user_by_username(username: str):
    with transaction() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
        ).fetchone()


def ensure_admin(username: str, password: str) -> None:
    if get_user_by_username(username) is None:
        create_user(username, password, "Administrador inicial", "Administrador")


def create_product(data: dict[str, Any], user: dict[str, Any]) -> int:
    unknown = set(data) - PRODUCT_FIELDS
    if unknown:
        raise ValueError(f"Campos de producto no permitidos: {', '.join(sorted(unknown))}")
    fields = list(data)
    values = [data[field] for field in fields]
    with transaction() as connection:
        cursor = connection.execute(
            f"INSERT INTO products ({', '.join(fields)}, created_by, updated_by) "
            f"VALUES ({', '.join(['?'] * (len(fields) + 2))})",
            (*values, user["id"], user["id"]),
        )
        record_id = int(cursor.lastrowid)
        for field, value in data.items():
            connection.execute(
                """INSERT INTO audit_log
                   (user_id, username, record_id, field_name, old_value, new_value, action)
                   VALUES (?, ?, ?, ?, NULL, ?, 'CREATE')""",
                (user["id"], user["username"], record_id, field, str(value)),
            )
        return record_id


def update_product(record_id: int, changes: dict[str, Any], user: dict[str, Any]) -> None:
    """Actualiza solo campos modificados y genera una línea de auditoría por campo."""
    if not changes:
        return
    unknown = set(changes) - PRODUCT_FIELDS
    if unknown:
        raise ValueError(f"Campos de producto no permitidos: {', '.join(sorted(unknown))}")
    with transaction() as connection:
        current = connection.execute("SELECT * FROM products WHERE id = ?", (record_id,)).fetchone()
        if current is None:
            raise ValueError("El producto solicitado no existe.")

        effective = {key: value for key, value in changes.items() if str(current[key] or "") != str(value or "")}
        if not effective:
            return
        assignments = ", ".join(f"{field} = ?" for field in effective)
        connection.execute(
            f"UPDATE products SET {assignments}, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*effective.values(), user["id"], record_id),
        )
        for field, new_value in effective.items():
            connection.execute(
                """INSERT INTO audit_log
                   (user_id, username, record_id, field_name, old_value, new_value, action)
                   VALUES (?, ?, ?, ?, ?, ?, 'UPDATE')""",
                (user["id"], user["username"], record_id, field, str(current[field] or ""), str(new_value or "")),
            )


def list_products():
    with transaction() as connection:
        return connection.execute("SELECT * FROM products ORDER BY expiration_date, description").fetchall()


def get_product(record_id: int):
    with transaction() as connection:
        return connection.execute("SELECT * FROM products WHERE id = ?", (record_id,)).fetchone()


def list_audit(record_id: int | None = None):
    with transaction() as connection:
        if record_id is None:
            return connection.execute("SELECT * FROM audit_log ORDER BY changed_at DESC, id DESC").fetchall()
        return connection.execute(
            "SELECT * FROM audit_log WHERE record_id = ? ORDER BY changed_at DESC, id DESC", (record_id,)
        ).fetchall()
