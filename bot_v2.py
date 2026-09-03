import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from binance.client import Client

# ============================================
# API DETAILS — apni values yahan daalo
# ============================================
API_KEY = "your_api_key"
API_SECRET = "your_secret_key"

GMAIL_ADDRESS = "your_email@gmail.com"
GMAIL_APP_PASSWORD = "your_app_password"
TO_EMAIL = "your_email@gmail.com"

# ============================================
# SETTINGS
# ============================================
TOP_N_COINS = 20
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
KLINES_LIMIT = 250

LEVERAGE = 15
MARGIN_USDT = 5
POSITION_SIZE = LEVERAGE * MARGIN_USDT   # $75

RR_RATIO = 2
MIN_SL_PERCENT = 0.015
MAX_SL_PERCENT = 0.05

MAX_TRADES_PER_DAY = 5
MAX_CONSECUTIVE_LOSSES = 2      # 🆕 2 loss ke baad band
RSI_PERIOD = 14
MIN_VOLUME_USDT = 5_000_000
SIGNAL_COOLDOWN_HOURS = 3
SCAN_EVERY_SECONDS = 300

# SL Monitor — kitne seconds baad check kare
SL_MONITOR_INTERVAL = 60        # 🆕 har 60 sec mein SL check

client = Client(API_KEY, API_SECRET)

# ============================================
# DASHBOARD URL — Railway deploy ke baad apna URL daalo
# ============================================
DASHBOARD_URL = "https://your-app.railway.app"   # ← yahan apna Railway URL

last_signaled = {}
trades_sent_today = 0
current_day = datetime.now().date()

# 🆕 Active trades track karne ke liye
# Format: { symbol: { signal, entry, sl, tp, alerted } }
active_trades = {}

# 🆕 Consecutive loss tracker
consecutive_losses = 0


# ============================================
# DAILY RESET
# ============================================
def reset_daily_counter():
    global trades_sent_today, current_day, consecutive_losses
    today = datetime.now().date()
    if today != current_day:
        trades_sent_today = 0
        consecutive_losses = 0
        current_day = today
        print("Daily counter reset.")


# ============================================
# EMAIL
# ============================================
def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = TO_EMAIL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("Email sent.")
    except Exception as e:
        print("Email error:", e)


# ============================================
# DATA
# ============================================
def get_top_movers():
    tickers = client.futures_ticker()
    usdt_pairs = [
        t for t in tickers
        if t["symbol"].endswith("USDT") and float(t["quoteVolume"]) >= MIN_VOLUME_USDT
    ]
    sorted_pairs = sorted(
        usdt_pairs,
        key=lambda x: float(x["quoteVolume"]) * abs(float(x["priceChangePercent"])),
        reverse=True
    )
    return [p["symbol"] for p in sorted_pairs[:TOP_N_COINS]]


def get_klines(symbol):
    klines = client.futures_klines(symbol=symbol, interval=INTERVAL, limit=KLINES_LIMIT)
    closes  = [float(k[4]) for k in klines]
    highs   = [float(k[2]) for k in klines]
    lows    = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    return closes, highs, lows, volumes


def get_current_price(symbol):
    ticker = client.futures_symbol_ticker(symbol=symbol)
    return float(ticker["price"])


# ============================================
# INDICATORS
# ============================================
def get_ema_series(prices, period):
    ema = [sum(prices[:period]) / period]
    m = 2 / (period + 1)
    for p in prices[period:]:
        ema.append((p - ema[-1]) * m + ema[-1])
    return ema


def get_ema(prices, period):
    return get_ema_series(prices, period)[-1]


def get_rsi(prices, period=14):
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains  = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100
    return 100 - (100 / (1 + ag / al))


def get_macd(prices):
    e12 = get_ema_series(prices, 12)
    e26 = get_ema_series(prices, 26)
    n = min(len(e12), len(e26))
    macd = [e12[-n:][i] - e26[-n:][i] for i in range(n)]
    sig  = get_ema_series(macd, 9)
    return macd[-1], sig[-1]


