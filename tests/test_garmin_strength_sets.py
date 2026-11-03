import unittest
from types import SimpleNamespace

from api.garmin_strength_sets import UNKNOWN_NAME, exercise_name, extract_exercise_rows
from api import garmin_sync

# Formas reales de `summarizedExerciseSets` (resumen de "Fuerza día 2" y "Fuerza Día 1" de Garmin).
DAY2 = {"summarizedExerciseSets": [
    {"reps": 37, "sets": 3, "volume": 925000, "category": "CURL", "distance": 0, "duration": 186930.0, "maxWeight": 25000, "subCategory": "STANDING_DUMBBELL_BICEPS_CURL"},
    {"reps": 18, "sets": 3, "volume": 1260000, "category": "DEADLIFT", "maxWeight": 90000, "subCategory": "ROMANIAN_DEADLIFT"},
    {"reps": 24, "sets": 3, "volume": 600000, "category": "TRICEPS_EXTENSION", "maxWeight": 25000, "subCategory": "CABLE_OVERHEAD_TRICEPS_EXTENSION"},
    {"reps": 28, "sets": 3, "volume": 1580000, "category": "SHOULDER_PRESS", "maxWeight": 60000, "subCategory": "MILITARY_PRESS"},
    {"reps": 101, "sets": 1, "volume": 0, "category": "CARDIO", "maxWeight": 0},
]}
DAY1 = {"summarizedExerciseSets": [
    {"reps": 8, "sets": 3, "volume": 0, "category": "PLANK", "maxWeight": 0, "subCategory": "PLANK"},
    {"reps": 11, "sets": 1, "volume": 990000, "category": "UNKNOWN", "maxWeight": 90000},
    {"reps": 0, "sets": 1, "volume": 0, "category": "UNKNOWN", "maxWeight": 0},
]}


class ExtractTest(unittest.TestCase):
    def test_exercises_with_reps_per_set_and_weight_in_kg(self):
        rows = extract_exercise_rows(DAY2)
        self.assertEqual([r["exercise"] for r in rows], [
            "Curl de bíceps con mancuernas", "Peso muerto rumano", "Extensión de tríceps en polea", "Press militar"])
        curl = rows[0]
        self.assertEqual((curl["sets"], curl["reps"], curl["weight_kg"]), (3, 12, 25.0))
        self.assertNotIn("volume_kg", curl)  # columna generada por la base
        self.assertIn("37 repeticiones en 3 series", curl["notes"])
        self.assertEqual(rows[1]["weight_kg"], 90.0)  # peso muerto rumano

    def test_reps_per_set_rounds_half_up(self):
        row = extract_exercise_rows({"summarizedExerciseSets": [{"reps": 9, "sets": 2, "category": "CURL", "maxWeight": 10000}]})[0]
        self.assertEqual(row["reps"], 5)  # 4,5 -> 5, igual que el histórico calculado en SQL

    def test_skips_cardio_and_empty_entries(self):
        self.assertEqual(len(extract_exercise_rows(DAY2)), 4)  # el bloque CARDIO no es fuerza
        self.assertEqual(len(extract_exercise_rows(DAY1)), 2)  # la entrada UNKNOWN sin repeticiones se descarta

    def test_bodyweight_has_no_weight_and_unknown_is_labeled(self):
        plank, unknown = extract_exercise_rows(DAY1)
        self.assertEqual(plank["exercise"], "Plancha")
        self.assertIsNone(plank["weight_kg"])
        self.assertEqual(unknown["exercise"], UNKNOWN_NAME)
        self.assertEqual(unknown["weight_kg"], 90.0)

    def test_unknown_subcategory_gets_readable_name(self):
        self.assertEqual(exercise_name("CURL", "HAMMER_CURL"), "Hammer Curl")
        self.assertEqual(exercise_name("UNKNOWN", None), UNKNOWN_NAME)

    def test_no_detail_or_bad_shape(self):
        for bad in (None, {}, {"summarizedExerciseSets": None}, {"summarizedExerciseSets": "x"}, {"summarizedExerciseSets": [None, 3]}):
            self.assertEqual(extract_exercise_rows(bad), [])


class FakeTable:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def delete(self):
        self.log.append((self.name, "delete"))
        return self

    def eq(self, col, val):
        self.log.append((self.name, "eq", col, val))
        return self

    def is_(self, col, val):
        self.log.append((self.name, "is", col, val))
        return self

    def insert(self, rows):
        self.log.append((self.name, "insert", rows))
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self):
        self.log = []

    def table(self, name):
        return FakeTable(self.log, name)


class SaveTest(unittest.TestCase):
    def act(self, type_key="strength_training", activity_id=24955009987, detail=DAY2):
        return {"activityId": activity_id, "activityType": {"typeKey": type_key}, **detail}

    def test_replaces_garmin_rows_of_that_activity_only(self):
        sb = FakeSupabase()
        result = SimpleNamespace(data=[{"id": 18, "external_id": "24955009987"}])
        garmin_sync.save_strength_exercises(sb, "2026-11-03", [self.act()], result)
        self.assertEqual(sb.log[0], ("strength_sessions", "delete"))
        self.assertIn(("strength_sessions", "eq", "activity_id", 18), sb.log)
        self.assertIn(("strength_sessions", "is", "workout_id", "null"), sb.log)  # no toca rutinas de la app
        inserted = [e for e in sb.log if e[1] == "insert"][0][2]
        self.assertEqual(len(inserted), 4)
        self.assertTrue(all(r["activity_id"] == 18 and r["date"] == "2026-11-03" and r["user_id"] == garmin_sync.USER_ID for r in inserted))

    def test_ignores_non_strength_and_missing_ids(self):
        sb = FakeSupabase()
        result = SimpleNamespace(data=[{"id": 5, "external_id": "1"}])
        garmin_sync.save_strength_exercises(sb, "2026-11-03", [self.act("cycling", 1)], result)
        garmin_sync.save_strength_exercises(sb, "2026-11-03", [self.act(activity_id=999)], result)  # sin id devuelto
        self.assertEqual(sb.log, [])

    def test_failure_never_raises(self):
        class Boom:
            def table(self, _):
                raise RuntimeError("db caída")
        garmin_sync.save_strength_exercises(Boom(), "2026-11-03", [self.act()], SimpleNamespace(data=[{"id": 18, "external_id": "24955009987"}]))


if __name__ == "__main__":
    unittest.main()
