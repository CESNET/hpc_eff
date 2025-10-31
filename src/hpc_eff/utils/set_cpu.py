import subprocess
import socket
from datetime import datetime
import sqlite3

def set_cpu_governor(number, governors, dry_run=True):
    """
    Sets the CPU governor based on the input number and available governors.

    Parameters:
    - number (int): Range 1–10, determines priority of governor.
    - governors (list[str]): List of available governors (e.g. ["powersave", "performance"]).

    Rules:
    - If "performance" is available and number is in 1–3, choose "performance".
    - If "ondemand" is available and number is in 4–7, choose "ondemand".
    - If "powersave" is available and number is in 8–10, choose "powersave".
    - If chosen governor is not available, fall back to the first valid option
      from the order ["performance", "ondemand", "powersave"] that exists in `governors`.

    The function prints the command instead of executing it.
    """

    try:
        # Map ranges to governors
        ranges = {
            "performance": range(1, 4),
            "ondemand": range(4, 8),
            "powersave": range(8, 11),
        }

        # Determine preferred governor
        selected = None
        for gov, valid_range in ranges.items():
            if number in valid_range and gov in governors:
                selected = gov
                break

        # If preferred governor not available, fallback
        if not selected:
            for fallback in ["performance", "ondemand", "powersave"]:
                if fallback in governors:
                    selected = fallback
                    break

        if not selected:
            raise ValueError("No valid governors available in the provided list.")

        # Print command
        command = ["cpupower", "frequency-set", "-g", selected]
        if dry_run:
            print(f"[DRY-RUN] Command to be executed: {' '.join(command)}")
        else:
            subprocess.run(command, check=True)
            print(f"Governor successfully set to '{governor}'")

    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def set_cpu_freq(number, freqs, governors, conn=None, **context):
    """
    Selects CPU frequency based on input number (1-10), available frequencies,
    and available governors.

    Parameters:
    - number (int): Value from 1 to 10.
    - freqs (list[int]): List of available frequencies in MHz
                         (e.g. [800, 1200, 1600, 2400]).
    - governors (list[str]): List of available governors.

    Rules:
    - 1 (cheapest) maps to the highest available frequency.
    - 10 maps to the lowest available frequency.
    - Values in between are scaled dynamically.
    - If "userspace" governor is available → use cpufreq-set.
    - Otherwise → write to scaling_max_freq for all CPUs (requires root).

    Prints the command(s) instead of executing them.
    """
    try:
        if not freqs:
            raise ValueError("No available frequencies provided.")

        if not (1 <= number <= 10):
            raise ValueError("Number must be between 1 and 10.")

        # Sort available frequencies
        freqs_sorted = sorted(freqs, reverse=True)
        print("Available frequencies: ", freqs_sorted)
        # Map number (1–10) to index in freqs
        scale = (number - 1) / 9  # 0.0 for 1, 1.0 for 10
        index = round(scale * (len(freqs_sorted) - 1))
        selected_freq = freqs_sorted[index]

        if "userspace" in governors:
            # cpufreq-set expects MHz
            command = f"cpufreq-set -f {selected_freq}"
            print(f"Command to be executed: {command}")
        else:
            # scaling_max_freq expects kHz
            freq_khz = selected_freq * 1000
            command = f"for cpu in /sys/devices/system/cpu/cpu[0-9]*; do echo {freq_khz} > $cpu/cpufreq/scaling_max_freq; done"
            print(f"Command to be executed: {command}")
        if conn:
            log_setting(conn, freq_min=selected, freq_max=selected, **context)

    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def log_setting(conn, **kwargs):
    """Log full context into SQLite using the new schema."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cpu_settings_log
        (timestamp, hostname, score_name, score_value, governor,
         freq_min, freq_max, rating, price, co2_current, power_w, cpu_freq_current)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        socket.gethostname(),
        kwargs.get('score_name'),
        kwargs.get('score_value'),
        kwargs.get('governor'),
        kwargs.get('freq_min'),
        kwargs.get('freq_max'),
        kwargs.get('rating'),
        kwargs.get('price'),
        kwargs.get('co2_current'),
        kwargs.get('power_w'),
        kwargs.get('cpu_freq_current')
    ))
    conn.commit()
