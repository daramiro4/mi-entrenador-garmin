"""Lógica de sincronización de un día de datos de Garmin Connect con Supabase.

Compartido entre main.py (cron diario, GitHub Actions, siempre trae "ayer")
y api/sync_now.py (Vercel Python Function, sincronización manual bajo demanda
desde mi-entrenador-web, siempre trae "hoy"). El único parámetro que cambia
entre ambos es la fecha -- toda la lógica de descarga/guardado/fatiga vive
aquí una sola vez.
"""

import os
from datetime import date, timedelta

from supabase import create_client

USER_ID = "d6310074-a851-49e9-bdb2-9750e752d5b6"

GARMIN_TYPE_MAP = {
    "cycling": "cycling",
    "road_biking": "cycling",
    "indoor_cycling": "cycling",
    "virtual_ride": "cycling",
    "mountain_biking": "cycling",
    "gravel_cycling": "cycling",
    "running": "running",
    "trail_running": "running",
    "treadmill_running": "running",
    "indoor_running": "running",
    "strength_training": "strength",
}


def map_activity_type(garmin_type_key):
    return GARMIN_TYPE_MAP.get(garmin_type_key, "other")


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("⚠️ Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY. Se omite la sincronización con Supabase.")
        return None
    return create_client(url, key)


def to_int(value):
    return int(round(value)) if isinstance(value, (int, float)) else None


def save_daily_metrics(supabase, date_str, sleep_score, sleep_duration_minutes, stress_avg, hrv_avg, rhr, bb_max, bb_min):
    if supabase is None:
        return
    try:
        supabase.table("daily_metrics").upsert({
            "user_id": USER_ID,
            "date": date_str,
            "sleep_score": to_int(sleep_score),
            "sleep_duration_minutes": sleep_duration_minutes,
            "stress_avg": to_int(stress_avg),
            "hrv_ms": hrv_avg if isinstance(hrv_avg, (int, float)) else None,
            "resting_hr": to_int(rhr),
            "body_battery_max": to_int(bb_max),
            "body_battery_min": to_int(bb_min),
            "source": "garmin",
        }, on_conflict="user_id,date").execute()
        print("✅ daily_metrics sincronizado con Supabase.")
    except Exception as e:
        print(f"⚠️ Error guardando daily_metrics en Supabase: {e}")


def save_activities(supabase, date_str, activities):
    if supabase is None or not activities:
        return
    rows = []
    for act in activities:
        duration_seconds = act.get("duration")
        # Garmin ya manda el pulso medio/máximo y el tiempo en cada zona en
        # el resumen de la actividad -- no hace falta pedir nada aparte.
        hr_zone_seconds = None
        if act.get("hrTimeInZone_1") is not None:
            hr_zone_seconds = {
                "z1": act.get("hrTimeInZone_1"),
                "z2": act.get("hrTimeInZone_2"),
                "z3": act.get("hrTimeInZone_3"),
                "z4": act.get("hrTimeInZone_4"),
                "z5": act.get("hrTimeInZone_5"),
            }
        rows.append({
            "user_id": USER_ID,
            "external_id": str(act.get("activityId")),
            "date": date_str,
            "activity_type": map_activity_type(act.get("activityType", {}).get("typeKey")),
            "duration_minutes": round(duration_seconds / 60, 1) if duration_seconds else None,
            "avg_power": act.get("avgPower"),
            "normalized_power": act.get("normPower"),
            "tss": act.get("trainingStressScore"),
            "training_load": act.get("activityTrainingLoad"),
            "avg_hr": to_int(act.get("averageHR")),
            "max_hr": to_int(act.get("maxHR")),
            "hr_zone_seconds": hr_zone_seconds,
            "raw_data": act,
            "source": "garmin",
        })
    try:
        supabase.table("activities").upsert(rows, on_conflict="user_id,external_id").execute()
        print(f"✅ {len(rows)} actividad(es) sincronizada(s) con Supabase.")
    except Exception as e:
        print(f"⚠️ Error guardando activities en Supabase: {e}")


def get_body_battery_range(garmin, date_str):
    try:
        bb = garmin.get_body_battery(date_str)
        values = bb[0].get("bodyBatteryValuesArray", []) if bb else []
        levels = [v[1] for v in values if v[1] is not None]
        if not levels:
            return None, None
        return max(levels), min(levels)
    except Exception as e:
        print(f"⚠️ Error descargando body battery: {e}")
        return None, None


