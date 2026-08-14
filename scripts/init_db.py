from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, DB_PATH
from src.database import initialize_database
from src.repositories import ensure_admin


if __name__ == "__main__":
    initialize_database()
    ensure_admin(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
    print(f"Base inicializada correctamente: {DB_PATH}")

