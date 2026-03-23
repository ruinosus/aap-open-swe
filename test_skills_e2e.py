"""E2E test file to trigger code-review and security-scan skills.

This file intentionally contains some issues for the skills to detect.
"""

import subprocess


def get_user_data(user_id):
    """Fetch user data based on user ID.

    Args:
        user_id (str): The ID of the user.

    Returns:
        str: SQL query string to fetch user data.
    """

    # Potential SQL injection - security-scan should flag this
    query = "SELECT * FROM users WHERE id = " + user_id
    return query


def process_config():
    """Process configuration and return API key.

    Returns:
        dict: Dictionary containing the API key.
    """

    # Hardcoded secret - security-scan should flag this
    api_key = "sk-test-1234567890abcdef1234567890abcdef"
    return {"key": api_key}


def calculate_discount(price, discount):
    """Calculate the discount on a price.

    Args:
        price (float): Original price.
        discount (float): Discount to apply.

    Returns:
        float: Price after discount.

    Raises:
        ZeroDivisionError: If discount is zero.
    """

    # Bug: no validation, division by zero possible
    return price / discount


def fetch_data(url):
    """Fetch data from a given URL.

    Args:
        url (str): The URL to fetch data from.

    Returns:
        bytes: The fetched data.
    """

    # Command injection risk
    result = subprocess.run(f"curl {url}", shell=True, capture_output=True)
    return result.stdout