# ============================================
# DYNAMIC SL/TP
# ============================================
def calculate_sl_tp(signal, price, highs, lows):
    rh = max(highs[-14:])
    rl = min(lows[-14:])

    if signal == "LONG":
        pct    = (price - rl) / price
        pct    = max(MIN_SL_PERCENT, min(MAX_SL_PERCENT, pct))
        sl     = price * (1 - pct)
        tp1    = price * (1 + pct * 1.0)        # TP1 = 1:1 RR (conservative)
        tp2    = price * (1 + pct * RR_RATIO)   # TP2 = 1:2 RR (original)
    else:
        pct    = (rh - price) / price
        pct    = max(MIN_SL_PERCENT, min(MAX_SL_PERCENT, pct))
        sl     = price * (1 + pct)
        tp1    = price * (1 - pct * 1.0)        # TP1 = 1:1 RR (conservative)
        tp2    = price * (1 - pct * RR_RATIO)   # TP2 = 1:2 RR (original)

    return sl, tp1, tp2, pct


# ============================================
# PRICE FORMATTER
# ============================================
def fmt(price):
    if price >= 100:    return f"{price:.2f}"
    if price >= 1:      return f"{price:.4f}"
    if price >= 0.01:   return f"{price:.6f}"
    if price >= 0.0001: return f"{price:.8f}"
    return f"{price:.10f}"


# ============================================
# 🆕 SL/TP MONITOR — active trades check karta hai
# ============================================
def monitor_active_trades():
    global consecutive_losses, active_trades

    to_remove = []

    for symbol, trade in active_trades.items():
        if trade.get("alerted"):
            to_remove.append(symbol)
            continue

        try:
            current = get_current_price(symbol)
            signal  = trade["signal"]
            sl      = trade["sl"]
            tp      = trade["tp"]    # TP2
            tp1     = trade.get("tp1", None)
            entry   = trade["entry"]

            sl_hit  = False
            tp1_hit = False
            tp_hit  = False

            if signal == "LONG":
                sl_hit  = current <= sl
                tp1_hit = tp1 and current >= tp1 and not trade.get("tp1_alerted")
                tp_hit  = current >= tp
            else:  # SHORT
                sl_hit  = current >= sl
                tp1_hit = tp1 and current <= tp1 and not trade.get("tp1_alerted")
                tp_hit  = current <= tp

            # TP1 Alert — 50% close karo
            if tp1_hit and not sl_hit:
                body = (
                    f"🎯 TP1 HIT — {symbol} {signal}\n\n"
                    f"Entry:   {fmt(entry)}\n"
                    f"TP1:     {fmt(tp1)}\n"
                    f"Current: {fmt(current)}\n\n"
                    f"✅ 50% position CLOSE karo abhi!\n"
                    f"Baaki 50% TP2 ({fmt(tp)}) ke liye hold karo.\n"
                    f"SL ab breakeven pe move kar do: {fmt(entry)}"
                )
                send_email(f"🎯 TP1 HIT — {symbol} {signal}", body)
                print(f"TP1 HIT: {symbol}")
                trade["tp1_alerted"] = True

            if sl_hit:
                consecutive_losses += 1
                loss_usd = MARGIN_USDT  # approximate
                body = (
                    f"🚨 SL HIT — {symbol} {signal}\n\n"
                    f"Entry:   {fmt(entry)}\n"
                    f"SL:      {fmt(sl)}\n"
                    f"Current: {fmt(current)}\n\n"
                    f"Loss: ~${loss_usd}\n"
                    f"Consecutive Losses: {consecutive_losses}/{MAX_CONSECUTIVE_LOSSES}\n\n"
                )
                if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                    body += f"⛔ {MAX_CONSECUTIVE_LOSSES} consecutive losses — TRADING BAND for today!\n"
                    body += "Bot aaj aur signals nahi bhejega."

                send_email(f"🚨 SL HIT — {symbol} {signal}", body)
                print(f"SL HIT: {symbol} | Consecutive losses: {consecutive_losses}")
                trade["alerted"] = True
                to_remove.append(symbol)

            elif tp_hit:
                consecutive_losses = 0  # reset on win
                profit_usd = MARGIN_USDT * RR_RATIO
                body = (
                    f"🚀 TP2 HIT — {symbol} {signal}\n\n"
                    f"Entry:   {fmt(entry)}\n"
                    f"TP2:     {fmt(tp)}\n"
                    f"Current: {fmt(current)}\n\n"
                    f"✅ Remaining 50% CLOSE karo!\n"
                    f"Full trade profit: ~${profit_usd} 🎉\n"
                    f"Consecutive losses reset to 0."
                )
                send_email(f"🚀 TP2 HIT — {symbol} {signal}", body)
                print(f"TP HIT: {symbol}")
                trade["alerted"] = True
                to_remove.append(symbol)

        except Exception as e:
            print(f"Monitor error {symbol}: {e}")

    for sym in to_remove:
        active_trades.pop(sym, None)


