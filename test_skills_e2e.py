"""E2E test file to trigger code-review and security-scan skills.

This file intentionally contains some issues for the skills to detect.
"""

import subprocess


def get_user_data(user_id):
    # Potential SQL injection - security-scan should flag this
    query = "SELECT * FROM users WHERE id = " + user_id
    return query


def process_config():
    # Hardcoded secret - security-scan should flag this
    api_key = "sk-test-1234567890abcdef1234567890abcdef"
    return {"key": api_key}


def calculate_discount(price, discount):
    # Bug: no validation, division by zero possible
    return price / discount


def fetch_data(url):
    # Command injection risk
    result = subprocess.run(f"curl {url}", shell=True, capture_output=True)
    return result.stdout
# Guardrails E2E test
