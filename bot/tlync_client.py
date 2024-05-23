import requests
from config import BotConfig
from pydantic import BaseModel
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
    def __init__(self, is_test_environment=True):
        self.test_url = config.tlync_test_base_url
        self.live_url = config.tlync_base_url
        self.base_url = self.test_url if is_test_environment else self.live_url
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.token = config.tlync_token

    def set_token(self, token):
        self.token = token
        self.headers["Authorization"] = f"Bearer {token}"

    def handle_request(self, method, endpoint, data=None):
        url = self.test_url + endpoint
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            else:  # POST request
                response = requests.post(url, data=data, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
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
