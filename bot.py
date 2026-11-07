import os
import time
import requests

# Reemplaza esto con tu Token de BotFather y tu ID de Telegram
TELEGRAM_TOKEN = "9093655969:AAGze8SjPdtuTicmsepTHI5KlPs_33HC4iA"
CHAT_ID = "8970733209"

def enviar_alerta(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error al enviar mensaje: {e}")

if __name__ == "__main__":
    print("Bot de alertas iniciado correctamente...")
    enviar_alerta("🟢 *¡El bot de alertas OTC se ha conectado con éxito en la nube!* Te avisaré cuando detecte una entrada.")
    
    while True:
        time.sleep(60)
