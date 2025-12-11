import re
import shutil
import glob
from .command_runner import run_command


def freq_to_khz(freq_str: str) -> int:
    """Convert frequency strings like '3.10GHz' to kHz integer.

    Args:
        freq_str: Frequency string (e.g., '3.10GHz', '3100000')

    Returns:
        Frequency in kHz as integer

    Raises:
        ValueError: If frequency string cannot be parsed
    """
    f = freq_str.strip().upper().replace("GHZ", "")
    try:
        val = float(f)
        # GHz -> kHz: GHz * 1e6
        return int(val * 1000000)
    except Exception:
        raise ValueError(f"Unable to parse frequency string: {freq_str}")


def get_cpu_count() -> int:
    """Get the number of CPU cores in the system.

    Returns:
        Number of CPUs found in /sys/devices/system/cpu/
    """
    cpus = glob.glob("/sys/devices/system/cpu/cpu[0-9]*")
    return len(cpus)


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


def get_cpu_max_frequency(cpu_id: int = 0) -> int | None:
    """
    Read current CPU max frequency from sysfs.

    Args:
        cpu_id: CPU index (default: 0)

    Returns:
        Max frequency in kHz, or None if unable to read
    """
    try:
        with open(f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_max_freq", "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def get_cpu_min_frequency(cpu_id: int = 0) -> int | None:
    """
    Read current CPU min frequency from sysfs.

    Args:
        cpu_id: CPU index (default: 0)

    Returns:
        Min frequency in kHz, or None if unable to read
    """
    try:
        with open(f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_min_freq", "r") as f:
            return int(f.read().strip())
    except Exception:
        return None
