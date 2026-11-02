import unittest

from api.garmin_extract import extract_hrv_ms, extract_stress_avg, non_null_fields


class StressTest(unittest.TestCase):
    def test_avg_stress_level_real_key(self):
        self.assertEqual(extract_stress_avg({"avgStressLevel": 27, "maxStressLevel": 90}), 27)

    def test_falls_back_to_average_key(self):
        self.assertEqual(extract_stress_avg({"averageStressLevel": 31}), 31)

    def test_sentinel_negative_means_no_data(self):
        self.assertIsNone(extract_stress_avg({"avgStressLevel": -1}))
        self.assertIsNone(extract_stress_avg({"avgStressLevel": -2}))

    def test_missing_or_bad_input(self):
        for bad in (None, {}, [], "x", {"avgStressLevel": None}, {"avgStressLevel": True}):
            self.assertIsNone(extract_stress_avg(bad))

    def test_zero_is_a_valid_value(self):
        self.assertEqual(extract_stress_avg({"avgStressLevel": 0}), 0)


class HrvTest(unittest.TestCase):
    def test_prefers_last_night(self):
        self.assertEqual(extract_hrv_ms({"hrvSummary": {"lastNightAvg": 48, "weeklyAvg": 55}}), 48)

    def test_falls_back_to_weekly(self):
        self.assertEqual(extract_hrv_ms({"hrvSummary": {"lastNightAvg": None, "weeklyAvg": 55}}), 55)

    def test_summary_none_does_not_crash(self):
        # Antes: (x or {}).get("hrvSummary", {}).get(...) reventaba si hrvSummary era None.
        self.assertIsNone(extract_hrv_ms({"hrvSummary": None}))

    def test_missing_or_bad_input(self):
        for bad in (None, {}, [], {"hrvSummary": {}}, {"hrvSummary": {"weeklyAvg": 0}}):
            self.assertIsNone(extract_hrv_ms(bad))


class NonNullTest(unittest.TestCase):
    def test_drops_none_keeps_zero(self):
        self.assertEqual(non_null_fields({"a": None, "b": 0, "c": 5}), {"b": 0, "c": 5})

    def test_all_none_is_empty(self):
        self.assertEqual(non_null_fields({"a": None}), {})


if __name__ == "__main__":
    unittest.main()
