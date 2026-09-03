"""
====================================================
TRADING DASHBOARD — FLASK BACKEND (Railway Ready)
====================================================
"""

from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime
import json, os

app = Flask(__name__, static_folder="static")

# Railway environment variables se API keys lo
API_KEY            = os.environ.get("API_KEY", "")
API_SECRET         = os.environ.get("API_SECRET", "")
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
TO_EMAIL           = os.environ.get("TO_EMAIL", "")

# Simple secret token — dashboard ko secure karo
DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "mohib123")

# Railway pe file system temporary hota hai
# isliye signals memory mein rakhte hain (100 tak)
signals_store = []
next_id       = 1

def recalc_stats():
    stats = {"total": len(signals_store), "wins": 0, "losses": 0, "open": 0, "pnl": 0.0}
    for s in signals_store:
        outcome = s.get("outcome", "OPEN")
        pnl     = s.get("pnl", 0.0)
        if outcome in ("TP1", "TP2", "TP1_THEN_SL"):
            stats["wins"] += 1
        elif outcome == "SL":
            stats["losses"] += 1
        else:
            stats["open"] += 1
        stats["pnl"] += pnl
    stats["pnl"] = round(stats["pnl"], 2)
    return stats

# ============================================
# ROUTES
# ============================================

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "signals": len(signals_store)})

# Bot signal POST karta hai
@app.route("/api/signal", methods=["POST"])
def add_signal():
    global next_id, signals_store
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    signal = {
        "id":        next_id,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "symbol":    data.get("symbol", ""),
        "signal":    data.get("signal", ""),
        "entry":     data.get("entry", 0),
        "sl":        data.get("sl", 0),
        "tp1":       data.get("tp1", 0),
        "tp2":       data.get("tp2", 0),
        "rsi":       data.get("rsi", 0),
        "vol":       data.get("vol", 0),
        "outcome":   "OPEN",
        "pnl":       0.0,
    }
    next_id += 1
    signals_store.insert(0, signal)
    signals_store = signals_store[:100]
    return jsonify({"ok": True, "id": signal["id"]})

@app.route("/api/signals")
def get_signals():
    return jsonify(signals_store)

@app.route("/api/stats")
def get_stats():
    return jsonify(recalc_stats())

@app.route("/api/signal/<int:signal_id>/outcome", methods=["POST"])
def update_outcome(signal_id):
    data    = request.json
    outcome = data.get("outcome", "OPEN")
    pnl     = data.get("pnl", 0.0)
    for s in signals_store:
        if s["id"] == signal_id:
            s["outcome"] = outcome
            s["pnl"]     = pnl
            break
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    os.makedirs("static", exist_ok=True)
    print(f"🚀 SignalDesk starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
