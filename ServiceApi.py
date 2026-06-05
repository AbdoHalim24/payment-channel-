# apis.py

import logging
import requests

from TokenManager import TokenManager


BASE_URL = "https://api-gateway-uat.ngenius-payments.com/config"

API_HEADERS_TEMPLATE = {
    "Accept": "application/vnd.ni-config.v1+json",
    "Content-Type": "application/vnd.ni-config.v1+json"
}


class ServiceAPI:

    @staticmethod
    def _headers():
        token = TokenManager.get_token()

        headers = API_HEADERS_TEMPLATE.copy()
        headers["Authorization"] = f"Bearer {token}"

        return headers

    @staticmethod
    def get_parents(node_type, ref):
        url = f"{BASE_URL}/{node_type}/{ref}/parents"

        logging.info("Calling get_parents API")
        logging.info("GET URL: %s", url)

        response = requests.get(
            url,
            headers=ServiceAPI._headers(),
            timeout=30
        )

        logging.info("get_parents response status: %s", response.status_code)
        logging.info("get_parents response body: %s", response.text)

        return response

    @staticmethod
    def add_amex_account(merchant_reference, mid_reference, amex_mid):
        url = f"{BASE_URL}/merchants/{merchant_reference}/configs/accounts/"

        payload = {
            "name": "amexIdTest",
            "midRef": mid_reference,
            "paymentMethod": "AMERICAN_EXPRESS",
            "currency": "USD",
            "channel": [],
            "enabled": True,
            "amexMid": amex_mid,
            "paymentProcessor": "NETWORK_INTERNATIONAL",
            "disabledOperations": ["void"],
            "threeDsId": None,
            "secretKey": ""
        }

        logging.info("Calling add_amex_account API")
        logging.info("POST URL: %s", url)
        logging.info("Request payload: %s", payload)

        response = requests.post(
            url,
            headers=ServiceAPI._headers(),
            json=payload,
            timeout=30
        )

        logging.info("add_amex_account response status: %s", response.status_code)
        logging.info("add_amex_account response body: %s", response.text)

        return response, payload