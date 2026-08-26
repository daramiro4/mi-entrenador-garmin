import os
import base64
import io
import tarfile
import tempfile
import garth
from garminconnect import Garmin
import requests
import google.generativeai as genai
from datetime import date, timedelta

def main():
    # ---------------------------------------------------------
    # 1. Recuperar Tokens de Garmin desde Base64
    # ---------------------------------------------------------
    garmin_b64 = os.environ.get("GARMIN_TOKEN_B64")
    if not garmin_b64:
        raise ValueError("❌ ERROR: El secreto GARMIN_TOKEN_B64 no existe o está vacío.")

    print("Desempaquetando tokens de Garmin...")
    tokens_bytes = base64.b64decode(garmin_b64.strip())
    
    tmp_dir = tempfile.mkdtemp()
    with tarfile.open(fileobj=io.BytesIO(tokens_bytes), mode="r:gz") as tar:
        tar.extractall(path=tmp_dir)
    
    # Iniciamos sesión reanudando los tokens
    try:
        garth.resume(tmp_dir)
        garmin = Garmin()
        garmin.garth = garth.client
        
        # 🔥 EL PARCHE DEFINITIVO 🔥
        # Forzamos la descarga del perfil para obtener el 'display_name' obligatorio
        try:
            garmin.display_name = garth.client.profile.get("displayName")
        except (AttributeError, TypeError):
            garth.client.download_profile()
            garmin.display_name = garth.client.profile.get("displayName")
            
        print(f"✅ Conectado a Garmin Connect con éxito. (Usuario: {garmin.display_name})")
    except Exception as e:
        raise ValueError(f"❌ ERROR al iniciar sesión con los tokens: {e}")

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
    # 3. Analizar con Google Gemini
    # ---------------------------------------------------------
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("❌ ERROR: El secreto GEMINI_API_KEY no existe o está vacío.")

    print("Generando análisis con Gemini...")
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

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
    
    try:
        response = model.generate_content(prompt)
        ai_message = response.text.strip()
    except Exception as e:
        ai_message = f"❌ ERROR al generar el mensaje con Gemini: {e}"

    print("Análisis generado:\n", ai_message)

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
            "text": f"📊 *Resumen Garmin {yesterday_str}*\n\n{ai_message}",
            "parse_mode": "Markdown"
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
