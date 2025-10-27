import os
import argparse
import sqlite3
from pathlib import Path

def create_log_db(db_path_str):
    """Create the SQLite database and initialize tables from SQL script."""
    db_path = Path(db_path_str).resolve()

    if db_path.exists():
        raise FileExistsError(f"DB already exists at {db_path}")

    sql_file = Path(os.path.dirname(__file__)) / "create_table.sql"

    if not sql_file.exists():
        raise FileNotFoundError(f"SQL schema not found at {sql_file}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sql_file.open() as fp:
        sql_script = fp.read()

    connection = sqlite3.connect(str(db_path))
    cursor = connection.cursor()
    cursor.executescript(sql_script)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize hpc_eff logging database")
    parser.add_argument("-o", "--output_db", type=Path, required=True, help="Output path for SQLite DB")
    args = parser.parse_args()

    create_log_db(args.output_db)
