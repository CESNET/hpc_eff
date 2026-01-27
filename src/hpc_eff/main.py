import os
import configparser
import sys
from pathlib import Path
import sqlite3 
import json
import time

from .utils.power_reader import get_power_reading
from .utils.energy_price import get_current_energy_price, get_averages_year, classify_price, classify_price_by_median
from .utils.frequency_reader import get_cpu_frequency
from .utils.get_available_attrs import get_available_frequencies, get_available_governors
from .utils.co2_value import co2_value
from .utils.set_cpu import set_cpu_freq, get_freq_list, calculate_selected_freq
from .utils.create_log_db import create_log_db

CONFIG_PATH = "/etc/hpc_eff/config.ini"
if not os.path.isfile(CONFIG_PATH):
    CONFIG_PATH = "src/hpc_eff/config.ini.example"

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
        "power": "ipmitool" if "ipmitool" in power_cmd else "unknown",
        "price": "energy_price.py",
        "co2": "co2_value.py"
    }
}

STATE_FILE_PATH = config.get("logging", "state_json_path", fallback="/var/lib/hpc_eff/state.json")
HISTORY_LENGTH = config.getint("logging", "history_length", fallback=10)

def update_state_json(new_entry):
    """Update the JSON state file with history."""
    state_path = Path(STATE_FILE_PATH)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {"static": static_context, "history": [], "current": {}}
        if state_path.exists():
            try:
                with open(state_path, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        data["current"] = new_entry
        data["history"].insert(0, new_entry)
        data["history"] = data["history"][:HISTORY_LENGTH]
        data["static"] = static_context
        
        with open(state_path, "w") as f:
            json.dump(data, f, indent=4)
        
        state_path.chmod(0o644)
        debug_log(f"Updated state JSON at {STATE_FILE_PATH}")
    except Exception as e:
        debug_log(f"Error updating state JSON: {e}")

debug = config.get("SYSTEM", "DEBUG", fallback="no").lower() == "yes"

def debug_log(message):
    """Log message if debugging is enabled."""
    if debug:
        print(f"[DEBUG] {message}")

def main():
    debug_log("Starting HPC efficiency evaluator...")

    price = power_w = cpu_freq_current = None
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
        historical_values, current_value, median_value, grade = None, None, None, 5 # default neutral
        debug_log(f"Error fetching co2 values and rating: {e}")

    # Calculate final rating based on configuration
    rating_type = config.get("aggregation", "rating_type", fallback="price").lower()
    
    if rating_type == "average":
        # Calculate weighted average rating as combination of price and CO2
        try:
            w_price = config.getfloat("aggregation", "weight_price", fallback=0.4)
            w_co2 = config.getfloat("aggregation", "weight_co2", fallback=0.6)
            
            r_price = float(rating) if rating is not None else 5.0
            r_co2 = float(grade) if grade is not None and grade != "unknown" else 5.0

            raw_rating = (r_price * w_price + r_co2 * w_co2) / (w_price + w_co2)
            final_rating = int(round(raw_rating))
            # Clamp to 1-10
            final_rating = max(1, min(10, final_rating))
            
            debug_log(f"Consolidated Rating (Average): {final_rating} (Price: {r_price}@{w_price}, CO2: {r_co2}@{w_co2})")

        except Exception as e:
            debug_log(f"Error calculating weighted rating: {e}")
            final_rating = rating # Fallback to price rating
    else:
        # Default to price-based rating
        final_rating = rating
        debug_log(f"Consolidated Rating (Price): {final_rating}")

    # Calculate target frequency upper limit based on rating
    try:
        freq_list = get_freq_list(config)
        freq_max = calculate_selected_freq(final_rating, freq_list)
        debug_log(f"Calculated freq_max for rating {final_rating}: {freq_max} kHz")
    except Exception as e:
        freq_max = None
        debug_log(f"Error calculating freq_max: {e}")

    log_context = static_context.copy()
    log_context.update({
        "rating": final_rating,
        "rating_price": rating,
        "rating_co2": grade,
        "price": current_price,
        "co2_current": current_value,
        "co2_median": median_value,
        "co2_grade": grade,
        "power_w": power_w,
        "cpu_freq_current": cpu_freq_current,
        "freq_max": freq_max,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

    update_state_json(log_context)

    # Set CPU min and max frequencies based on rating
    debug_log(f"Current consolidated rating: {final_rating}")
    set_cpu_freq(final_rating, conn, **log_context)

if __name__ == "__main__":
    main()
    conn.close()
