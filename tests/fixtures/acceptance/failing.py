import unittest

class Failing(unittest.TestCase):
    def test_failure(self):
        self.assertEqual(2 + 2, 5)
