import os
import time
import hyundai_kia_connect_api
from flask import Flask, jsonify, request
from hyundai_kia_connect_api import VehicleManager

app = Flask(__name__)

# ===============================
# CONFIG
# ===============================

API_KEY = os.environ.get("RENDER_API_KEY")
USERNAME = os.environ.get("KIA_USER")
PASSWORD = os.environ.get("KIA_PASS")
PIN = os.environ.get("KIA_PIN")

# ✅ CONFIG CORRIGÉE
REGION = 2
BRAND = 1

vm = None

# ===============================
# SESSION
# ===============================

def get_vm():
    global vm
    print("Module:", dir(hyundai_kia_connect_api))
    if vm is None:
        vm = VehicleManager(
            REGION,
            BRAND,
            "en",
            USERNAME,
            PASSWORD,
            PIN
        )

        vm.login()

        # ✅ CORRECTION ICI
        vm.get_vehicles()

        time.sleep(2)

    else:
        vm.check_and_refresh_token()

    return vm


def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


# ===============================
# STATUS
# ===============================

@app.route("/vehicle/status", methods=["GET"])
def vehicle_status():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        vm = get_vm()

        # ✅ dict access (CRUCIAL)
        vehicle_keys = list(vm.vehicles.keys())
        if not vehicle_keys:
            return jsonify({"error": "No vehicle found"}), 404

        vehicle_id = vehicle_keys[0]

        # ✅ SAFE CALL
        try:
            vm.update_vehicle(vehicle_id)
        except Exception as e:
            print("Update failed:", e)

        vehicle = vm.vehicles[vehicle_id]

        return jsonify({
            "status": "ok",
            "result": {
                "status": vehicle.data
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===============================
# ACTIONS
# ===============================

@app.route("/vehicle/<cmd>", methods=["POST"])
def vehicle_action(cmd):

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        vm = get_vm()

        vehicle_keys = list(vm.vehicles.keys())
        vehicle_id = vehicle_keys[0]

        if cmd == "lock":
            vm.lock(vehicle_id)

        elif cmd == "unlock":
            vm.unlock(vehicle_id)

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
    return "Kia API CA-compatible ✅"
