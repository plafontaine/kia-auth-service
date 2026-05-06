from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "Kia Auth Service is running"

@app.route("/status")
def status():
    return jsonify({"status": "ok"})
