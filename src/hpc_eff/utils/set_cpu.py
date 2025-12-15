import subprocess
import socket
from datetime import datetime
import sqlite3
import configparser
import logging

config = configparser.ConfigParser()
config.read("/etc/hpc_eff/config.ini")
logging.basicConfig(
    level=config.get("logging", "log_level", fallback="INFO"),
    format="%(asctime)s %(levelname)-8s | %(message)s",
    force=True
)

logger = logging.getLogger("hpc_eff")

def get_cpu_type():
    try:
        cpuinfo = subprocess.check_output(["cat", "/proc/cpuinfo"], text=True).upper()
        model_line = [l for l in cpuinfo.splitlines() if "MODEL NAME" in l][0]
    except Exception:
        return "default"

    model = model_line.split(":", 1)[1].strip() if ":" in model_line else ""

    if "EPYC" in model:
        return "amd_epyc"

    if "E5-" in model and "V3" in model:
        return "intel_e5"

    if "GOLD" in model:
        return "intel_xeon_gold"

    return "default"

def set_cpu_freq(number, conn=None, **context):
    """
    Selects CPU frequency based on input number (1-10) and available frequencies.

    Parameters:
    - number (int): Value from 1 to 10.
    - freqs (list[int]): List of available frequencies in MHz
                         (e.g. [800, 1200, 1600, 2400]).

    Rules:
    - 1 (cheapest) maps to the highest available frequency.
    - 10 maps to the lowest available frequency.
    - Values in between are scaled dynamically.
    - Uses cpupower frequency-set to set max frequency.

    Prints the command(s) instead of executing them.
    """
    try:
        if not (1 <= number <= 10):
            raise ValueError("Number must be between 1 and 10.")

        config = configparser.ConfigParser()
        config.read('/etc/hpc_eff/config.ini')

        cpu_type = get_cpu_type()
        freq_list = config.get('frequency_tables', cpu_type, fallback=config.get('frequency_tables', 'default')).split(',')
        freq_list = [int(f.strip()) for f in freq_list]

        scale = (number - 1) / 9.0
        index = int(round(scale * (len(freq_list) - 1)))
        selected_freq_mhz = sorted(freq_list, reverse=True)[index]
        selected_freq_khz = selected_freq_mhz * 1000
       
        command = ["cpupower", "frequency-set", "-u", f"{selected_freq_khz}"]
        subprocess.run(command, check=True)
        logger.info(f"Command to be executed: {' '.join(command)}")
        if conn:
            log_setting(conn, freq_min=0, freq_max=selected_freq_khz, **context)

    except ValueError as e:
        logger.error(f"Error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

def log_setting(conn, **kwargs):
    """Log full context into SQLite using the new schema."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cpu_settings_log
            (timestamp, hostname, freq_min, freq_max, score_name, score_value, price,
             co2_current, co2_median, co2_grade, power_w, cpu_freq_current, rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            socket.gethostname(),
            kwargs.get('freq_min'),
            kwargs.get('freq_max'),
            kwargs.get('score_name'),
            kwargs.get('score_value'),
            kwargs.get('price'),
            kwargs.get('co2_current'),
            kwargs.get('co2_median'),
            kwargs.get('co2_grade'),
            kwargs.get('power_w'),
            kwargs.get('cpu_freq_current'),
            kwargs.get('rating'),
        ))
        conn.commit()
        logger.info("DB log entry inserted")
    except Exception as e:
        logger.error(f"DB insert failed: {e}")
        raise
