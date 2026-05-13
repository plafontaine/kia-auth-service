import os
import time
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

# ✅ TA BONNE CONFIG (NE PAS CHANGER)
REGION = 4
BRAND = 2

vm = None

# ===============================
# SESSION (persistante comme HA)
# ===============================

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
        vm.login()
        vm.get_account_vehicles()

    else:
        # ✅ refresh token propre
        vm.check_and_refresh_token()

    return vm


# ===============================
# SECURITY
# ===============================

def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


# ===============================
# GET VEHICLES (équivalent Hubitat)
# ===============================

@app.route("/vehicle/list", methods=["GET"])
def vehicle_list():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        vm = get_vm()

        vehicles = []

        for v in vm.vehicles:
            vehicles.append({
                "vehicleId": v.id,
                "vin": v.VIN,
                "modelName": getattr(v, "model_name", None),
                "modelYear": getattr(v, "model_year", None),
                "trim": getattr(v, "trim", None),
                "fuelKindCode": getattr(v, "fuel_type", None),
                "exteriorColor": getattr(v, "exterior_color", None),
                "nickName": getattr(v, "name", None)
            })

        return jsonify({
            "status": "ok",
            "result": {
                "vehicles": vehicles
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===============================
# STATUS
# ===============================

@app.route("/vehicle/status", methods=["GET"])
def vehicle_status():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        refresh = request.args.get("refresh", "false") == "true"

        vm = get_vm()
        vehicle = vm.vehicles[0]

        # ✅ BON CALL
        if refresh:
            vehicle.force_refresh()
        else:
            vehicle.update()

        return jsonify({
            "status": "ok",
            "result": {
                "status": vehicle.data
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===============================
# COMMANDES
# ===============================

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

        elif cmd == "start":
            vm.start_climate(vehicle.id)

        elif cmd == "stop":
            vm.stop_climate(vehicle.id)

        else:
            return jsonify({"error": "invalid command"}), 400

        return jsonify({
            "status": "ok",
            "action": cmd
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===============================
# HEALTH
# ===============================

@app.route("/")
def home():
    return "Kia API HA-style ✅"
