"""Traduce (session_type, planned_tss, ftp_watts) en un workout estructurado
de ciclismo para Garmin Connect.

Función pura, sin dependencias de garminconnect ni de red -- solo construye
el dict JSON que send_workout.py sube con garmin.upload_workout(). Los IDs de
Garmin usados abajo (sportType/stepType/conditionType/targetType) no están
documentados oficialmente; se confirmaron leyendo el código fuente de la
librería garminconnect (garminconnect/workout.py, clases SportType, StepType,
ConditionType, TargetType) en vez de adivinarlos.

Solo soporta 'z2' y 'quality' -- 'strength'/'rest' no tienen contenido de
potencia que traducir a un workout de Garmin.
"""

SPORT_TYPE_CYCLING = {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2}

STEP_TYPE_WARMUP = {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1}
STEP_TYPE_COOLDOWN = {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2}
STEP_TYPE_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_TYPE_RECOVERY = {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4}
STEP_TYPE_REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}

END_CONDITION_TIME = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}
END_CONDITION_ITERATIONS = {
    "conditionTypeId": 7,
    "conditionTypeKey": "iterations",
    "displayOrder": 7,
    "displayable": False,
}

TARGET_NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
TARGET_POWER_ZONE = {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 2}

# --- Supuestos de zona/duración (documentados, ajustables) ---
# Igual que en lib/plan-generator.ts de mi-entrenador-web: no hay una fórmula
# cerrada para esto, son valores de partida razonables.
Z2_LOW_PCT = 0.65
Z2_HIGH_PCT = 0.75
Z2_ASSUMED_IF = 0.70  # punto medio de la zona, para despejar duración desde TSS

QUALITY_WARMUP_SECONDS = 600
QUALITY_COOLDOWN_SECONDS = 600
QUALITY_INTERVAL_SECONDS = 180
QUALITY_RECOVERY_SECONDS = 180
QUALITY_INTERVAL_LOW_PCT = 1.05
QUALITY_INTERVAL_HIGH_PCT = 1.20
QUALITY_RECOVERY_LOW_PCT = 0.50
QUALITY_RECOVERY_HIGH_PCT = 0.60
QUALITY_WARMUP_COOLDOWN_IF = 0.60
QUALITY_INTERVAL_IF = 1.10
QUALITY_RECOVERY_IF = 0.55
QUALITY_MIN_REPS = 3
QUALITY_MAX_REPS = 8


def _tss_for_block(seconds, intensity_factor):
    """TSS ~= horas * IF^2 * 100 (aproximación estándar de Coggan para bloques estables)."""
    hours = seconds / 3600
    return hours * (intensity_factor**2) * 100


def _power_zone_target(ftp_watts, low_pct, high_pct):
    return {
        "targetType": TARGET_POWER_ZONE,
        "targetValueOne": round(ftp_watts * low_pct),
        "targetValueTwo": round(ftp_watts * high_pct),
    }


def _build_z2_workout(ftp_watts, date_str, planned_tss=None, duration_minutes=None):
    """`duration_minutes` cubre las z2 de reaclimatación (decisión 5), que no
    llevan `planned_tss` a propósito -- si viene, manda sobre la derivación
    por TSS."""
    if duration_minutes is not None:
        duration_seconds = max(600, round(duration_minutes * 60))
    else:
        duration_seconds = max(600, round((planned_tss / (Z2_ASSUMED_IF**2 * 100)) * 3600))
    zone = _power_zone_target(ftp_watts, Z2_LOW_PCT, Z2_HIGH_PCT)

    step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 1,
        "stepType": STEP_TYPE_INTERVAL,
        "endCondition": END_CONDITION_TIME,
        "endConditionValue": duration_seconds,
        "targetType": zone["targetType"],
        "targetValueOne": zone["targetValueOne"],
        "targetValueTwo": zone["targetValueTwo"],
    }

    return {
        "workoutName": f"Z2 {date_str}",
        "sportType": SPORT_TYPE_CYCLING,
        "estimatedDurationInSecs": duration_seconds,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": SPORT_TYPE_CYCLING, "workoutSteps": [step]}
        ],
    }


