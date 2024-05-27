import hashlib
import base64
import json
import requests
import uuid
import logging
from config import BotConfig
from pydantic import BaseModel


config = BotConfig()


class CryptoBodyRequest(BaseModel):
    amount: str
    currency: str
    order_id: str
    lifetime: int
    url_callback: str


class SignatureError(Exception):
    """Custom exception for errors during signature generation or validation."""


class InvoiceCreationError(Exception):
    """Custom exception for errors during invoice creation."""


class CryptomusManager:
    def __init__(self):
        self.api_key = config.cryptomus_key
        self.merchant_id = config.cryptomus_merchant_id
        self.base_url = config.cryptomus_base_url
        self.webhook_url = config.cryptomus_webhook

    @staticmethod
    def generate_order_id():
        return str(uuid.uuid4())

    def generate_signature(self, data):
        try:
            data_str = json.dumps(data, separators=(",", ":"))
            encoded_str = base64.b64encode(data_str.encode("utf-8")).decode("utf-8")
            sign = hashlib.md5((encoded_str + self.api_key).encode("utf-8")).hexdigest()
            return sign
        except Exception as e:
            raise SignatureError(f"Error generating signature: {e}")

    def validate_signature(self, data, provided_signature):
        try:
            data_without_signature = dict(data)
            data_without_signature.pop("sign", None)
            body_data = base64.b64encode(
                json.dumps(data_without_signature).encode("utf-8")
            ).decode("utf-8")
            calculated_signature = hashlib.md5(
                (body_data + self.api_key).encode("utf-8")
            ).hexdigest()
            return provided_signature == calculated_signature
        except Exception as e:
            raise SignatureError(f"Error validating signature: {e}")

    def create_invoice(self, user_id: int, user_name: str, payment_method, timeout=10):
        request_body = {
            "amount": str(payment_method),
            "currency": "USDT",
            "order_id": f"{payment_method}-{user_name}-{user_id}-{uuid.uuid4()}",
            "lifetime": 3600,
            "url_callback": self.webhook_url,
        }

        logging.info(f"the request body is {request_body}")
        endpoint = f"{self.base_url}/payment"
        signature = self.generate_signature(request_body)

        headers = {
            "merchant": str(self.merchant_id),
            "sign": signature,
            "Content-Type": "application/json",
        }
        logging.info(f"the clean json {json.dumps(request_body, separators=(',', ':'))}")
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(request_body, separators=(",", ":")),
                timeout=timeout,
            )
            logging.info(f"the error maybe happend here {response.json()}")
            response.raise_for_status()
            data = response.json()

            if (
                "result" not in data
                or "url" not in data["result"]
                or "order_id" not in data["result"]
            ):
                raise InvoiceCreationError(
                    "Unexpected response format or missing information in the response."
                )

            return data["result"]["url"], data["result"]["order_id"]

        except requests.ConnectionError:
            raise InvoiceCreationError("Failed to connect to the server.")
        except requests.Timeout:
            raise InvoiceCreationError("The request timed out.")
        except requests.HTTPError:
            raise InvoiceCreationError(
                f"HTTP error occurred. Status Code: {response.status_code}"
            )
        except json.JSONDecodeError:
            raise InvoiceCreationError("Error decoding the server's response.")
        except Exception as e:
            raise InvoiceCreationError(f"An unexpected error occurred: {e}")
