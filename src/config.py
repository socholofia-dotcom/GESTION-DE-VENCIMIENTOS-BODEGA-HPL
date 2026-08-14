from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("APP_DB_PATH", DATA_DIR / "gestion_vencimientos.db"))
DEFAULT_ADMIN_USERNAME = os.getenv("APP_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("APP_ADMIN_PASSWORD", "Cambiar123!")

APP_TITLE = "Gestión proactiva de productos con pronto vencimiento"

