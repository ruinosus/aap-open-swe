import subprocess
import unittest

class TestHello(unittest.TestCase):
    def test_hello(self):
            result = subprocess.run(['python3', 'hello.py'], capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'Hello from AAP Open SWE!', 'Output did not match expected string')