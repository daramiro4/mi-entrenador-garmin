import os
import requests

def main():
    gemini_key = os.environ.get("GEMINI_API_KEY")
    tel_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tel_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not all([gemini_key, tel_token, tel_chat_id]):
        print("❌ Faltan claves secretas.")
        return

    print("Consultando la lista de modelos de Gemini...")
    
    # Le pedimos a Google su lista oficial de modelos para tu API Key
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}"
    
    try:
        resp = requests.get(url)
        data = resp.json()
        
        if "models" in data:
            # Filtramos solo los que sirven para generar texto ("generateContent")
            nombres = []
            for m in data["models"]:
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    nombres.append(f"✅ `{m['name']}`")
            
            texto_telegram = "🤖 *Modelos disponibles para tu API:* \n\n" + "\n".join(nombres)
        else:
            texto_telegram = f"⚠️ Respuesta de Google: {data}"
            
    except Exception as e:
        texto_telegram = f"❌ Error consultando modelos: {e}"

    print("Enviando lista a Telegram...")
    tel_url = f"https://api.telegram.org/bot{tel_token}/sendMessage"
    requests.post(tel_url, json={
        "chat_id": tel_chat_id, 
        "text": texto_telegram,
        "parse_mode": "Markdown"
    })
    print("✅ Hecho. Mira tu Telegram.")

if __name__ == "__main__":
    main()
