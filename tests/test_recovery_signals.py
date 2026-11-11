import unittest

from api.recovery_signals import recovery_notes, resting_hr_note, short_sleep_note

HISTORY = [46, 47, 46, 46, 47, 46, 46]  # media ~46,3


class RestingHrTest(unittest.TestCase):
    def test_rise_of_five_or_more_warns(self):
        self.assertIn("ppm por encima", resting_hr_note(52, HISTORY))
        self.assertIn("ppm por encima", resting_hr_note(67, HISTORY))

    def test_small_rise_or_no_data_is_ignored(self):
        self.assertIsNone(resting_hr_note(50, HISTORY))  # +3,7
        self.assertIsNone(resting_hr_note(None, HISTORY))
        self.assertIsNone(resting_hr_note(60, [46, 47, 46]))  # pocas muestras
        self.assertIsNone(resting_hr_note("No data", HISTORY))

    def test_ignores_null_history_values(self):
        self.assertIsNone(resting_hr_note(60, [None, None, 46, 47]))


class SleepTest(unittest.TestCase):
    def test_short_average_sleep_warns(self):
        self.assertIn("5.", short_sleep_note([306, 323, 300]))  # ~5,2 h

    def test_enough_sleep_or_too_few_nights_is_ignored(self):
        self.assertIsNone(short_sleep_note([450, 400, 420]))
        self.assertIsNone(short_sleep_note([300]))  # una sola noche con dato
        self.assertIsNone(short_sleep_note([None, None, 300]))

    def test_exactly_six_hours_is_fine(self):
        self.assertIsNone(short_sleep_note([360, 360]))


class CombinedTest(unittest.TestCase):
    def test_empty_when_no_signal(self):
        self.assertEqual(recovery_notes(47, HISTORY, [450, 460, 470]), [])

    def test_both_signals_listed(self):
        notes = recovery_notes(67, HISTORY, [219, 300, 310])
        self.assertEqual(len(notes), 2)


if __name__ == "__main__":
    unittest.main()
