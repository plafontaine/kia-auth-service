from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
import json
import traceback
import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/app/.cache/ms-playwright"
os.environ["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
app = Flask(__name__)

KIA_USER = os.environ.get("KIA_USER")
KIA_PASS = os.environ.get("KIA_PASS")

COOKIE_FILE = "/tmp/kia_cookies.json"


@app.route("/kia-init")
def kia_init():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )



            context = browser.new_context()
            page = context.new_page()

            page.goto("https://kiaconnect.ca/login", timeout=20000)
            page.wait_for_selector('input[type="email"]', timeout=10000)

            page.fill('input[type="email"]', KIA_USER)
            page.fill('input[type="password"]', KIA_PASS)

            page.click('button[type="submit"]')

            page.wait_for_url("**/cwp/**", timeout=20000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

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


@app.route("/kia-vehicles")
def kia_vehicles():
    try:
        if not os.path.exists(COOKIE_FILE):
            return jsonify({
                "error": "run /kia-init first"
            })

        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )



            context = browser.new_context()
            context.add_cookies(cookies)

            page = context.new_page()

            page.goto("https://kiaconnect.ca/cwp/overview", timeout=15000)
            page.wait_for_timeout(2000)

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

            return jsonify(data)

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        })


@app.route("/")
def home():
    return "Kia API OK ✅"
