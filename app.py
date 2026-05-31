from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
import json
import traceback
import os

app = Flask(__name__)

KIA_USER = os.environ.get("KIA_USER")
KIA_PASS = os.environ.get("KIA_PASS")

COOKIE_FILE = "kia_session.json"


# =========================
# 🔑 LOGIN + TOKEN CAPTURE
# =========================
@app.route("/kia-init")
def kia_init():
    try:
        access_token = None

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            context = browser.new_context()

            # 🔥 CAPTURE AUTOMATIQUE TOKEN depuis requêtes
            def handle_request(request):
                nonlocal access_token
                headers = request.headers

                if "accesstoken" in headers:
                    access_token = headers["accesstoken"]

            context.on("request", handle_request)

            page = context.new_page()

            page.goto("https://kiaconnect.ca/login", timeout=20000)

            page.wait_for_selector('input[type="email"]', timeout=10000)

            page.fill('input[type="email"]', KIA_USER)
            page.fill('input[type="password"]', KIA_PASS)

            page.click('button[type="submit"]')

            # 🔥 Aller sur overview pour forcer appels API Kia
            page.goto("https://kiaconnect.ca/cwp/overview", timeout=20000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            cookies = context.cookies()

            # sauvegarde cookies + token
            with open(COOKIE_FILE, "w") as f:
                json.dump({
                    "cookies": cookies,
                    "token": access_token
                }, f)

            browser.close()

            return jsonify({
                "status": "✅ session initialisée",
                "cookies": len(cookies),
                "token_found": access_token is not None
            })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        })


# =========================
# 🚗 VEHICLES
# =========================
@app.route("/kia-vehicles")
def kia_vehicles():
    try:

        if not os.path.exists(COOKIE_FILE):
            return jsonify({"error": "run /kia-init first"})

        with open(COOKIE_FILE, "r") as f:
            session_data = json.load(f)

        cookies = session_data.get("cookies")
        access_token = session_data.get("token")

        if not access_token:
            return jsonify({"error": "no access token, run /kia-init again"})

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            context = browser.new_context()
            context.add_cookies(cookies)

            # 🔥 REQUÊTE API CORRECTE
            response = context.request.post(
                "https://kiaconnect.ca/tods/api/lstvhclsts",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "accesstoken": access_token
                },
                data=json.dumps({
                    "From": "CWP",
                    "Language": "1",
                    "Offset": "-4"
                })
            )

            data = response.json()

            browser.close()

            return jsonify(data)

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        })


@app.route("/")
def home():
    return "Kia API OK ✅"
