import requests
import os
import time
import traceback
import logging
logging.basicConfig(level=logging.DEBUG)
from flask import Flask, jsonify, request
from hyundai_kia_connect_api import VehicleManager
from hyundai_kia_connect_api.exceptions import AuthenticationError
import json

HUBITAT_URL = "https://cloud.hubitat.com/api/a2640f5d-3176-449c-a37b-44a7eaa1824a/apps/246/devices/272/sendKiaRequest"
ACCESS_TOKEN = "57ad1d4c-edcc-4c24-aaaa-bbbbcccc"

import urllib.parse

def envoyer_via_hubitat_bridge(kia_url, kia_headers, kia_body):

    arg1 = urllib.parse.quote(kia_url)
    arg2 = urllib.parse.quote(json.dumps(kia_headers))
    arg3 = urllib.parse.quote(json.dumps(kia_body))

    url = f"{HUBITAT_URL}/{arg1}/{arg2}/{arg3}?access_token={ACCESS_TOKEN}"

    response = requests.get(url)

    print("STATUS:", response.status_code)
    print("TEXT:", response.text)

    return response.text





original_request = requests.request

captured_request = {}

def hooked_request(method, url, **kwargs):
    global captured_request

    try:
        headers = kwargs.get("headers", {})

        clean_headers = {}
        if headers:
            for k, v in headers.items():
                clean_headers[str(k)] = str(v)

        captured_request = {
            "method": str(method),
            "url": str(url),
            "headers": clean_headers,
            "data": str(kwargs.get("data")) if kwargs.get("data") else None,
            "json": kwargs.get("json"),
            "params": kwargs.get("params")
        }

        print("🔥 INTERCEPTED GLOBAL REQUEST 🔥")
        print(captured_request)

    except Exception as e:
        print("HOOK ERROR:", e)

    return original_request(method, url, **kwargs)

requests.request = hooked_request

# =======
# hoock #2
# =========

original_send = requests.Session.send

def hooked_send(self, request, **kwargs):
    global captured_request

    try:
        captured_request = {
            "method": request.method,
            "url": request.url,
            "headers": {k: str(v) for k, v in request.headers.items()},
            "body": request.body.decode() if isinstance(request.body, bytes) else str(request.body)
        }

        print("🔥 INTERCEPTED RAW REQUEST 🔥")
        print(captured_request)

    except Exception as e:
        print("HOOK ERROR:", e)

    return original_send(self, request, **kwargs)

requests.Session.send = hooked_send

# =========
# add latest (end)
# ==========

app = Flask(__name__)

API_KEY = os.environ.get("RENDER_API_KEY")
USERNAME = os.environ.get("KIA_USER")
PASSWORD = os.environ.get("KIA_PASS")
PIN = os.environ.get("KIA_PIN")

vm = None


def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


def get_vm():
    global vm
    global captured_request  # ✅ AJOUT

    if vm is None:
        vm = VehicleManager(
            region=2,
            brand=1,
            username=USERNAME,
            password=PASSWORD,
            pin=PIN,
            language="en"
        )

        try:
            vm.login()
            vm.vehicles = None
            captured_request = {}  # ✅ maintenant global
            vm.vehicles  # accès simple pour forcer init
            time.sleep(2)

        except AuthenticationError:
            raise Exception("MFA_REQUIRED")

    else:
        try:
            vm.check_and_refresh_token()
        except Exception as e:
            print("Token refresh warning:", e)

    return vm


