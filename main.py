import os
import base64
import requests
import datetime
import garth
from garminconnect import Garmin

# 1. Restaurar tokens de Garmin desde GitHub Secrets
garmin_b64 = os.environ.get("GARMIN_TOKEN_B64")
if not garmin_b64:
    raise ValueError("No se encontró la variable GARMIN_TOKEN_B64.")

import io, tarfile
tokens_bytes = base64.b64decode(garmin_b64.strip())
with tarfile.open(fileobj=io.BytesIO(tokens_bytes), mode="r:gz") as tar:
    tar.extractall(path="./garth_tokens")
# 2. Conectar a Garmin
garth.resume("./garth_tokens")
today = datetime.date.today().isoformat()

garmin = Garmin()
garmin.login(tokenstate=garth.client.dumps())

# 3. Extraer Métricas clave
try:
    stats = garmin.get_user_summary(today)
    sleep = garmin.get_sleep_data(today)
    hrv = garmin.get_hrv_data(today)
    
    # Extraer actividades de ayer para analizar fatiga
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    activities = garmin.get_activities_by_date(yesterday, yesterday, "")
    
    act_summary = []
    for act in activities:
        name = act.get('activityName', 'Desconocida')
        type_key = act.get('activityType', {}).get('typeKey', '')
        duration = round(act.get('duration', 0) / 60)
        act_summary.append(f"- {name} ({type_key}): {duration} min")
    
    activities_str = "\n".join(act_summary) if act_summary else "Ninguna (Descanso)"

    hrv_val = hrv.get('hrvSummary', {}).get('lastNightAvg', 'N/D') if hrv else 'N/D'
    sleep_score = sleep.get('dailySleepDTO', {}).get('sleepScores', {}).get('overall', {}).get('value', 'N/D') if sleep else 'N/D'
    rhr = stats.get('restingHeartRate', 'N/D')

    data_text = f"""
    Métricas de hoy ({today}):
    - HRV Nocturna: {hrv_val} ms
    - Puntuación de Sueño: {sleep_score}/100
    - Pulsaciones en Reposo: {rhr} bpm
    
    Actividades de ayer ({yesterday}):
    {activities_str}
    """
except Exception as e:
    data_text = f"Error al extraer métricas detalladas: {e}"

# 4. Consultar a Gemini AI
prompt = f"""
Eres un entrenador de ciclismo de alto rendimiento. Analiza el estado diario del atleta y prescribe la recomendación del día.

Contexto del Atleta:
- Objetivo principal: Ciclismo (Mejora de FTP / VO2 Max / Gran Fondo).
- Disciplinas: Ciclismo (Exterior/Rodillo) y Entrenamiento de Fuerza en Gimnasio.

{data_text}

Instrucciones de respuesta:
1. Sé conciso y directo (máximo 150 palabras).
2. Evalúa si el cuerpo está preparado para carga o si requiere recuperación/fuerza ligera según la HRV, sueño y actividad previa.
3. Propón una sesión concreta para hoy (Bici, Fuerza o Descanso) adaptada a estos datos.
"""

gemini_key = os.environ.get("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
headers = {'Content-Type': 'json'}
payload = {
    "contents": [{"parts": [{"text": prompt}]}]
}

res = requests.post(url, json=payload)
ai_recommendation = res.json()['candidates'][0]['content']['parts'][0]['text']

# 5. Enviar mensaje por Telegram
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
chat_id = os.environ.get("TELEGRAM_CHAT_ID")

msg = f"🚴‍♂️ *INFORME DIARIO DE ENTRENAMIENTO*\n\n{ai_recommendation}"
telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
requests.post(telegram_url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
