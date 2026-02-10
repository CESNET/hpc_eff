
import subprocess
import re
import shutil


def run_command(cmd):
    """Helper function to run shell commands."""
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()


def get_freq_cpufreq():
    """Reads current CPU frequency using cpufreq-info -f.
    Returns frequency in MHz (converted from kHz if needed)."""
    output = run_command("cpufreq-info -f -c 0")
    try:
        # output is usually in kHz from cpufreq-info? Check man page or assume typical behavior
        # hpc-eff original code treated it as kHz and divided by 1000.
        khz = int(output.strip())
        return khz // 1000
    except ValueError:
        return None


def get_freq_proc_cpuinfo():
    """Reads average frequency from /proc/cpuinfo."""
    output = run_command("cat /proc/cpuinfo | grep 'cpu MHz'")
    try:
        freqs = [float(line.split(":")[1]) for line in output.splitlines()]
        return int(sum(freqs) / len(freqs)) if freqs else None
    except Exception:
        return None

def get_freq_lscpu():
    """Reads frequency from lscpu output."""
    output = run_command("lscpu")
    match = re.search(r"CPU MHz:\s+(\d+(\.\d+)?)", output)
    return int(float(match.group(1))) if match else None


def get_cpu_frequency():
    """
    Try different methods to get current CPU frequency.
    Returns frequency in MHz (integer).
    """
    if shutil.which("cpufreq-info"):
        freq = get_freq_cpufreq()
        if freq:
            return freq

    freq = get_freq_proc_cpuinfo()
    if freq:
        return freq

    return get_freq_lscpu()


def get_cpu_count():
    try:
        return int(run_command("nproc"))
    except:
        return 1


def get_cpu_max_frequency(cpu_id=0):
    """Read max scaling frequency for a given CPU from sysfs.
    Returns frequency in kHz, or None.
    """
    path = f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_max_freq"
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def freq_to_khz(freq_str):
    """Convert a frequency string (e.g. '2.40GHz', '2400MHz') to kHz int."""
    if isinstance(freq_str, (int, float)):
        # assume MHz if no unit? or kHz?
        # Better safe context: if > 10000 probably kHz, else MHz?
        # But commonly in this app config values are in MHz (3000, 2200).
        if freq_str < 10000:
            return int(freq_str * 1000)
        return int(freq_str)

    s = freq_str.strip().upper()
    if s.endswith("GHZ"):
        val = float(s[:-3])
        return int(val * 1000000)
    elif s.endswith("MHZ"):
        val = float(s[:-3])
        return int(val * 1000)
    elif s.endswith("KHZ"):
        val = float(s[:-3])
        return int(val)
    else:
        # assume MHz
        try:
            val = float(s)
            return int(val * 1000)
        except ValueError:
            return 0
