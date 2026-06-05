# --- TokenManager.py ---
import sys
import time

import requests

IDENTITY_URL = "https://api-gateway-uat.ngenius-payments.com/identity/auth/access-token"

CLIENT_ID = "transaction-service"
#uat
CLIENT_SECRET = "c5fe74d5-9324-412a-bee1-55a1018d625e"

#prod
# CLIENT_SECRET = "00e0b7af-7fd2-4d13-91bf-5b9adb95a59e"


REALM_NAME = "services"


class TokenManager:
    _token = None
    _expiry_time = 0

    @staticmethod
    def get_token():
        if not TokenManager._token or time.time() > TokenManager._expiry_time - 30:
            TokenManager._generate_token()
        return TokenManager._token

    @staticmethod
    def _generate_token():
        payload = {
            "grantType": "client_credentials",
            "realmName": REALM_NAME,
            "clientId": CLIENT_ID,
            "clientSecret": CLIENT_SECRET

        }

        headers = {
            "Content-Type": "application/vnd.ni-identity.v1+json"
        }

        try:
            response = requests.post(IDENTITY_URL, headers=headers, json=payload)

            response.raise_for_status()
            data = response.json()
            TokenManager._token = data.get("access_token")
            expires_in = data.get("expires_in", 300)
            TokenManager._expiry_time = time.time() + expires_in
            print("🔐 Access token successfully generated ")
        except requests.RequestException as e:
            print(f"❌ Token generation failed: {e}")
            sys.exit(1)
