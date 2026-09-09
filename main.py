import os
from datetime import date, timedelta
from garminconnect import Garmin
import requests

from api.garmin_sync import get_supabase, sync_day


def main():
    # ---------------------------------------------------------
    # 1. Iniciar sesión en Garmin de forma nativa
    # ---------------------------------------------------------
    garmin_email = os.environ.get("GARMIN_EMAIL")
    garmin_pass = os.environ.get("GARMIN_PASSWORD")

    if not garmin_email or not garmin_pass:
        raise ValueError("❌ ERROR: Faltan los secretos GARMIN_EMAIL o GARMIN_PASSWORD en GitHub.")

    print("Iniciando sesión en Garmin Connect...")
    try:
        garmin = Garmin(garmin_email, garmin_pass)
        garmin.login()
        print(f"✅ Conectado a Garmin Connect con éxito. (Usuario: {garmin.display_name})")
    except Exception as e:
        raise ValueError(f"❌ ERROR al iniciar sesión nativa: {e}")

    # ---------------------------------------------------------
    # 2. Descargar Métricas de Ayer y sincronizar con Supabase
    #    (descarga + guardado + fatiga viven en api/garmin_sync.py,
    #    compartido con la sincronización manual de api/sync_now.py)
    # ---------------------------------------------------------
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.isoformat()
    print(f"Descargando datos del día: {yesterday_str}")

    supabase = get_supabase()
    result = sync_day(garmin, supabase, yesterday_str)

    sleep_score = result["sleep_score"]
    sleep_hours = result["sleep_hours"]
    stress_avg = result["stress_avg"]
    hrv_avg = result["hrv_avg"]
    rhr = result["rhr"]
    act_str = result["act_str"]
    fatigue = result["fatigue"]

    # ---------------------------------------------------------
    # 4. Analizar con Google Gemini (Vía API Directa)
    # ---------------------------------------------------------
    gemini_key = os.environ.get("GEMINI_API_KEY")

    print("Generando análisis con Gemini...")

    acwr_ratio = fatigue.get("acwr_ratio") if fatigue else None
    recommendation = fatigue.get("recommendation") if fatigue else None
    acwr_display = acwr_ratio if acwr_ratio is not None else "No disponible"
    recommendation_display = {
        "normal": "Normal, carga bien gestionada",
        "precaucion": "Precaución, la carga está subiendo rápido",
        "descanso": "Descanso recomendado, riesgo de sobrecarga o falta de datos",
    }.get(recommendation, "No disponible")

    alerta_instruccion = ""
    if recommendation in ("precaucion", "descanso"):
        alerta_instruccion = (
            f"\n    Es muy importante: la recomendación del sistema hoy es '{recommendation}'. "
            "Menciónalo explícitamente en tu respuesta y prioriza la prevención de lesiones "
            "por encima de la intensidad del entrenamiento."
        )

    prompt = f"""
    Eres un entrenador personal de élite. Analiza mis métricas de salud y recuperación de ayer ({yesterday_str}) y dame un resumen breve, motivador y directo (máximo 150 palabras).

    Métricas:
    - Puntuación de Sueño: {sleep_score}/100 ({sleep_hours} horas)
    - Estrés Promedio: {stress_avg}/100
    - VFC (HRV) Semanal: {hrv_avg} ms
    - Frecuencia Cardíaca en Reposo: {rhr} ppm
    - Actividad: {act_str}
    - Ratio Carga Aguda:Crónica (ACWR): {acwr_display}
    - Estado de fatiga del sistema: {recommendation_display}

    Dime cómo me he recuperado y qué tipo de entrenamiento o descanso recomiendas para hoy. Termina con un emoji.{alerta_instruccion}
    """

    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={gemini_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        gemini_resp = requests.post(gemini_url, json=payload)
        gemini_resp.raise_for_status()
        ai_message = gemini_resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        print("✅ Análisis generado con éxito.")
    except Exception as e:
        error_details = gemini_resp.text if 'gemini_resp' in locals() else str(e)
        ai_message = f"❌ ERROR al contactar con Gemini: {error_details}"
        print(f"Error detallado de Gemini: {error_details}")

    # ---------------------------------------------------------
    # 5. Enviar Mensaje a Telegram
    # ---------------------------------------------------------
    tel_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tel_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if tel_token and tel_chat_id:
        print("Enviando mensaje a Telegram...")
        url = f"https://api.telegram.org/bot{tel_token}/sendMessage"

        payload = {
            "chat_id": tel_chat_id,
            "text": f"📊 Resumen Garmin {yesterday_str}\n\n{ai_message}"
        }

        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            print("✅ Mensaje enviado a Telegram correctamente.")
        else:
            print(f"⚠️ Error enviando a Telegram: {resp.text}")
    else:
        print("⚠️ No se encontraron tokens de Telegram. Se omite el envío.")

if __name__ == "__main__":
    main()
