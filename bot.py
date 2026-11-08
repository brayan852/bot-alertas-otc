
import os
import time
import requests
import pandas as pd
import numpy as np

from collections import deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from otcharts import Client


# ==================================================
# CONFIGURACION GENERAL
# ==================================================

OTCHARTS_API_KEY = os.getenv("OTCHARTS_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

VENUE = "quotex"
TIMEFRAME = 300                 # 5 minutos
EXPIRACION = 5                  # 5 minutos
HISTORIAL = 250

MIN_PUNTOS = 7
DIFERENCIA_MINIMA = 2
MIN_ADX = 18

ZONA_HORARIA = ZoneInfo("America/Santo_Domingo")

# Prioriza USD/DZD si aparece en el catálogo.
# Los demás son alternativas disponibles en el plan gratuito.
PREFERIDOS = [
    "USDDZD_otc",
    "EURUSD_otc",
    "GBPUSD_otc",
    "USDJPY_otc",
    "AUDUSD_otc",
    "BTCUSD_otc"
]

# Número máximo de instrumentos de la conexión.
# Lite: 5 | Build: 10 | Run: 50
MAX_INSTRUMENTOS = 5

# ==================================================
# TELEGRAM
# ==================================================

def enviar_telegram(mensaje):

    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Faltan las credenciales de Telegram.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:
        respuesta = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": mensaje
            },
            timeout=15
        )

        respuesta.raise_for_status()

        resultado = respuesta.json()

        if not resultado.get("ok"):
            print("Telegram rechazó el mensaje.")
            return False

        return True

    except requests.RequestException as error:
        print("Error enviando Telegram:", error)
        return False


# ==================================================
# CONEXION API
# ==================================================

def conectar_api():

    if not OTCHARTS_API_KEY:
        raise RuntimeError(
            "Configura OTCHARTS_API_KEY."
        )

    cliente = Client()

    instrumentos = cliente.symbols(VENUE)

    disponibles = {
        item.symbol: item
        for item in instrumentos
        if getattr(item, "open", True) is not False
    }

    seleccionados = [
        par for par in PREFERIDOS
        if par in disponibles
    ][:MAX_INSTRUMENTOS]

    if not seleccionados:
        print("No se encontraron instrumentos disponibles.")
        print("Catálogo recibido:")

        for item in instrumentos:
            print(item.symbol, item.name)

        raise RuntimeError(
            "No hay pares compatibles en la configuración."
        )

    print("\nPARES ACTIVOS:")

    for par in seleccionados:
        print(" -", par)

    return cliente, seleccionados


# ==================================================
# HISTORIAL DE VELAS
# ==================================================

def cargar_historico(cliente, simbolo):

    velas = cliente.candles(
        VENUE,
        simbolo,
        tf=TIMEFRAME,
        limit=HISTORIAL
    )

    ahora = time.time()

    resultado = deque(maxlen=500)

    for vela in velas:

        t = int(vela.time)

        # Solo velas completamente cerradas.
        if t + TIMEFRAME > ahora:
            continue

        resultado.append({
            "time": t,
            "open": float(vela.open),
            "high": float(vela.high),
            "low": float(vela.low),
            "close": float(vela.close)
        })

    if len(resultado) < 60:
        raise RuntimeError(
            f"Historial insuficiente para {simbolo}"
        )

    return resultado


# ==================================================
# INDICADORES TECNICOS
# ==================================================

