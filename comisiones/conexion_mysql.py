import mysql.connector
from mysql.connector import Error

# === CONFIGURACIÓN RAILWAY ===
DB_CONFIG = {
    "host": "yamanote.proxy.rlwy.net",
    "user": "root",
    "password": "ROEtoKkghFtmkUjJfPVQzHlvwFcHnCJn",  # la que me diste
    "database": "railway",
    "port": 27508
}

def crear_conexion():
    """Crea y retorna una conexión MySQL válida (Railway)."""
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        if conexion.is_connected():
            print("✅ Conectado correctamente a Railway MySQL")
        return conexion
    except Error as e:
        print(f"❌ Error al conectar a MySQL: {e}")
        return None
