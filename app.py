import os
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

# ✅ CORRECT pour ton environnement
REGION = 4
BRAND = 2

vm = None

# ===============================
# SESSION
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
        vm.check_and_refresh_token()

    return vm


# ===============================
# SECURITY
# ===============================

def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


# ===============================
# GET VEHICLES
# ===============================

@app.route("/vehicle/list", methods=["GET"])
def vehicle_list():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        current_vm = get_vm()

        vehicles = []

        for v in current_vm.vehicles:
            vehicles.append({
                "vehicleId": v.id,
                "vin": v.VIN,
                "modelName": getattr(v, "model_name", None),
                "modelYear": getattr(v, "model_year", None),
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
# STATUS (FIX CRITIQUE ✅)
# ===============================

@app.route("/vehicle/status", methods=["GET"])
def vehicle_status():

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        current_vm = get_vm()

        # ✅ EXTRACTION CORRECTE (clé du bug)
        vehicle = current_vm.vehicles[0]  # ✅ car ta version est LIST

        # ✅ appeler une seule fois
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


# ===============================
# COMMANDES
# ===============================

@app.route("/vehicle/<cmd>", methods=["POST"])
def vehicle_action(cmd):

    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        current_vm = get_vm()
        vehicle = current_vm.vehicles[0]

        if cmd == "lock":
            current_vm.lock(vehicle.id)

        elif cmd == "unlock":
            current_vm.unlock(vehicle.id)

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
    return "Kia API running ✅"