# ============================================
# 🆕 IMPROVED SIGNAL CHECK
# ============================================
def check_signal(symbol):
    closes, highs, lows, volumes = get_klines(symbol)
    price = closes[-1]

    e7s  = get_ema_series(closes, 7)
    e25s = get_ema_series(closes, 25)
    e7   = e7s[-1];  e7p = e7s[-3]
    e25  = e25s[-1]
    e99  = get_ema(closes, 99)

    rsi     = get_rsi(closes, RSI_PERIOD)
    ml, ms  = get_macd(closes)

    avg_vol    = sum(volumes[-20:]) / 20
    recent_vol = sum(volumes[-3:])  / 3
    vol_ratio  = recent_vol / avg_vol
    vol_ok     = vol_ratio >= 1.5   # 🆕 1.1 se badha ke 1.5x

    # Sideways filter
    if abs(e7 - e25) / price < 0.0015:
        return None

    # Late-entry filter
    lookback = closes[-6:]
    if abs((lookback[-1] - lookback[0]) / lookback[0]) > 0.03:
        return None

    # 🆕 Lower highs/lows check (last 3 candles)
    def is_downtrend_candles():
        # Last 3 highs decreasing
        return highs[-1] < highs[-2] < highs[-3] and lows[-1] < lows[-2] < lows[-3]

    def is_uptrend_candles():
        # Last 3 highs increasing
        return highs[-1] > highs[-2] > highs[-3] and lows[-1] > lows[-2] > lows[-3]

    signal   = None
    strength = 0

    # ✅ LONG — price MA99 ke upar, bullish MA stack, RSI recovery zone
    if (
        price > e99                          # 🆕 Price MA99 ke upar honi chahiye
        and e7 > e25 > e99                   # Bullish MA stack
        and e7 > e7p                         # MA7 upar ja raha
        and 35 <= rsi <= 65                  # 🆕 RSI range thoda widen — oversold recovery
        and ml > ms                          # MACD bullish
        and vol_ok                           # Volume confirm
        and not is_downtrend_candles()       # 🆕 Downtrend candles mein long nahi
    ):
        signal   = "LONG"
        strength = (e7 - e99) / e99 * 100

    # ✅ SHORT — price MA99 ke neeche, bearish MA stack, RSI overbought zone
    elif (
        price < e99                          # 🆕 Price MA99 ke neeche honi chahiye
        and e7 < e25 < e99                   # Bearish MA stack
        and e7 < e7p                         # MA7 neeche ja raha
        and 35 <= rsi <= 65                  # RSI range
        and ml < ms                          # MACD bearish
        and vol_ok                           # Volume confirm
        and not is_uptrend_candles()         # 🆕 Uptrend candles mein short nahi
    ):
        signal   = "SHORT"
        strength = (e99 - e7) / e99 * 100

    if not signal:
        return None

    sl, tp1, tp2, pct = calculate_sl_tp(signal, price, highs, lows)

    return {
        "symbol":       symbol,
        "signal":       signal,
        "price":        price,
        "sl":           sl,
        "tp1":          tp1,
        "tp2":          tp2,
        "sl_pct":       pct,
        "rsi":          rsi,
        "strength":     strength,
        "volume_ratio": round(vol_ratio, 2),
        "e7":           e7,
        "e25":          e25,
        "e99":          e99,
    }


