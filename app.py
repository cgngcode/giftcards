from flask import Flask, request, jsonify
import requests
import smtplib
from email.mime.text import MIMEText
import logging
import time

app = Flask(__name__)

# =========================
# CONFIGURATION
# =========================

EZPIN_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzayI6IjA1ZjAxYmY2LWEzOTgtNDY3MC1iMThkLTM4ZWZiMjA5YzVjNSJ9.BUVMBubP9rcYALSLngB8psSSzg7CUxjlDuyiLfWkOCw"

SMTP_SERVER = "smtp.zoho.com"
SMTP_PORT = 587
SMTP_USER = "giftcards@cheapgamesng.com"
SMTP_PASS = "widt myjd fgec wfyq"

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# =========================
# PLAYSTATION SKU MAPPING
# =========================
SKUS = {
    "0008800010007": "PlayStation US $10",
}

# =========================
# LOGGING SETUP
# =========================
logging.basicConfig(
    filename='giftcard_webhook.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# =========================
# HELPER FUNCTION: EZPIN REQUEST WITH RETRY
# =========================
def ezpin_request_with_retry(order_name, sku, quantity):
    url = "https://api.ezpaypin.com/vendors/v2/orders"
    headers = {
        "Authorization": f"Bearer {EZPIN_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "CustomerOrderNumber": order_name,
        "items": [{"sku": sku, "quantity": quantity}]
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(url, json=body, headers=headers, timeout=10)
            response.raise_for_status()
            response_data = response.json()
            return response_data
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed for SKU {sku} in order {order_name}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                logging.error(f"All {MAX_RETRIES} attempts failed for SKU {sku} in order {order_name}")
                return None

# =========================
# WEBHOOK ROUTE
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    if not data or 'customer' not in data:
        logging.warning("Invalid payload received.")
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    order_name = data.get('name', 'UNKNOWN_ORDER')
    financial_status = data.get('financial_status', 'unknown')

    # Only process paid orders
    if financial_status != 'paid':
        logging.info(f"Ignored order {order_name} - financial_status: {financial_status}")
        return jsonify({"status": "ignored", "message": "Order not paid"}), 200

    customer_email = data['customer']['email']
    logging.info(f"Processing paid order {order_name} for {customer_email}")

    # Loop through items and process only PlayStation ones
    for item in data['line_items']:
        sku = item.get('sku')
        quantity = item.get('quantity', 1)

        if sku not in SKUS:
            logging.info(f"SKU {sku} not in PlayStation mapping, skipping.")
            continue

        response_data = ezpin_request_with_retry(order_name, sku, quantity)
        if not response_data:
            continue

        pins = response_data.get('pins', [])
        if not pins:
            logging.warning(f"No pins returned from EZPin for SKU {sku} in order {order_name}")
            continue

        for pin in pins:
            send_email(customer_email, SKUS[sku], pin['pin'])
            logging.info(f"Sent gift card code for SKU {sku} to {customer_email} (Order: {order_name})")

    return jsonify({"status": "success"}), 200

# =========================
# EMAIL FUNCTION
# =========================
def send_email(to_email, product_name, pin_code):
    subject = f"Your {product_name} Gift Card Code"
    body = f"""
Hello,

Thank you for your purchase on CheapGamesNG!

Here is your gift card code for {product_name}:

{pin_code}

Enjoy your games!

- CheapGamesNG Team
"""

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = to_email

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        logging.info(f"Email sent successfully to {to_email}")
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {e}")

# =========================
# RUN SERVER
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
