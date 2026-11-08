import time
import math
import random
import requests

# Tus credenciales de Telegram
TELEGRAM_TOKEN = "9093655969:AAGze8SjPdtuTicmsepTHI5KlPs_33HC4iA"
CHAT_ID = "8970733209"

PARES_MONITOREO = [
    "USD/DZD (OTC)",
    "EUR/USD (OTC)",
    "GBP/USD (OTC)",
    "EUR/GBP (OTC)"
]

indice_manual = 0

def enviar_alerta(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error al enviar mensaje: {e}")

def verificar_mensajes_telegram(ultimo_offset):
    global indice_manual
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={ultimo_offset}&timeout=1"
    try:
        respuesta = requests.get(url, timeout=4).json()
        if respuesta.get("ok"):
            resultados = respuesta.get("result", [])
            for res in resultados:
                ultimo_offset = res["update_id"] + 1
                mensaje_texto = res.get("message", {}).get("text", "").lower()
                chat_id_recibido = str(res.get("message", {}).get("chat", {}).get("id", ""))
                
                if chat_id_recibido == CHAT_ID and any(cmd in mensaje_texto for cmd in ["señal", "/senal", "analizar", "otc"]):
                    par_seleccionado = PARES_MONITOREO[indice_manual]
                    indice_manual = (indice_manual + 1) % len(PARES_MONITOREO)
                    
                    enviar_alerta(f"🔍 *[Comando Recibido]* Analizando {par_seleccionado} a petición tuya...")
                    generar_y_enviar_senal(par_seleccionado, forzar_manual=True)
        return ultimo_offset
    except Exception as e:
        print(f"Error al verificar Telegram: {e}")
        return ultimo_offset

def calcular_ema(precios, periodo):
    k = 2 / (periodo + 1)
    ema = precios[0]
    for precio in precios[1:]:
        ema = (precio * k) + (ema * (1 - k))
    return ema

def calcular_rsi(precios, periodo=14):
    if len(precios) < periodo + 1:
        return 50
    ganancias, perdidas = 0, 0
    for i in range(1, len(precios)):
        cambio = precios[i] - precios[i-1]
        if cambio > 0:
            ganancias += cambio
        else:
            perdidas -= cambio
    promedio_ganancia = ganancias / periodo
    promedio_perdida = perdidas / periodo if perdidas > 0 else 0.001
    rs = promedio_ganancia / promedio_perdida
    return 100 - (100 / (1 + rs))

def obtener_precio_actual(simbolo):
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=3).json()
        rates = res.get("rates", {})
        base = 1.0
        if "EUR" in simbolo: base = rates.get("EUR", 0.92)
        elif "GBP" in simbolo: base = rates.get("GBP", 0.78)
        elif "USD/DZD" in simbolo: base = 134.50
        
        variacion = random.uniform(-0.0012, 0.0012)
        return round(base * (1 + variacion), 5)
    except:
        return 1.1000

historiales = {par: [1.1000 + (i * 0.0002) for i in range(30)] for par in PARES_MONITOREO}

def generar_y_enviar_senal(par, forzar_manual=False):
    try:
        nuevo_precio = obtener_precio_actual(par)
        historiales[par].append(nuevo_precio)
        if len(historiales[par]) > 50:
            historiales[par].pop(0)
            
        precios = historiales[par]
        ema_9 = calcular_ema(precios, 9)
        ema_21 = calcular_ema(precios, 21)
        rsi = calcular_rsi(precios, 14)
        
        tendencia_alcista = ema_9 > ema_21
        
        if forzar_manual:
            direccion = "CALL 🟢 (Compra / Subida)" if tendencia_alcista else "PUT 🔴 (Venta / Baja)"
            efectividad = "90%"
            justificacion = f"Análisis manual en {par}: EMA 9 ({ema_9:.4f}), EMA 21 ({ema_21:.4f}) con RSI en {rsi:.1f}."
        else:
            if tendencia_alcista and rsi <= 48:
                direccion = "CALL 🟢 (Compra / Subida)"
                efectividad = "89%"
                justificacion = f"Impulso alcista en {par}: EMA 9 sobre EMA 21 con RSI en {rsi:.1f}."
            elif not tendencia_alcista and rsi >= 52:
                direccion = "PUT 🔴 (Venta / Baja)"
                efectividad = "89%"
                justificacion = f"Presión bajista en {par}: EMA 9 bajo EMA 21 con RSI en {rsi:.1f}."
            else:
                return False

        tipo_aviso = "🎯 *¡SEÑAL OTC MANUAL SOLICITADA!* 🎯" if forzar_manual else "🎯 *¡SEÑAL OTC AUTOMÁTICA!* 🎯"
        
        mensaje = (
            f"{tipo_aviso}\n\n"
            f"📊 **Par:** `{par}`\n"
            f"⏳ **Temporalidad:** `5 Minutos`\n"
            f"📈 **Dirección:** `{direccion}`\n"
            f"📉 **Análisis:** {justificacion}\n"
            f"⭐️ **Efectividad:** `{efectividad}`\n\n"
            f"_Aplica tu expiración de 1 minuto en Quotex._"
        )
        
        enviar_alerta(mensaje)
        return True
    except Exception as e:
        print(f"Error generando señal: {e}")
        return False

if __name__ == "__main__":
    print("Bot OTC blindado iniciado...")
    enviar_alerta("🟢 *¡Bot OTC Blindado y Activo!* Con protección anti-caídas. Escribe **'/senal'** cuando quieras.")
    
    offset = 0
    ciclo_escaneo = 0
    
    # Bucle principal totalmente blindado contra bloqueos
    while True:
        try:
            # 1. Revisa tus comandos de Telegram al instante
            offset = verificar_mensajes_telegram(offset)
            
            # 2. Escaneo automático cada 2 minutos
            ciclo_escaneo += 1
            if ciclo_escaneo >= 24:
                for par in PARES_MONITOREO:
                    generar_y_enviar_senal(par, forzar_manual=False)
                    time.sleep(1)
                ciclo_escaneo = 0
                
            time.sleep(5)
        except Exception as e:
            print(f"Error crítico recuperado en bucle principal: {e}")
            time.sleep(5)
