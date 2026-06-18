"""Controller/orchestrator for evaluation and action calls.

Moves logic out of `main.py`: gathers inputs (price, power, freq, CO2,
temperature), computes ratings and log context, and conditionally calls the
terminal actions `apply_cpu_thermo` and `set_cpu_freq` based on config flags.

Two independent feature flags drive the pipeline (see [FEATURES] in config):
- ENABLE_SET_CPU   : price/CO2 -> rating -> max-frequency cap
- ENABLE_CPU_THERMO: temperature -> hysteresis-based max-frequency control
- ENABLE_GPU_POWER : temperature -> power limiting for NVIDIA GPUs (NEW)

Both may run together; when both are on, temperature acts as a hard limit:
exceeding TEMPERATURE/THRESHOLD forces the rating to 10 (lowest frequency).
"""

import json
import time
from pathlib import Path

from .energy_price import get_current_energy_price, get_averages_year, classify_price_by_median
from .power_reader import get_power_reading
from .frequency_reader import get_cpu_frequency
from .co2_value import co2_value
from .cpu_thermo import apply_cpu_thermo
from .set_cpu import set_cpu_freq

def update_state_json(new_entry, state_file_path, history_length, static_context, debug_log):
    """Update the JSON state file with history."""
    state_path = Path(state_file_path)
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
        data["history"] = data["history"][:history_length]
        data["static"] = static_context

        with open(state_path, "w") as f:
            json.dump(data, f, indent=4)

        state_path.chmod(0o644)
        debug_log(f"Updated state JSON at {state_file_path}")
    except Exception as e:
        debug_log(f"Error updating state JSON: {e}")

