from typing import Optional
import re
import shutil
import glob

from .system_utils import run_command


def freq_to_khz(freq_str):
    """Convert a frequency value to kHz (int).

    Accepts strings with units ('2.40GHz', '2400MHz', '2400000KHz') or a
    bare numeric value. Bare numbers are assumed to be MHz when < 10000,
    otherwise kHz. Returns 0 for unparseable strings.
    """
    if isinstance(freq_str, (int, float)):
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


def get_cpu_count() -> int:
    """Return the number of CPU cores found in /sys/devices/system/cpu/."""
    cpus = glob.glob("/sys/devices/system/cpu/cpu[0-9]*")
    return len(cpus)


def get_freq_cpufreq():
    """Reads current CPU frequency using cpufreq-info -f.
    Returns frequency in MHz (converted from kHz)."""
    output = run_command("cpufreq-info -f -c 0")
    try:
        khz = int(output.strip())
        return khz // 1000
    except ValueError:
        return None


def get_freq_proc_cpuinfo():
    """Reads average frequency from /proc/cpuinfo. Returns MHz (int)."""
    output = run_command("cat /proc/cpuinfo | grep 'cpu MHz'")
    try:
        freqs = [float(line.split(":")[1]) for line in output.splitlines()]
        return int(sum(freqs) / len(freqs)) if freqs else None
    except Exception:
        return None


def get_freq_lscpu():
    """Reads frequency from lscpu output. Returns MHz (int)."""
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


def get_cpu_max_frequency(cpu_id: int = 0) -> Optional[int]:
    """Read max scaling frequency for a given CPU from sysfs.
    Returns frequency in kHz, or None.
    """
    path = f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_max_freq"
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def get_cpu_min_frequency(cpu_id: int = 0) -> Optional[int]:
    """Read min scaling frequency for a given CPU from sysfs.
    Returns frequency in kHz, or None.
    """
    path = f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_min_freq"
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None
