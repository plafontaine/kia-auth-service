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

REGION = 2
BRAND = 1

vm = None


def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


def get_vm():
    global vm

    if vm is None:
        vm = VehicleManager(
            REGION,
            BRAND,
            "en",
            USERNAME,
            PASSWORD,
            PIN
        )

        try:
            vm.login()
            vm.get_vehicles()
            time.sleep(2)

        except AuthenticationError as e:
            print("MFA REQUIRED:", e)
            raise Exception("MFA_REQUIRED")

    else:
        try:
            vm.check_and_refresh_token()
        except:
            pass

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
                    "status": "mfa_required",
                    "message": "Check SMS/email and send code to /vehicle/auth-otp"
                }), 403
            raise e

        vehicle = current_vm.vehicles[0]

        try:
            vehicle.update()
        except Exception as e:
            print("Update failed:", e)

        return jsonify({
            "status": "ok",
            "result": {
                "status": vehicle.data
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/vehicle/<cmd>", methods=["POST"])
def vehicle_action(cmd):

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        vm = get_vm()
        vehicle = vm.vehicles[0]

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

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return "Kia API (MFA ready) ✅"
