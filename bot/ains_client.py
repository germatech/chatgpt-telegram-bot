import uuid
from typing import Dict, Any

import logging
from config import BotConfig

from binance.spot import Spot as Client
from binance.error import ServerError, ClientError, Error
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
import base64


config = BotConfig()


def generate_order_id():
    return str(uuid.uuid4())


# this is when I use RSA binance key
def get_public_key(public_key_string: str):
    public_key_bytes = base64.b64decode(public_key_string)
    public_key = serialization.load_pem_public_key(
        public_key_bytes, backend=default_backend()
    )
    return public_key


# this is when I use RSA binance key
def encrypt(content, public_key_string):
    if not content or not public_key_string:
        raise ValueError("Invalid content or public key.")

    public_key = get_public_key(public_key_string)
    encrypted = public_key.encrypt(
        content.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.urlsafe_b64encode(encrypted).decode("utf-8")


class RedeemManager:
    def __init__(self) -> None:
        if config.env == "true":
            self.base_url = config.test_binance_base_url
            self.binance_api_key = config.test_binance_key
        else:
            self.base_url = config.binance_base_url
            self.binance_api_key = config.binance_api_key
            self.binance_api_secret = config.binance_api_secret
        try:
            self.binance_client = Client(
                api_key=self.binance_api_key,
                api_secret=self.binance_api_secret,
                base_url=self.base_url,
            )
        except ClientError as e:
            logging.error(f"Initialization Error in BinanceManager: {e}")
            raise ServerError(
                message="Failed to initialize Binance client due to client error.",
                status_code=500,
            )

    def anis_redeem_code(self, redeem_code: str, user_id: int) -> Dict[str, Any] | Any:
        try:
            external_uid = generate_order_id()
            resp = self.binance_client.gift_card_redeem_code(
                code=redeem_code,
                keyword={"externalUid": f"redeem{user_id}-{external_uid}"},
            )
            if resp.get("success"):
                return {
                    "success": resp["success"],
                    "referenceNo": resp["data"]["referenceNo"],
                    "identityNo": resp["data"]["identityNo"],
                    "coin": resp["data"]["token"],
                    "amount": resp["data"]["amount"],
                }
            else:
                logging.error(f"Redeem Code Error: {resp.get('message')}")
                raise ValueError("Redeem code failed.")
        except ServerError as e:
            logging.error(f"Server Error in anis_redeem_code: {e}")
            raise
        except Error as e:
            logging.error(f"General Error in anis_redeem_code: {e}")
            raise

    def exchange_price(self, coin: str):
        try:
            resp = self.binance_client.ticker_price(symbol=coin)
            if resp:
                return resp["price"]
        except ServerError as e:
            logging.error(f"General Error in {e}")
            raise ValueError("General Error when trying to get price.")
