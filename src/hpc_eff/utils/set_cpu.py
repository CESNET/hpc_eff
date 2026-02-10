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

def get_freq_list(config):
    """
    Retrieves the frequency list for the current CPU type from the config.
    """
    cpu_type = get_cpu_type()
    try:
        # Get frequency table for CPU type, fallback to default
        freq_str = config.get('frequency_tables', cpu_type, fallback=config.get('frequency_tables', 'default'))
    except Exception:
        # Last resort fallback
        freq_str = "3000,2800,2700,2600,2400,2200"

    return [int(f.strip()) for f in freq_str.split(',')]

def calculate_selected_freq(number, freq_list):
    """
    Calculates the target frequency (in kHz) based on the rating (1-10).
    """
    if not (1 <= number <= 10):
        raise ValueError("Number must be between 1 and 10.")

    scale = (number - 1) / 9.0
    index = int(round(scale * (len(freq_list) - 1)))
    selected_freq_mhz = sorted(freq_list, reverse=True)[index]
    return selected_freq_mhz * 1000  # returns in kHz

def set_cpu_freq(number, conn=None, **context):
    """
    Selects CPU frequency based on input number (1-10) and available frequencies.

    Parameters:
    - number (int): Value from 1 to 10.
    - conn: SQLite connection for logging.
    - context: Full log context.

    Rules:
    - 1 (cheapest) maps to the highest available frequency.
    - 10 maps to the lowest available frequency.
    - Values in between are scaled dynamically.
    - Uses cpupower frequency-set to set max frequency.
    """
    try:
        if context.get('freq_max'):
            selected_freq_khz = context['freq_max']
        else:
            if config is None:
                raise ValueError("Config required for frequency calculation")
            freq_list = get_freq_list(config)
            selected_freq_khz = calculate_selected_freq(number, freq_list)

        command = ["cpupower", "frequency-set", "-u", f"{selected_freq_khz}"]
        subprocess.run(command, check=True)
        logger.info(f"Command to be executed: {' '.join(command)}")

        if conn:
            # Update context with freq_max if not already there
            context.setdefault('freq_max', selected_freq_khz)
            log_setting(conn, freq_min=0, **context)
        return selected_freq_mhz

    except ValueError as e:
        logger.error(f"Error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return None

def log_setting(conn, **kwargs):
    """Log full context into SQLite using the new schema."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cpu_settings_log
            (timestamp, hostname, freq_min, freq_max, score_name, score_value, price,
             co2_current, co2_median, co2_grade, power_w, cpu_freq_current, rating,
             rating_price, rating_co2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            kwargs.get('rating_price'),
            kwargs.get('rating_co2'),
        ))
        conn.commit()
        logger.info("DB log entry inserted")
    except Exception as e:
        logger.error(f"DB insert failed: {e}")
        raise
