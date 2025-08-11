# utils/get_available_attrs.py

import os
import subprocess
import re
import glob

def run_command(cmd):
    """
    Runs a shell command and returns its output.
    """
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()

def get_available_frequencies():
    """
    Tries to read available CPU frequencies (in MHz) from sysfs or cpufreq-info.
    Returns a sorted list of unique frequencies in MHz.
    """
    # Try reading from sysfs if available
    freq_files = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_available_frequencies")
    for file in freq_files:
        if os.path.exists(file):
            with open(file) as f:
                content = f.read().strip()
                if content:
                    return sorted(list(set(int(int(khz)//1000) for khz in content.split())))

    # Fallback to min/max range from cpufreq-info
    output = run_command("cpufreq-info -c 0")
    match = re.search(r"hardware limits: (\d+) MHz - (\d+(\.\d+)?) GHz", output)
    if match:
        min_freq = int(match.group(1))
        max_freq = float(match.group(2)) * 1000  # Convert GHz to MHz
        return [min_freq, int(max_freq)]

    # If everything fails, return an empty list
    return []

def get_available_governors():
    """
    Tries to read available CPU governors from cpufreq-info.
    Returns a sorted list.
    """
    output = run_command("cpufreq-info -g")
    return sorted(output.split())
