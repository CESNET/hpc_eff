import sqlite3
from pathlib import Path

def create_log_db(db_path: Path) -> None:
    """Create the SQLite database and initialize tables from SQL script."""

    sql_file = Path(__file__).parent / "create_table.sql"
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL schema not found at {sql_file}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with open(sql_file) as fp:
        sql_script = fp.read()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(sql_script)
    conn.commit()
    conn.close()

    print(f"Database created successfully at {db_path}")
