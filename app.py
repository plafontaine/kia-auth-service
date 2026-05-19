import requests
import os
import time
import traceback
import logging
logging.basicConfig(level=logging.DEBUG)
from flask import Flask, jsonify, request
from hyundai_kia_connect_api import VehicleManager
from hyundai_kia_connect_api.exceptions import AuthenticationError


original_request = requests.Session.request

captured_request = {}

def hooked_request(self, method, url, **kwargs):
    global captured_request

    try:
        headers = kwargs.get("headers", {})

        # ✅ rendre sérialisable
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

        print("🔥 INTERCEPTED REQUEST 🔥")
        print(captured_request)

    except Exception as hook_error:
        print("HOOK ERROR:", hook_error)

    return original_request(self, method, url, **kwargs)


requests.Session.request = hooked_request

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
            vm.get_vehicles()
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
        return "LOGIN OK"

    except Exception as e:
        return str(e)
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

@app.route("/bridge/capture-vehicles", methods=["GET"])
def capture_vehicles():

    global captured_request

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        vm = get_vm()

        # reset avant capture
        captured_request = {}

        # 🔥 trigger appel Kia
        vm.get_vehicles()

        return jsonify({
            "status": "ok",
            "captured": captured_request
        })

    except Exception as e:
        import traceback
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


@app.route("/")
def home():
    return "Kia API ✅"
