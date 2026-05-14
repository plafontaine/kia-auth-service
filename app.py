import os
import time
from flask import Flask, jsonify, request
from hyundai_kia_connect_api import VehicleManager

app = Flask(__name__)

API_KEY = os.environ.get("RENDER_API_KEY")
USERNAME = os.environ.get("KIA_USER")
PASSWORD = os.environ.get("KIA_PASS")
PIN = os.environ.get("KIA_PIN")

REGION = 4
BRAND = 2

vm = None


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

        # ✅ IMPORTANT 1 : charger les véhicules
        vm.get_account_vehicles()

        # ✅ IMPORTANT 2 : hydrater (TRÈS IMPORTANT)
        for v in vm.vehicles:
            try:
                v.update()
            except Exception as e:
                print("Initial hydrate fail:", e)

        # ✅ IMPORTANT 3 : attente (HA fait ça implicitement)
        time.sleep(2)

    else:
        vm.check_and_refresh_token()

    return vm


def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


# ===============================
# VEHICLES
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
                "modelName": getattr(v, "model_name", None)
            })

        return jsonify({
            "status": "ok",
            "result": {"vehicles": vehicles}
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
        vm = get_vm()
        vehicle = vm.vehicles[0]

        # ✅ HA STYLE LOOP (CRUCIAL)
        success = False

        for i in range(3):
            try:
                vehicle.update()
                success = True
                break
            except Exception as e:
                print(f"Retry {i+1} failed:", e)
                time.sleep(2)

        if not success:
            return jsonify({
                "error": "update failed after retries"
            }), 500

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
    return "Kia API HA-compatible ✅"
