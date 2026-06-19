import re
import socket
import time
import requests
from .set_cpu import logger, set_max_freq_khz
from .system_utils import run_command
from .temperature_reader import read_temperature
from .frequency_reader import get_cpu_max_frequency, freq_to_khz, get_cpu_count


def apply_cpu_thermo(config=None):
    """Apply temperature-based CPU max-frequency settings.

    Args:
        config: configparser.ConfigParser instance with configuration (required)

    Performs only the action (setting CPU max frequency when it needs to change)
    plus optional Slack notification. DB logging is owned by the controller, so
    this returns the data it gathered.

    Returns: dict with keys: temperature (int|None), changed (bool),
    target_freq (str|None), target_khz (int|None)
    """
    if config is None:
        logger.error("Config required for apply_cpu_thermo")
        return {"temperature": None, "changed": False, "target_freq": None, "target_khz": None}

    cfg = config
    section = "CPU_THERMO"
    if section not in cfg:
        logger.debug("No [CPU_THERMO] section in config, skipping cpu_thermo.")
        return {"temperature": None, "changed": False, "target_freq": None, "target_khz": None}

    mid_limit = cfg.getint(section, "MID_LIMIT", fallback=None)
    high_limit = cfg.getint(section, "HIGH_LIMIT", fallback=None)

    high_freq = cfg.get(section, "HIGH_FREQUENCY", fallback=None)
    mid_freq = cfg.get(section, "MID_FREQUENCY", fallback=None)
    low_freq = cfg.get(section, "LOW_FREQUENCY", fallback=None)

    if not all([mid_limit is not None, high_limit is not None, high_freq, mid_freq, low_freq]):
        logger.debug("Incomplete CPU_THERMO config; skipping cpu_thermo.")
        return {"temperature": None, "changed": False, "target_freq": None, "target_khz": None}

    temp = read_temperature(config)
    if temp is None:
        logger.warning("Unable to read temperature from configured source.")
        return {"temperature": None, "changed": False, "target_freq": None, "target_khz": None}

    # Read current max freq (kHz) from sysfs
    current_khz = get_cpu_max_frequency(cpu_id=0)
    if current_khz is None:
        logger.warning("Unable to read current max frequency from sysfs")

    # determine current state
    curr_state = "UNKNOWN"
    try:
        if current_khz is not None:
            if current_khz == freq_to_khz(high_freq):
                curr_state = "HIGH"
            elif current_khz == freq_to_khz(mid_freq):
                curr_state = "MID"
            elif current_khz == freq_to_khz(low_freq):
                curr_state = "LOW"
    except Exception:
        curr_state = "UNKNOWN"

    # Hysteresis logic: immediate downshift on rise
    target_freq = None
    if temp >= high_limit:
        target_freq = low_freq
    elif temp >= mid_limit:
        target_freq = mid_freq
    else:
        # below MID_LIMIT: allow UP shifts with -2°C hysteresis
        if curr_state == "LOW":
            if temp <= mid_limit - 2:
                target_freq = mid_freq
            else:
                target_freq = low_freq
        elif curr_state == "MID":
            if temp <= mid_limit - 2:
                target_freq = high_freq
            else:
                target_freq = mid_freq
        else:
            target_freq = high_freq

    target_khz = freq_to_khz(target_freq)
    if current_khz == target_khz:
        logger.info(f"Temperature {temp}°C → target {target_freq} already set.")
        return {"temperature": temp, "changed": False, "target_freq": target_freq, "target_khz": target_khz}

    # Apply the new max frequency to every CPU using the available tool
    # (cpupower or cpufreq-set, auto-detected in set_max_freq_khz).
    cpu_count = get_cpu_count()
    success = True
    for cpu in range(cpu_count):
        if not set_max_freq_khz(target_khz, cpu=cpu):
            success = False

    if success:
        logger.info(f"Temperature {temp}°C → max CPU frequency set to {target_freq}")
        # Send optional HTTP POST and Slack notification
        try:
            slack_url = cfg.get(section, "SLACK_URL", fallback=None)
        except Exception:
            slack_url = None

        payload = {
            "hostname": socket.gethostname().split('.')[0],
            "temperature": temp,
            "target_freq": target_freq,
            "target_khz": target_khz,
            "changed": bool(success),
            "timestamp": int(time.time()),
        }
        if slack_url:
            try:
                text = f"{payload['hostname']} Temperature {temp}°C → max CPU frequency set to {target_freq}"
                # Slack incoming webhook expects JSON {"text": "..."}
                requests.post(slack_url, json={"text": text}, timeout=5)
                logger.debug("Sent Slack webhook notification")
            except Exception as e:
                logger.error(f"Slack webhook failed: {e}")
    else:
        logger.warning("One or more cpufreq-set calls failed.")

    return {"temperature": temp, "changed": success, "target_freq": target_freq, "target_khz": target_khz}
