import os
import configparser
import sys
from pathlib import Path
import sqlite3 
import argparse

from .utils.create_log_db import create_log_db
from .utils.controller import run_evaluation
from .utils.cron_control import enable_cron, disable_cron

# Convenience presets that map [MODE] control_mode to the [FEATURES] flags.
CONTROL_MODE_PRESETS = {
    "temperature": {"ENABLE_CPU_THERMO": "yes", "ENABLE_SET_CPU": "no"},
    "co2":         {"ENABLE_CPU_THERMO": "no",  "ENABLE_SET_CPU": "yes"},
    "both":        {"ENABLE_CPU_THERMO": "yes", "ENABLE_SET_CPU": "yes"},
}


CONFIG_PATH = "/etc/hpc_eff/config.ini"
if not os.path.isfile(CONFIG_PATH):
    CONFIG_PATH = "src/hpc_eff/config.ini.example"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

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

def resolve_control_mode(config):
    """Resolve the [MODE] control_mode preset into [FEATURES] flags.

    When [MODE] control_mode is set (temperature|co2|both) it *drives* the
    [FEATURES] flags, overriding any manual values. When [MODE] is absent or
    the value is unknown, the manual [FEATURES] flags are used unchanged
    (backward-compatible / power-user path).
    """
    mode = config.get("MODE", "control_mode", fallback=None)
    if not mode:
        return
    mode = mode.strip().lower()
    preset = CONTROL_MODE_PRESETS.get(mode)
    if preset is None:
        debug_log(f"Unknown control_mode '{mode}'; using [FEATURES] flags as-is")
        return
    if not config.has_section("FEATURES"):
        config.add_section("FEATURES")
    for key, value in preset.items():
        config.set("FEATURES", key, value)
    debug_log(f"control_mode='{mode}' applied -> FEATURES {preset}")

def main():
    debug_log("Starting HPC efficiency evaluator...")
    
    parser = argparse.ArgumentParser(prog="hpc-eff", description="HPC efficiency evaluator")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="Enable cronjob (/etc/cron.d/hpc-eff) to run every 10 minutes")
    group.add_argument("--disable", action="store_true", help="Disable cronjob and remove /etc/cron.d/hpc-eff")
    parser.add_argument("--cron-path", default="/etc/cron.d/hpc-eff", help="Path to cron file to create/remove")
    parser.add_argument("--cron-interval", type=int, default=10, help="Interval in minutes for cron schedule (1-60)")

    args, _ = parser.parse_known_args()

    if args.enable:
        try:
            enable_cron(cron_path=args.cron_path, command="/usr/bin/hpc-eff", interval_minutes=args.cron_interval)
            print(f"Cronjob enabled at {args.cron_path}")
        except PermissionError:
            print("Permission denied: enabling cron requires root. Run with sudo.")
            raise
        return

    if args.disable:
        try:
            disable_cron(cron_path=args.cron_path)
            print(f"Cronjob disabled and {args.cron_path} removed (if existed)")
        except PermissionError:
            print("Permission denied: disabling cron requires root. Run with sudo.")
            raise
        return

    # Resolve [MODE] preset into [FEATURES] flags, then delegate to controller
    resolve_control_mode(config)
    run_evaluation(conn, config, static_context, debug_log)

if __name__ == "__main__":
    main()
    conn.close()
