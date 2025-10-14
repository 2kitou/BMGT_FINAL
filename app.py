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

# Path to service account JSON
SERVICE_ACCOUNT_FILE = "/etc/secrets/credentials.json"
if not os.path.exists(SERVICE_ACCOUNT_FILE):
    raise Exception("Google credentials secret file not found.")

# ---------- PRICE + CONVERSION ----------
# Rule: 1 quantity = 5000 VND = 0.20 USD
VND_TO_USD_RATE = 25000.0  # 1 USD = 25,000 VND
PER_ITEM_COST_VND = 5000
PER_ITEM_COST_USD = 0.20

# ---------- GOOGLE SHEET SETUP ----------
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1HP_5ikAvDYe98PoaNjQdLDG-10BI_PoH6kxqrrhqOKg/edit?usp=sharing"
client = gspread.authorize(creds)
spreadsheet = client.open_by_url(SHEET_URL)
worksheet = spreadsheet.sheet1

# ---------- SHEET HEADERS ----------
SHEET_HEADERS = [
    "id", "customer_name", "customer_phone", "dateTime", "description",
    "quantity", "costVND", "costUSD", "note", "status",
    "waiter_name", "waiter_phone", "accepterId",
    "createdAt", "acceptedAt", "completedAt", "rating", "feedback"
]


def ensure_headers():
    first_row = worksheet.row_values(1)
    if first_row != SHEET_HEADERS:
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
    records = get_all_jobs()
    for job in records:
        status = job.get('status')

        # hide customer info only when job is still available
        if status == 'AVAILABLE':
            job['customer_name'] = 'Hidden until accepted'
            job['customer_phone'] = 'Hidden until accepted'
            job['waiter_name'] = ''
            job['waiter_phone'] = ''
        elif status == 'IN_PROGRESS':
            # show both customer and worker info
            pass
        elif status == 'COMPLETED':
            # show everything including rating + feedback
            pass
    return jsonify(records), 200


@app.route('/api/submit', methods=['POST'])
def submit_job():
    try:
        data = request.get_json() or {}
        required_fields = ["customer_name", "customer_phone", "dateTime", "description"]

        # --- Validate ---
        if not all(field in data and data[field] for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        # --- Quantity ---
        try:
            quantity = int(data.get("quantity", 1))
            if quantity < 1:
                return jsonify({"error": "Quantity must be ≥ 1"}), 400
        except Exception:
            return jsonify({"error": "Invalid quantity"}), 400

        # --- Compute cost ---
        cost_vnd = PER_ITEM_COST_VND * quantity
        cost_usd = format(cost_vnd / VND_TO_USD_RATE, ".2f")

        # --- Build row ---
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

        # --- Try appending to Google Sheets (with auto-retry) ---
        try:
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
        except Exception as e:
            print("⚠️ First attempt failed, retrying after 3s:", e)
            time.sleep(3)
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')

        return jsonify({
            "message": "Job added successfully!",
            "id": job_id,
            "costVND": cost_vnd,
            "costUSD": cost_usd
        }), 200

    except Exception as e:
        print("❌ Error submitting job:", e)
        return jsonify({"error": str(e)}), 500


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

        worksheet.update_acell(f"J{row_number}", "IN_PROGRESS")  # status
        worksheet.update_acell(f"K{row_number}", waiter_name)
        worksheet.update_acell(f"L{row_number}", waiter_phone)
        worksheet.update_acell(f"M{row_number}", str(uuid.uuid4()))  # accepterId
        worksheet.update_acell(f"O{row_number}", accepted_time)

        return jsonify({"message": "Job accepted successfully!"}), 200

    except Exception as e:
        print("Error accepting job:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/cancel_job', methods=['POST'])
def cancel_job():
    try:
        data = request.get_json() or {}
        job_id = data.get('id')
        if not job_id:
            return jsonify({"error": "Missing job ID"}), 400

        records = worksheet.get_all_records()

        for i, record in enumerate(records, start=2):  # skip header row
            if str(record.get("id")) == str(job_id):
                # Only cancel if still AVAILABLE
                if record.get("status") != "AVAILABLE":
                    return jsonify({"error": "Cannot cancel — job already accepted"}), 400

                cancelled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                worksheet.update_acell(f"J{i}", "CANCELLED")  # status
                worksheet.update_acell(f"P{i}", cancelled_time)  # completedAt
                worksheet.update_acell(f"I{i}", "Cancelled by customer")  # note column
                return jsonify({"message": "Job cancelled successfully"}), 200

        return jsonify({"error": "Job not found"}), 404

    except Exception as e:
        print("❌ Cancel job error:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/api/complete', methods=['POST'])
def complete_job():
    try:
        data = request.get_json() or {}
        job_id = data.get("id")
        rating = data.get("rating")
        feedback = data.get("feedback", "")

        row_number = find_row_by_id(job_id)
        if not row_number:
            return jsonify({"error": "Job not found"}), 404

        completed_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ✅ Correct columns
        worksheet.update_acell(f"J{row_number}", "COMPLETED")  # status
        worksheet.update_acell(f"P{row_number}", completed_time)  # completedAt

        if rating is not None:
            try:
                r = int(rating)
                if 1 <= r <= 5:
                    worksheet.update_acell(f"Q{row_number}", str(r))  # rating
            except Exception:
                pass

        if feedback:
            worksheet.update_acell(f"R{row_number}", str(feedback))  # feedback

        return jsonify({"message": "Job marked as completed!"}), 200

    except Exception as e:
        print("Error completing job:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
