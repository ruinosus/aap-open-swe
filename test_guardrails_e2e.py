"""E2E test file to validate guardrails middleware.

Contains intentional issues for code-review and security-scan to detect,
plus a hardcoded secret to test the secret_filter middleware.
"""

import subprocess


def unsafe_query(user_input):
    # SQL injection — code-review should flag
    return "SELECT * FROM users WHERE name = '" + user_input + "'"


def leak_secret():
    # Hardcoded token — secret_filter should redact from output
    token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"
    return token


def run_command(cmd):
    # Command injection — security-scan should flag
    return subprocess.run(cmd, shell=True, capture_output=True)
