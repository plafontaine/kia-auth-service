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


def envoyer_via_hubitat_bridge(kia_url, kia_headers, kia_body):

    params = {
        "access_token": ACCESS_TOKEN,
        "targetUrl": kia_url,
        "headersJson": json.dumps(kia_headers),
        "bodyData": json.dumps(kia_body)
    }

    response = requests.get(HUBITAT_URL, params=params)

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

    token = "eyJlbmMiOiJTVVJOUjNWZEFHZXpvOUxsM3ozTEg5SWJrRnYrNk03WmEvbnJDajhOeFV5L1VlMnd2NS9NMlludy9DYzRadUROcXdvL3p1TWczd0hjSmM0MlpwT3RXZ1VPRjNMRUFyeUpnWVV3dlhlVzVmdFV6VkxFQkVhVTZsU2d4SFZacHhxNXZCdXowMHRVTlFmVE1tMjdVaTVjOEZiejNTelJCZjY3WkU0Y1grTlVyZ3RVcnRUdCtyWis2bUtDQ3VBZXJxT0JhMmlkcmZpaDlPYkVlOVJCRG53Y0tzZEhoR09LNzRTZEI3WDI4anJXbUprTzlkN3B4eVhwSC9BNkRhTS92VEVpdElEQWpwQ1RuakwxLzVwS2M2T0o4SFFtTFRFbllxYnEvV25YUEFaSnJYWGJpQzZRV2puamU2NzZvdURQaEMzd3U0Vk0ydHI3OFM0WW5SYXVmd3JNTXUxT2JyNjF2cGZGejJ2UFBRTGhEQ2ltd1JuUU8wL1hpMGp3bTFqK0xLRjhld0E4bnlwdmF3N0N6d2FXbUhhZTRmTjhKV3RVSFlqZkNlYTM2M1FCcG9Td3kzdGZ5TThTTU12clBsaXRTcjRveDZSYTBXdlNJcmtrTERpcE8wN3J1UG9MSjdyTTFOSmZrcXNDMkJoRWZBc1pTNGoxK2kxdU0zcnNKWTE1TUJ4N24zSC8zWi8xV3lrMzJpSVZQbTFDa052a0JZQ1BKb0VubWwvTGo4aFQ0ZjNQdGFKUGRDWUpEZ3FwN0xRMzVqNGtzMGVIRStOQ3llN0J5aGl2TElKdEoxYzNSZTlRWmFjOEtISmdKN1pZU3luYmZTL3ZNOXZXVTFwL0dJSWNGVkxRU2FDWDJxdmdoM1d0RnpZek00UHc4ODAyQlNXVkVnazhqaWpwWityNHlSZFpMNzZwMUdRTnpGTHgyc0J1NDJoL3JYNW44L1Fvd21HWGFEd21MN0Q3aENVbFYrSEpDaUhhYWFXL3FvUmlZUDJVQUNxNHcvL2owWXQ2dE5kblcwSHE1SDQ2TXQ1SCsydXZKMXo2a1pma2E1NVVvaFlVME5SbkkrM3VHWExFWDN0VGlhNmpWSFdBTHJrWGVTdTBzdE54bzhrbFZTbDQzaFU2VXovbE1MeVBMR2FBNFB2cThIZWs2UWJoUDh6ZVpVT2tFRnBDTUpubXlBOWhGamVvQ0toZGhyT0luYWJTTjhFVnlkbU9vTE9UU3VUYk9ISHZNR3lxMVF3VFg4TGM1TjZ3cE5laStVeVZSdnhObDJycFFlc0VuVjI5MUVpNXdiTjVqbGhRcE9mYUJFbTdvOTkzbkN4UmY3ZGdUY1Y0aUoxdXlndUc5NC9rY0Y3QWlDQUQ1b1FhZ21FQ29jSFVheVJNU1Roclk0SUY5bllYeFhQNm9DWE5lWDM5Q0ZZPSIsImtleSI6IkltdERLeEY1bUZnVlNFRzJURjE3eU5OV0NOUVRnUUVmTUxianNaTEFzdHlOQWphQ21FWlhGWHVsbzBBUTZLd2RZdm9aVmJMMk5sdVdlNjlDRU0rcEtnPT0ifQ=="

    result = envoyer_via_hubitat_bridge(
        "https://api.connect.kia.com/v1/spa/vehicles",
        {
            "Authorization": f"Bearer {token}"
        },
        {}
    )

    return result


@app.route("/")
def home():
    return "Kia API ✅"