# ============================================
# SEND SIGNAL EMAIL
# ============================================
def send_signal_email(data):
    global trades_sent_today
    sym  = data["symbol"]
    sig  = data["signal"]
    p    = data["price"]
    sl   = data["sl"]
    tp1  = data["tp1"]
    tp2  = data["tp2"]
    pct  = data["sl_pct"]
    rsi  = data["rsi"]
    vol  = data["volume_ratio"]
    e7   = data["e7"]
    e25  = data["e25"]
    e99  = data["e99"]

    body = (
        f"Coin: {sym}\n"
        f"Trade: {sig}\n"
        f"Margin: ${MARGIN_USDT} | Leverage: {LEVERAGE}x | Position: ${POSITION_SIZE}\n\n"
        f"Entry:       {fmt(p)}\n"
        f"Stop Loss:   {fmt(sl)}   ({pct*100:.2f}% away) → Risk: ${MARGIN_USDT}\n"
        f"TP1 (50%):   {fmt(tp1)}  ({pct*100:.2f}% away) → Reward: ${MARGIN_USDT} 🎯\n"
        f"TP2 (50%):   {fmt(tp2)}  ({pct*RR_RATIO*100:.2f}% away) → Reward: ${MARGIN_USDT*RR_RATIO} 🚀\n\n"
        f"📌 Plan: TP1 pe 50% close karo, baaki TP2 pe hold karo\n\n"
        f"RSI: {rsi:.1f} | Volume: {vol}x average\n"
        f"MA7: {fmt(e7)} | MA25: {fmt(e25)} | MA99: {fmt(e99)}\n"
        f"Price vs MA99: {'ABOVE ✅' if p > e99 else 'BELOW ⚠️'}\n"
        f"RR Ratio: 1:{RR_RATIO}\n"
        f"Trade {trades_sent_today + 1}/{MAX_TRADES_PER_DAY} today ✅"
    )
    print(body)
    send_email(f"🚨 {trades_sent_today+1}/{MAX_TRADES_PER_DAY}: {sym} {sig}", body)
    trades_sent_today += 1

    # Dashboard pe signal bhejo
    try:
        import urllib.request, json as _json
        payload = _json.dumps({
            "symbol": sym, "signal": sig,
            "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
            "rsi": round(rsi, 1), "vol": vol,
        }).encode()
        req = urllib.request.Request(
            f"{DASHBOARD_URL}/api/signal",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
        print("-> Dashboard updated.")
    except Exception as e:
        print(f"Dashboard post error (ok if dashboard not running): {e}")

    # Active trade mein add karo — TP2 monitor karega
    active_trades[sym] = {
        "signal":  sig,
        "entry":   p,
        "sl":      sl,
        "tp":      tp2,   # monitor TP2 for final exit alert
        "tp1":     tp1,
        "alerted": False,
    }


# ============================================
# MAIN LOOP
# ============================================
if __name__ == "__main__":
    print("🔥 Bot v2 started — 15x, max 5 signals/day, SL monitor ON.")
    print("Ctrl+C to stop.\n")

    last_monitor_check = time.time()

    while True:
        try:
            reset_daily_counter()
            now = datetime.now()

            # 🆕 SL/TP monitor — har 60 sec mein
            if time.time() - last_monitor_check >= SL_MONITOR_INTERVAL:
                if active_trades:
                    print(f"[{now.strftime('%H:%M:%S')}] Monitoring {len(active_trades)} active trade(s)...")
                    monitor_active_trades()
                last_monitor_check = time.time()

            # 🆕 Consecutive loss check
            if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                print(f"[{now.strftime('%H:%M:%S')}] ⛔ {MAX_CONSECUTIVE_LOSSES} consecutive losses — trading band today!")
                time.sleep(SCAN_EVERY_SECONDS)
                continue

            if trades_sent_today >= MAX_TRADES_PER_DAY:
                print(f"[{now.strftime('%H:%M:%S')}] Daily limit reached. Waiting...")
            else:
                symbols = get_top_movers()
                print(f"[{now.strftime('%H:%M:%S')}] Scanning {len(symbols)} coins... ({trades_sent_today}/{MAX_TRADES_PER_DAY} today)")

                found = []
                for sym in symbols:
                    try:
                        if sym in last_signaled:
                            hrs = (now - last_signaled[sym]).total_seconds() / 3600
                            if hrs < SIGNAL_COOLDOWN_HOURS:
                                continue
                        r = check_signal(sym)
                        if r:
                            found.append(r)
                        time.sleep(1.2)
                    except Exception as e:
                        print(f"Error {sym}: {e}")

                found.sort(key=lambda x: x["strength"], reverse=True)

                if found:
                    best = found[0]
                    send_signal_email(best)
                    last_signaled[best["symbol"]] = now
                    print(f"-> Signal sent: {best['symbol']} {best['signal']}")
                else:
                    print("-> No strong signal this cycle.")

        except Exception as e:
            print("Loop error:", e)

        print(f"Sleeping {SCAN_EVERY_SECONDS}s...\n")
        time.sleep(SCAN_EVERY_SECONDS)
