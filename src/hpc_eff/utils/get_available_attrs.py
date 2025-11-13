import os
import subprocess
import re
import glob
import shutil

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

    # Fallback to min/max range from cpupower
    if shutil.which("cpupower"):
        output = run_command("cpupower frequency-info")
        match = re.search(r"hardware limits:\s*([\d\.]+)\s*GHz\s*-\s*([\d\.]+)\s*GHz", output)
        if match:
            min_freq = float(match.group(1)) * 1000
            max_freq = float(match.group(2)) * 1000
            return [int(min_freq), int(max_freq)]

    return []

def get_available_governors():
    """
    Tries to read available CPU governors from cpupower.
    Returns a sorted list.
    """
    if shutil.which("cpupower"):
        output = run_command("cpupower frequency-info --governors")
        match = re.search(r"available cpufreq governors:\s*(.*)", output)
        if match:
            governors = match.group(1).strip()
            if governors.lower() == "not available":
                return []
            return sorted(governors.split())

    return []
