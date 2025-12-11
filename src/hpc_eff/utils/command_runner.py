"""
Centralized command execution utilities.
"""
import subprocess


def run_command(cmd: str) -> str:
    """
    Execute a shell command and return its output.
    
    Args:
        cmd: Shell command to execute
        
    Returns:
        Command stdout (stripped)
    """
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()
