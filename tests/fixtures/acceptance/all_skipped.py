import unittest

@unittest.skip("Deliberately skipped negative acceptance fixture")
class AllSkipped(unittest.TestCase):
    def test_never_executed(self):
        raise AssertionError("fixture must remain skipped")
