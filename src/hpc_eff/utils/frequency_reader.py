import subprocess
import re
import shutil

def run_command(cmd):
    """Helper function to run shell commands."""
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()

def get_freq_cpufreq():
    """
    Reads current CPU frequency using cpufreq-info -f.
    Returns frequency in MHz (converted from kHz).
    """
    output = run_command("cpufreq-info -f")
    try:
        khz = int(output)
        return khz // 1000  # Convert to MHz
    except ValueError:
        return None

def get_freq_proc_cpuinfo():
    """Reads average frequency from /proc/cpuinfo."""
    output = run_command("cat /proc/cpuinfo | grep 'cpu MHz'")
    freqs = [float(line.split(":")[1]) for line in output.splitlines()]
    return sum(freqs) / len(freqs) if freqs else None

def get_freq_lscpu():
    """Reads frequency from lscpu output."""
    output = run_command("lscpu")
    match = re.search(r"CPU MHz:\s+(\d+(\.\d+)?)", output)
    return float(match.group(1)) if match else None

def get_cpu_frequency():
    """
    Try different methods to get current CPU frequency.
    Returns frequency in MHz.
    """
    if shutil.which("cpufreq-info"):
        freq = get_freq_cpufreq()
        if freq:
            return freq

    freq = get_freq_proc_cpuinfo()
    if freq:
        return freq

    return get_freq_lscpu()
