import requests
import logging
from config import BotConfig
from pydantic import BaseModel
from urllib.parse import urlencode
import json


config = BotConfig()


class DataBody(BaseModel):
    id: str
    amount: float
    phone: str
    email: str
    backend_url: str
    frontend_url: str
    custom_ref: str


class TlyncClient:
    def __init__(self, is_test_environment=False):
        self.test_url = config.tlync_test_base_url
        self.live_url = config.tlync_base_url
        self.base_url = self.test_url if is_test_environment else self.live_url
        self.token = config.tlync_token
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self.token}"
        }

    def handle_request(self, method, endpoint, data=None):
        url = self.base_url + endpoint
        try:
            logging.info(f"the url used is {url}")
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            else:
                logging.info(f"the method is {method}")
                response = requests.post(url, data=urlencode(data), headers=self.headers)
                logging.info(f"the original resp is {response}")
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as err:
            logging.error(f"the error is {err}")
            return {"error": str(err), "response": err.response.json()}

    def initiate_payment(self, data: DataBody):
        return self.handle_request("POST", "payment/initiate", data.model_dump())

    def get_transaction_receipt(self, store_id, transaction_ref, custom_ref):
        data = {
            "store_id": store_id,
            "transaction_ref": transaction_ref,
            "custom_ref": custom_ref
        }
        return self.handle_request("POST", "receipt/transaction", data)


# # Usage example
# api_client = TlyncClient(is_test_environment=True)
# api_client.set_token("your-access-token-here")
# response = api_client.initiate_payment("store-id", 100.0, "123456789", "test@example.com", "http://backend.url",
#                                        "http://frontend.url", "custom-ref")
# print(response)
