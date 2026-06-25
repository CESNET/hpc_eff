#!/usr/bin/env python3
"""
GPU Power Regulator Module for hpc_eff - Simplified Version

Uses global ambient temperature (from temperature_reader) to set ALL GPUs
to the same power limit. Similar hysteresis logic as cpu_thermo.py.

Features:
- Single ambient temperature source (IPMI, HTTP API, or custom)
- All GPUs get same power limit
- 3 power states (HIGH/MID/LOW) with hysteresis
- Configurable via [GPU_POWER] section
- Optional Slack notifications
- Returns regulation results; DB logging is owned by the controller (unified
  hpc_eff_log row alongside CPU data)

Usage (from controller.py):
    from .gpu_power import regulate_gpus
    results = regulate_gpus(conn, config, debug_log)
"""

import socket
import subprocess
from typing import Optional, List, Dict, Any, Callable

# Optional imports
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import sqlite3
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False

import logging
logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)-8s | %(message)s",
    force=True
)
logger = logging.getLogger("hpc_eff.gpu_power")


# ============================================================================
# NVIDIA SMI Wrapper - Power Control Only
# ============================================================================

class NvidiaSMI:
    """Simple wrapper for nvidia-smi power limit commands."""
    
    def __init__(self):
        self._gpu_count = None
    
    def get_gpu_count(self) -> int:
        """Get number of NVIDIA GPUs."""
        if self._gpu_count is not None:
            return self._gpu_count
        
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=True
            )
            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            self._gpu_count = int(lines[0]) if lines else 0
        except Exception as e:
            # Fallback: count index lines
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self._gpu_count = len([line for line in result.stdout.strip().split('\n') if line.strip()])
            except Exception as e2:
                logger.error(f"Failed to get GPU count: {e2}")
                return 0
        
        return self._gpu_count
    
    def get_all_gpu_names(self) -> List[str]:
        """Get names of all GPUs."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=True
            )
            return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        except Exception as e:
            logger.error(f"Failed to get GPU names: {e}")
            return []
    
    def get_current_power_limit(self, gpu_id: int = 0) -> Optional[int]:
        """Get current power limit for a GPU."""
        try:
            result = subprocess.run(
                ["nvidia-smi", f"--query-gpu=power.limit", "--format=csv,noheader,nounits", "-i", str(gpu_id)],
                capture_output=True,
                text=True,
                check=True
            )
            return int(float(result.stdout.strip()))
        except Exception as e:
            logger.error(f"Failed to get power limit for GPU {gpu_id}: {e}")
            return None
    
    def set_power_limit(self, power_watts: int, gpu_id: int = 0) -> bool:
        """Set power limit for a specific GPU."""
        try:
            # Enable persistence mode (harmless if already enabled)
            subprocess.run(
                ["nvidia-smi", "-pm", "1"],
                capture_output=True,
                check=False
            )
            
            # Set power limit
            result = subprocess.run(
                ["nvidia-smi", "-pl", str(power_watts), "-i", str(gpu_id)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"GPU {gpu_id}: Power limit set to {power_watts}W")
                return True
            else:
                logger.error(f"GPU {gpu_id}: Failed to set power limit: {result.stderr.strip()}")
                return False
                
        except Exception as e:
            logger.error(f"GPU {gpu_id}: Exception setting power limit: {e}")
            return False
    
    def set_all_gpus_power_limit(self, power_watts: int) -> List[bool]:
        """Set same power limit for all GPUs."""
        results = []
        for i in range(self.get_gpu_count()):
            results.append(self.set_power_limit(power_watts, i))
        return results


# ============================================================================
# GPU Power Regulator - Simplified (Global Temperature)
# ============================================================================

class GPUPowerRegulator:
    """
    Temperature-based GPU power regulator using global ambient temperature.
    
    All GPUs get the same power limit based on ambient temp.
    Hysteresis logic identical to cpu_thermo.py.
    """
    
    def __init__(self, config):
        self.config = config
        self.nvidia = NvidiaSMI()
        self.section = "GPU_POWER"
        
        # Load configuration - use raw=True to disable interpolation (% handling)
        self.mid_limit = config.getint(self.section, "MID_LIMIT", fallback=70)
        self.high_limit = config.getint(self.section, "HIGH_LIMIT", fallback=80)
        
        # Power limits in Watts (percentages of max or absolute values)
        self.high_power = config.get(self.section, "HIGH_POWER", fallback="100%", raw=True)
        self.mid_power = config.get(self.section, "MID_POWER", fallback="70%", raw=True)
        self.low_power = config.get(self.section, "LOW_POWER", fallback="40%", raw=True)
        
        # Optional features
        self.slack_url = config.get(self.section, "SLACK_URL", fallback=None)
        
        # State tracking for hysteresis
        self._current_state = "UNKNOWN"  # HIGH, MID, LOW, UNKNOWN
        self._resolved_power_limits = {}
        self._gpu_count = 0
        self._gpu_names = []
    
    def _parse_power_value(self, value: str, max_power: int) -> int:
        """Parse power value (percentage or absolute) to Watts."""
        value = value.strip()
        if value.endswith("%"):
            percentage = int(value[:-1])
            return int(max_power * percentage / 100)
        else:
            return int(value)
    
    def _resolve_power_limits(self, max_power: int) -> Dict[str, int]:
        """Resolve percentage-based power limits to absolute values."""
        return {
            "high": self._parse_power_value(self.high_power, max_power),
            "mid": self._parse_power_value(self.mid_power, max_power),
            "low": self._parse_power_value(self.low_power, max_power),
        }
    
    def _determine_target_power(self, temp: float, power_limits: Dict[str, int]) -> int:
        """
        Determine target power based on temperature and hysteresis.
        
        Hysteresis logic (same as cpu_thermo.py):
        - Immediate downshift on temperature rise
        - Up-shift only when temp drops 2°C below threshold
        """
        hysteresis = 2  # °C for upward shift
        
        if temp >= self.high_limit:
            self._current_state = "LOW"
            return power_limits["low"]
        elif temp >= self.mid_limit:
            self._current_state = "MID"
            return power_limits["mid"]
        else:
            # Below MID_LIMIT: allow UP shifts with hysteresis
            if self._current_state == "LOW":
                if temp <= self.mid_limit - hysteresis:
                    self._current_state = "MID"
                    return power_limits["mid"]
                else:
                    return power_limits["low"]
            elif self._current_state == "MID":
                if temp <= self.mid_limit - hysteresis:
                    self._current_state = "HIGH"
                    return power_limits["high"]
                else:
                    return power_limits["mid"]
            else:
                self._current_state = "HIGH"
                return power_limits["high"]
    
    def _get_max_power_limit(self) -> int:
        """Get max power limit from first GPU (assumes all GPUs are same model)."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.max_limit", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=True
            )
            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            if lines:
                return int(float(lines[0]))
        except Exception as e:
            # Not all GPUs support max_power_limit query - use current power as fallback
            logger.debug(f"max_power_limit not available, using current power as fallback")
        
        # Fallback: use current power limit
        current = self.nvidia.get_current_power_limit(0)
        return current if current else 300  # Default fallback
    
    def regulate(self) -> Dict[str, Any]:
        """
        Regulate all GPUs based on global ambient temperature.
        
        Returns:
            Dict with regulation results
        """
        from .temperature_reader import read_temperature
        
        # Get ambient temperature
        temp = read_temperature(self.config)
        if temp is None:
            logger.warning("GPU Power: Unable to read ambient temperature")
            return {
                "success": False,
                "error": "Unable to read ambient temperature",
                "temperature": None,
            }
        
        # Get GPU info
        gpu_count = self.nvidia.get_gpu_count()
        if gpu_count == 0:
            logger.warning("GPU Power: No NVIDIA GPUs detected")
            return {
                "success": False,
                "error": "No GPUs detected",
                "temperature": temp,
            }
        
        # Get GPU names (for logging)
        gpu_names = self.nvidia.get_all_gpu_names()
        
        # Resolve power limits on first run (or if GPU count changed)
        if not self._resolved_power_limits or self._gpu_count != gpu_count:
            max_power = self._get_max_power_limit()
            self._resolved_power_limits = self._resolve_power_limits(max_power)
            self._gpu_count = gpu_count
            self._gpu_names = gpu_names
            logger.info(f"GPU Power: Resolved limits (max={max_power}W): {self._resolved_power_limits}")
        
        # Determine target power based on temperature
        target_power = self._determine_target_power(temp, self._resolved_power_limits)
        
        # Get current power (from first GPU)
        current_power = self.nvidia.get_current_power_limit(0)
        
        # Check if change is needed
        if current_power == target_power:
            logger.info(f"GPU Power: Temp {temp}°C, Power {current_power}W - stable ({self._current_state})")
            return {
                "success": True,
                "temperature": temp,
                "power_limit": current_power,
                "changed": False,
                "target_power": target_power,
                "state": self._current_state,
                "gpu_count": gpu_count,
            }
        
        # Apply new power limit to ALL GPUs
        logger.info(f"GPU Power: Temp {temp}°C → Setting power to {target_power}W ({self._current_state})")
        results = self.nvidia.set_all_gpus_power_limit(target_power)
        
        success = all(results)
        
        if success:
            # Send Slack notification
            if self.slack_url and HAS_REQUESTS:
                self._send_slack_notification(temp, target_power, gpu_count)
            
            return {
                "success": True,
                "temperature": temp,
                "power_limit": target_power,
                "changed": True,
                "target_power": target_power,
                "previous_power": current_power,
                "state": self._current_state,
                "gpu_count": gpu_count,
            }
        else:
            logger.error("GPU Power: Failed to set power limit on some GPUs")
            return {
                "success": False,
                "error": "Failed to set power limit",
                "temperature": temp,
                "gpu_count": gpu_count,
            }
    
    def _send_slack_notification(self, temp: float, power: int, gpu_count: int):
        """Send Slack webhook notification."""
        try:
            hostname = socket.gethostname().split('.')[0]
            text = f"{hostname}: GPU Power - Temp {temp}°C → {power}W ({gpu_count}x {self._gpu_names[0] if self._gpu_names else 'GPU'})"
            requests.post(self.slack_url, json={"text": text}, timeout=5)
            logger.debug("GPU Power: Slack notification sent")
        except Exception as e:
            logger.error(f"GPU Power: Slack webhook failed: {e}")


# ============================================================================
# Public API
# ============================================================================

def regulate_gpus(config, debug_log: Callable) -> List[Dict[str, Any]]:
    """
    Main entry point for GPU power regulation.

    Args:
        config: configparser.ConfigParser instance
        debug_log: Debug logging function

    Returns:
        List of regulation results (one per GPU, but all same in simplified
        version). DB logging is handled by the controller, not here.
    """
    # Import here to avoid circular dependencies
    from .temperature_reader import read_temperature
    
    # Check if we have temperature source configured
    temp = read_temperature(config)
    if temp is None:
        debug_log("GPU Power: No temperature source configured or failed to read")
        return [{"success": False, "error": "No temperature"}]
    
    debug_log(f"GPU Power: Ambient temperature {temp}°C")
    
    try:
        regulator = GPUPowerRegulator(config)
        result = regulator.regulate()

        # Database logging now handled by controller (unified hpc_eff_log table)
        return [result]
        
    except Exception as e:
        debug_log(f"GPU Power: Exception - {e}")
        return [{"success": False, "error": str(e)}]
