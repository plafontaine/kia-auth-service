import json
import os
import time
from flask import Flask, jsonify, request

from hyundai_kia_connect_api import VehicleManager

# ===============================
# Configuration
# ===============================

RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
TOKENS_FILE = "tokens.json"

app = Flask(__name__)

# ===============================
# Sécurité : API key Render
# ===============================

def check_api_key():
    client_key = request.headers.get("X-API-Key")
    return bool(RENDER_API_KEY and client_key == RENDER_API_KEY)

# ===============================
# Utilitaires tokens
# ===============================

def load_tokens():
    access = os.environ.get("KIA_ACCESS_TOKEN")
    refresh = os.environ.get("KIA_REFRESH_TOKEN")

    if access or refresh:
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": time.time() + 300  # court, juste pour amorcer
        }

    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)

    return None


def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f)

def tokens_valid(tokens):
    return bool(tokens and tokens.get("expires_at", 0) > time.time() + 60)

# ===============================
# Initialisation VehicleManager
# (VERSION LEGACY COMPATIBLE)
# ===============================

def get_vehicle_manager():
    return VehicleManager(
        4,                               # ✅ region = CANADA
        2,                               # ✅ brand = KIA (ENUM, PAS "KIA")
        "en",                            # ✅ language
        os.environ.get("KIA_USER"),      # ✅ username
        os.environ.get("KIA_PASS"),      # ✅ password
        os.environ.get("KIA_PIN", "")    # ✅ pin
    )

# ===============================
# Routes
# ===============================

@app.route("/")
def home():
    return "Kia Auth Service is running"

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "tokens_present": load_tokens() is not None
    })

@app.route("/status")
def status():
    tokens = load_tokens()
    return jsonify({
        "tokens_present": tokens is not None,
        "tokens_valid": tokens_valid(tokens)
    })

@app.route("/token", methods=["GET"])
def get_token():

    if not check_api_key():
        return jsonify({"status": "unauthorized"}), 401

    tokens = load_tokens()

    # ✅ Token encore valide
    if tokens_valid(tokens):
        return jsonify({"status": "ok", **tokens})

    # 🔄 Nouvelle session Kia
    try:
       # print("DEBUG entering /token")
        vm = get_vehicle_manager()
       # print("DEBUG VehicleManager created")
        new_tokens = {
            "access_token": vm.token.access_token,
            "refresh_token": vm.token.refresh_token,
            "expires_at": time.time() + vm.token.expires_in,
        }
        save_tokens(new_tokens)

        return jsonify({"status": "ok", **new_tokens})

    except Exception as e:
        return jsonify({
            "status": "error",
            "detail": str(e)
        }), 500

# ===============
# refresh 
# ============

@app.route("/vehicle/status", methods=["GET"])
def vehicle_status():

    if not check_api_key():
        return jsonify({"status": "unauthorized"}), 401

    try:
        refresh = request.args.get("refresh", "false").lower() == "true"
        debug = request.args.get("debug", "false").lower() == "true"

        vm = get_vehicle_manager()

        # ⚡ appel Kia (version SAFE)
        vm.update_all_vehicles_with_cached_state()

        if refresh:
            vm.force_refresh_all_vehicles()

        vehicle = vm.vehicles[0]
        status = vehicle.data

        response = {
            "status": "ok",
            "result": {
                "status": status,
                "vehicle": {
                    "subscriptionEndDate": getattr(vehicle, "subscription_end_date", None),
                    "fuelKindCode": getattr(vehicle, "fuel_kind_code", None)
                }
            }
        }

        if debug:
            response["raw"] = status

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "status": "error",
            "detail": str(e)
        }), 500


# ===============================
# MFA (non supporté proprement
# dans cette version legacy)
# ===============================

@app.route("/mfa", methods=["POST"])
def mfa():
    return jsonify({
        "status": "not_supported",
        "detail": "MFA is automatically handled by Kia API in this version"
    }), 400

# ===============================
# Lancement local (optionnel)
# ===============================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
