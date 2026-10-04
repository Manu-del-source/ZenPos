import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import base64
import json
import os

class MpesaGateWay:
    def __init__(self, consumer_key, consumer_secret, shortcode, passkey):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.shortcode = shortcode
        self.passkey = passkey
        environment = os.getenv("MPESA_ENV", "sandbox").strip().lower()
        if environment not in {"sandbox", "production"}:
            raise ValueError("MPESA_ENV must be sandbox or production")
        self.base_url = (
            "https://sandbox.safaricom.co.ke"
            if environment == "sandbox"
            else "https://api.safaricom.co.ke"
        )

    def get_token(self):
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        response = requests.get(url, auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret))
        return response.json().get("access_token")

    def stk_push(self, phone, amount, callback_url, account_ref="POS_System"):
        token = self.get_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(f"{self.shortcode}{self.passkey}{timestamp}".encode()).decode()
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": callback_url,
            "AccountReference": account_ref,
            "TransactionDesc": "POS Sale"
        }
        
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