# --- Señal adicional de HRV (decisión propia, no viene del ACWR) ---
# El ACWR solo ve carga de entrenamiento -- no detecta sobrecarga por mala
# noche, estrés o enfermedad. El HRV sí. Umbral y ventana documentados como
# ajustables, mismo criterio que el resto de constantes del proyecto.
HRV_BASELINE_WINDOW_DAYS = 28
HRV_BASELINE_MIN_SAMPLES = 5  # por debajo de esto se ignora la señal, no hay base fiable
HRV_DROP_THRESHOLD_PCT = 0.15


def _hrv_warning_note(supabase, target_date_str, today_hrv_ms):
    """Devuelve una frase explicativa si el HRV de hoy cae por debajo de la
    media reciente, o None si no hay señal (sin dato de hoy, o sin
    suficiente historial para una media fiable)."""
    if not isinstance(today_hrv_ms, (int, float)):
        return None

    target_date = date.fromisoformat(target_date_str)
    window_start = (target_date - timedelta(days=HRV_BASELINE_WINDOW_DAYS)).isoformat()
    window_end = (target_date - timedelta(days=1)).isoformat()

    try:
        resp = (
            supabase.table("daily_metrics")
            .select("hrv_ms")
            .eq("user_id", USER_ID)
            .gte("date", window_start)
            .lte("date", window_end)
            .execute()
        )
        values = [r["hrv_ms"] for r in (resp.data or []) if r.get("hrv_ms") is not None]
    except Exception as e:
        print(f"⚠️ Error leyendo daily_metrics para la línea base de HRV: {e}")
        return None

    if len(values) < HRV_BASELINE_MIN_SAMPLES:
        return None

    baseline = sum(values) / len(values)
    if baseline <= 0:
        return None

    drop_pct = (baseline - today_hrv_ms) / baseline
    if drop_pct < HRV_DROP_THRESHOLD_PCT:
        return None

    return f"HRV {round(drop_pct * 100)}% por debajo de tu media de los últimos {HRV_BASELINE_WINDOW_DAYS} días."


