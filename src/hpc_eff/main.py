import configparser
import sys
from .utils.power_reader import get_power_reading
from .utils.energy_price import get_current_energy_price, get_averages_year, classify_price, classify_price_by_median
from .utils.frequency_reader import get_cpu_frequency
from .utils.get_available_attrs import get_available_frequencies, get_available_governors
from .utils.co2_value import co2_value
from .utils.set_cpu import set_cpu_governor
import os

# Load configuration
CONFIG_PATH = "/etc/hpc_eff/config.ini"
if not os.path.isfile(CONFIG_PATH):
    # fallback for dev environment or if config missing
    CONFIG_PATH = "config.ini.example"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

API_HEADERS = {
    'User-Agent': config['API']['USER_AGENT'],
    'X-Api-Key': config['API']['API_KEY']
}

debug = config.get("SYSTEM", "DEBUG", fallback="no").lower() == "yes"

def debug_log(message):
    """Log message if debugging is enabled."""
    if debug:
        print(f"[DEBUG] {message}")

def main():
    debug_log("Starting HPC efficiency evaluator...")

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
        power = get_power_reading(cmd)
        debug_log(f"Current power usage (Watts): {power['instantaneous']}")
    except Exception as e:
        debug_log(f"Error reading power data: {e}")

    # Read current CPU frequency
    try:
        freq = get_cpu_frequency()
        debug_log(f"Current CPU frequency (MHz): {freq}")
    except Exception as e:
        debug_log(f"Error reading CPU frequency: {e}")

	# Get available CPU frequencies
    try:
        available_freqs = get_available_frequencies()
        debug_log(f"Available CPU frequencies (MHz): {available_freqs}")
    except Exception as e:
        debug_log(f"Error fetching available CPU frequencies: {e}")

	# Get available CPU governors
    try:
        available_govers = get_available_governors()
        debug_log(f"Available CPU governors: {available_govers}")
    except Exception as e:
        debug_log(f"Error fetching available CPU governors: {e}")

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
        debug_log(f"Error fetching co2 values and rating: {e}")


    # Set CPU Governor based on rating
    set_cpu_governor(rating, dry_run=False)

if __name__ == "__main__":
    main()
