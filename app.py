import os
import time
import traceback
from flask import Flask, jsonify, request

# Importation obligatoire des classes de mappage officielles
from hyundai_kia_connect_api import VehicleManager
from hyundai_kia_connect_api.exceptions import AuthenticationError

app = Flask(__name__)

# ===============================
# CONFIGURATION
# ===============================
API_KEY = os.environ.get("RENDER_API_KEY")
USERNAME = os.environ.get("KIA_USER")
PASSWORD = os.environ.get("KIA_PASS")
PIN = os.environ.get("KIA_PIN")

# On initialise à None pour laisser get_vm() configurer proprement la session
vm = None

def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY

def get_vm():
    global vm

    if vm is None:
        # ✅ LA CORRECTION CRITIQUE : Utiliser les index natifs pour le Canada (CA=2, KIA=1)
        # en laissant l'objet se valider de manière native.
        vm = VehicleManager(
            region=2,          # Canada / Amérique du Nord
            brand=1,           # Kia
            username=USERNAME,
            password=PASSWORD,
            pin=PIN,
            language="en"
        )

        try:
            vm.login()
            vm.get_vehicles()
            time.sleep(2)

        except AuthenticationError as e:
            print("MFA REQUIRED DETECTED:", e)
            raise Exception("MFA_REQUIRED")
        except Exception as e:
            print("CRITICAL LOGIN ERROR:", e)
            raise e
    else:
        try:
            vm.check_and_refresh_token()
        except Exception as e:
            print("Token refresh failed, keeping active session:", e)

    return vm

# ===============================
# SÉCURITÉ MFA / OTP
# ===============================
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
        if vm is None:
            vm = VehicleManager(region=2, brand=1, username=USERNAME, password=PASSWORD, pin=PIN, language="en")
        
        vm.validate_mfa(otp_code)
        vm.get_vehicles()

        return jsonify({
            "status": "ok",
            "message": "MFA validated ✅"
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
        try:
            current_vm = get_vm()
        except Exception as e:
            if "MFA_REQUIRED" in str(e):
                return jsonify({
                    "status": "mfa_required",
                    "message": "Kia exige la double authentification. Entrez le code recu sur /vehicle/auth-otp."
                }), 403
            raise e

        # Extraction sécurisée des véhicules
        vehicles = current_vm.vehicles
        if not vehicles:
            return jsonify({"error": "No vehicle found on account"}), 404

        # Extraction de la clé textuelle (VIN ou ID unique)
        if isinstance(vehicles, dict):
            vehicle_id = list(vehicles.keys())[0]
            vehicle = vehicles[vehicle_id]
        else:
            vehicle = vehicles[0]

        try:
            # Demande de rafraîchissement au serveur cloud de Kia
            current_vm.update_vehicle(vehicle.id)
        except Exception as e:
            print("Cloud refresh failed, serving local state:", e)

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

# ===============================
# ACTIONS (LOCK / UNLOCK)
# ===============================
@app.route("/vehicle/<cmd>", methods=["POST"])
def vehicle_action(cmd):
    if not check_api_key():
        return jsonify({"error": "unauthorized"}), 401

    try:
        current_vm = get_vm()
        vehicles = current_vm.vehicles
        
        if not vehicles:
            return jsonify({"error": "No vehicle found"}), 404

        if isinstance(vehicles, dict):
            vehicle_id = list(vehicles.keys())[0]
        else:
            vehicle = vehicles[0]
            vehicle_id = vehicle.id

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

@app.route("/")
def home():
    return "Kia API (Canada Engine 2.0) ✅"
