"""Ejercicios y pesos de un entreno de fuerza de Garmin -> filas de `strength_sessions`.

Garmin manda en el resumen de la actividad `summarizedExerciseSets`: una entrada por ejercicio con
`category`, `subCategory`, `sets`, `reps` (total de todas las series), `volume` y `maxWeight`
(ambos en gramos). Solo hay el peso máximo del ejercicio, no el de cada serie.

Convenciones de las filas (mismas columnas que ya lee la web: series×reps @ peso):
  sets      series del ejercicio
  reps      repeticiones por serie = total / series, redondeado
  weight_kg peso máximo usado (None si no hay carga: peso corporal)
  notes     el total real, para no perder el dato original
`volume_kg` NO se escribe: es una columna generada por la base (sets * reps * weight_kg).
"""

# Categorías que no son fuerza (el bloque de cardio del reloj, etc.).
SKIP_CATEGORIES = {"CARDIO"}

# Nombre en español de los ejercicios más habituales (subCategory de Garmin). El resto cae a un
# nombre legible en inglés derivado del identificador, para no mostrar MAYÚSCULAS_CON_GUIONES.
NAMES_ES = {
    "STANDING_DUMBBELL_BICEPS_CURL": "Curl de bíceps con mancuernas",
    "ROMANIAN_DEADLIFT": "Peso muerto rumano",
    "CABLE_OVERHEAD_TRICEPS_EXTENSION": "Extensión de tríceps en polea",
    "MILITARY_PRESS": "Press militar",
    "BARBELL_SQUAT_SNATCH": "Sentadilla con barra",
    "BARBELL_BENCH_PRESS": "Press de banca con barra",
    "DUMBBELL_BENCH_PRESS": "Press de pecho con mancuernas",
    "DUMBBELL_SHOULDER_PRESS": "Press de hombro con mancuernas",
    "PLANK": "Plancha",
    "REVERSE_GRIP_PULLDOWN": "Jalón con agarre supino",
    "LAT_PULLDOWN": "Jalón al pecho",
    "BARBELL_DEADLIFT": "Peso muerto con barra",
    "KETTLEBELL_DEADLIFT": "Peso muerto con kettlebell",
    "GOBLET_SQUAT": "Sentadilla goblet",
    "AIR_SQUAT": "Sentadilla con peso corporal",
    "SQUAT": "Sentadilla",
    "STEP_UP": "Subida al cajón",
    "LEG_PRESS": "Prensa de piernas",
    "DUMBBELL_LUNGE": "Zancada con mancuernas",
    "DUMBBELL_REVERSE_LUNGE": "Zancada hacia atrás con mancuernas",
    "DUMBBELL_BULGARIAN_SPLIT_SQUAT": "Sentadilla búlgara",
    "DUMBBELL_ROW": "Remo con mancuerna",
    "INVERTED_ROW": "Remo invertido",
    "SEATED_CABLE_ROW": "Remo sentado en polea",
    "BANDED_FACE_PULLS": "Face pull con banda",
    "PUSH_UP": "Flexiones",
    "BAND_ASSISTED_PULL_UP": "Dominadas asistidas con banda",
    "BARBELL_HIP_THRUST_WITH_BENCH": "Hip thrust",
    "BARBELL_HIP_THRUST_ON_FLOOR": "Puente de glúteo con barra",
    "STANDING_CALF_RAISE": "Elevación de talones",
    "FARMERS_CARRY": "Paseo del granjero",
    "DEAD_BUG": "Dead bug",
    "CABLE_CORE_PRESS": "Press Pallof",
}
UNKNOWN_NAME = "Ejercicio sin identificar"


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def exercise_name(category, sub_category):
    key = sub_category or category
    if not key or key == "UNKNOWN":
        return UNKNOWN_NAME
    if key in NAMES_ES:
        return NAMES_ES[key]
    return key.replace("_", " ").title()


def extract_exercise_rows(activity):
    """Filas (sin user_id/activity_id/date) de un entreno de fuerza de Garmin. [] si no hay detalle."""
    if not isinstance(activity, dict):
        return []
    sets_summary = activity.get("summarizedExerciseSets")
    if not isinstance(sets_summary, list):
        return []
    rows = []
    for entry in sets_summary:
        if not isinstance(entry, dict):
            continue
        category = entry.get("category")
        if category in SKIP_CATEGORIES:
            continue
        sets = _num(entry.get("sets"))
        total_reps = _num(entry.get("reps"))
        if not sets or sets <= 0 or not total_reps or total_reps <= 0:
            continue  # sin series o sin repeticiones registradas: no hay nada que guardar
        sets = int(sets)
        max_weight_g = _num(entry.get("maxWeight"))
        weight_kg = round(max_weight_g / 1000, 1) if max_weight_g and max_weight_g > 0 else None
        notes = f"Garmin: {int(total_reps)} repeticiones en {sets} series"
        if weight_kg is not None:
            notes += f"; peso máximo {weight_kg:g} kg"
        rows.append({
            "exercise": exercise_name(category, entry.get("subCategory")),
            "sets": sets,
            "reps": max(1, int(total_reps / sets + 0.5)),  # medio hacia arriba (no el redondeo a pares de round())
            "weight_kg": weight_kg,
            "notes": notes,
        })
    return rows
