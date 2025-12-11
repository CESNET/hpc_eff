import os
import configparser
import sys
from pathlib import Path
import sqlite3 

from .utils.power_reader import get_power_reading
from .utils.energy_price import get_current_energy_price, get_averages_year, classify_price, classify_price_by_median
from .utils.frequency_reader import get_cpu_frequency
from .utils.get_available_attrs import get_available_frequencies, get_available_governors
from .utils.co2_value import co2_value
from .utils.set_cpu import set_cpu_freq
from .utils.create_log_db import create_log_db
from .utils.cpu_thermo import apply_cpu_thermo

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

static_context = {
    "score_name": config.get("SYSTEM", "SCORENAME", fallback="unknown"),
    "score_value": config.getfloat("SYSTEM", "SCORE", fallback=None),
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

    price = power_w = cpu_freq_current = temperature = None
    available_freqs = available_govs = average_prices = historical_values = []
    current_price = None
    rating = 5 # neutral
    current_value = median_value = grade = None

    # Print SCORE just read from config
    score_name = config.get("SYSTEM", "SCORENAME")
    score = config.get("SYSTEM", "SCORE")
    debug_log(f"Actual {score_name} score: {score}")

    # Read current electricity price (CZK/MWh)
    try:
        price = get_current_energy_price()
        debug_log(f"Current electricity price (CZK/MWh): {price}")
    except Exception as e:
        debug_log(f"Error fetching electricity price: {e}")

    # Read current power consumption
    cmd = config.get("SYSTEM", "POWERREADINGCMD")
    try:
        power_data = get_power_reading(cmd)
        power_w = power_data["instantaneous"]
        debug_log(f"Current power usage (Watts): {power_w}")
    except Exception as e:
        debug_log(f"Error reading power data: {e}")

    # Read current CPU frequency
    try:
        cpu_freq_current = get_cpu_frequency()
        debug_log(f"Current CPU frequency (MHz): {cpu_freq_current}")
    except Exception as e:
        debug_log(f"Error reading CPU frequency: {e}")

    # Get year average prices
    try:
        average_prices = get_averages_year()
        debug_log(f"Average monthly prices last year (CZK/MWh): {average_prices}")
    except Exception as e:
        debug_log(f"Error fetching average prices: {e}")

    # For debuging purposes
    if len(sys.argv) > 1:
        try:
            current_price = int(sys.argv[1])
        except ValueError:
            debug_log("ERROR: argv not a number!")
            sys.exit(1)
    else:
        current_price = price
        
    # Get historical prices, classify and rate it
    try:
        history = get_averages_year()
        classify, rating = classify_price_by_median(current_price, history)
        debug_log(f"The current price of {current_price} is {classify} ({rating}).")
    except Exception as e:
        debug_log(f"Error fetching classify price and rating: {e}")

    try:
        historical_values, current_value, median_value, grade = co2_value(API_HEADERS)
        debug_log(f"Last 24 hours CO2 values (g CO2eq/kWh): {historical_values}")
        debug_log(f"Current CO2 value (g CO2eq/kWh): {current_value}")
        debug_log(f"Median value from 24 hours values (g CO2eq/kWh): {median_value}")
        debug_log(f"Current CO2 value grade from 1 (low) to 10 (high): {grade}")
    except Exception as e:
        historical_values, current_value, median_value, grade = None, None, None, "unknown"
        debug_log(f"Error fetching co2 values and rating: {e}")

    log_context = static_context.copy()
    log_context.update({
        "rating": rating,
        "price": current_price,
        "co2_current": current_value,
        "co2_median": median_value,
        "co2_grade": grade,
        "power_w": power_w,
        "cpu_freq_current": cpu_freq_current,
    })

    # Apply temperature-based CPU frequency control (cpu_thermo)
    try:
        res = apply_cpu_thermo(conn, log_context, config)
        temperature = res.get("temperature")
        if res.get("changed"):
            debug_log(f"cpu_thermo applied target {res.get('target_freq')}")
    except Exception as e:
        debug_log(f"cpu_thermo error: {e}")

    # Check temperature threshold
    if temperature is not None and temperature > temp_threshold:
        debug_log(f"Temperature {temperature} exceeds threshold {temp_threshold}. Forcing lowest frequency.")
        rating = 10 # Force lowest frequency (highest rating number)

    # Set CPU min and max frequencies based on rating
    debug_log(f"Current rating: {rating}")
    set_cpu_freq(rating, conn, config, **log_context)

if __name__ == "__main__":
    main()
    conn.close()