@app.route("/vehicle/auth-otp", methods=["POST"])
def auth_otp():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    global vm

    data = request.get_json()
    otp_code = data.get("code") if data else None

    if not otp_code:
        return jsonify({"error": "Missing code"}), 400

    try:
        vm.validate_mfa(otp_code)
        vm.get_vehicles()

        return jsonify({
            "status": "ok",
            "message": "MFA validated ✅"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/vehicle/status", methods=["GET"])
def vehicle_status():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        try:
            current_vm = get_vm()
        except Exception as e:
            if "MFA_REQUIRED" in str(e):
                return jsonify({
                    "status": "mfa_required"
                }), 403
            raise e

        vehicles = current_vm.vehicles

        if not vehicles:
            return jsonify({"error": "No vehicle found"}), 404

        if isinstance(vehicles, dict):
            vehicle = list(vehicles.values())[0]
        else:
            vehicle = vehicles[0]

        try:
            current_vm.update_vehicle(vehicle.id)
        except Exception as e:
            print("Update failed:", e)

        return jsonify({
            "status": "ok",
            "result": {
                "status": vehicle.data
            }
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

@app.route("/bridge/status", methods=["POST"])
def bridge_status():

    data = request.json

    # data = réponse brute Kia envoyée par Hubitat

    try:
        # Ici tu pourrais parser manuellement
        return jsonify({
            "status": "ok",
            "raw": data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route("/vehicle/<cmd>", methods=["POST"])
def vehicle_action(cmd):

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        current_vm = get_vm()
        vehicles = current_vm.vehicles

        if isinstance(vehicles, dict):
            vehicle_id = list(vehicles.keys())[0]
        else:
            vehicle_id = vehicles[0].id

        if cmd == "lock":
            current_vm.lock(vehicle_id)
        elif cmd == "unlock":
            current_vm.unlock(vehicle_id)
        else:
            return jsonify({"error": "invalid command"}), 400

        return jsonify({
            "status": "ok",
            "action": cmd
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# =========
# test route
# =======
@app.route("/test-login")
def test_login():

    url = "https://auth.kiaconnect.ca/oauth2/token"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    body = {
        "username": "TON_EMAIL",
        "password": "TON_PASSWORD",
        "grant_type": "password"
    }

    result = envoyer_via_hubitat_bridge(url, headers, body)

    return result
# ======
# bridge prepare route
# ==========

@app.route("/bridge/prepare-status", methods=["GET"])
def prepare_status():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    # ✅ simulation d'une requête Kia
    return jsonify({
        "target_url": "https://postman-echo.com/post",
        "headers": {
            "Content-Type": "application/json"
        },
        "payload": {
            "test": "hubitat working"
        }
    })


@app.route("/bridge/decode-login", methods=["POST"])
def decode_login():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        data = request.get_json()

        return jsonify({
            "status": "ok",
            "raw_response": data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
# ========
# bridge prepare login
# =============

@app.route("/bridge/prepare-kia-test", methods=["GET"])
def prepare_kia_test():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    return jsonify({
        "target_url": "https://httpbin.org/get",
        "headers": {},
        "payload": None,
        "method": "GET"
    })

# =========
# capture demande
# ============

@app.route("/bridge/capture-status", methods=["GET"])
def capture_status():

    global captured_request

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        vm = get_vm()

        vehicles = vm.vehicles

        if not vehicles:
            return jsonify({"error": "No vehicle"}), 404

        if isinstance(vehicles, dict):
            vehicle = list(vehicles.values())[0]
        else:
            vehicle = vehicles[0]

        # ✅ reset capture
        captured_request = {}

        # ✅ 🔥 FORCE APPEL RÉEL KIA
        vm.update_vehicle(vehicle.id)

        return jsonify({
            "status": "ok",
            "captured": captured_request if captured_request else "EMPTY"
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500
# =========
# test proxy
# =========

def test_hubitat_proxy():
    url_kia = "https://httpbin.org/post"

    headers = {
        "Content-Type": "application/json"
    }

    body = {
        "test": "hubitat proxy works"
    }

    result = envoyer_via_hubitat_bridge(url_kia, headers, body)

    print("RESULT:", result)
# =======
# test proxy device
# =========

@app.route("/test-proxy")
def test_proxy():

    result = envoyer_via_hubitat_bridge(
        "https://httpbin.org/post",
        {"Content-Type": "application/json"},
        {"hello": "hubitat"}
    )

    return result


@app.route("/test-kia")
def test_kia():

    token = "eyJlbmMiOiJTVVJOUnk3M040dTlFMVpJdjM3cHZEOHhGczh1R2FyaWtSTnFyS3BCOW9jNjZ2b2J4KzJpRzFkbjZ6STJwV1VyK3RWVW1mUEs0UXR4cWdlVWV3UDI1VkpuaGMzS0FQOThLTVBEeVdqQTlObFBIQXNMWE4raS96ZDRrdVlrd0VpTk5kQXRWUVhnQndJMndKT3RvelZjMzdkTFNpa2I3SVRRNTZDVXh1R3p0TThCVm1UTEF1clNpWW1yNHU0N2I4K243MU1HRkFTSlE4UmNpSG5tT2RzWW9Qd0djRVlPZWh6TXNFM1NVZ00rUllxUk83SzN0eFhSeVd1dUM2U202MGswdi9MeUl0MEo4bGtRYldEZjUveFRPZEs4VDFmZ3IvWURVeXFFTzFsOFVnUUxEbE12bTFneURrL3A5clRHdGZib29TZnk3a1RBV01lcTdVRGtoRlE5WGh6VGF5WTYrZjJ2Q1g2L29RZXVCWWcvelQwTUtkaVNSdThRVWdMTTV4dnBKTkdoQ25FTlJhc3ZzaEluYXQvcUxXOGlJZ1N2azZWMVE3UWhuUHMyZUNXY3h5MWttNzcrNCtxWkFDWXY4QW5KYjRsbW9COUZzZ3pXUjZzUkRza0VXaElLOW5GbTNxQzNMZXZrMlJoamF2Wmhzb1ZCMlFxanllRnduN1Yra0x2L0hSUXd3YzdVYXB2N09XWFBFMFIvODBlcFJ6VC92NEJYRFJ1S3pwU2J0WmRzUjZzU2hodWsycWRPNFI4dVFWSjkvUmtlYSt6cHlidG5KUW0yNFNQQ0YzSE1QdmVCUHFRKzlwTlZneXIxTU16M2JvNGkwbXpaZGRhd004YmFhZTdvbU1FS2ZDaVdtU1A3NjRXcTBQVGQ5YWpsbXdtSE5RajZwZGUrMUFxZjFuK0xuQ0tqQnk3MzdZeEhmcHk2aC8rTkZOR3ZFOEo1RFcyRi80OFoyUnRmMHo5QmJEekdEWGhGeGkyd2s1OVZJTVFncGRKL1NYakFkYitlMDNTR3BmUVNkSWQ2TERBTDg3aGVoVTYydnRGQ1dsTmpSYlk1RmkyYzlqNCtqTjB0WGxjQVFIVFBnTStkWkxLbVBBMXJWRVFQbE9lL2RWWElBeXB4YW9rZHY4Y3JTQngreWpXWXRrQjh6OTUwNTF1TmFVT3lXZXQrNWlWY1RBN0w4Wi9URU10RmY5U0x3UWtnaWw4R2JtUjFqUGdTOE16a05aRmp3TnMwR3BGYy9BOWJCOE40d3VKaEkreS9rSWUzS3I0M0d0YlNncytybko3aGt1YU80dGR5OUpidU1aYVJLdXhYMEhIMDhwTzA3VTBUK0NQSlBnU3A0bWwxM3o4ZHE0NmpjNFZ2a0ovV1Q0U1BwVE51SHhZWENMbVNtZW9JMmVuanNoc2hQTGhvcnBJPSIsImtleSI6ImJGTENTU2ZzcHptZDArSk0zcERQUGdFc1VoZHlTMlY3ajVMd1FjdHlxVUpoTGRXSVJNMmZoR25pT3BPdUFwZmIwK3JUYUZkUVBtc21COUxDckhrNnN3PT0ifQ=="

    result = envoyer_via_hubitat_bridge(
        "https://api.connect.kia.com/v1/spa/vehicles",
        {
            "Authorization": f"Bearer {token}"
        },
        {}
    )

    return result


@app.route("/test-kia-real")
def test_kia_real():

    token = "eyJlbmMiOiJTVVJOUjBiQnUxeEpvMVN0YVJjZjN5aTNCZTZaYldDT1pPNzBjaVJXQmtYNHU3QU9IdWp1aitmMXdrTS9RcE1NY3UxK0NhNTl4VFJNdHcxV2JVTWxaS3U0RkFIdTE2bUg0Vk1nWGJCV0srWlVzdXFhWmd2SGVJd09UNzZVbitjdUhraGw4aDkrZW5SY3JtQlYyM3lYUzRVU2o0YWF3c2ZVa1Z2ekVtbisvSnRlS09UVFVua3RNTjF4YkNiNEVNajJ2bXhrbzE1MVZxdFVPUERZSG5UVG5RNkRzaEN4T3lrM0FuODhjeGtNbi9SM0tnTG8yWXA2QURzUGo2ZVRVbmZGU3NlMWpINUY1WVZLdk1oWFc1eHh1dVlpczB4MjFIZGpuS01odS95SkRlVm95Um1IZ2FvZmtnbmVzbUZLVE5VSUxrVlhZSU9XTm9sQnR5M2o3Q2VSVnZpOUVCVWtGdUZhTjhRUEtlRFI2UlhkWGNDajVUSFN4L3FMMXlsVVN6ME42bDMyYjk3K1ZwNlpKL3BXbFl5ZStPRkNpd2dudVJBclBObmRTVG5VenZiNFpuMHdPRmM0cHM3RTV4NWo3cGNMdzBQU0dJa09FQW44SEpaZU5ZOU9KL1pHVGVVVngzeElEVkRQV1BxTU8xZUVlbmRDR3pLZjc2aVY3L09KOGhheUtqQnBPU2ZJUEpGNmxzZ2IyQ1lRZHQyeDFXQ0pXRWlBRzhyeHRNeXoyRE9RTEpCNm0zWFNsS05QMUg2MFhFdTBzK0tZanNMNEFDb055eVhXb09hV1RPYVdIUEpRMEVlakt2azgyUzRwcEVOWklaOTN0WERGUmhlWmpQWmpuQVVuQndEYlFCZGRjbndwaUlncUhJRjhsS2gzcW5RckVCd3VzRys5cnZwd0VrY3VxOURBTGI2ekp5ZGtNeHUvZUlPUjQ4R01qY1docmpJYzJaYm5EMm1DVVNnalBwZHZnY0I1YnN1M2xlek8vSDY2c1Y2aGFma0tGbWpJeXluakR1dXBxNzJJWmVDWHMrNlA5NHdGLzJ6RlM5ellxUllWYUczK2EwNGhQK3ZzcmJFYytZVVlCUDRZbGhBUERHUzRWMlpjR2E0WmR5SnhDQTBESlJzUk1yVnQvUi83N3BtR2JwVFRhRTBROE9FSW1TSGp2R2JGTFZGaTJra3hIZkJyMUVVYmdieDdWOEdvdHlGVlFacTNuc2RKVWlzMlExV0NCZ1dNand4eGpwMVFSbHd0L012bUNRVU5EK2plN0JDeGc2cUFsOWlQckE1SmNid0N4dHpleVkyMGFDQ000RWttZmUvSHdKN1k4VlNmTklnQmtvR0tBK0ZPN2dFaVlRVnMwd1NuczVQelV5eXI4TkpZVjlYdHZ6aGs4OVpUU3g0V0lHdGUyalNBQnFzPSIsImtleSI6ImhzR0pmSUVRdThZakFtdGhlOXNZQk5YVnRMTTA5ZUlPKzgvQ0JSQU55dG9oNjJOQmFranpUeWF3M2E3QTlqY2liQWNLSFE4U25Kcm1SUFNBWTQ4ZGJnPT0ifQ=="

    headers = {
        "Accesstoken": token,
        "Content-Type": "application/json",
        "Language": "1",
        "Offset": "-4",

        # ✅ CRITIQUE (manquants)
        "Origin": "https://kiaconnect.ca",
        "Referer": "https://kiaconnect.ca/login",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*"
    }

    result = envoyer_via_hubitat_bridge(
        "https://kiaconnect.ca/tods/api/lstvhcls",
        headers,
        {}
    )

    return result

# =======
# login mobile
# ==========


@app.route("/test-login-mobile")
def test_login_mobile():

    url = "https://api.connect.kia.com/v1/user/oauth2/token"

    headers = {
    "Content-Type": "application/json",
    "User-Agent": "okhttp/3.12.0",
    "Accept": "application/json"
}

    body = {
    "grant_type": "password",
    "username": "PLAFONTAINE44@GMAIL.COM",
    "password": "Ludovyck22",
    "client_id": "SPA",
    "client_secret": ""
}


    result = envoyer_via_hubitat_bridge(url, headers, body)

    return result



@app.route("/")
def home():
    return "Kia API ✅"