def calcular_indicadores(df):

    df = df.copy()

    # EMA 9, 21 y 50
    df["EMA9"] = df["close"].ewm(
        span=9, adjust=False
    ).mean()

    df["EMA21"] = df["close"].ewm(
        span=21, adjust=False
    ).mean()

    df["EMA50"] = df["close"].ewm(
        span=50, adjust=False
    ).mean()

    # RSI 14 - Wilder
    delta = df["close"].diff()

    ganancias = delta.clip(lower=0)
    perdidas = -delta.clip(upper=0)

    media_ganancia = ganancias.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    media_perdida = perdidas.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    rs = media_ganancia / media_perdida.replace(
        0, np.nan
    )

    df["RSI"] = 100 - (100 / (1 + rs))

    df["RSI"] = df["RSI"].fillna(50)

    # MACD 12, 26, 9
    ema12 = df["close"].ewm(
        span=12, adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26, adjust=False
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACD_SIGNAL"] = df["MACD"].ewm(
        span=9, adjust=False
    ).mean()

    df["HIST"] = (
        df["MACD"] - df["MACD_SIGNAL"]
    )

    # Bollinger 20, 2
    media20 = df["close"].rolling(20).mean()

    desviacion = df["close"].rolling(20).std()

    df["BB_MID"] = media20
    df["BB_UPPER"] = media20 + 2 * desviacion
    df["BB_LOWER"] = media20 - 2 * desviacion

    # ATR y ADX - Wilder
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    df["ATR"] = tr.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    up = high.diff()
    down = -low.diff()

    plus_dm = up.where(
        (up > down) & (up > 0), 0
    )

    minus_dm = down.where(
        (down > up) & (down > 0), 0
    )

    plus_di = (
        100 * plus_dm.ewm(
            alpha=1/14, adjust=False
        ).mean() / df["ATR"].replace(0, np.nan)
    )

    minus_di = (
        100 * minus_dm.ewm(
            alpha=1/14, adjust=False
        ).mean() / df["ATR"].replace(0, np.nan)
    )

    dx = (
        100 * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    df["PLUS_DI"] = plus_di
    df["MINUS_DI"] = minus_di

    df["ADX"] = dx.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    return df


# ==================================================
# PATRONES DE VELAS
# ==================================================

def patron_alcista(actual, anterior):

    cuerpo = abs(actual.close - actual.open)

    rango = actual.high - actual.low

    if rango <= 0:
        return False

    mecha_inferior = (
        min(actual.open, actual.close) - actual.low
    )

    envolvente = (
        actual.close > actual.open
        and anterior.close < anterior.open
        and actual.close > anterior.open
        and actual.open < anterior.close
    )

    martillo = (
        actual.close > actual.open
        and mecha_inferior > cuerpo * 1.5
    )

    vela_fuerte = (
        actual.close > actual.open
        and cuerpo / rango >= 0.60
    )

    return envolvente or martillo or vela_fuerte


def patron_bajista(actual, anterior):

    cuerpo = abs(actual.close - actual.open)

    rango = actual.high - actual.low

    if rango <= 0:
        return False

    mecha_superior = (
        actual.high - max(actual.open, actual.close)
    )

    envolvente = (
        actual.close < actual.open
        and anterior.close > anterior.open
        and actual.close < anterior.open
        and actual.open > anterior.close
    )

    estrella = (
        actual.close < actual.open
        and mecha_superior > cuerpo * 1.5
    )

    vela_fuerte = (
        actual.close < actual.open
        and cuerpo / rango >= 0.60
    )

    return envolvente or estrella or vela_fuerte


# ==================================================
# ANALISIS Y PUNTUACION
# ==================================================

def analizar(df):

    if len(df) < 60:
        return None

    # Evitar analizar series con huecos recientes.
    ultimas = df["time"].tail(20).diff().dropna()

    if not (ultimas == TIMEFRAME).all():
        return None

    df = calcular_indicadores(df)

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    columnas = [
        "EMA9", "EMA21", "EMA50",
        "RSI", "MACD", "HIST",
        "BB_UPPER", "BB_LOWER",
        "ATR", "ADX", "PLUS_DI", "MINUS_DI"
    ]

    if actual[columnas].isna().any():
        return None

    if actual["ATR"] <= 0:
        return None

    compra = 0
    venta = 0

    # 1. Tendencia principal
    alcista = (
        actual.EMA9 > actual.EMA21
        and actual.EMA21 > actual.EMA50
    )

    bajista = (
        actual.EMA9 < actual.EMA21
        and actual.EMA21 < actual.EMA50
    )

    if alcista:
        compra += 2

    if bajista:
        venta += 2

    # 2. MACD y momentum
    if (
        actual.HIST > 0
        and actual.HIST > anterior.HIST
        and actual.MACD > actual.MACD_SIGNAL
    ):
        compra += 2

    if (
        actual.HIST < 0
        and actual.HIST < anterior.HIST
        and actual.MACD < actual.MACD_SIGNAL
    ):
        venta += 2

    # 3. RSI
    if (
        50 < actual.RSI < 68
        and actual.RSI > anterior.RSI
    ):
        compra += 1

    if (
        32 < actual.RSI < 50
        and actual.RSI < anterior.RSI
    ):
        venta += 1

    # 4. ADX y dirección de fuerza
    if actual.ADX >= MIN_ADX:

        if actual.PLUS_DI > actual.MINUS_DI:
            compra += 1

        elif actual.MINUS_DI > actual.PLUS_DI:
            venta += 1

    # 5. Confirmación de vela
    if patron_alcista(actual, anterior):
        compra += 2

    if patron_bajista(actual, anterior):
        venta += 2

    # 6. Posición frente a EMA 9
    if actual.close > actual.EMA9:
        compra += 1

    if actual.close < actual.EMA9:
        venta += 1

    # 7. Reacción en bandas de Bollinger
    if (
        actual.close > actual.BB_LOWER
        and anterior.close <= anterior.BB_LOWER
    ):
        compra += 1

    if (
        actual.close < actual.BB_UPPER
        and anterior.close >= anterior.BB_UPPER
    ):
        venta += 1

    # Evitar señales contradictorias.
    if (
        compra >= MIN_PUNTOS
        and compra - venta >= DIFERENCIA_MINIMA
    ):

        direccion = "COMPRA 🟢"
        puntos = compra

    elif (
        venta >= MIN_PUNTOS
        and venta - compra >= DIFERENCIA_MINIMA
    ):

        direccion = "VENTA 🔴"
        puntos = venta

    else:
        return None

    return {
        "direccion": direccion,
        "puntos": puntos,
        "compra": compra,
        "venta": venta,
        "rsi": round(float(actual.RSI), 2),
        "adx": round(float(actual.ADX), 2),
        "precio": float(actual.close),
        "hora": int(actual.time)
    }


# ==================================================
# CONSTRUCCION DE VELAS EN TIEMPO REAL
# ==================================================

def nueva_vela(tiempo, precio):

    return {
        "time": tiempo,
        "open": precio,
        "high": precio,
        "low": precio,
        "close": precio
    }


def actualizar_vela(vela, precio):

    vela["high"] = max(vela["high"], precio)
    vela["low"] = min(vela["low"], precio)
    vela["close"] = precio


# ==================================================
# ESTADO POR INSTRUMENTO
# ==================================================

ESTADOS = {}


def preparar_estados(cliente, simbolos):

    for simbolo in simbolos:

        ESTADOS[simbolo] = {
            "historial": cargar_historico(
                cliente, simbolo
            ),
            "vela_actual": None,
            "ultima_senal": None
        }

        print(
            simbolo,
            "- historial:",
            len(ESTADOS[simbolo]["historial"])
        )


# ==================================================
# ENVIO DE SEÑALES
# ==================================================

def enviar_senal(simbolo, resultado):

    hora = datetime.fromtimestamp(
        resultado["hora"],
        timezone.utc
    ).astimezone(ZONA_HORARIA)

    mensaje = (
        "🎯 NUEVA SEÑAL QUOTEX OTC\n\n"
        f"📊 Par: {simbolo}\n"
        f"📈 Dirección: {resultado['direccion']}\n"
        "⏳ Temporalidad: 5 MINUTOS\n"
        "⌛ Expiración: 5 MINUTOS\n\n"
        f"⭐ Puntuación: {resultado['puntos']}/10\n"
        f"🟢 Puntos compra: {resultado['compra']}\n"
        f"🔴 Puntos venta: {resultado['venta']}\n\n"
        f"📉 RSI: {resultado['rsi']}\n"
        f"📊 ADX: {resultado['adx']}\n"
        f"💹 Precio de cierre: {resultado['precio']}\n"
        f"🕒 Cierre de vela: {hora:%H:%M:%S}\n\n"
        "➡️ Entrada prevista: siguiente vela\n"
        "⚠️ Señal técnica, no garantía de ganancia."
    )

    enviar_telegram(mensaje)

    print("\n", mensaje, "\n")


# ==================================================
# PROCESAMIENTO DE CADA TICK
# ==================================================

def procesar_tick(tick):

    simbolo = tick.symbol

    if simbolo not in ESTADOS:
        return

    estado = ESTADOS[simbolo]

    precio = float(tick.price)
    timestamp = int(tick.time)

    if not np.isfinite(precio) or precio <= 0:
        return

    bucket = (timestamp // TIMEFRAME) * TIMEFRAME

    vela = estado["vela_actual"]

    # Primer tick recibido.
    if vela is None:

        estado["vela_actual"] = nueva_vela(
            bucket, precio
        )

        return

    # Mismo período: actualizar vela.
    if bucket == vela["time"]:

        actualizar_vela(vela, precio)
        return

    # Tick atrasado: ignorar.
    if bucket < vela["time"]:
        return

    # Se ha iniciado una nueva vela.
    anterior_bucket = vela["time"]

    diferencia = bucket - anterior_bucket

    if diferencia == TIMEFRAME:

        historial = estado["historial"]

        if (
            not historial
            or historial[-1]["time"] != anterior_bucket
        ):
            historial.append(vela.copy())

        # Analizar únicamente velas cerradas.
        df = pd.DataFrame(list(historial))

        resultado = analizar(df)

        if resultado:

            # Una señal por instrumento y vela.
            if estado["ultima_senal"] != anterior_bucket:

                enviar_senal(simbolo, resultado)

                estado["ultima_senal"] = anterior_bucket

        else:

            print(
                datetime.now(ZONA_HORARIA).strftime("%H:%M:%S"),
                simbolo,
                "| Sin señal válida"
            )

    else:

        print(
            "Hueco de datos detectado en",
            simbolo,
            "- análisis omitido."
        )

    # Comenzar nueva vela.
    estado["vela_actual"] = nueva_vela(
        bucket, precio
    )


# ==================================================
# MOTOR PRINCIPAL
# ==================================================

def iniciar_bot():

    cliente, simbolos = conectar_api()

    preparar_estados(cliente, simbolos)

    enviar_telegram(
        "🟢 BOT QUOTEX OTC ACTIVADO\n\n"
        "Temporalidad: 5 minutos\n"
        "Expiración: 5 minutos\n"
        "Señales: COMPRA y VENTA\n"
        "Monitoreo: continuo\n"
        "Fuente: datos OTC de Quotex\n"
        "Filtro técnico: activado\n\n"
        "Esperando oportunidades..."
    )

    print("\nBOT INICIADO CORRECTAMENTE\n")

    while True:

        try:

            print("Conectando transmisión en vivo...")

            for tick in cliente.stream(
                VENUE,
                simbolos
            ):

                procesar_tick(tick)

        except KeyboardInterrupt:

            print("Bot detenido por el usuario.")
            break

        except Exception as error:

            print("Error de conexión:", error)

            print(
                "Intentando reconectar en 15 segundos..."
            )

            time.sleep(15)

            # Si se reinicia la conexión, no inventar
            # velas faltantes ni operar sobre huecos.
            try:
                preparar_estados(cliente, simbolos)
            except Exception as error_historial:
                print(
                    "Error actualizando historial:",
                    error_historial
                )
                time.sleep(30)


# ==================================================
# EJECUCION
# ==================================================

if __name__ == "__main__":

    try:
        iniciar_bot()

    except KeyboardInterrupt:
        print("Programa finalizado.")
