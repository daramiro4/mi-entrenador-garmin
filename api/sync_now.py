"""Vercel Python Function: sincronización manual e inmediata con Garmin
Connect para el día de HOY (o los últimos `days` días).

Independiente del cron diario (main.py, GitHub Actions, que siempre trae
"ayer") -- login propio, sin token cacheado, mismo patrón que main.py usa.
Se invoca desde mi-entrenador-web cuando el usuario pulsa "Actualizar desde
Garmin" en el dashboard (sin body -- un solo día, hoy). Reutiliza el mismo
secreto (`GARMIN_SEND_SECRET`) que ya protege api/send_workout.py -- ambos
endpoints viven en el mismo proyecto Vercel y tienen el mismo nivel de
confianza (solo mi-entrenador-web los llama).

BaseHTTPRequestHandler puro (sin Flask/FastAPI), mismo motivo que
send_workout.py: no añadir dependencias nuevas ni arriesgar que Vercel
confunda main.py con el entrypoint de un framework detectado automáticamente.

`days` (body JSON opcional, ej. `{"days": 7}`) sincroniza también los
`days - 1` días anteriores a hoy, de más antiguo a más reciente -- backfill
puntual bajo demanda (curl directo, no hay botón para esto en el dashboard).
sync_day() ya es idempotente (upsert por user_id+date/external_id), así que
repetir un día ya sincronizado no duplica nada.
"""

import json
import os
import sys
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler

# Vercel ejecuta cada archivo de /api sin añadir su propio directorio a
# sys.path, así que el import de un módulo hermano falla sin este ajuste.
sys.path.insert(0, os.path.dirname(__file__))

from garminconnect import Garmin
from garmin_sync import get_supabase, sync_day


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

        garmin_email = os.environ.get("GARMIN_EMAIL")
        garmin_pass = os.environ.get("GARMIN_PASSWORD")
        if not garmin_email or not garmin_pass:
            self._send_json(500, {"ok": False, "error": "missing Garmin credentials"})
            return

        try:
            content_length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(content_length)) if content_length else {}
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        days = body.get("days", 1) if isinstance(body, dict) else 1
        if not isinstance(days, int) or days < 1:
            self._send_json(400, {"ok": False, "error": "days must be a positive integer"})
            return

        debug_days = body.get("debug_days") if isinstance(body, dict) else None

        today = date.today()
        target_dates = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]

        try:
            garmin = Garmin(garmin_email, garmin_pass)
            garmin.login()

            # DIAGNÓSTICO TEMPORAL (quitar tras confirmar por qué faltan
            # actividades en el backfill): {"debug_days": N} pide a Garmin
            # las actividades de los últimos N días SIN acotar por fecha
            # exacta, para ver bajo qué fecha las tiene registradas de
            # verdad -- get_activities_by_date(fecha, fecha) por día podría
            # estar perdiendo alguna por una fecha distinta a la esperada.
            if isinstance(debug_days, int) and debug_days > 0:
                raw = garmin.get_activities_by_date(
                    (today - timedelta(days=debug_days)).isoformat(), today.isoformat()
                )
                self._send_json(200, {
                    "ok": True,
                    "debug": [
                        {
                            "activityId": a.get("activityId"),
                            "activityName": a.get("activityName"),
                            "typeKey": (a.get("activityType") or {}).get("typeKey"),
                            "startTimeLocal": a.get("startTimeLocal"),
                            "startTimeGMT": a.get("startTimeGMT"),
                        }
                        for a in (raw or [])
                    ],
                })
                return

            supabase = get_supabase()
            results = [sync_day(garmin, supabase, target_date_str) for target_date_str in target_dates]
        except Exception as e:  # noqa: BLE001 -- superficie cualquier fallo de Garmin/Supabase al llamador
            self._send_json(502, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {
            "ok": True,
            "date": today.isoformat(),
            "activities_synced": sum(r["activities_synced"] for r in results),
            "fatigue": results[-1]["fatigue"],
            "days": [
                {"date": r["date"], "activities_synced": r["activities_synced"], "fatigue": r["fatigue"]}
                for r in results
            ],
        })
