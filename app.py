import json
import os
import time
from flask import Flask, jsonify, request

from hyundai_kia_connect_api import VehicleManager
from hyundai_kia_connect_api.const import (
    BRAND_KIA,
    REGION_CANADA,
)

# 🔐 Clé API Render (variable d’environnement)
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")

TOKENS_FILE = "tokens.json"

app = Flask(__name__)

# -------------------------------
# Sécurité : clé API Render
# -------------------------------

def check_api_key():
    client_key = request.headers.get("X-API-Key")
    if not RENDER_API_KEY or client_key != RENDER_API_KEY:
        return False
    return True

# -------------------------------
# Utilitaires tokens
# -------------------------------

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return None

def save_tokens(data):
    with open(TOKENS_FILE, "w") as f:
        json.dump(data, f)

def tokens_valid(tokens):
    if not tokens:
        return False
    return tokens.get("expires_at", 0) > time.time() + 60

# -------------------------------
# Initialisation Kia
# -------------------------------

def get_vehicle_manager():
    return VehicleManager(
        region=REGION_CANADA,
        brand=BRAND_KIA,
        username=os.environ.get("KIA_USERNAME"),
        password=os.environ.get("KIA_PASSWORD"),
        pin=os.environ.get("KIA_PIN", ""),
    )

# -------------------------------
# Routes HTTP
# -------------------------------

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

    # 🔐 Sécurité Render
    if not check_api_key():
        return jsonify({"status": "unauthorized"}), 401

    tokens = load_tokens()

    # ✅ Token valide
    if tokens_valid(tokens):
        return jsonify({
            "status": "ok",
            "access_token": tokens["access_token"],
            "expires_at": tokens["expires_at"]
        })

    # 🔄 Tentative de refresh automatique
    vm = get_vehicle_manager()
    try:
        vm.check_and_refresh_token()
        new_tokens = {
            "access_token": vm.token.access_token,
            "refresh_token": vm.token.refresh_token,
            "expires_at": time.time() + vm.token.expires_in,
        }
        save_tokens(new_tokens)

        return jsonify({
            "status": "ok",
            **new_tokens
        })

    # 🚨 MFA requis
    except Exception as e:
        return jsonify({
            "status": "mfa_required",
            "detail": str(e)
        }), 401

@app.route("/mfa", methods=["POST"])
def mfa():

    # 🔐 Sécurité Render
    if not check_api_key():
        return jsonify({"status": "unauthorized"}), 401

    data = request.json or {}
    otp = data.get("otp")

    if not otp:
        return jsonify({"status": "otp_required"}), 400

    vm = get_vehicle_manager()

    try:
        vm.login()
        vm.verify_otp(otp)

        new_tokens = {
            "access_token": vm.token.access_token,
            "refresh_token": vm.token.refresh_token,
            "expires_at": time.time() + vm.token.expires_in,
        }
        save_tokens(new_tokens)

        return jsonify({"status": "ok"})

    except Exception as e:
        return jsonify({
            "status": "error",
            "detail": str(e)
        }), 500
