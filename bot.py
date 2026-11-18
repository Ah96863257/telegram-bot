
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gold-signals")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

SYMBOL = "XAU/USD"
INTERVAL = "5min"
CHECK_SECONDS = 60

# Twelve Data returns UTC candles when timezone=UTC.
OMAN_TZ = ZoneInfo("Asia/Muscat")
UTC = timezone.utc

API_URL = "https://api.twelvedata.com/time_series"
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"

last_checked_candle = None
# Gold Precision Signals - deployment update

def send_telegram(message):
    response = httpx.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": message,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(str(data))


def get_candles():
    response = httpx.get(
        API_URL,
        params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "outputsize": 100,
            "timezone": "UTC",
            "apikey": API_KEY,
        },
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "error":
        raise RuntimeError(data.get("message", "API error"))

    values = data.get("values", [])

    if len(values) < 30:
        raise RuntimeError("Not enough candles")

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


def ema_series(prices, period):
    if len(prices) < period:
        raise ValueError("Not enough prices for EMA")

    result = [None] * len(prices)

    current = sum(prices[:period]) / period
    result[period - 1] = current

    multiplier = 2 / (period + 1)

    for i in range(period, len(prices)):
        current = (
            (prices[i] - current) * multiplier
            + current
        )
        result[i] = current

    return result


def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        raise ValueError("Not enough candles for ATR")

    ranges = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )
        ranges.append(true_range)

    return sum(ranges[-period:]) / period


def candle_datetime(candle):
    return datetime.fromisoformat(
        candle["time"].replace("Z", "+00:00")
    ).replace(tzinfo=UTC) if (
        "+" not in candle["time"]
        and not candle["time"].endswith("Z")
    ) else datetime.fromisoformat(
        candle["time"].replace("Z", "+00:00")
    ).astimezone(UTC)


def analyze(candles):
    # Ignore the newest candle because it may be open.
    closed = candles[:-1]
    candle = closed[-1]

    candle_start = candle_datetime(candle)
    candle_end = candle_start + timedelta(minutes=5)
    now = datetime.now(UTC)

    # Only accept a signal shortly after its candle closes.
    if now < candle_end:
        return candle["time"], None

    if now - candle_end > timedelta(minutes=3):
        log.info("Skipping stale candle %s", candle["time"])
        return candle["time"], None

    prices = [c["close"] for c in closed]

    ema9 = ema_series(prices, 9)
    ema21 = ema_series(prices, 21)

    buy = (
        ema9[-2] <= ema21[-2]
        and ema9[-1] > ema21[-1]
    )

    sell = (
        ema9[-2] >= ema21[-2]
        and ema9[-1] < ema21[-1]
    )

    if not buy and not sell:
        return candle["time"], None

    entry = candle["close"]
    atr = calculate_atr(closed, 14)

    if buy:
        direction = "BUY"
        symbol = "🟢"
        tp1 = entry + atr
        tp2 = entry + 2 * atr
        sl = entry - 1.5 * atr
    else:
        direction = "SELL"
        symbol = "🔴"
        tp1 = entry - atr
        tp2 = entry - 2 * atr
        sl = entry + 1.5 * atr

    oman_time = candle_end.astimezone(OMAN_TZ)

    message = (
        f"{symbol} Gold Precision Signals\n\n"
        f"Gold: {SYMBOL}\n"
        f"Signal: {direction}\n"
        f"Timeframe: {INTERVAL}\n"
        f"Candle closed (Oman): "
        f"{oman_time:%Y-%m-%d %H:%M}\n\n"
        f"Entry reference: {entry:.2f}\n"
        f"🎯 TP1: {tp1:.2f}\n"
        f"🎯 TP2: {tp2:.2f}\n"
        f"🛑 SL: {sl:.2f}\n\n"
        f"ATR 14: {atr:.2f}\n"
        f"EMA 9: {ema9[-1]:.2f}\n"
        f"EMA 21: {ema21[-1]:.2f}\n\n"
        "Strategy: EMA crossover + ATR\n"
        "Educational signal - not guaranteed."
    )

    return candle["time"], message


def main():
    global last_checked_candle

    if not TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    if not API_KEY:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")
    if not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID")

    log.info("Gold Precision Signals started")

    send_telegram(
        "✅ Gold Precision Signals updated.\n"
        "Monitoring XAU/USD every 5 minutes.\n"
        "New signals include TP1, TP2 and SL.\n"
        "Old signals will be ignored."
    )

    while True:
        try:
            candles = get_candles()
            candle_time, message = analyze(candles)

            if candle_time != last_checked_candle:
                if message:
                    send_telegram(message)
                    log.info(
                        "Signal sent for %s",
                        candle_time,
                    )

                last_checked_candle = candle_time

        except Exception:
            log.exception("Error checking signals")

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
