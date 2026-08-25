"""
Base de datos para favoritos, estado de la app, y operaciones en seguimiento.

Dos modos, sin cambiar nada del resto del código:

1. LOCAL (por defecto, sin configurar nada): guarda en un archivo
   crypto_dashboard.db dentro del propio contenedor/teléfono. Funciona bien
   en Termux. En Streamlit Cloud, sobrevive mientras la app siga corriendo,
   pero un "Reboot" o redeploy grande puede borrarlo.

2. TURSO (recomendado para producción, gratis): si configuras
   TURSO_DATABASE_URL y TURSO_AUTH_TOKEN (en config.py, igual que el token
   de Telegram -- nunca hardcodeados en el repo), la base de datos vive en
   la nube de Turso (basado en SQLite/libSQL) y sobrevive a cualquier
   reinicio de Streamlit Cloud.

Cómo activar el modo Turso (gratis, ~5 minutos):
  1. Crea una cuenta en https://turso.tech
  2. Crea una base de datos (botón "Create Database" en el dashboard)
  3. Copia la "Database URL" (empieza con libsql://...)
  4. Genera un "Auth Token" desde el dashboard de esa base de datos
  5. Agrega esos dos valores como secrets (igual que hiciste con Telegram):
     TURSO_DATABASE_URL = "libsql://tu-db-tu-usuario.turso.io"
     TURSO_AUTH_TOKEN = "tu_token_aqui"
"""
import json
from datetime import datetime, timezone
import libsql_client

try:
    import config
    _TURSO_URL = getattr(config, "TURSO_DATABASE_URL", "")
    _TURSO_TOKEN = getattr(config, "TURSO_AUTH_TOKEN", "")
except Exception:
    _TURSO_URL = ""
    _TURSO_TOKEN = ""

LOCAL_DB_PATH = "file:crypto_dashboard.db"


def _get_client():
    if _TURSO_URL:
        # El esquema libsql:// equivale a wss:// (WebSocket) en el cliente
        # de Python. Streamlit Cloud bloquea/interfiere con WebSockets
        # salientes, así que forzamos https:// (protocolo HTTP de Hrana),
        # más compatible con entornos cloud restringidos.
        url = _TURSO_URL.replace("libsql://", "https://", 1)
        return libsql_client.create_client_sync(url=url, auth_token=_TURSO_TOKEN)
    return libsql_client.create_client_sync(LOCAL_DB_PATH)


def _rows_as_dicts(result_set):
    return [dict(zip(result_set.columns, row)) for row in result_set.rows]


def init_db(default_symbols=None):
    with _get_client() as c:
        c.execute("CREATE TABLE IF NOT EXISTS favorites (symbol TEXT PRIMARY KEY)")
        c.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry REAL NOT NULL,
                stop REAL NOT NULL,
                tp REAL NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                outcome TEXT,
                close_price REAL,
                pnl_pct REAL,
                early_warning_sent INTEGER DEFAULT 0
            )
        """)
        if default_symbols:
            existing = c.execute("SELECT COUNT(*) AS n FROM favorites").rows[0][0]
            if existing == 0:
                for s in default_symbols:
                    c.execute("INSERT OR IGNORE INTO favorites (symbol) VALUES (?)", [s])


# --- Favoritos ---
def get_favorites() -> list:
    with _get_client() as c:
        rs = c.execute("SELECT symbol FROM favorites ORDER BY symbol")
        return [row[0] for row in rs.rows]


def add_favorite(symbol: str):
    with _get_client() as c:
        c.execute("INSERT OR IGNORE INTO favorites (symbol) VALUES (?)", [symbol.upper()])


def remove_favorite(symbol: str):
    with _get_client() as c:
        c.execute("DELETE FROM favorites WHERE symbol = ?", [symbol.upper()])


# --- Estado simple ---
def get_state(key: str, default=None):
    with _get_client() as c:
        rs = c.execute("SELECT value FROM app_state WHERE key = ?", [key])
        return rs.rows[0][0] if rs.rows else default


def set_state(key: str, value: str):
    with _get_client() as c:
        c.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [key, value],
        )


# --- Operaciones en seguimiento ---
def create_operation(symbol, direction, entry, stop, tp) -> int:
    with _get_client() as c:
        rs = c.execute(
            "INSERT INTO operations (symbol, direction, entry, stop, tp, opened_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'open') RETURNING id",
            [symbol, direction, entry, stop, tp, datetime.now(timezone.utc).isoformat()],
        )
        return rs.rows[0][0]


def get_open_operations() -> list:
    with _get_client() as c:
        rs = c.execute("SELECT * FROM operations WHERE status = 'open' ORDER BY opened_at")
        return _rows_as_dicts(rs)


def get_operation_history(limit: int = 20) -> list:
    with _get_client() as c:
        rs = c.execute(
            "SELECT * FROM operations WHERE status = 'closed' ORDER BY closed_at DESC LIMIT ?", [limit]
        )
        return _rows_as_dicts(rs)


def close_operation(op_id: int, close_price: float, outcome: str):
    with _get_client() as c:
        rs = c.execute("SELECT * FROM operations WHERE id = ?", [op_id])
        rows = _rows_as_dicts(rs)
        if not rows:
            return
        op = rows[0]
        if op["direction"] == "COMPRA":
            pnl_pct = (close_price - op["entry"]) / op["entry"] * 100
        else:
            pnl_pct = (op["entry"] - close_price) / op["entry"] * 100
        c.execute(
            "UPDATE operations SET status='closed', closed_at=?, outcome=?, close_price=?, pnl_pct=? WHERE id=?",
            [datetime.now(timezone.utc).isoformat(), outcome, close_price, pnl_pct, op_id],
        )


def mark_early_warning_sent(op_id: int):
    with _get_client() as c:
        c.execute("UPDATE operations SET early_warning_sent = 1 WHERE id = ?", [op_id])


# --- Respaldo ---
def export_backup() -> str:
    with _get_client() as c:
        favorites = [row[0] for row in c.execute("SELECT symbol FROM favorites").rows]
        state_rs = c.execute("SELECT key, value FROM app_state")
        state = {row[0]: row[1] for row in state_rs.rows}
        operations = _rows_as_dicts(c.execute("SELECT * FROM operations"))
    return json.dumps({"favorites": favorites, "state": state, "operations": operations}, indent=2)


def import_backup(json_text: str):
    data = json.loads(json_text)
    with _get_client() as c:
        for s in data.get("favorites", []):
            c.execute("INSERT OR IGNORE INTO favorites (symbol) VALUES (?)", [s])
        for k, v in data.get("state", {}).items():
            c.execute(
                "INSERT INTO app_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [k, v],
            )
        for op in data.get("operations", []):
            existing = c.execute("SELECT id FROM operations WHERE id = ?", [op["id"]])
            if existing.rows:
                continue
            c.execute(
                "INSERT INTO operations (id, symbol, direction, entry, stop, tp, opened_at, closed_at, "
                "status, outcome, close_price, pnl_pct, early_warning_sent) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [op["id"], op["symbol"], op["direction"], op["entry"], op["stop"], op["tp"],
                 op["opened_at"], op.get("closed_at"), op["status"], op.get("outcome"),
                 op.get("close_price"), op.get("pnl_pct"), op.get("early_warning_sent", 0)],
            )
