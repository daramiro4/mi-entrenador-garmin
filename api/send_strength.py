"""Vercel Python Function: envío manual de una rutina de FUERZA a Garmin Connect.

Hermana de send_workout.py (bici): mismo secreto compartido (GARMIN_SEND_SECRET), mismo login nativo
de `garminconnect` y mismo `upload_workout`. Aquí NO se construye el entreno: lo hace
mi-entrenador-web (lib/strength/garmin-map.ts) y llega ya en el formato de Garmin.

Cuerpo: {"workout": {...JSON de Garmin...}, "date": "YYYY-MM-DD" | null}
Respuesta: {"ok": true, "workout_id": ..., "scheduled_for": "YYYY-MM-DD" | null}
Una sola pasada, sin reintentos: si Garmin rechaza el login no se vuelve a probar (riesgo de bloqueo).
"""

import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

from garminconnect import Garmin
from strength_payload import MAX_BODY_BYTES, validate_date, validate_strength_payload

MIN_SECONDS_BETWEEN_SENDS = 20
_last_send = 0.0


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global _last_send
        send_secret = os.environ.get("GARMIN_SEND_SECRET")
        auth_header = self.headers.get("Authorization", "")
        if not send_secret or not hmac.compare_digest(auth_header, f"Bearer {send_secret}"):
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "cuerpo vacío o demasiado grande"})
            return
        try:
            body = json.loads(self.rfile.read(content_length))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        workout = body.get("workout")
        date_str = body.get("date")
        problem = validate_strength_payload(workout) or validate_date(date_str)
        if problem:
            self._send_json(400, {"ok": False, "error": problem})
            return

        wait = MIN_SECONDS_BETWEEN_SENDS - (time.time() - _last_send)
        if wait > 0:
            self._send_json(429, {"ok": False, "error": f"Espera {int(wait) + 1} s antes de volver a enviar."})
            return

        garmin_email = os.environ.get("GARMIN_EMAIL")
        garmin_pass = os.environ.get("GARMIN_PASSWORD")
        if not garmin_email or not garmin_pass:
            self._send_json(500, {"ok": False, "error": "missing Garmin credentials"})
            return

        _last_send = time.time()
        try:
            garmin = Garmin(garmin_email, garmin_pass)
            garmin.login()
            uploaded = garmin.upload_workout(workout)
            workout_id = uploaded.get("workoutId") if isinstance(uploaded, dict) else None
            if workout_id is None:
                raise RuntimeError(f"No se pudo leer workoutId de la respuesta de Garmin: {uploaded}")
            scheduled = None
            if date_str:
                garmin.schedule_workout(workout_id, date_str)
                scheduled = date_str
        except Exception as e:  # noqa: BLE001 -- superficie cualquier fallo de Garmin al llamador
            self._send_json(502, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {"ok": True, "workout_id": workout_id, "scheduled_for": scheduled})
