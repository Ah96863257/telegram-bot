import os
import time
import json
import logging
from datetime import datetime, timezone

import httpx

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gold-signals")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

SYMBOL = "XAU/USD"
INTERVAL = "5min"
CHECK_SECONDS = 60

API_URL = "https://api.twelvedata.com/time_series"
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

last_candle = None


def ema_series(prices, period):
    if len(prices) < period:
        raise ValueError("Not enough candles")

    result = [None] * len(prices)
    current = sum(prices[:period]) / period
    result[period - 1] = current
    multiplier = 2 / (period + 1)

    for i in range(period, len(prices)):
        current = (
            prices[i] * multiplier
            + current * (1 - multiplier)
        )
        result[i] = current

    return result


def send_telegram(message):
    url = f"{TELEGRAM_URL}/sendMessage"
    response = httpx.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
        },
        timeout=20,
    )
    response.raise_for_status()

    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(str(result))


def get_candles():
    response = httpx.get(
        API_URL,
        params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "outputsize": 100,
            "apikey": TWELVE_KEY,
        },
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "error":
        raise RuntimeError(data.get("message", "API error"))

    values = data.get("values", [])
    if len(values) < 30:
        raise RuntimeError("Not enough price data")

    candles = []
    for item in reversed(values):
        candles.append({
            "time": item["datetime"],
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
        })

    return candles


def analyze(candles):
    # Exclude the newest candle, which may still be open.
    closed = candles[:-1]
    prices = [c["close"] for c in closed]

    ema9 = ema_series(prices, 9)
    ema21 = ema_series(prices, 21)

    previous = -2
    current = -1

    buy = (
        ema9[previous] <= ema21[previous]
        and ema9[current] > ema21[current]
    )

    sell = (
        ema9[previous] >= ema21[previous]
        and ema9[current] < ema21[current]
    )

    candle = closed[-1]

    if buy:
        direction = "BUY"
        symbol = "🟢"
    elif sell:
        direction = "SELL"
        symbol = "🔴"
    else:
        return candle["time"], None

    message = (
        f"{symbol} Gold Precision Signals\n\n"
        f"Gold: {SYMBOL}\n"
        f"Signal: {direction}\n"
        f"Timeframe: {INTERVAL}\n"
        f"Candle: {candle['time']}\n\n"
        f"Close: {candle['close']:.2f}\n"
        f"EMA 9: {ema9[current]:.2f}\n"
        f"EMA 21: {ema21[current]:.2f}\n\n"
        "Strategy: EMA crossover\n"
        "Educational signal - not guaranteed."
    )

    return candle["time"], message


def main():
    global last_candle

    if not TELEGRAM_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    if not TWELVE_KEY:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")
    if not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID")

    log.info("Gold signal bot started")

    send_telegram(
        "✅ Gold Precision Signals is running.\n"
        "Monitoring XAU/USD on the 5-minute timeframe."
    )

    while True:
        try:
            candles = get_candles()
            candle_time, signal = analyze(candles)

            if candle_time != last_candle:
                if signal:
                    send_telegram(signal)
                    log.info("Signal sent: %s", candle_time)

                last_candle = candle_time

        except Exception:
            log.exception("Signal check failed")

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
