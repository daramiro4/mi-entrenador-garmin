"""Vercel Python Function: sincronización manual e inmediata con Garmin
Connect para el día de HOY.

Independiente del cron diario (main.py, GitHub Actions, que siempre trae
"ayer") -- login propio, sin token cacheado, mismo patrón que main.py usa.
Se invoca desde mi-entrenador-web cuando el usuario pulsa "Actualizar desde
Garmin" en el dashboard. Reutiliza el mismo secreto (`GARMIN_SEND_SECRET`)
que ya protege api/send_workout.py -- ambos endpoints viven en el mismo
proyecto Vercel y tienen el mismo nivel de confianza (solo mi-entrenador-web
los llama).

BaseHTTPRequestHandler puro (sin Flask/FastAPI), mismo motivo que
send_workout.py: no añadir dependencias nuevas ni arriesgar que Vercel
confunda main.py con el entrypoint de un framework detectado automáticamente.

No hace backfill de "ayer": si el cron ya corrió esa mañana, ayer ya está en
Supabase; si no corrió, es un problema del cron, no de este botón.
"""

import json
import os
import sys
from datetime import date
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

        today_str = date.today().isoformat()

        try:
            garmin = Garmin(garmin_email, garmin_pass)
            garmin.login()

            supabase = get_supabase()
            result = sync_day(garmin, supabase, today_str)
        except Exception as e:  # noqa: BLE001 -- superficie cualquier fallo de Garmin/Supabase al llamador
            self._send_json(502, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {
            "ok": True,
            "date": today_str,
            "activities_synced": result["activities_synced"],
            "fatigue": result["fatigue"],
        })
