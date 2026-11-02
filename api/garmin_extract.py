"""Extracción tolerante de métricas diarias de las respuestas de Garmin Connect.

Sin dependencias (solo stdlib) para poder probarse sin red ni credenciales.
Garmin no documenta estas respuestas y los nombres de campo cambian entre
endpoints, así que se aceptan varias claves y se descartan los centinelas
negativos (-1/-2 = "sin datos") en vez de guardarlos como si fueran medidas.
"""


def _num(value):
    # bool es subclase de int: no lo tratamos como número.
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def extract_stress_avg(stress_data):
    """Estrés medio del día (0-100) o None.

    get_stress_data devuelve `avgStressLevel`; el resumen de usuario usa
    `averageStressLevel`. Hasta ahora solo se leía la segunda, que no existe en
    este endpoint, y stress_avg quedó a null en todas las filas.
    """
    data = stress_data if isinstance(stress_data, dict) else {}
    for key in ("avgStressLevel", "averageStressLevel", "overallStressLevel"):
        v = _num(data.get(key))
        if v is not None and v >= 0:
            return v
    return None


def extract_hrv_ms(hrv_data):
    """VFC en ms o None. Prefiere la media de la última noche (refleja el estado
    de hoy, que es lo que compara la señal de HRV de la fatiga) y cae a la media
    semanal si no hay dato de anoche."""
    data = hrv_data if isinstance(hrv_data, dict) else {}
    summary = data.get("hrvSummary")
    summary = summary if isinstance(summary, dict) else {}
    for key in ("lastNightAvg", "weeklyAvg"):
        v = _num(summary.get(key))
        if v is not None and v > 0:
            return v
    return None


def non_null_fields(fields):
    """Solo los campos con valor: un upsert con None pisaría datos buenos ya guardados."""
    return {k: v for k, v in fields.items() if v is not None}
