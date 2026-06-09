"""
General system utilities: centralized command execution and hardware sensors.
"""
import subprocess
import re
from typing import Optional


def run_command(cmd: str) -> str:
    """Execute a shell command and return its stdout (stripped).

    Args:
        cmd: Shell command to execute

    Returns:
        Command stdout (stripped)
    """
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()


def read_temperature(sensor_name: str) -> Optional[int]:
    """Try to read temperature via `ipmitool sensor reading`.

    Returns integer Celsius on success or None on failure.
    """
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
