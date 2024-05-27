import hmac
import json
import logging
from flask import Flask, request, jsonify
from usage import UsageTracker
from utils import extract_user_id
from cryptomus_client import CryptomusManager
from config import BotConfig


app = Flask(__name__)

bot_config = BotConfig()
API_KEY = bot_config.cryptomus_key
CRYPTOMUS_IP = bot_config.cryptomus_allowed_ip


@app.route("/cryptomus_callback", methods=["POST"])
async def cryptomus_callback():
    # IP validation
    if request.remote_addr != CRYPTOMUS_IP:
        logging.error("Error IP is unknown")
        return jsonify({"error": "Unauthorized IP"}), 401

    # Ensure the request is JSON formatted
    if not request.is_json:
        logging.error(f"is not json")
        return jsonify({"error": "Invalid request format"}), 400

    data = request.json

    sign = data.get("sign")
    if not sign:
        logging.error(f"the sign is not provided")
        return jsonify({"error": "Sign not provided"}), 400

    del data["sign"]
    # Encoding and hashing logic as per given example
    crypto = CryptomusManager()
    hash_string = crypto.generate_signature(data=data)
    computed_hash = hash_string

    if not hmac.compare_digest(computed_hash, sign):
        logging.error(f"invalid sign")
        return jsonify({"error": "Invalid sign detected!"}), 400

    # Assuming `user_id` can be retrieved from `data`:
    # order_id = data["order_id"]
    # amount = data["amount"]
    # user_id = extract_user_id(order_id)
    # usage_tracker = UsageTracker(user_id, user_name=)
    # # # Update user details in the database based on the payment received

    return jsonify(data), 200


@app.route("/tlync_callback", methods=["POST"])
async def tlync_callback():
    data = json.loads(request.data)
    logging.info(f"the data response fron tlyinc is {data}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8300)
