from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Dict

import pandas as pd
import sqlite3

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"

DB_FILES: Dict[str, str] = {
    "clientes_db": "clientes.db",
    "estimador_db": "estimador_ing.db",
    "fiducuenta_db": "crean_fiducuenta.db",
    "invesbot_db": "invesbot.db",
    "aho_db": "crean_aho_cte.db",
    "bolsillos_db": "crean_bolsillos.db",
    "cdt_db": "crean_inv_virtual_cdt.db",
}


def resolve_data_dir() -> Path:
    for candidate in [ROOT / "02_Datos", ROOT / "datos_2"]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No se encontro la carpeta de datos (02_Datos o datos_2)")


def _main_table_name(conn: sqlite3.Connection, schema_alias: str) -> str:
    rows = conn.execute(
        f"SELECT name FROM {schema_alias}.sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    if not rows:
        raise ValueError(f"No hay tablas en '{schema_alias}'")
    return rows[0][0]


def _attach_all(conn: sqlite3.Connection, data_dir: Path) -> Dict[str, str]:
    attached: Dict[str, str] = {}
    for alias, filename in DB_FILES.items():
        db_path = data_dir / filename
        if not db_path.exists():
            raise FileNotFoundError(f"No existe: {db_path}")
        conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(db_path),))
        attached[alias] = _main_table_name(conn, alias)
    return attached


@contextmanager
def open_ecosystem(data_dir: Path | None = None):
    data_dir = data_dir or resolve_data_dir()
    conn = sqlite3.connect(":memory:")
    try:
        yield conn, _attach_all(conn, data_dir)
    finally:
        conn.close()
