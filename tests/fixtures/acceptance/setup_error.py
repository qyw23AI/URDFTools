import unittest


class SetupError(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError("intentional fixture setup failure")

    def test_never_executed(self):
        raise AssertionError("setup should prevent execution")
