import copy
import unittest

from api.strength_payload import validate_date, validate_strength_payload

GOOD = {
    "workoutName": "Pelotón",
    "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
    "workoutSegments": [{
        "segmentOrder": 1,
        "sportType": {"sportTypeKey": "strength_training"},
        "workoutSteps": [
            {"type": "ExecutableStepDTO", "stepOrder": 1},
            {"type": "RepeatGroupDTO", "stepOrder": 2, "numberOfIterations": 3, "workoutSteps": [
                {"type": "ExecutableStepDTO", "stepOrder": 3},
                {"type": "ExecutableStepDTO", "stepOrder": 4},
            ]},
        ],
    }],
}


class PayloadTest(unittest.TestCase):
    def test_valid_payload(self):
        self.assertIsNone(validate_strength_payload(GOOD))

    def test_rejects_wrong_shapes(self):
        for bad in (None, [], "x", {}):
            self.assertIsNotNone(validate_strength_payload(bad))

    def test_rejects_other_sports_and_missing_name(self):
        p = copy.deepcopy(GOOD)
        p["sportType"]["sportTypeKey"] = "cycling"
        self.assertIn("fuerza", validate_strength_payload(p))
        p = copy.deepcopy(GOOD)
        p["workoutName"] = "  "
        self.assertIn("workoutName", validate_strength_payload(p))

    def test_rejects_empty_or_huge_steps(self):
        p = copy.deepcopy(GOOD)
        p["workoutSegments"][0]["workoutSteps"] = []
        self.assertIn("vacío", validate_strength_payload(p))
        p["workoutSegments"][0]["workoutSteps"] = [{"stepOrder": i} for i in range(201)]
        self.assertIn("largo", validate_strength_payload(p))
        nested = {"stepOrder": 1, "workoutSteps": [{"stepOrder": i} for i in range(401)]}
        p["workoutSegments"][0]["workoutSteps"] = [nested]
        self.assertIn("largo", validate_strength_payload(p))

    def test_dates(self):
        self.assertIsNone(validate_date(None))
        self.assertIsNone(validate_date("2026-11-05"))
        for bad in ("05/11/2026", "2026-11-5", 20261105, ""):
            self.assertIsNotNone(validate_date(bad))


if __name__ == "__main__":
    unittest.main()
