import os
import time
import threading
import requests
from flask import Flask, render_template_string, request, session
from uuid import uuid4

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

api_key = "421e82a7db893c3076bc2ad5a4265e62"
service = "ra1"
country = "22"
base_url = "https://sim91.com/stubs/handler_api.php"

user_data_store = {}
user_threads = {}

def safe_request(method, params, user_data):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        if method == "GET":
            print("GET", base_url, "params:", params)
            response = requests.get(base_url, params=params, headers=headers, timeout=10)
        else:
            print("POST", base_url, "params:", params)
            response = requests.post(base_url, data=params, headers=headers, timeout=10)

        print("Status Code:", response.status_code)
        print("Response Headers:", response.headers)
        print("Response Text:", response.text)

        response.raise_for_status()
        user_data["calls"] += 1
        return response.text.strip()

    except requests.exceptions.RequestException as e:
        user_data["error"] = f"Request failed: {e}"
        print("❌ Exception:", e)
        return None


def background_worker(user_id):
    user_data = user_data_store[user_id]
    for k in ["phone", "otp", "error", "id", "cancelled"]:
        user_data[k] = None
    user_data["status"] = "Starting..."

    # Balance request (GET)
    user_data["balance"] = safe_request("GET", {
        "api_key": api_key,
        "action": "getBalance"
    }, user_data)

    # Try to acquire number
    retry = 0
    while not user_data["cancelled"]:
        result = safe_request("GET", {
    "api_key": api_key,
    "action": "getNumber",
    "service": service,
    "country": country,
}, user_data)

        if result and "ACCESS_NUMBER" in result:
            parts = result.split(":")
            user_data["id"] = parts[1]
            user_data["phone"] = parts[2][-10:]
            user_data["status"] = "Number Acquired"
            break
        else:
            retry += 1
            user_data["status"] = f"Retrying to get number... (attempt {retry})"
            time.sleep(2)

    if not user_data["id"]:
        user_data["status"] = "Failed to acquire number."
        return

    # Get OTP
    start = time.time()
    timeout = 180
    while time.time() - start < timeout:
        if user_data["cancelled"]:
            return
        result = safe_request("GET", {
            "api_key": api_key,
            "action": "getStatus",
            "id": user_data["id"]
        }, user_data)
        if result and "STATUS_OK" in result:
            user_data["otp"] = result.split(":")[1].strip('%')
            user_data["status"] = "✅ OTP Received"
            return
        user_data["status"] = "⌛ Waiting for OTP..."
        time.sleep(2)

    # Cancel if timeout
    if user_data["id"]:
        cancel_activation(user_data["id"], user_data)
        user_data["status"] = "OTP Timeout - Number Cancelled"

def cancel_activation(activation_id, user_data):
    print(f"Trying to cancel activation ID: {activation_id}")
    params = {
        "api_key": api_key,
        "action": "setStatus",
        "id": activation_id,
        "status": 8
    }
    response = safe_request("GET", params, user_data)
    print("Cancel response:", response)

    if response and "ACCESS_CANCEL" in response:
        user_data["cancelled"] = True
        user_data["status"] = "❌ Number Cancelled"
        print("Cancel successful.")
        return True
    else:
        user_data["error"] = f"Cancel error: {response}"
        print("Cancel failed.")
        return False


def restart_process(user_id):
    user_data = user_data_store[user_id]
    if user_id in user_threads and user_threads[user_id].is_alive():
        user_data["cancelled"] = True
        time.sleep(1)
    user_data["cancelled"] = False
    t = threading.Thread(target=background_worker, args=(user_id,), daemon=True)
    user_threads[user_id] = t
    t.start()

@app.before_request
def setup_user():
    if "user_id" not in session:
        session["user_id"] = str(uuid4())
    user_id = session["user_id"]
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "balance": None, "status": "Starting...",
            "phone": None, "otp": None, "error": None,
            "calls": 0, "id": None, "cancelled": False
        }
        restart_process(user_id)

@app.route("/", methods=["GET"])
def index():
    user_id = session["user_id"]
    user_data = user_data_store[user_id]
    html = """
    <html>
    <head>
        <title>OTP Dashboard</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body { font-family: Arial; background: #111; color: #0f0; padding: 2rem; }
            h1, h2 { color: #0f0; }
            .box { border: 1px solid #0f0; padding: 1rem; margin: 1rem 0; }
            button {
                background: red; color: white; padding: 0.5rem 1rem;
                font-size: 16px; border: none; cursor: pointer; margin-top: 1rem;
            }
            .green-button {
                background: green;
                margin-left: 1rem;
            }
        </style>
    </head>
    <body>
        <h1>🔐 SHIVAM </h1>
        <div class="box">📶 API Calls: {{calls}}</div>
        <div class="box">💰 Balance: {{balance}}</div>
        <div class="box">📱 Number: {{phone}}</div>
        <div class="box">⌛ Status: {{status}}</div>
        <div class="box">🔐 OTP: <b>{{otp}}</b></div>
        {% if error %}
        <div class="box" style="color: red;">❌ Error: {{error}}</div>
        {% endif %}
        <form method="POST" action="/cancel" style="display:inline;">
            {% if id and not cancelled %}
            <button type="submit">❌ Cancel Number</button>
            {% endif %}
        </form>
        <form method="POST" action="/restart" style="display:inline;">
            {% if cancelled or otp %}
            <button type="submit" class="green-button">🔁 Buy Next Number</button>
            {% endif %}
        </form>
    </body>
    </html>
    """
    return render_template_string(html, **user_data)

@app.route("/cancel", methods=["POST"])
def cancel():
    user_id = session["user_id"]
    user_data = user_data_store[user_id]
    if user_data.get("id") and not user_data["cancelled"]:
        cancel_activation(user_data["id"], user_data)
    return ("", 204)

@app.route("/restart", methods=["POST"])
def restart():
    user_id = session["user_id"]
    restart_process(user_id)
    return ("", 204)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
