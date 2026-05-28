from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
import json
import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

import traceback

app = Flask(__name__)

KIA_USER = os.environ.get("KIA_USER")
KIA_PASS = os.environ.get("KIA_PASS")

COOKIE_FILE = "/tmp/kia_cookies.json"


# =========================================
# 🔑 1. LOGIN + SAVE SESSION (À FAIRE 1 FOIS)
# =========================================
@app.route("/kia-init")
def kia_init():
    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(
            headless=True,
            executable_path="/opt/render/.cache/ms-playwright/chromium-1223/chrome-linux/chrome",
            args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            context = browser.new_context()
            page = context.new_page()

            # 🔹 Ouvrir page login
            page.goto("https://kiaconnect.ca/login", timeout=20000)

            page.wait_for_selector('input[type="email"]', timeout=10000)

            # 🔹 Login
            page.fill('input[type="email"]', KIA_USER)
            page.fill('input[type="password"]', KIA_PASS)

            page.click('button[type="submit"]')

            # 🔥 IMPORTANT : attendre vraie session Kia
            page.wait_for_url("**/cwp/**", timeout=20000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            # 🔹 Sauvegarde cookies
            cookies = context.cookies()

            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f)

            browser.close()

            return jsonify({
                "status": "✅ session initialisée",
                "cookies_saved": len(cookies)
            })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        })


# =========================================
# 🚗 2. FETCH VEHICLES (RAPIDE)
# =========================================
@app.route("/kia-vehicles")
def kia_vehicles():
    try:

        # Vérifier si session existe
        if not os.path.exists(COOKIE_FILE):
            return jsonify({
                "status": "error",
                "message": "⚠️ exécute /kia-init d'abord"
            })

        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            context = browser.new_context()
            context.add_cookies(cookies)

            page = context.new_page()

            # 🔹 Aller directement Kia (rapide)
            page.goto("https://kiaconnect.ca/cwp/overview", timeout=15000)

            page.wait_for_timeout(2000)

            # 🔥 Appel API réel
            data = page.evaluate("""
                async () => {
                    try {
                        const res = await fetch('https://kiaconnect.ca/tods/api/lstvhclsts', {
                            method: 'POST',
                            credentials: 'include',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: '{"from":0}'
                        });

                        return await res.json();

                    } catch (e) {
                        return { error: e.toString() };
                    }
                }
            """)

            browser.close()

            return jsonify({
                "status": "ok",
                "data": data
            })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        })


# =========================================
# 🏠 HOME
# =========================================
@app.route("/")
def home():
    return "Kia API OK ✅"
