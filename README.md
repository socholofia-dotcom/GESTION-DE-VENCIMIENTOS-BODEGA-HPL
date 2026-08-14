# Gestión proactiva de productos con pronto vencimiento

Aplicación modular en Python y Streamlit para registrar, tramitar y resolver productos farmacéuticos e insumos con riesgo de vencimiento.

## Funcionalidades incluidas

- Login y permisos por rol para los Pasos 1 a 5.
- Formularios de creación y actualización con auditoría por campo.
- Dashboard con KPIs, semáforo, gráficos y alertas urgentes.
- Gestión de usuarios para Jefatura y Administrador.
- Importación masiva validada desde Excel o CSV y plantilla descargable.
- Historial Bincard con filtros por usuario y tipo de registro.

## Inicio rápido

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

La base `data/gestion_vencimientos.db` se crea automáticamente en el primer inicio.

## Acceso inicial

- Usuario: `admin`
- Contraseña: `Cambiar123!`

Cambie esta contraseña antes de usar el sistema con datos reales. En producción, configure `APP_ADMIN_PASSWORD` como secreto del despliegue.

## Estructura

```text
gestion_vencimientos/
├── app.py
├── requirements.txt
├── data/                       # Base SQLite local (no versionada)
├── scripts/
│   └── init_db.py
└── src/
    ├── auth.py                 # Login, sesión y permisos
    ├── config.py               # Configuración central
    ├── database.py             # Conexión, esquema y transacciones
    ├── importer.py             # Plantilla y carga masiva Excel/CSV
    ├── permissions.py          # Matriz de roles por paso
    ├── repositories.py         # Acceso a usuarios, productos y auditoría
    ├── risk.py                 # Meses por vencer y semáforo
    └── ui.py                   # Dashboard, formularios y paneles
```

## Despliegue en Streamlit Community Cloud

1. Suba esta carpeta a un repositorio privado de GitHub.
2. En Streamlit Community Cloud seleccione `app.py` como archivo principal.
3. Agregue `APP_ADMIN_PASSWORD` en Secrets.

> SQLite funciona para el prototipo académico y despliegues de baja concurrencia. En Streamlit Community Cloud el disco puede reiniciarse; para producción se recomienda migrar la misma capa de repositorios a PostgreSQL/Supabase.
