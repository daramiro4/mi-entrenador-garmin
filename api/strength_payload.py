"""Validación de forma del entreno de fuerza que manda mi-entrenador-web (sin red ni Garmin).

La web construye el JSON de Garmin (lib/strength/garmin-map.ts); este módulo solo comprueba que
tenga la forma mínima y que no exceda límites razonables antes de subirlo a Garmin Connect.
"""
import re

MAX_BODY_BYTES = 200_000
MAX_TOP_LEVEL_STEPS = 200
MAX_TOTAL_STEPS = 400
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _count_steps(steps):
    total = 0
    for step in steps:
        total += 1
        if isinstance(step, dict) and isinstance(step.get("workoutSteps"), list):
            total += _count_steps(step["workoutSteps"])
    return total


def validate_strength_payload(payload):
    """Devuelve un mensaje de error en español, o None si el entreno es aceptable."""
    if not isinstance(payload, dict):
        return "workout debe ser un objeto"
    name = payload.get("workoutName")
    if not isinstance(name, str) or not name.strip():
        return "falta workoutName"
    sport = payload.get("sportType")
    if not isinstance(sport, dict) or sport.get("sportTypeKey") != "strength_training":
        return "solo se admiten entrenos de fuerza"
    segments = payload.get("workoutSegments")
    if not isinstance(segments, list) or not segments or not isinstance(segments[0], dict):
        return "faltan workoutSegments"
    steps = segments[0].get("workoutSteps")
    if not isinstance(steps, list) or not steps:
        return "workoutSteps vacío"
    if len(steps) > MAX_TOP_LEVEL_STEPS or _count_steps(steps) > MAX_TOTAL_STEPS:
        return "workoutSteps demasiado largo"
    return None


def validate_date(date_str):
    """None si la fecha es válida (YYYY-MM-DD) o no se pide programar."""
    if date_str is None:
        return None
    if not isinstance(date_str, str) or not DATE_RE.match(date_str):
        return "fecha inválida (YYYY-MM-DD)"
    return None
