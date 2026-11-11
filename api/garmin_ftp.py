"""FTP de ciclismo que Garmin Connect tiene registrado (`get_cycling_ftp`).

La librería no documenta el formato de la respuesta, así que la extracción es defensiva: busca el valor
bajo cualquier clave que contenga "functionalthresholdpower" (o "ftp"), en el dict o en el elemento más
reciente de una lista, y exige un valor razonable. Funciones puras, sin red.
"""

FTP_MIN_WATTS = 80
FTP_MAX_WATTS = 500


def _plausible(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    watts = round(value)
    return watts if FTP_MIN_WATTS <= watts <= FTP_MAX_WATTS else None


def _find(payload):
    if isinstance(payload, dict):
        # Claves directas primero (más fiables que buscar en profundidad).
        for key, value in payload.items():
            lowered = str(key).lower()
            if "functionalthresholdpower" in lowered or lowered in ("ftp", "cyclingftp"):
                found = _plausible(value)
                if found is not None:
                    return found
        for value in payload.values():
            if isinstance(value, (dict, list)):
                found = _find(value)
                if found is not None:
                    return found
    elif isinstance(payload, list):
        # Si es una serie, el último elemento es el más reciente.
        for item in reversed(payload):
            found = _find(item)
            if found is not None:
                return found
    return None


def extract_cycling_ftp(payload):
    """FTP en vatios (int) o None si la respuesta no trae un valor razonable."""
    return _find(payload)
