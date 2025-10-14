from flask import Flask, render_template, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid
import os

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------- CONFIG ----------
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SERVICE_ACCOUNT_FILE = "/etc/secrets/credentials.json"
if not os.path.exists(SERVICE_ACCOUNT_FILE):
    raise Exception("Google credentials secret file not found.")

# ---------- PRICE + CONVERSION ----------
VND_TO_USD_RATE = 25000.0  # 1 USD = 25,000 VND
PER_ITEM_COST_VND = 5000
PER_ITEM_COST_USD = 0.20

# ---------- GOOGLE SHEET ----------
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1HP_5ikAvDYe98PoaNjQdLDG-10BI_PoH6kxqrrhqOKg/edit?usp=sharing"
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1

HEADERS = [
    "id","customer_name","customer_phone","dateTime","description",
    "quantity","costVND","costUSD","note","status",
    "waiter_name","waiter_phone","accepterId",
    "createdAt","acceptedAt","completedAt","rating","feedback"
]

def ensure_headers():
    first = sheet.row_values(1)
    if first != HEADERS:
        try:
            sheet.delete_rows(1)
        except Exception:
            pass
        sheet.insert_row(HEADERS, 1)

ensure_headers()

def all_jobs():
    return sheet.get_all_records()

def find_row(job_id):
    data = all_jobs()
    for i, row in enumerate(data, start=2):
        if str(row.get("id")) == str(job_id):
            return i
    return None

# ---------- ROUTES ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    jobs = all_jobs()
    for job in jobs:
        if job.get("status") == "AVAILABLE":
            job["customer_name"] = "Hidden until accepted"
            job["customer_phone"] = "Hidden until accepted"
    return jsonify(jobs), 200

@app.route('/api/submit', methods=['POST'])
def submit_job():
    data = request.get_json() or {}
    req = ["customer_name","customer_phone","dateTime","description"]
    if not all(field in data and data[field] for field in req):
        return jsonify({"error":"Missing required fields"}),400

    try:
        quantity = int(data.get("quantity",1))
        if quantity < 1: raise ValueError
    except:
        return jsonify({"error":"Invalid quantity"}),400

    cost_vnd = PER_ITEM_COST_VND * quantity
    cost_usd = format(cost_vnd / VND_TO_USD_RATE, ".2f")
    job_id = str(uuid.uuid4())
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = [
        job_id, data["customer_name"], data["customer_phone"],
        data["dateTime"], data["description"], quantity,
        cost_vnd, cost_usd, data.get("note",""),
        "AVAILABLE", "", "", "", created, "", "", "", ""
    ]
    sheet.append_row(new_row, value_input_option='USER_ENTERED')
    return jsonify({"message":"Job added!", "id":job_id}),200

@app.route('/api/accept', methods=['POST'])
def accept_job():
    data = request.get_json() or {}
    job_id = data.get("id")
    name = data.get("waiter_name")
    phone = data.get("waiter_phone")
    if not all([job_id,name,phone]):
        return jsonify({"error":"Missing fields"}),400
    row = find_row(job_id)
    if not row: return jsonify({"error":"Job not found"}),404

    jobs = all_jobs()
    job = jobs[row-2]
    if job["status"] != "AVAILABLE":
        return jsonify({"error":"Job not available"}),400

    accepted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.update_acell(f"I{row}","IN_PROGRESS")
    sheet.update_acell(f"J{row}",name)
    sheet.update_acell(f"K{row}",phone)
    sheet.update_acell(f"L{row}",str(uuid.uuid4()))
    sheet.update_acell(f"N{row}",accepted)
    return jsonify({"message":"Job accepted!"}),200

@app.route('/api/complete', methods=['POST'])
def complete_job():
    data = request.get_json() or {}
    job_id = data.get("id")
    row = find_row(job_id)
    if not row: return jsonify({"error":"Job not found"}),404
    sheet.update_acell(f"I{row}","WAITING_FEEDBACK")
    sheet.update_acell(f"O{row}",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return jsonify({"message":"Job completed, waiting for feedback."}),200

@app.route('/api/feedback', methods=['POST'])
def feedback_job():
    data = request.get_json() or {}
    job_id = data.get("id")
    rating = data.get("rating")
    feedback = data.get("feedback","")
    row = find_row(job_id)
    if not row: return jsonify({"error":"Job not found"}),404

    try:
        if rating and 1 <= int(rating) <= 5:
            sheet.update_acell(f"P{row}",str(rating))
    except: pass
    if feedback:
        sheet.update_acell(f"Q{row}",feedback)
    sheet.update_acell(f"I{row}","COMPLETED")
    return jsonify({"message":"Feedback submitted. Thank you!"}),200

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
