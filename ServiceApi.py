# apis.py

"""
This file contains all external API calls.

Responsibilities:
1. Build request headers using TokenManager.
2. Call get_parents API when the current node is not a merchant.
3. Call add_amex_account API to create AMERICAN_EXPRESS account/payment channel.

Expected existing dependency:
- TokenManager.py
- TokenManager.get_token() should return a valid Bearer token string without the word "Bearer".
"""

import logging
import requests

from TokenManager import TokenManager


# Base config API URL.
# Change this if you want to run against another environment.
BASE_URL = "https://api-gateway-uat.ngenius-payments.com/config"


# Common headers required by config APIs.
API_HEADERS_TEMPLATE = {
    "Accept": "application/vnd.ni-config.v1+json",
    "Content-Type": "application/vnd.ni-config.v1+json"
}


class ServiceAPI:
    """
    ServiceAPI wraps all HTTP calls needed by the script.
    """

    @staticmethod
    def _headers():
        """
        Build API headers with Authorization token.

        Returns:
            dict: Headers containing Accept, Content-Type, and Authorization.
        """

        token = TokenManager.get_token()

        headers = API_HEADERS_TEMPLATE.copy()
        headers["Authorization"] = f"Bearer {token}"

        return headers

    @staticmethod
    def get_parents(node_type, ref):
        """
        Get all parent nodes for a given node.

        Example endpoint:
            GET /config/{node_type}/{ref}/parents

        Example:
            node_type = "outlets"
            ref = "some-outlet-reference"

            Final URL:
            /config/outlets/some-outlet-reference/parents

        Args:
            node_type (str): API path type, for example "outlets".
            ref (str): Current node reference.

        Returns:
            requests.Response: Raw HTTP response.
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
    def add_amex_account(merchant_reference, mid_reference, amex_mid, mcc):
        """
        Add AMERICAN_EXPRESS account/payment channel under a merchant.

        Endpoint:
            POST /config/merchants/{merchant_reference}/configs/accounts/

        Args:
            merchant_reference (str):
                The merchant reference.
                If _type == merchant, this comes from attached_to_node_reference.
                If _type != merchant, this comes from parents response merchant["reference"].

            mid_reference (str):
                MID reference from mid_merchant_info.csv.

            amex_mid (str):
                AMEX ID from NGEN_List.xlsx column "AMEX ID".

            mcc (str):
                MCC value from mid_mcc.csv column "mcc".
                It will be sent in the request as "merchantType".

        Returns:
            tuple:
                response: requests.Response
                payload: dict
        """

        url = f"{BASE_URL}/merchants/{merchant_reference}/configs/accounts/"

        payload = {
            "name": "MCCtest",
            "midRef": mid_reference,
            "paymentMethod": "AMERICAN_EXPRESS",
            "currency": "USD",
            "channel": [],
            "enabled": True,

            # AMEX ID from NGEN_List.xlsx
            "amexMid": amex_mid,

            # MCC from mid_mcc.csv should be sent as merchantType in the API request
            "merchantType": int(mcc),

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