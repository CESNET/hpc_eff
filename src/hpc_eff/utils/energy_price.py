import requests
import re
from datetime import date
import numpy as np

def get_current_energy_price():
    """
    Fetches current electricity price from the API.
    Returns the price in CZK/MWh.
    """
    url = "https://spotovaelektrina.cz/api/v1/price/get-actual-price-czk"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return int(response.text)

def parse_monthly_averages(html_content):
    """
    Parse monthly average prices from a spotovaelektrina.cz historical page.

    Returns:
        dict {(year, month): price} with the FIRST ⌀ value of each row
        (the monthly average).
    """
    tokens = re.findall(
        r'href="/historicke-ceny/(\d{4})/(\d{1,2})"|⌀\s+([\d\s]+)\s*Kč',
        html_content,
    )
    monthly = {}
    for current, following in zip(tokens, tokens[1:]):
        is_month_link = bool(current[0])
        next_is_price = bool(following[2])
        if is_month_link and next_is_price:
            key = (int(current[0]), int(current[1]))
            monthly.setdefault(key, int(following[2].replace(' ', '')))
    return monthly

def get_averages_year(months=12, min_months=6):
    """
    Fetches monthly average electricity prices for the trailing ~year from
    spotovaelektrina.cz. The current and previous year pages are combined so
    the window is always ~12 months regardless of the date (early in a year
    the current page alone only has a few months).

    Returns:
        list of int prices in CZK/MWh, newest month first, at most `months`
        entries.

    Raises:
        ValueError: if fewer than `min_months` months could be parsed
        (e.g. the page layout changed and the scraper silently broke).
    """
    monthly = {}
    current_year = date.today().year
    for year in (current_year, current_year - 1):
        url = f'https://spotovaelektrina.cz/historicke-ceny/{year}/1'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        monthly.update(parse_monthly_averages(response.text))

    newest_first = sorted(monthly.keys(), reverse=True)[:months]
    prices = [monthly[key] for key in newest_first]

    if len(prices) < min_months:
        raise ValueError(
            f"Only parsed {len(prices)} monthly averages from "
            f"spotovaelektrina.cz (expected at least {min_months}); "
            f"the page layout may have changed"
        )

    return prices

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
