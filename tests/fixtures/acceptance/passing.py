import unittest

class Passing(unittest.TestCase):
    def test_numeric(self):
        self.assertAlmostEqual(sum([0.1, 0.2, 0.3]), 0.6)
