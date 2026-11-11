import unittest

from api.garmin_ftp import extract_cycling_ftp


class ExtractFtpTest(unittest.TestCase):
    def test_direct_key(self):
        self.assertEqual(extract_cycling_ftp({"sport": "CYCLING", "functionalThresholdPower": 208}), 208)

    def test_float_is_rounded(self):
        self.assertEqual(extract_cycling_ftp({"functionalThresholdPower": 207.6}), 208)

    def test_list_takes_most_recent(self):
        self.assertEqual(extract_cycling_ftp([{"functionalThresholdPower": 190}, {"functionalThresholdPower": 208}]), 208)

    def test_nested(self):
        self.assertEqual(extract_cycling_ftp({"data": {"ftp": 215}}), 215)

    def test_implausible_or_missing_is_none(self):
        self.assertIsNone(extract_cycling_ftp({"functionalThresholdPower": 20}))
        self.assertIsNone(extract_cycling_ftp({"functionalThresholdPower": 2000}))
        self.assertIsNone(extract_cycling_ftp({"functionalThresholdPower": None}))
        self.assertIsNone(extract_cycling_ftp({"functionalThresholdPower": True}))
        self.assertIsNone(extract_cycling_ftp({}))
        self.assertIsNone(extract_cycling_ftp(None))
        self.assertIsNone(extract_cycling_ftp("208"))


if __name__ == "__main__":
    unittest.main()
