import os
import configparser
import sys
from pathlib import Path
import sqlite3 

from .utils.create_log_db import create_log_db
from .utils.controller import run_evaluation

CONFIG_PATH = "/etc/hpc_eff/config.ini"
if not os.path.isfile(CONFIG_PATH):
    CONFIG_PATH = "src/hpc_eff/config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

API_HEADERS = {
    'User-Agent': config['API']['USER_AGENT'],
    'X-Api-Key': config['API']['API_KEY']
}

DB_PATH_STR = config.get("logging", "db_path", fallback="history.db")
DB_PATH = Path(DB_PATH_STR).resolve()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if not DB_PATH.exists():
    print(f"DB not found; creating {DB_PATH}")
    create_log_db(DB_PATH)

conn = sqlite3.connect(DB_PATH_STR)
conn.execute("PRAGMA journal_mode=WAL;")

power_cmd = config.get("SYSTEM", "POWERREADINGCMD", fallback="")
static_context = {
    "score_name": config.get("SYSTEM", "SCORENAME", fallback="unknown"),
    "score_value": config.getfloat("SYSTEM", "SCORE", fallback=None),
    "power_cmd": power_cmd,
    "plugins": {
        "power": "power_reader.py",
        "price": "energy_price.py",
        "co2": "co2_value.py",
        "temperature": "cpu_thermo.py"
    }
}

debug = config.get("SYSTEM", "DEBUG", fallback="no").lower() == "yes"


def debug_log(message):
    """Log message if debugging is enabled."""
    if debug:
        print(f"[DEBUG] {message}")


# temperature threshold used as forced limit fallback
temp_threshold = config.getint("TEMPERATURE", "THRESHOLD", fallback=80)


def main():
    debug_log("Starting HPC efficiency evaluator...")

    # Delegate evaluation and actions to controller
    run_evaluation(conn, config, static_context, debug_log)


if __name__ == "__main__":
    main()
    conn.close()
