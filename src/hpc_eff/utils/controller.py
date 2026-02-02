"""Controller/orchestrator for evaluation and action calls.

Moves logic out of `main.py`: gathers inputs (price, power, freq, CO2),
computes ratings and log context, and conditionally calls terminal
actions `apply_cpu_thermo` and `set_cpu_freq` based on config flags.
"""
from .energy_price import get_current_energy_price, get_averages_year, classify_price_by_median
from .power_reader import get_power_reading
from .frequency_reader import get_cpu_frequency
from .co2_value import co2_value
from .cpu_thermo import apply_cpu_thermo
from .set_cpu import set_cpu_freq


def run_evaluation(conn, config, static_context: dict, debug_log):
    """Run the full evaluation pipeline and apply actions depending on config.

    Args:
        conn: sqlite3.Connection for logging
        config: configparser.ConfigParser loaded in `main.py`
        static_context: dict with static values (score_name, score_value)
        debug_log: callable for debug logging

    This function mirrors the logic previously embedded in `main.main()`.
    It reads the config flags `FEATURES/ENABLE_CPU_THERMO` and
    `FEATURES/ENABLE_SET_CPU` to decide whether to call the final actions.
    """
    debug_log("Controller: starting evaluation")

    # Determine which final actions are enabled; avoid gathering data
    # that we don't need when the corresponding action is disabled.
    enable_thermo = config.getboolean("FEATURES", "ENABLE_CPU_THERMO", fallback=True)
    enable_set_cpu = config.getboolean("FEATURES", "ENABLE_SET_CPU", fallback=True)

    # initialize placeholders
    price = power_w = cpu_freq_current = temperature = None
    available_freqs = available_govs = average_prices = historical_values = []
    current_price = None
    rating = 5  # neutral default if not computed
    current_value = median_value = grade = None

    # Build minimal log_context now (static info always useful)
    log_context = static_context.copy()
    log_context.update({
        "rating": rating,
        "price": None,
        "co2_current": None,
        "co2_median": None,
        "co2_grade": None,
        "power_w": None,
        "cpu_freq_current": None,
        "temperature": None,
    })

    # If set_cpu is enabled we need price/history/CO2/power/freq to compute rating
    if enable_set_cpu:
        # Read current electricity price (CZK/MWh)
        try:
            price = get_current_energy_price()
            debug_log(f"Current electricity price (CZK/MWh): {price}")
        except Exception as e:
            debug_log(f"Error fetching electricity price: {e}")

        # Read current power consumption
        try:
            cmd = config.get("SYSTEM", "POWERREADINGCMD")
            power_data = get_power_reading(cmd)
            power_w = power_data.get("instantaneous")
            debug_log(f"Current power usage (Watts): {power_w}")
        except Exception as e:
            debug_log(f"Error reading power data: {e}")

        # Read current CPU frequency
        try:
            cpu_freq_current = get_cpu_frequency()
            debug_log(f"Current CPU frequency (MHz): {cpu_freq_current}")
        except Exception as e:
            debug_log(f"Error reading CPU frequency: {e}")

        # Get year average prices (for classification)
        try:
            average_prices = get_averages_year()
            debug_log(f"Average monthly prices last year (CZK/MWh): {average_prices}")
        except Exception as e:
            debug_log(f"Error fetching average prices: {e}")

        # Determine current_price (allow overriding via argv handled previously in main)
        current_price = price

        # Get historical prices, classify and rate it
        try:
            history = get_averages_year()
            classify, rating = classify_price_by_median(current_price, history)
            debug_log(f"The current price of {current_price} is {classify} ({rating}).")
        except Exception as e:
            debug_log(f"Error fetching classify price and rating: {e}")

        # Fetch CO2 values and grading (only if set_cpu needs them for logging)
        try:
            historical_values, current_value, median_value, grade = co2_value({
                'User-Agent': config['API']['USER_AGENT'],
                'X-Api-Key': config['API']['API_KEY']
            })
            debug_log(f"Last 24 hours CO2 values (g CO2eq/kWh): {historical_values}")
            debug_log(f"Current CO2 value (g CO2eq/kWh): {current_value}")
            debug_log(f"Median value from 24 hours values (g CO2eq/kWh): {median_value}")
            debug_log(f"Current CO2 value grade from 1 (low) to 10 (high): {grade}")
        except Exception as e:
            historical_values, current_value, median_value, grade = None, None, None, "unknown"
            debug_log(f"Error fetching co2 values and rating: {e}")

        # update log_context with gathered values
        log_context.update({
            "rating": rating,
            "price": current_price,
            "co2_current": current_value,
            "co2_median": median_value,
            "co2_grade": grade,
            "power_w": power_w,
            "cpu_freq_current": cpu_freq_current,
        })

    # Build log_context
    log_context = static_context.copy()
    log_context.update({
        "rating": rating,
        "price": current_price,
        "co2_current": current_value,
        "co2_median": median_value,
        "co2_grade": grade,
        "power_w": power_w,
        "cpu_freq_current": cpu_freq_current,
        "temperature": temperature,
    })

    # Conditional execution controlled via config
    enable_thermo = config.getboolean("FEATURES", "ENABLE_CPU_THERMO", fallback=True)
    enable_set_cpu = config.getboolean("FEATURES", "ENABLE_SET_CPU", fallback=True)

    # Apply temperature-based CPU frequency control
    if enable_thermo:
        try:
            res = apply_cpu_thermo(conn, log_context, config)
            temperature = res.get("temperature")
            if res.get("changed"):
                debug_log(f"cpu_thermo applied target {res.get('target_freq')}")
        except Exception as e:
            debug_log(f"cpu_thermo error: {e}")
    else:
        debug_log("CPU thermo disabled by config; skipping apply_cpu_thermo")

    # Check temperature threshold and possibly adjust rating
    temp_threshold = config.getint("TEMPERATURE", "THRESHOLD", fallback=80)
    if temperature is not None and temperature > temp_threshold:
        debug_log(f"Temperature {temperature} exceeds threshold {temp_threshold}. Forcing lowest frequency.")
        rating = 10

    # Set CPU min and max frequencies based on rating
    debug_log(f"Current rating: {rating}")
    if enable_set_cpu:
        set_cpu_freq(rating, conn, config, **log_context)
    else:
        debug_log("set_cpu_freq disabled by config; skipping set_cpu_freq")

    debug_log("Controller: evaluation finished")
