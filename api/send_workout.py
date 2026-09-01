"""Vercel Python Function: envío manual de una sesión planificada a Garmin
Connect como workout estructurado.

Independiente del cron diario (main.py, GitHub Actions) -- login propio,
sin token cacheado, mismo patrón que main.py usa. Se invoca desde
mi-entrenador-web cuando el usuario pulsa "Enviar a Garmin" en una sesión de
tipo quality/z2.

BaseHTTPRequestHandler puro (sin Flask/FastAPI) para no añadir dependencias
nuevas ni arriesgar que Vercel confunda main.py (el script del cron, que no
define `app`) con el entrypoint de un framework detectado automáticamente.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# Vercel ejecuta cada archivo de /api sin añadir su propio directorio a
# sys.path, así que el import de un módulo hermano falla sin este ajuste.
sys.path.insert(0, os.path.dirname(__file__))

from garminconnect import Garmin
from workout_builder import build_cycling_workout, summarize_workout

SUPPORTED_SESSION_TYPES = ("z2", "quality")


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        send_secret = os.environ.get("GARMIN_SEND_SECRET")
        auth_header = self.headers.get("Authorization", "")
        if not send_secret or auth_header != f"Bearer {send_secret}":
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            body = json.loads(raw_body)
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        date_str = body.get("date")
        session_type = body.get("session_type")
        planned_tss = body.get("planned_tss")
        duration_minutes = body.get("duration_minutes")
        ftp_watts = body.get("ftp_watts")
        preview = bool(body.get("preview"))

        has_tss = isinstance(planned_tss, (int, float))
        # duration_minutes solo es válido para z2 (reacclimatización, decisión 5)
        # -- quality siempre necesita planned_tss para construir los intervalos.
        has_duration = session_type == "z2" and isinstance(duration_minutes, (int, float))

        if (
            not date_str
            or session_type not in SUPPORTED_SESSION_TYPES
            or not isinstance(ftp_watts, (int, float))
            or not (has_tss or has_duration)
        ):
            self._send_json(400, {"ok": False, "error": "missing or invalid fields"})
            return

        try:
            workout_json = build_cycling_workout(
                session_type,
                ftp_watts,
                date_str,
                planned_tss=planned_tss if has_tss else None,
                duration_minutes=duration_minutes if has_duration else None,
            )
        except Exception as e:  # noqa: BLE001
            self._send_json(400, {"ok": False, "error": str(e)})
            return

        # La vista previa no toca Garmin en absoluto -- ni credenciales ni
        # red -- para que sea barata y no dependa de que la cuenta esté bien.
        if preview:
            self._send_json(200, {"ok": True, "preview": summarize_workout(workout_json)})
            return

        garmin_email = os.environ.get("GARMIN_EMAIL")
        garmin_pass = os.environ.get("GARMIN_PASSWORD")
        if not garmin_email or not garmin_pass:
            self._send_json(500, {"ok": False, "error": "missing Garmin credentials"})
            return

        try:
            garmin = Garmin(garmin_email, garmin_pass)
            garmin.login()

            uploaded = garmin.upload_workout(workout_json)
            workout_id = uploaded.get("workoutId") if isinstance(uploaded, dict) else None
            if workout_id is None:
                raise RuntimeError(f"No se pudo leer workoutId de la respuesta de Garmin: {uploaded}")

            garmin.schedule_workout(workout_id, date_str)
        except Exception as e:  # noqa: BLE001 -- superficie cualquier fallo de Garmin al llamador
            self._send_json(502, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {"ok": True, "garmin_workout_id": workout_id, "scheduled_date": date_str})
