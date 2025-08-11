import requests
import re
import numpy as np

def get_current_energy_price():
    """
    Fetches current electricity price from the API.
    Returns the price in CZK/MWh.
    """
    url = "https://spotovaelektrina.cz/api/v1/price/get-actual-price-czk"
    response = requests.get(url)
    try:
        data = int(response.text)
    except ValueError:
        print("Cannot convert to int")

    # Returns price
    return data

def get_averages_year():
    """
    Fetches electricity price for last year from webpage.
    Returns list of prices in CZK/MWh.
    """
    url = 'https://spotovaelektrina.cz/historicke-ceny/2025/1'
    response = requests.get(url)
    html_content = response.text

    monthly_averages = []

    matches = re.findall(r'⌀\s+([\d\s]+)\s*Kč', html_content)
    for match in matches:
        price = int(match.replace(' ', ''))
        monthly_averages.append(price)

    return(monthly_averages)

def classify_price(price, history):
    """
    Classifies the current price based on a numerical rating from 1 to 10.
    
    Parameters:
    - price: The current price to be classified.
    - history: A list of historical prices used to calculate the rating.
    
    The function calculates:
    1. The minimum and maximum of the historical prices.
    2. A rating between 1 and 10 based on the current price's position relative to the historical price range.
    
    It then classifies the current price as follows:
    - Ratings 1, 2, 3 are classified as "cheap".
    - Ratings 4, 5, 6, 7 are classified as "average".
    - Ratings 8, 9, 10 are classified as "expensive".
    
    Returns:
    - A tuple: (classification, rating)
      - classification: A string ("cheap", "average", "expensive").
      - rating: A numerical rating from 1 (cheapest) to 10 (most expensive).
    """
    
    # Calculate the minimum and maximum of the historical data
    min_price = min(history)
    max_price = max(history)
    
    # Calculate the numerical rating (1 to 10) based on how far the price is from the historical range
    # Normalize the current price to a scale from 0 to 1 based on the historical min and max
    normalized_price = (price - min_price) / (max_price - min_price)
    
    # Map the normalized price to a rating between 1 and 10
    rating = round(1 + normalized_price * 9)  # Scale to [1, 10]

    # Clamp the rating to ensure it doesn't exceed 10 or go below 1
    rating = max(1, min(rating, 10))
    
    # Classify based on the rating
    if rating <= 3:
        classification = "cheap"
    elif rating <= 7:
        classification = "average"
    else:
        classification = "expensive"
    
    return classification, rating

def classify_price_by_median(price, history):
    """
    Classifies the current price using a rating system from 1 to 10 based on its
    distance from the median of historical prices.

    Classification rules:
    - Rating 1–3: "cheap"
    - Rating 4–7: "average"
    - Rating 8–10: "expensive"

    Parameters:
    - price: Current electricity price.
    - history: List of historical electricity prices.

    Returns:
    - (classification, rating):
        classification as "cheap", "average", or "expensive",
        and rating as integer from 1 to 10.
    """

    median_price = np.median(history)
    max_price = max(history)
    min_price = min(history)

    if price >= median_price:
        normalized = (price - median_price) / (max_price - median_price)
        rating = 5 + round(normalized * 5)
    else:
        normalized = (median_price - price) / (median_price - min_price)
        rating = 5 - round(normalized * 4)

    rating = max(1, min(rating, 10))

    if rating <= 3:
        classification = "cheap"
    elif rating <= 7:
        classification = "average"
    else:
        classification = "expensive"

    return classification, rating
