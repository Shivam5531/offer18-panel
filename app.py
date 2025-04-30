from flask import Flask, render_template, request
import requests
from datetime import datetime

app = Flask(__name__)

API_KEY = "M22j7zWtO14vVFGP0rFe591B78o12r"  # ?? Replace with your real API key
AFFILIATE_ID = "3740"
API_URL = "https://tracking.offerborn.com/v1/api/advertiser/getperformacereport"

@app.route("/", methods=["GET", "POST"])
def dashboard():
    start_date = request.form.get("start_date", datetime.today().strftime('%Y-%m-%d'))
    end_date = request.form.get("end_date", datetime.today().strftime('%Y-%m-%d'))

    payload = {
        "api_key": API_KEY,
        "affiliate_id": AFFILIATE_ID,
        "from_date": start_date,
        "to_date": end_date
    }

    try:
        response = requests.post(API_URL, json=payload)
        data = response.json()
        if data["status"] == 200:
            report = data.get("data", [])
        else:
            report = []
    except:
        report = []

    return render_template("dashboard.html", report=report, start_date=start_date, end_date=end_date)

if __name__ == "__main__":
    app.run(debug=True)
