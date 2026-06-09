"""Modular temperature reading from various sources (IPMI, HTTP API, etc.).

Supports multiple temperature sources:
1. IPMI sensor (via ipmitool)
2. HTTP API (e.g., GreenDIGIT, custom JSON endpoints)

Configuration is done via config.ini under [TEMPERATURE_SOURCE] section.
"""
from __future__ import annotations

import json
import re
from typing import Optional, Any
from abc import ABC, abstractmethod

from .system_utils import run_command


class TemperatureSource(ABC):
    """Abstract base class for temperature sources."""

    @abstractmethod
    def read(self) -> Optional[float]:
        """Read and return temperature in Celsius, or None on failure."""
        pass


class IPMISensorSource(TemperatureSource):
    """Read temperature from IPMI sensor via ipmitool."""

    def __init__(self, sensor_name: str):
        """
        Args:
            sensor_name: Name of the IPMI sensor (e.g., "INLET_AIR_TEMP")
        """
        self.sensor_name = sensor_name

    def read(self) -> Optional[float]:
        """Read IPMI sensor and extract numeric temperature."""
        try:
            out = run_command(f'ipmitool sensor reading "{self.sensor_name}" 2>/dev/null')
            if not out:
                return None
            # Extract first number found (typically the temperature value)
            m = re.search(r"(\d+(?:\.\d+)?)", out)
            if not m:
                return None
            return float(m.group(1))
        except Exception:
            return None


class HTTPAPISource(TemperatureSource):
    """Read temperature from HTTP API endpoint."""

    def __init__(self, url: str, json_path: Optional[str] = None):
        """
        Args:
            url: Full HTTP URL (e.g., "http://192.168.1.100/api/greendigit/data")
            json_path: JSONPath or key sequence to extract temp (e.g., "temperature.value" or "module.temp")
                      If None, assumes response is a plain number.
        """
        self.url = url
        self.json_path = json_path

    def read(self) -> Optional[float]:
        """Fetch temperature from HTTP API."""
        try:
            import requests
            response = requests.get(self.url, timeout=5)
            response.raise_for_status()
            data = response.text.strip()

            # Try plain number first
            try:
                return float(data)
            except ValueError:
                pass

            # Try JSON parsing
            try:
                json_data = json.loads(data)
                if self.json_path:
                    value = self._extract_json_value(json_data, self.json_path)
                    if value is not None:
                        return float(value)
                else:
                    # No path given; try common top-level keys
                    for key in ["temperature", "temp", "value", "data"]:
                        if key in json_data:
                            try:
                                return float(json_data[key])
                            except (TypeError, ValueError):
                                pass
            except (json.JSONDecodeError, ValueError):
                pass

            # Last resort: regex to find any number
            m = re.search(r"(\d+(?:\.\d+)?)", data)
            if m:
                return float(m.group(1))

            return None
        except Exception:
            return None

    @staticmethod
    def _extract_json_value(data: Any, path: str) -> Any:
        """Extract value from nested JSON using dot-separated path.

        Example:
            data = {"temperature": {"value": 25.5}}
            _extract_json_value(data, "temperature.value") => 25.5
        """
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current


def create_temperature_source(config) -> Optional[TemperatureSource]:
    """Factory function to create appropriate temperature source from config.

    Args:
        config: configparser.ConfigParser instance

    Returns:
        TemperatureSource instance or None if config is invalid/missing
    """
    if not config.has_section("TEMPERATURE_SOURCE"):
        return None

    source_type = config.get("TEMPERATURE_SOURCE", "TYPE", fallback=None)

    if source_type == "ipmi":
        sensor_name = config.get("TEMPERATURE_SOURCE", "IPMI_SENSOR_NAME", fallback=None)
        if not sensor_name:
            return None
        return IPMISensorSource(sensor_name)

    elif source_type == "http_api":
        url = config.get("TEMPERATURE_SOURCE", "HTTP_URL", fallback=None)
        if not url:
            return None
        json_path = config.get("TEMPERATURE_SOURCE", "HTTP_JSON_PATH", fallback=None)
        return HTTPAPISource(url, json_path)

    return None


def read_temperature(config) -> Optional[float]:
    """Convenience function: create source from config and read temperature.

    Args:
        config: configparser.ConfigParser instance

    Returns:
        Temperature in Celsius or None on failure
    """
    source = create_temperature_source(config)
    if not source:
        return None
    return source.read()
