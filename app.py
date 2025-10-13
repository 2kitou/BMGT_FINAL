from flask import Flask, render_template, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid
import os

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------- CONFIG ----------
SERVICE_ACCOUNT_FILE = os.path.join('credentials', 'credentials.json')
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Your Google Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1HP_5ikAvDYe98PoaNjQdLDG-10BI_PoH6kxqrrhqOKg/edit?usp=sharing"

# ---------- CONNECT TO GOOGLE SHEET ----------
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_url(SHEET_URL)
worksheet = spreadsheet.sheet1

# ---------- HEADERS ----------
SHEET_HEADERS = [
    "id", "customer_name", "customer_phone", "dateTime", "description",
    "costVND", "costUSD", "note", "status",
    "waiter_name", "waiter_phone", "accepterId",
    "createdAt", "acceptedAt", "completedAt"
]

def ensure_headers():
    first_row = worksheet.row_values(1)
    if first_row != SHEET_HEADERS:
        worksheet.delete_rows(1)
        worksheet.insert_row(SHEET_HEADERS, 1)

ensure_headers()

# ---------- HELPERS ----------
def get_all_jobs():
    """Return all job records from the sheet."""
    return worksheet.get_all_records()

def find_row_by_id(job_id):
    """Find the row number (2-based) for a given job ID."""
    records = worksheet.get_all_records()
    for i, row in enumerate(records, start=2):  # skip header
        if str(row["id"]) == str(job_id):
            return i
    return None

# ---------- ROUTES ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Return all jobs (for both available & in-progress)."""
    return jsonify(get_all_jobs())

@app.route('/api/submit', methods=['POST'])
def submit_job():
    """Create a new job (customer posting)."""
    data = request.get_json()
    required_fields = ["customer_name", "customer_phone", "dateTime", "description", "costVND"]

    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        cost_vnd = int(data["costVND"])
        if not (5000 <= cost_vnd <= 10000):
            return jsonify({"error": "Cost must be between 5,000–10,000 VND"}), 400
    except ValueError:
        return jsonify({"error": "Invalid cost"}), 400

    job_id = str(uuid.uuid4())
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cost_usd = round(cost_vnd / 25000, 2)

    new_row = [
        job_id, data["customer_name"], data["customer_phone"], data["dateTime"],
        data["description"], cost_vnd, cost_usd, data.get("note", ""), "AVAILABLE",
        "", "", "", created_at, "", ""
    ]

    worksheet.append_row(new_row)
    return jsonify({"message": "Job added successfully!"}), 200


@app.route('/api/accept', methods=['POST'])
def accept_job():
    """Waiter accepts a job."""
    try:
        data = request.get_json()
        job_id = data.get("id")
        waiter_name = data.get("waiter_name")
        waiter_phone = data.get("waiter_phone")

        if not all([job_id, waiter_name, waiter_phone]):
            return jsonify({"error": "Missing required fields"}), 400

        row_number = find_row_by_id(job_id)
        if not row_number:
            return jsonify({"error": "Job not found"}), 404

        records = worksheet.get_all_records()
        job = records[row_number - 2]  # adjust for header

        if job["status"] != "AVAILABLE":
            return jsonify({"error": "Job is not available"}), 400

        accepted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ✅ FIX: use update_acell() to avoid APIError
        worksheet.update_acell(f"I{row_number}", "IN_PROGRESS")      # status
        worksheet.update_acell(f"J{row_number}", waiter_name)        # waiter_name
        worksheet.update_acell(f"K{row_number}", waiter_phone)       # waiter_phone
        worksheet.update_acell(f"L{row_number}", str(uuid.uuid4()))  # accepterId
        worksheet.update_acell(f"N{row_number}", accepted_time)      # acceptedAt

        return jsonify({"message": "Job accepted successfully!"}), 200

    except Exception as e:
        print("Error accepting job:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/api/complete', methods=['POST'])
def complete_job():
    """Mark job as completed."""
    try:
        data = request.get_json()
        job_id = data.get("id")
        row_number = find_row_by_id(job_id)
        if not row_number:
            return jsonify({"error": "Job not found"}), 404

        completed_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.update_acell(f"I{row_number}", "COMPLETED")   # status
        worksheet.update_acell(f"O{row_number}", completed_time)  # completedAt

        return jsonify({"message": "Job marked as completed!"}), 200

    except Exception as e:
        print("Error completing job:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
