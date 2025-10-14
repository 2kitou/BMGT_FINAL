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

# Path to service account JSON in your environment
SERVICE_ACCOUNT_FILE = "/etc/secrets/credentials.json"
if not os.path.exists(SERVICE_ACCOUNT_FILE):
    raise Exception("Google credentials secret file not found.")

# VND -> USD conversion rate (adjust if you want a different rate)
VND_TO_USD_RATE = 24000.0  # <-- change this value to match current FX if needed

# Per-item cost rules (VND)
PER_ITEM_MIN = 5000
PER_ITEM_MAX = 10000

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# Your Google Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1HP_5ikAvDYe98PoaNjQdLDG-10BI_PoH6kxqrrhqOKg/edit?usp=sharing"

client = gspread.authorize(creds)
spreadsheet = client.open_by_url(SHEET_URL)
worksheet = spreadsheet.sheet1

# ---------- SHEET HEADERS (updated to include quantity, rating, feedback) ----------
SHEET_HEADERS = [
    "id", "customer_name", "customer_phone", "dateTime", "description",
    "quantity", "costVND", "costUSD", "note", "status",
    "waiter_name", "waiter_phone", "accepterId",
    "createdAt", "acceptedAt", "completedAt", "rating", "feedback"
]

def ensure_headers():
    first_row = worksheet.row_values(1)
    if first_row != SHEET_HEADERS:
        # Replace header row with our canonical headers
        try:
            worksheet.delete_rows(1)
        except Exception:
            pass
        worksheet.insert_row(SHEET_HEADERS, 1)

ensure_headers()

# ---------- HELPERS ----------
def get_all_jobs():
    return worksheet.get_all_records()

def find_row_by_id(job_id):
    records = worksheet.get_all_records()
    for i, row in enumerate(records, start=2):  # skip header
        if str(row.get("id")) == str(job_id):
            return i
    return None

# ---------- ROUTES ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Return all jobs (no mutation)."""
    records = get_all_jobs()
    # Hide sensitive info for AVAILABLE jobs
    for job in records:
        if job.get('status') == 'AVAILABLE':
            job['customer_name'] = 'Hidden until accepted'
            job['customer_phone'] = 'Hidden until accepted'
    return jsonify(records), 200

@app.route('/api/submit', methods=['POST'])
def submit_job():
    """Create a new job; validate quantity & cost rules."""
    data = request.get_json() or {}
    required_fields = ["customer_name", "customer_phone", "dateTime", "description", "costVND"]

    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Quantity (default 1)
    try:
        quantity = int(data.get("quantity", 1))
        if quantity < 1:
            return jsonify({"error": "Quantity must be >= 1"}), 400
    except Exception:
        return jsonify({"error": "Invalid quantity"}), 400

    # Total cost
    try:
        cost_vnd = int(data["costVND"])
    except Exception:
        return jsonify({"error": "Invalid costVND"}), 400

    # Validate total cost against per-item min/max
    min_total = PER_ITEM_MIN * quantity
    max_total = PER_ITEM_MAX * quantity
    if cost_vnd < min_total or cost_vnd > max_total:
        return jsonify({
            "error": f"Total cost must be between {min_total:,} VND and {max_total:,} VND for quantity {quantity}."
        }), 400

    # Convert to USD using rate
    cost_usd = round(cost_vnd / VND_TO_USD_RATE, 2) if VND_TO_USD_RATE else 0.0

    job_id = str(uuid.uuid4())
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = [
        job_id,
        data.get("customer_name", ""),
        data.get("customer_phone", ""),
        data.get("dateTime", ""),
        data.get("description", ""),
        quantity,
        cost_vnd,
        cost_usd,
        data.get("note", ""),
        "AVAILABLE",
        "", "", "", created_at, "", "", "", ""
    ]

    worksheet.append_row(new_row, value_input_option='USER_ENTERED')
    return jsonify({"message": "Job added successfully!", "id": job_id}), 200

@app.route('/api/accept', methods=['POST'])
def accept_job():
    try:
        data = request.get_json() or {}
        job_id = data.get("id")
        waiter_name = data.get("waiter_name")
        waiter_phone = data.get("waiter_phone")

        if not all([job_id, waiter_name, waiter_phone]):
            return jsonify({"error": "Missing required fields"}), 400

        row_number = find_row_by_id(job_id)
        if not row_number:
            return jsonify({"error": "Job not found"}), 404

        records = worksheet.get_all_records()
        job = records[row_number - 2]

        if job.get("status") != "AVAILABLE":
            return jsonify({"error": "Job is not available"}), 400

        accepted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Columns based on our SHEET_HEADERS:
        # status -> col 9 (index 9 in SHEET_HEADERS is 'status' => column I)
        # waiter_name -> column J, waiter_phone -> K, accepterId -> L, acceptedAt -> N
        worksheet.update_acell(f"I{row_number}", "IN_PROGRESS")
        worksheet.update_acell(f"J{row_number}", waiter_name)
        worksheet.update_acell(f"K{row_number}", waiter_phone)
        worksheet.update_acell(f"L{row_number}", str(uuid.uuid4()))
        worksheet.update_acell(f"N{row_number}", accepted_time)

        return jsonify({"message": "Job accepted successfully!"}), 200

    except Exception as e:
        print("Error accepting job:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/complete', methods=['POST'])
def complete_job():
    """Mark job completed and optionally persist rating/feedback (rating optional)."""
    try:
        data = request.get_json() or {}
        job_id = data.get("id")
        rating = data.get("rating")   # optional
        feedback = data.get("feedback", "")

        row_number = find_row_by_id(job_id)
        if not row_number:
            return jsonify({"error": "Job not found"}), 404

        completed_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        worksheet.update_acell(f"I{row_number}", "COMPLETED")   # status
        worksheet.update_acell(f"O{row_number}", completed_time)  # completedAt

        if rating is not None:
            try:
                r = int(rating)
                if 1 <= r <= 5:
                    worksheet.update_acell(f"P{row_number}", str(r))
            except Exception:
                pass

        if feedback:
            worksheet.update_acell(f"Q{row_number}", str(feedback))

        return jsonify({"message": "Job marked as completed!"}), 200

    except Exception as e:
        print("Error completing job:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
