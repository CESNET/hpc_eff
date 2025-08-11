import subprocess
import re

def get_power_reading(command):
    """
    Executes the given command to read power consumption.
    Returns a dictionary with power readings.
    """
    result = subprocess.run(command.split(), capture_output=True, text=True)
    output = result.stdout

    power_data = {
        "instantaneous": None,
        "average": None,
        "minimum": None,
        "maximum": None
    }

    # Parse values using regex
    power_data["instantaneous"] = int(re.search(r"Instantaneous power reading:\s+(\d+)", output).group(1))
    power_data["minimum"] = int(re.search(r"Minimum during sampling period:\s+(\d+)", output).group(1))
    power_data["maximum"] = int(re.search(r"Maximum during sampling period:\s+(\d+)", output).group(1))
    power_data["average"] = int(re.search(r"Average power reading over sample period:\s+(\d+)", output).group(1))

    return power_data
