import os
from garminconnect import Garmin
import requests
from datetime import date, timedelta

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
    # 2. Descargar Métricas de Ayer
    # ---------------------------------------------------------
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.isoformat()
    print(f"Descargando datos del día: {yesterday_str}")

    try:
        sleep_data = garmin.get_sleep_data(yesterday_str)
        stress_data = garmin.get_stress_data(yesterday_str)
        hrv_data = garmin.get_hrv_data(yesterday_str)
        rhr_data = garmin.get_rhr_day(yesterday_str)
        activities = garmin.get_activities_by_date(yesterday_str, yesterday_str)
    except Exception as e:
        raise RuntimeError(f"❌ ERROR descargando datos de Garmin: {e}")

    # Extraer valores útiles
    sleep_score = sleep_data.get('dailySleepDTO', {}).get('sleepScores', {}).get('overall', {}).get('value', 'No data')
    sleep_duration_ms = sleep_data.get('dailySleepDTO', {}).get('sleepTimeSeconds', 0) * 1000
    sleep_hours = round(sleep_duration_ms / (1000 * 60 * 60), 1) if sleep_duration_ms else 'No data'
    
    stress_avg = stress_data.get('averageStressLevel', 'No data')
    hrv_avg = hrv_data.get('hrvSummary', {}).get('weeklyAvg', 'No data')
    
    # Extraer la frecuencia cardíaca en reposo de forma segura
    rhr = 'No data'
    if rhr_data and 'allMetrics' in rhr_data and 'metricsMap' in rhr_data['allMetrics']:
        metrics_map = rhr_data['allMetrics']['metricsMap']
        if 'WELLNESS_RESTING_HEART_RATE' in metrics_map and metrics_map['WELLNESS_RESTING_HEART_RATE']:
            rhr = metrics_map['WELLNESS_RESTING_HEART_RATE'][0].get('value', 'No data')

    activity_summary = []
    if activities:
        for act in activities:
            name = act.get('activityName', 'Actividad')
            dist = round(act.get('distance', 0) / 1000, 2)
            activity_summary.append(f"{name} ({dist} km)")
    act_str = ", ".join(activity_summary) if activity_summary else "Descanso"

    # ---------------------------------------------------------
    # 3. Analizar con Google Gemini (Vía API Directa)
    # ---------------------------------------------------------
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    print("Generando análisis con Gemini...")
    
    prompt = f"""
    Eres un entrenador personal de élite. Analiza mis métricas de salud y recuperación de ayer ({yesterday_str}) y dame un resumen breve, motivador y directo (máximo 150 palabras). 
    
    Métricas:
    - Puntuación de Sueño: {sleep_score}/100 ({sleep_hours} horas)
    - Estrés Promedio: {stress_avg}/100
    - VFC (HRV) Semanal: {hrv_avg} ms
    - Frecuencia Cardíaca en Reposo: {rhr} ppm
    - Actividad: {act_str}

    Dime cómo me he recuperado y qué tipo de entrenamiento o descanso recomiendas para hoy. Termina con un emoji.
    """
    
    # 🔥 AHORA SÍ: Apuntamos al modelo ultra-rápido confirmado en tu lista 🔥
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={gemini_key}"
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
    # 4. Enviar Mensaje a Telegram
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
