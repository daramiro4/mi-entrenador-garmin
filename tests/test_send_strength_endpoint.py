"""El endpoint api/send_strength.py de punta a punta con un Garmin simulado (sin red hacia Garmin)."""
import json
import os
import sys
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest import mock

# garminconnect real no hace falta (ni debe usarse) en los tests: se sustituye antes de importar el endpoint.
fake_gc = types.ModuleType("garminconnect")


class _Placeholder:  # pragma: no cover - se reemplaza en cada test
    pass


fake_gc.Garmin = _Placeholder
sys.modules.setdefault("garminconnect", fake_gc)
sys.modules["garminconnect"].Garmin = _Placeholder

from api import send_strength  # noqa: E402

SECRET = "secreto-de-prueba"
GOOD = {
    "workoutName": "Pelotón",
    "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
    "workoutSegments": [{"segmentOrder": 1, "workoutSteps": [
        {"type": "RepeatGroupDTO", "stepOrder": 1, "numberOfIterations": 3, "workoutSteps": [
            {"type": "ExecutableStepDTO", "stepOrder": 2}, {"type": "ExecutableStepDTO", "stepOrder": 3}]},
    ]}],
}


class FakeGarmin:
    instances = []
    fail_login = False

    def __init__(self, email, password):
        self.calls = []
        FakeGarmin.instances.append(self)

    def login(self):
        self.calls.append("login")
        if FakeGarmin.fail_login:
            raise RuntimeError("login rechazado")

    def upload_workout(self, workout):
        self.calls.append(("upload", workout["workoutName"]))
        return {"workoutId": 987654}

    def schedule_workout(self, workout_id, date_str):
        self.calls.append(("schedule", workout_id, date_str))


class EndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), send_strength.handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeGarmin.instances = []
        FakeGarmin.fail_login = False
        send_strength._last_send = 0.0
        self.env = mock.patch.dict(os.environ, {"GARMIN_SEND_SECRET": SECRET, "GARMIN_EMAIL": "a@b.c", "GARMIN_PASSWORD": "x"})
        self.env.start()
        self.garmin = mock.patch.object(send_strength, "Garmin", FakeGarmin)
        self.garmin.start()

    def tearDown(self):
        self.garmin.stop()
        self.env.stop()

    def post(self, body, secret=SECRET, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers["Authorization"] = f"Bearer {secret}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_unauthorized_never_touches_garmin(self):
        for secret in (None, "otro"):
            status, body = self.post({"workout": GOOD, "date": None}, secret=secret)
            self.assertEqual(status, 401)
        self.assertEqual(FakeGarmin.instances, [])

    def test_uploads_and_schedules(self):
        status, body = self.post({"workout": GOOD, "date": "2026-11-05"})
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "workout_id": 987654, "scheduled_for": "2026-11-05"})
        self.assertEqual(FakeGarmin.instances[0].calls, ["login", ("upload", "Pelotón"), ("schedule", 987654, "2026-11-05")])

    def test_upload_without_date_does_not_schedule(self):
        status, body = self.post({"workout": GOOD, "date": None})
        self.assertEqual(status, 200)
        self.assertIsNone(body["scheduled_for"])
        self.assertEqual(FakeGarmin.instances[0].calls, ["login", ("upload", "Pelotón")])

    def test_invalid_input_is_rejected_before_login(self):
        self.assertEqual(self.post({"workout": {"workoutName": "x"}, "date": None})[0], 400)
        self.assertEqual(self.post({"workout": GOOD, "date": "05/11/2026"})[0], 400)
        self.assertEqual(self.post(None, raw=b"no es json")[0], 400)
        self.assertEqual(FakeGarmin.instances, [])

    def test_rate_limit_between_sends(self):
        self.assertEqual(self.post({"workout": GOOD, "date": None})[0], 200)
        status, body = self.post({"workout": GOOD, "date": None})
        self.assertEqual(status, 429)
        self.assertEqual(len(FakeGarmin.instances), 1)

    def test_garmin_login_failure_is_a_single_attempt(self):
        FakeGarmin.fail_login = True
        status, body = self.post({"workout": GOOD, "date": None})
        self.assertEqual(status, 502)
        self.assertIn("login rechazado", body["error"])
        self.assertEqual(len(FakeGarmin.instances), 1)
        self.assertEqual(FakeGarmin.instances[0].calls, ["login"])

    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {"GARMIN_EMAIL": "", "GARMIN_PASSWORD": ""}):
            status, _ = self.post({"workout": GOOD, "date": None})
        self.assertEqual(status, 500)


if __name__ == "__main__":
    unittest.main()