def calculate_fatigue_index(supabase, target_date_str, today_hrv_ms=None):
    """
    ACWR = media(training_load últimos 7 días) / media(training_load últimos 28 días).
    'Datos insuficientes' = sin ninguna actividad registrada en la ventana de 28 días.
    El HRV de hoy (si viene y hay línea base suficiente) solo puede agravar
    la recomendación del ACWR, nunca mejorarla -- mismo espíritu que la capa
    diaria adaptativa de mi-entrenador-web (nunca cancela, solo degrada).
    """
    if supabase is None:
        return None

    target_date = date.fromisoformat(target_date_str)
    chronic_start = (target_date - timedelta(days=27)).isoformat()
    acute_start = target_date - timedelta(days=6)

    try:
        resp = (
            supabase.table("activities")
            .select("date, training_load")
            .eq("user_id", USER_ID)
            .gte("date", chronic_start)
            .lte("date", target_date_str)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        print(f"⚠️ Error leyendo activities para calcular ACWR: {e}")
        return None

    chronic_values = [r["training_load"] for r in rows if r.get("training_load") is not None]
    acute_values = [
        r["training_load"] for r in rows
        if r.get("training_load") is not None and date.fromisoformat(r["date"]) >= acute_start
    ]

    if not chronic_values:
        acute_load, chronic_load, acwr_ratio = None, None, None
        recommendation = "descanso"
        notes = "Datos insuficientes: sin actividades registradas en los últimos 28 días."
    else:
        chronic_load = round(sum(chronic_values) / len(chronic_values), 2)
        acute_load = round(sum(acute_values) / len(acute_values), 2) if acute_values else 0.0
        if chronic_load == 0:
            acwr_ratio = None
            recommendation = "descanso"
            notes = "Datos insuficientes: carga crónica es 0."
        else:
            acwr_ratio = round(acute_load / chronic_load, 2)
            notes = None
            if acwr_ratio > 1.5:
                recommendation = "descanso"
            elif acwr_ratio > 1.3:
                recommendation = "precaucion"
            else:
                recommendation = "normal"

    hrv_note = _hrv_warning_note(supabase, target_date_str, today_hrv_ms)
    if hrv_note:
        if recommendation == "normal":
            recommendation = "precaucion"
        notes = f"{notes} {hrv_note}" if notes else hrv_note

    try:
        supabase.table("fatigue_index").upsert({
            "user_id": USER_ID,
            "date": target_date_str,
            "acute_load": acute_load,
            "chronic_load": chronic_load,
            "acwr_ratio": acwr_ratio,
            "recommendation": recommendation,
            "notes": notes,
        }, on_conflict="user_id,date").execute()
        print(f"✅ fatigue_index sincronizado con Supabase (ACWR: {acwr_ratio}, recomendación: {recommendation}).")
    except Exception as e:
        print(f"⚠️ Error guardando fatigue_index en Supabase: {e}")

    return {"acwr_ratio": acwr_ratio, "recommendation": recommendation}


def sync_day(garmin, supabase, target_date_str):
    """Descarga sueño/estrés/VFC/FC reposo/actividades/body battery de Garmin
    Connect para `target_date_str`, los guarda en Supabase, y recalcula
    `fatigue_index` para esa misma fecha.

    Usado tanto por el cron diario (main.py, siempre con "ayer") como por el
    endpoint de sincronización manual (api/sync_now.py, siempre con "hoy") --
    el único parámetro que cambia es la fecha.
    """
    try:
        sleep_data = garmin.get_sleep_data(target_date_str)
        stress_data = garmin.get_stress_data(target_date_str)
        hrv_data = garmin.get_hrv_data(target_date_str)
        rhr_data = garmin.get_rhr_day(target_date_str)
        activities = garmin.get_activities_by_date(target_date_str, target_date_str)
    except Exception as e:
        raise RuntimeError(f"❌ ERROR descargando datos de Garmin: {e}")

    # Extraer valores útiles (Garmin puede devolver None si no hay datos ese día)
    sleep_score = (sleep_data or {}).get('dailySleepDTO', {}).get('sleepScores', {}).get('overall', {}).get('value', 'No data')
    sleep_time_seconds = (sleep_data or {}).get('dailySleepDTO', {}).get('sleepTimeSeconds') or 0
    sleep_duration_ms = sleep_time_seconds * 1000
    sleep_hours = round(sleep_duration_ms / (1000 * 60 * 60), 1) if sleep_duration_ms else 'No data'
    sleep_duration_minutes = round(sleep_time_seconds / 60) if sleep_time_seconds else None

    stress_avg = (stress_data or {}).get('averageStressLevel', 'No data')
    hrv_avg = (hrv_data or {}).get('hrvSummary', {}).get('weeklyAvg', 'No data')

    # Extraer la frecuencia cardíaca en reposo de forma segura
    rhr = 'No data'
    if rhr_data and 'allMetrics' in rhr_data and 'metricsMap' in rhr_data['allMetrics']:
        metrics_map = rhr_data['allMetrics']['metricsMap']
        if 'WELLNESS_RESTING_HEART_RATE' in metrics_map and metrics_map['WELLNESS_RESTING_HEART_RATE']:
            rhr = metrics_map['WELLNESS_RESTING_HEART_RATE'][0].get('value', 'No data')

    bb_max, bb_min = get_body_battery_range(garmin, target_date_str)

    activity_summary = []
    if activities:
        for act in activities:
            name = act.get('activityName', 'Actividad')
            dist = round(act.get('distance', 0) / 1000, 2)
            activity_summary.append(f"{name} ({dist} km)")
    act_str = ", ".join(activity_summary) if activity_summary else "Descanso"

    # Sincronizar con Supabase (nunca debe bloquear al llamador)
    save_daily_metrics(supabase, target_date_str, sleep_score, sleep_duration_minutes, stress_avg, hrv_avg, rhr, bb_max, bb_min)
    save_activities(supabase, target_date_str, activities)
    fatigue = calculate_fatigue_index(supabase, target_date_str, today_hrv_ms=hrv_avg)

    return {
        "date": target_date_str,
        "sleep_score": sleep_score,
        "sleep_hours": sleep_hours,
        "stress_avg": stress_avg,
        "hrv_avg": hrv_avg,
        "rhr": rhr,
        "act_str": act_str,
        "activities_synced": len(activities) if activities else 0,
        "fatigue": fatigue,
    }