def _build_quality_workout(planned_tss, ftp_watts, date_str):
    warmup_cooldown_tss = 2 * _tss_for_block(QUALITY_WARMUP_SECONDS, QUALITY_WARMUP_COOLDOWN_IF)
    pair_tss = _tss_for_block(QUALITY_INTERVAL_SECONDS, QUALITY_INTERVAL_IF) + _tss_for_block(
        QUALITY_RECOVERY_SECONDS, QUALITY_RECOVERY_IF
    )
    reps = round((planned_tss - warmup_cooldown_tss) / pair_tss) if pair_tss > 0 else QUALITY_MIN_REPS
    reps = max(QUALITY_MIN_REPS, min(QUALITY_MAX_REPS, reps))

    interval_zone = _power_zone_target(ftp_watts, QUALITY_INTERVAL_LOW_PCT, QUALITY_INTERVAL_HIGH_PCT)
    recovery_zone = _power_zone_target(ftp_watts, QUALITY_RECOVERY_LOW_PCT, QUALITY_RECOVERY_HIGH_PCT)

    warmup_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 1,
        "stepType": STEP_TYPE_WARMUP,
        "endCondition": END_CONDITION_TIME,
        "endConditionValue": QUALITY_WARMUP_SECONDS,
        "targetType": TARGET_NO_TARGET,
    }

    interval_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 1,
        "stepType": STEP_TYPE_INTERVAL,
        "endCondition": END_CONDITION_TIME,
        "endConditionValue": QUALITY_INTERVAL_SECONDS,
        "targetType": interval_zone["targetType"],
        "targetValueOne": interval_zone["targetValueOne"],
        "targetValueTwo": interval_zone["targetValueTwo"],
    }

    recovery_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 2,
        "stepType": STEP_TYPE_RECOVERY,
        "endCondition": END_CONDITION_TIME,
        "endConditionValue": QUALITY_RECOVERY_SECONDS,
        "targetType": recovery_zone["targetType"],
        "targetValueOne": recovery_zone["targetValueOne"],
        "targetValueTwo": recovery_zone["targetValueTwo"],
    }

    repeat_group = {
        "type": "RepeatGroupDTO",
        "stepOrder": 2,
        "stepType": STEP_TYPE_REPEAT,
        "numberOfIterations": reps,
        "workoutSteps": [interval_step, recovery_step],
        "endCondition": END_CONDITION_ITERATIONS,
        "endConditionValue": float(reps),
    }

    cooldown_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": 3,
        "stepType": STEP_TYPE_COOLDOWN,
        "endCondition": END_CONDITION_TIME,
        "endConditionValue": QUALITY_COOLDOWN_SECONDS,
        "targetType": TARGET_NO_TARGET,
    }

    total_seconds = (
        QUALITY_WARMUP_SECONDS
        + reps * (QUALITY_INTERVAL_SECONDS + QUALITY_RECOVERY_SECONDS)
        + QUALITY_COOLDOWN_SECONDS
    )

    return {
        "workoutName": f"Calidad {date_str}",
        "sportType": SPORT_TYPE_CYCLING,
        "estimatedDurationInSecs": total_seconds,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": SPORT_TYPE_CYCLING,
                "workoutSteps": [warmup_step, repeat_group, cooldown_step],
            }
        ],
    }


def build_cycling_workout(session_type, ftp_watts, date_str, planned_tss=None, duration_minutes=None):
    """Construye el JSON de un workout de ciclismo para Garmin Connect."""
    if session_type == "z2":
        return _build_z2_workout(ftp_watts, date_str, planned_tss=planned_tss, duration_minutes=duration_minutes)
    if session_type == "quality":
        if planned_tss is None:
            raise ValueError("quality requiere planned_tss (no soporta duración fija)")
        return _build_quality_workout(planned_tss, ftp_watts, date_str)
    raise ValueError(f"session_type no soportado para envío a Garmin: {session_type}")


_STEP_TYPE_LABEL = {
    STEP_TYPE_WARMUP["stepTypeId"]: "Calentamiento",
    STEP_TYPE_COOLDOWN["stepTypeId"]: "Enfriamiento",
    STEP_TYPE_INTERVAL["stepTypeId"]: "Intervalo",
    STEP_TYPE_RECOVERY["stepTypeId"]: "Recuperación",
}


def _summarize_step(step, reps):
    label = _STEP_TYPE_LABEL.get(step["stepType"]["stepTypeId"], "Bloque")
    if reps > 1:
        label = f"{label} x{reps}"

    entry = {
        "label": label,
        "duration_minutes": round(step["endConditionValue"] / 60),
    }
    if step.get("targetType", {}).get("workoutTargetTypeId") == TARGET_POWER_ZONE["workoutTargetTypeId"]:
        entry["target_low_watts"] = step["targetValueOne"]
        entry["target_high_watts"] = step["targetValueTwo"]
    return entry


def summarize_workout(workout_json):
    """Resume un workout ya construido (build_cycling_workout) para mostrarlo
    como vista previa antes de subirlo -- mismo JSON, nunca se desincroniza
    porque no reimplementa ningún cálculo, solo lo recorre."""
    steps = []
    for segment in workout_json["workoutSegments"]:
        for step in segment["workoutSteps"]:
            if step["type"] == "RepeatGroupDTO":
                reps = int(step["numberOfIterations"])
                for sub_step in step["workoutSteps"]:
                    steps.append(_summarize_step(sub_step, reps))
            else:
                steps.append(_summarize_step(step, 1))

    return {
        "workout_name": workout_json["workoutName"],
        "estimated_duration_minutes": round(workout_json["estimatedDurationInSecs"] / 60),
        "steps": steps,
    }
