import os
import subprocess
import glob
import configparser
import re
import socket
import time
import requests
from .set_cpu import log_setting, logger


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()


def freq_to_khz(freq_str: str) -> int:
    """Convert frequency strings like '3.10GHz' to kHz integer."""
    f = freq_str.strip().upper().replace("GHZ", "")
    try:
        val = float(f)
        # GHz -> kHz: GHz * 1e6
        return int(val * 1000000)
    except Exception:
        raise ValueError(f"Unable to parse frequency string: {freq_str}")


def get_cpu_count() -> int:
    cpus = glob.glob("/sys/devices/system/cpu/cpu[0-9]*")
    return len(cpus)


def read_temperature(sensor_name: str) -> int | None:
    """Try to read temperature via ipmitool sensor reading. Return integer Celsius or None."""
    try:
        out = run_command(f'ipmitool sensor reading "{sensor_name}" 2>/dev/null')
        if not out:
            return None
        m = re.search(r"\d+", out)
        if not m:
            return None
        return int(m.group(0))
    except Exception:
        return None


def apply_cpu_thermo(conn=None, log_context=None):
    """Apply temperature-based CPU max-frequency settings.

    Returns: dict with keys: temperature (int|None), changed (bool), target_freq (str|None)
    """
    cfg = configparser.ConfigParser()
    cfg.read("/etc/hpc_eff/config.ini")

    section = "CPU_THERMO"
    if section not in cfg:
        logger.debug("No [CPU_THERMO] section in config, skipping cpu_thermo.")
        return {"temperature": None, "changed": False, "target_freq": None}

    mid_limit = cfg.getint(section, "MID_LIMIT", fallback=None)
    high_limit = cfg.getint(section, "HIGH_LIMIT", fallback=None)

    high_freq = cfg.get(section, "HIGH_FREQUENCY", fallback=None)
    mid_freq = cfg.get(section, "MID_FREQUENCY", fallback=None)
    low_freq = cfg.get(section, "LOW_FREQUENCY", fallback=None)

    sensor = cfg.get(section, "SENSOR_NAME", fallback=None)
    enable_log = cfg.getint(section, "ENABLE_LOG", fallback=1)

    if not all([mid_limit is not None, high_limit is not None, high_freq, mid_freq, low_freq, sensor]):
        logger.debug("Incomplete CPU_THERMO config; skipping cpu_thermo.")
        return {"temperature": None, "changed": False, "target_freq": None}

    temp = read_temperature(sensor)
    if temp is None:
        logger.warning(f"Unable to read temperature from sensor '{sensor}'.")
        return {"temperature": None, "changed": False, "target_freq": None}

    # Read current max freq (kHz)
    try:
        current_khz = None
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq", "r") as f:
            current_khz = int(f.read().strip())
    except Exception:
        current_khz = None

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
        return {"temperature": temp, "changed": False, "target_freq": target_freq}

    # Apply new freq per CPU using cpufreq-set (cpufrequtils)
    cpu_count = get_cpu_count()
    success = True
    for cpu in range(cpu_count):
        cmd = f"cpufreq-set -c {cpu} --max {target_freq} >/dev/null 2>&1"
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set cpu{cpu} max freq to {target_freq}: {e}")
            success = False

    if success:
        logger.info(f"Temperature {temp}°C → max CPU frequency set to {target_freq}")
        # Log into DB if connection provided
        if conn is not None and log_context is not None:
            try:
                log_ctx = log_context.copy()
                log_ctx.update({"freq_min": 0, "freq_max": target_khz, "temperature": temp})
                log_setting(conn, **log_ctx)
            except Exception as e:
                logger.error(f"DB log failed: {e}")
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

    return {"temperature": temp, "changed": success, "target_freq": target_freq}
