import requests
import statistics
import configparser

def fetch_emissions_data(api_headers):
    """
    Fetch emissions data for the past 24 hours from the Nowtricity API.

    Returns:
        list of int: A list of emission values (in g CO2eq/kWh).
    """
    url = 'https://www.nowtricity.com/api/emissions-previous-24h/czech-republic/'

    response = requests.get(url, headers=api_headers)
    response.raise_for_status()
    data = response.json()
    
    # Extract emission values
    return [entry['value'] for entry in data['emissions']]


def fetch_current_emission(api_headers):
    """
    Fetch the current emission value from the Nowtricity API.

    Returns:
        int: The current emission value (in g CO2eq/kWh).
    """
    url = 'https://www.nowtricity.com/api/current-emissions/czech-republic/'

    response = requests.get(url, headers=api_headers)
    response.raise_for_status()
    data = response.json()
    
    return data['emissions']['value']


def assign_grade(current_value, historical_values):
    """
    Assign a grade (1 to 10) based on the position of the current value
    within the distribution of historical values.

    Args:
        current_value (int): The current emission value.
        historical_values (list of int): Historical emission values.

    Returns:
        int: Grade from 1 (low) to 10 (high).
    """
    sorted_values = sorted(historical_values)
    position = sum(1 for v in sorted_values if v < current_value)
    percentile = position / len(sorted_values)
    
    # Scale percentile to 1–10 range
    return round(percentile * 9) + 1


def co2_value(api_headers):
    """
    Main execution function.
    Fetches data, calculates median, compares current value, and returns all.
    """
    historical_values = fetch_emissions_data(api_headers)
    current_value = fetch_current_emission(api_headers)
    median_value = statistics.median(historical_values)
    grade = assign_grade(current_value, historical_values)

    return historical_values, current_value, median_value, grade
