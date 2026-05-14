import os
import time
from flask import Flask, jsonify, request
from hyundai_kia_connect_api import VehicleManager
from hyundai_kia_connect_api.exceptions import AuthenticationError

app = Flask(__name__)

API_KEY = os.environ.get("RENDER_API_KEY")
USERNAME = os.environ.get("KIA_USER")
PASSWORD = os.environ.get("KIA_PASS")
PIN = os.environ.get("KIA_PIN")

REGION = "CA"
BRAND = "KIA"

vm = None

def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


def get_vm():
    global vm

    if vm is None:
        vm = VehicleManager(
            region=REGION,
            brand=BRAND,
            username=USERNAME,
            password=PASSWORD,
            pin=PIN,
            language="en"
        )

        try:
            vm.login()
            vm.get_account_vehicles()

        except AuthenticationError:
            raise Exception("MFA_REQUIRED")

    else:
        vm.check_and_refresh_token()

    return vm


@app.route("/vehicle/auth-otp", methods=["POST"])
def auth_otp():
    global vm

    code = request.json.get("code")

    try:
        vm.validate_mfa(code)
        vm.get_account_vehicles()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/vehicle/status", methods=["GET"])
def vehicle_status():
    try:
        vm = get_vm()

    except Exception as e:
        if "MFA_REQUIRED" in str(e):
            return jsonify({"status": "mfa_required"}), 403
        raise

    vehicle = list(vm.vehicles.values())[0]

    vm.update_vehicle(vehicle.id)

    return jsonify({
        "status": "ok",
        "result": vehicle.data
    })


@app.route("/vehicle/<cmd>", methods=["POST"])
def vehicle_action(cmd):
    vm = get_vm()
    vehicle = list(vm.vehicles.values())[0]

    if cmd == "lock":
        vm.lock(vehicle.id)
    elif cmd == "unlock":
        vm.unlock(vehicle.id)
    else:
        return jsonify({"error": "invalid command"}), 400

    return jsonify({
        "status": "ok",
        "action": cmd
    })


@app.route("/")
def home():
    return "Kia API V2 ✅"
