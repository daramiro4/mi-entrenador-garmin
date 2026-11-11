"""Señales de recuperación para el índice de fatiga: FC en reposo y sueño.

El ACWR solo ve carga de entrenamiento: no detecta una mala semana de descanso. Estas señales solo
pueden agravar la recomendación (de "normal" a "precaucion"), nunca mejorarla -- mismo criterio que el HRV
(api/garmin_sync.py) y que la capa diaria adaptativa de mi-entrenador-web. Funciones puras, sin red.
"""

RESTING_HR_BASELINE_DAYS = 28
RESTING_HR_MIN_SAMPLES = 5      # por debajo se ignora la señal: no hay línea base fiable
RESTING_HR_RISE_BPM = 5         # ppm por encima de la media de los 28 días
SLEEP_RECENT_NIGHTS = 3         # noches que se promedian (la de hoy incluida)
SLEEP_MIN_NIGHTS_WITH_DATA = 2  # con menos noches con dato se ignora
SLEEP_SHORT_MINUTES = 360       # 6 h de media


def resting_hr_note(resting_hr_today, history):
    """Frase si la FC en reposo de hoy supera la media del historial en RESTING_HR_RISE_BPM o más."""
    if not isinstance(resting_hr_today, (int, float)):
        return None
    values = [v for v in history if isinstance(v, (int, float)) and v > 0]
    if len(values) < RESTING_HR_MIN_SAMPLES:
        return None
    baseline = sum(values) / len(values)
    rise = resting_hr_today - baseline
    if rise < RESTING_HR_RISE_BPM:
        return None
    return (
        f"FC en reposo {round(rise)} ppm por encima de tu media de los últimos "
        f"{RESTING_HR_BASELINE_DAYS} días ({round(resting_hr_today)} frente a {round(baseline)})."
    )


def short_sleep_note(recent_sleep_minutes):
    """Frase si el sueño medio de las últimas noches con dato es menor de SLEEP_SHORT_MINUTES."""
    values = [v for v in recent_sleep_minutes if isinstance(v, (int, float)) and v > 0]
    if len(values) < SLEEP_MIN_NIGHTS_WITH_DATA:
        return None
    average = sum(values) / len(values)
    if average >= SLEEP_SHORT_MINUTES:
        return None
    return f"Sueño medio de {average / 60:.1f} h en las últimas {len(values)} noches."


def recovery_notes(resting_hr_today, resting_hr_history, recent_sleep_minutes):
    """Lista de frases de aviso (vacía si no hay señal)."""
    notes = [
        resting_hr_note(resting_hr_today, resting_hr_history),
        short_sleep_note(recent_sleep_minutes),
    ]
    return [n for n in notes if n]