def run_evaluation(conn, config, static_context: dict, debug_log):
    """Run the full evaluation pipeline and apply actions depending on config.

    Args:
        conn: sqlite3.Connection for logging
        config: configparser.ConfigParser loaded in `main.py`
        static_context: dict with static values (score_name, score_value)
        debug_log: callable for debug logging

    Reads the config flags `FEATURES/ENABLE_CPU_THERMO` and
    `FEATURES/ENABLE_SET_CPU` to decide which final actions to call. Data that
    a disabled action would need is not gathered, to save work.
    """
    debug_log("Controller: starting evaluation")

    # Determine which final actions are enabled; avoid gathering data
    # that we don't need when the corresponding action is disabled.
    enable_thermo = config.getboolean("FEATURES", "ENABLE_CPU_THERMO", fallback=True)
    enable_set_cpu = config.getboolean("FEATURES", "ENABLE_SET_CPU", fallback=True)
    enable_gpu = config.getboolean("FEATURES", "ENABLE_GPU_POWER", fallback=False)

    # initialize placeholders
    price = power_w = cpu_freq_current = temperature = None
    available_freqs = available_govs = average_prices = historical_values = []
    current_price = None
    rating = 5  # neutral default if not computed
    rating_price = rating_co2 = None
    current_value = median_value = grade = None
    price_notes = []
    temp_notes = []
    
    # GPU power tracking
    gpu_power_result = None

    # Build base log_context with static info
    log_context = static_context.copy()

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
            power_cmd = config.get("SYSTEM", "POWERREADINGCMD")
            power_data = get_power_reading(power_cmd)
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

        # Get year average prices (used for both logging and classification)
        try:
            average_prices = get_averages_year()
            debug_log(f"Average monthly prices last year (CZK/MWh): {average_prices}")
        except Exception as e:
            debug_log(f"Error fetching average prices: {e}")

        # Determine current_price
        current_price = price

        # Classify and rate the current price against the same year history
        try:
            classify, rating = classify_price_by_median(current_price, average_prices)
            rating_price = rating
            debug_log(f"The current price of {current_price} is {classify} ({rating}).")
            price_notes.append(f"Price {current_price} is {classify}")
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

        # CO2 grade (1 low - 10 high) doubles as the CO2 rating
        rating_co2 = grade if isinstance(grade, int) else None

        # update log_context with gathered values
        log_context.update({
            "price": current_price,
            "co2_current": current_value,
            "co2_median": median_value,
            "co2_grade": grade,
            "rating_price": rating_price,
            "rating_co2": rating_co2,
            "power_w": power_w,
            "cpu_freq_current": cpu_freq_current,
        })

    # Ensure core metrics are in log_context for other functions
    log_context.update({
        "rating": rating,
        "temperature": temperature,
    })

    # Get previous temperature for comparison (rising/dropping annotation)
    old_temp = None
    try:
        state_file_path = config.get("logging", "state_json_path", fallback="/var/lib/hpc_eff/state.json")
        if Path(state_file_path).exists():
            with open(state_file_path, "r") as f:
                old_data = json.load(f)
                old_temp = old_data.get("current", {}).get("temperature")
    except Exception:
        pass

    # Apply temperature-based CPU frequency control
    thermo_freq_limit = None
    if enable_thermo:
        try:
            res = apply_cpu_thermo(conn, log_context, config)
            temperature = res.get("temperature")
            log_context["temperature"] = temperature  # update with real reading

            status_msg = f"Temp {temperature} C"
            if temperature is not None and old_temp is not None:
                if temperature >= old_temp + 2:
                    status_msg += " (rising)"
                elif temperature <= old_temp - 2:
                    status_msg += " (dropping)"

            if res.get("changed"):
                thermo_freq_limit = res.get('target_freq')
                debug_log(f"cpu_thermo applied target {thermo_freq_limit}")
                temp_notes.append(f"{status_msg}: Applied thermal frequency limit: {thermo_freq_limit}")
            else:
                current_target = res.get('target_freq')
                temp_notes.append(f"{status_msg}: Thermal state stable at {current_target}")
        except Exception as e:
            debug_log(f"cpu_thermo error: {e}")
            temp_notes.append(f"Thermal policy evaluation error: {e}")
    else:
        debug_log("CPU thermo disabled; skipping")

    # Check temperature threshold and possibly adjust rating (temperature wins)
    temp_threshold = config.getfloat("TEMPERATURE", "THRESHOLD", fallback=80)
    if temperature is not None and temperature > temp_threshold:
        debug_log(f"Temperature {temperature} exceeds threshold {temp_threshold}. Forcing lowest frequency.")
        rating = 10
        log_context["rating"] = rating
        temp_notes.append(f"Temperature {temperature} exceeds threshold {temp_threshold}. Forcing lowest frequency.")

    # Set CPU max frequency based on rating
    selected_freq = None
    if enable_set_cpu:
        debug_log(f"Current rating: {rating}")
        selected_freq = set_cpu_freq(rating, conn, config, **log_context)
        if selected_freq:
            price_notes.append(f"Rating {rating} set {selected_freq}kHz")
    else:
        debug_log("set_cpu_freq disabled; skipping")

    # Finalize log entry for JSON (no static info)
    json_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Temperature/thermo fields only if the thermo action is enabled
    if enable_thermo:
        json_entry.update({
            "temperature": temperature,
            "thermo_freq_limit": thermo_freq_limit,
            "action_temp": "; ".join(temp_notes),
        })

    # Price/rating/frequency fields only if set_cpu is enabled
    if enable_set_cpu:
        json_entry.update({
            "rating": rating,
            "rating_price": rating_price,
            "rating_co2": rating_co2,
            "selected_freq_khz": selected_freq,
            "action_price": "; ".join(price_notes),
            "price": current_price,
            "co2_current": current_value,
            "co2_median": median_value,
            "co2_grade": grade,
            "power_w": power_w,
            "cpu_freq_current": cpu_freq_current,
        })
    
    # GPU Power Regulation (MUST run BEFORE json_entry.update for GPU fields)
    if enable_gpu:
        try:
            from .gpu_power import regulate_gpus as gpu_regulate
            results = gpu_regulate(conn, config, debug_log)
            debug_log(f"GPU Power: finished - {len(results)} GPUs processed")
            if results and len(results) > 0:
                gpu_power_result = results[0]  # Take first (and only) result
        except ImportError as e:
            debug_log(f"GPU Power: module not found - {e}")
        except Exception as e:
            import traceback
            debug_log(f"GPU Power: error during regulation - {e}")
            debug_log(f"GPU Power: traceback: {traceback.format_exc()}")
    else:
        debug_log("GPU Power: disabled (FEATURES/ENABLE_GPU_POWER=no)")
    
    # GPU power fields only if GPU power is enabled AND we have a result
    if enable_gpu and gpu_power_result:
        gpu_fields = {
            "gpu_power_limit": gpu_power_result.get("power_limit"),
            "gpu_target_power": gpu_power_result.get("target_power"),
            "gpu_state": gpu_power_result.get("state"),
            "gpu_changed": gpu_power_result.get("changed", False),
            "gpu_success": gpu_power_result.get("success", False),
            "gpu_count": gpu_power_result.get("gpu_count"),
        }
        json_entry.update(gpu_fields)
        log_context.update(gpu_fields)

    # Update state JSON
    state_file_path = config.get("logging", "state_json_path", fallback="/var/lib/hpc_eff/state.json")
    history_length = config.getint("logging", "history_length", fallback=10)
    update_state_json(json_entry, state_file_path, history_length, static_context, debug_log)
    
    debug_log("Controller: evaluation finished")
