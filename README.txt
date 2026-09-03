====================================================
SIGNAL DESK — COMPLETE SETUP GUIDE
====================================================

FOLDER STRUCTURE:
  trading-bot/
  ├── app.py
  ├── bot_v2.py
  ├── requirements.txt
  ├── Procfile
  ├── runtime.txt
  └── static/
      └── index.html

====================================================
STEP 1 — GITHUB PE UPLOAD KARO
====================================================
1. github.com pe account banao
2. New Repository → naam: trading-bot → Create
3. Sab files upload karo (static/index.html bhi)

====================================================
STEP 2 — RAILWAY PE DEPLOY KARO
====================================================
1. railway.app pe jao
2. "Start a New Project" → Deploy from GitHub
3. trading-bot repo select karo
4. Settings → Environment Variables mein yeh daalo:

   API_KEY            = teri Binance API key
   API_SECRET         = tera Binance secret
   GMAIL_ADDRESS      = tera@gmail.com
   GMAIL_APP_PASSWORD = tera Gmail app password
   TO_EMAIL           = tera@gmail.com

5. Deploy hoga — URL milega jaise:
   https://trading-bot-xyz.railway.app

====================================================
STEP 3 — BOT UPDATE KARO
====================================================
bot_v2.py mein yeh line update karo:
  DASHBOARD_URL = "https://trading-bot-xyz.railway.app"

Phir bot_v2.py dobara GitHub pe upload karo.

====================================================
STEP 4 — DASHBOARD KHOLNA
====================================================
Bas browser mein URL kholo:
  https://trading-bot-xyz.railway.app

Phone pe bhi, laptop pe bhi — kahi bhi!

====================================================
APP BANANA CHAHTE HO? (Android/iPhone)
====================================================
Seedha browser se home screen pe add karo:

ANDROID (Chrome):
  1. URL kholo
  2. Top right 3 dots → "Add to Home Screen"
  3. App jaise icon ban jayega!

iPHONE (Safari):
  1. URL kholo Safari mein
  2. Share button → "Add to Home Screen"
  3. App jaise icon ban jayega!

Yeh PWA (Progressive Web App) hai —
bilkul app jaise lagega, app store ki zarurat nahi!

====================================================
BOT CHALANA (apne PC/laptop pe):
====================================================
  pip install flask python-binance gunicorn
  python bot_v2.py

Bot Railway Dashboard pe signals bhejta rahega.
====================================================
