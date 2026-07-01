# apis.py

"""
API layer.

This file is responsible only for HTTP calls:
1. Get node parents.
2. Create a new payment account/channel.

It does not contain business logic.
"""

import logging
import requests

from TokenManager import TokenManager


BASE_URL = "https://api-gateway.ngenius-payments.com/config"

API_HEADERS_TEMPLATE = {
    "Accept": "application/vnd.ni-config.v1+json",
    "Content-Type": "application/vnd.ni-config.v1+json"
}


class ServiceAPI:
    """
    Wrapper for config-service APIs.
    """

    @staticmethod
    def _headers():
        """
        Build headers for API requests.

        TokenManager.get_token() should return the token only,
        without the word "Bearer".
        """

        token = TokenManager.get_token()

        headers = API_HEADERS_TEMPLATE.copy()
        headers["Authorization"] = f"Bearer {token}"

        return headers

    @staticmethod
    def get_parents(node_type, ref):
        """
        Get all parent nodes for a given hierarchy node.

        Example:
            node_type = outlets
            ref = outlet reference

            GET /config/outlets/{ref}/parents

        This is used when the current row _type is not merchant.
        We use the response to find the parent merchant.
        """

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
    def add_account(merchant_reference, mid_reference, mcc, payment_method):
        """
        Create a new account/payment channel under a merchant.

        Args:
            merchant_reference:
                Merchant reference used in the URL.

            mid_reference:
                Value from mid_merchant_info.csv.
                This is sent as midRef.

            mcc:
                Value from mid_mcc.csv.
                This is sent as merchantType.

            payment_method:
                Payment method to create.
                Currently AMERICAN_EXPRESS.

        Note:
            amexMid was removed as requested.
        """

        url = f"{BASE_URL}/merchants/{merchant_reference}/configs/accounts/"

        payload = {
            "name": "JAYWANAED",
            "midRef": mid_reference,
            "paymentMethod": payment_method,
            "currency": "AED",
            "channel": [],
            "enabled": True,

            # MCC is sent to API as merchantType.
            "merchantType": int(mcc),

            "paymentProcessor": "NETWORK_INTERNATIONAL",
            "disabledOperations": ["void"],
            "threeDsId": None,
            "secretKey": ""
        }

        logging.info("Calling add_account API")
        logging.info("POST URL: %s", url)
        logging.info("Request payload: %s", payload)

        response = requests.post(
            url,
            headers=ServiceAPI._headers(),
            json=payload,
            timeout=30
        )

        logging.info("add_account response status: %s", response.status_code)
        logging.info("add_account response body: %s", response.text)

        return response, payload