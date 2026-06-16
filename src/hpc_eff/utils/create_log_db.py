import sqlite3
from pathlib import Path

_SQL_FILE = Path(__file__).parent / "create_table.sql"

_TABLE = "cpu_settings_log"


def _expected_columns(sql_script: str) -> list[tuple[str, str]]:
    """Return [(name, type), ...] for the canonical table, as SQLite parses it.

    Builds the table in an in-memory database from the same SQL the real DB
    uses, then reads it back via PRAGMA. This keeps create_table.sql as the
    single source of truth -- no column list is duplicated here.
    """
    mem = sqlite3.connect(":memory:")
    try:
        mem.executescript(sql_script)
        rows = mem.execute(f"PRAGMA table_info({_TABLE})").fetchall()
    finally:
        mem.close()
    # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
    return [(row[1], row[2]) for row in rows]


def _migrate_columns(conn: sqlite3.Connection, sql_script: str) -> None:
    """Add any expected columns missing from an existing cpu_settings_log table."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}
    if not existing:
        # Table doesn't exist yet; the CREATE TABLE statement handles it.
        return
    for name, col_type in _expected_columns(sql_script):
        if name not in existing:
            conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {name} {col_type}")


def create_log_db(db_path: Path) -> None:
    """Create the SQLite database and initialize/migrate tables from SQL script."""

    if not _SQL_FILE.exists():
        raise FileNotFoundError(f"SQL schema not found at {_SQL_FILE}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    sql_script = _SQL_FILE.read_text()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(sql_script)
    _migrate_columns(conn, sql_script)
    conn.commit()
    conn.close()

    print(f"Database ready at {db_path}")


def _db_path_from_config() -> Path:
    """Resolve the DB path the same way main.py does."""
    import configparser
    import os

    config_path = "/etc/hpc_eff/config.ini"
    if not os.path.isfile(config_path):
        config_path = "src/hpc_eff/config.ini.example"

    config = configparser.ConfigParser()
    config.read(config_path)
    return Path(config.get("logging", "db_path", fallback="history.db")).resolve()


if __name__ == "__main__":
    create_log_db(_db_path_from_config())
