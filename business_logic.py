# business_logic.py

"""
Business logic layer.

Main responsibility:
- Process rows from mid_mcc.csv.
- Find matching merchant/MID info from mid_merchant_info.csv.
- Skip already existing payment method.
- Resolve merchant reference.
- Call API to create account.

Input files:
1. mid_mcc.csv
   Required columns:
   - mids
   - mcc
   - processed optional
   - processing_reason optional

2. mid_merchant_info.csv
   Required columns:
   - mid
   - attached_to_node_reference
   - mid_reference
   - payment_method
   - _type
"""

import json
import logging
import pandas as pd

from ServiceApi import ServiceAPI


# Payment method to create.
# Change this value if later you want to create another payment method.
PAYMENT_METHOD_TO_ADD = "JAYWAN"



def normalize_value(value):
    """
    Convert any value from CSV into a clean string.

    Handles:
    - NaN
    - None
    - leading/trailing spaces
    - numeric values read by pandas
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_mid(value):
    """
    Keep MID as string.

    This is important because some MIDs may start with leading zeroes.
    """

    return normalize_value(value)


def normalize_mid_without_leading_zeroes(value):
    """
    Normalize MID for matching only.

    Example:
        0024343503 -> 24343503

    This allows matching between:
        0024343503
        24343503
        00024343503
    """

    value = normalize_mid(value)

    if not value:
        return ""

    stripped = value.lstrip("0")

    return stripped if stripped else "0"


def strict_fetch(api_function, *args):
    """
    Execute API function and return:
        status_code, response_json

    If response body is not JSON, response_json will be {}.
    """

    response = api_function(*args)

    try:
        response_body = response.json()
    except ValueError:
        response_body = {}

    return response.status_code, response_body


def to_api_node_type(node_type):
    """
    Convert _type value from CSV into API path value.

    Example:
        outlet -> outlets
        merchant_organisation_unit -> merchant-organisation-units

    Unknown node types are not allowed because calling the wrong endpoint
    may create incorrect behavior.
    """

    node_type = normalize_value(node_type).lower()

    type_mapping = {
        "merchant": "merchants",
        "outlet": "outlets",
        "merchant_organisation_unit": "merchant-organisation-units",
        "tenant": "tenants"
    }

    if node_type not in type_mapping:
        raise RuntimeError(f"Unsupported node type: {node_type}")

    return type_mapping[node_type]


def validate_mcc(mid, mcc):
    """
    Validate MCC before sending it to the API.

    MCC must:
    - Exist
    - Be numeric
    """

    if not mcc:
        raise RuntimeError(f"MCC not found for MID {mid}")

    if not mcc.isdigit():
        raise RuntimeError(f"Invalid MCC for MID {mid}. MCC value: {mcc}")


def find_merchant_from_parents(parents):
    """
    Find merchant from get_parents response.

    Expected response structure:
        {
            "items": [
                {
                    "_type": "merchant",
                    "reference": "merchant-reference"
                }
            ]
        }
    """

    items = parents.get("items", [])

    return next(
        (
            item for item in items
            if normalize_value(item.get("_type")).lower() == "merchant"
        ),
        None
    )


def resolve_merchant_reference(attached_to_node_reference, node_type):
    """
    Resolve merchant reference.

    Logic:
    1. If _type == merchant:
       Use attached_to_node_reference directly.

    2. If _type != merchant:
       Call get_parents API.
       Find parent where _type == merchant.
       Use merchant["reference"].
    """

    normalized_node_type = normalize_value(node_type).lower()

    logging.info("Resolving merchant reference")
    logging.info("Current node type: %s", normalized_node_type)
    logging.info("Current attached_to_node_reference: %s", attached_to_node_reference)

    if normalized_node_type == "merchant":
        logging.info("Node is merchant, using attached_to_node_reference directly")
        return attached_to_node_reference

    api_node_type = to_api_node_type(normalized_node_type)

    code, parents = strict_fetch(
        ServiceAPI.get_parents,
        api_node_type,
        attached_to_node_reference
    )

    if code != 200:
        raise RuntimeError(
            f"get_parents API failed with status code {code}. Response: {parents}"
        )

    merchant = find_merchant_from_parents(parents)

    if not merchant:
        raise RuntimeError("Merchant not found in parents response")

    merchant_reference = normalize_value(merchant.get("reference"))

    if not merchant_reference:
        raise RuntimeError("Merchant reference is empty in parents response")

    logging.info("Merchant reference resolved: %s", merchant_reference)

    return merchant_reference


def find_mid_rows_in_merchant_info(mid, mid_merchant_info_df):
    """
    Find matching MID rows from mid_merchant_info.csv.

    Matching ignores leading zeroes only for lookup.

    Example:
        mid_mcc.csv MID = 0024343503
        mid_merchant_info.csv MID = 24343503

        They will match.
    """

    normalized_mid = normalize_mid_without_leading_zeroes(mid)

    return mid_merchant_info_df[
        mid_merchant_info_df["mid"].apply(normalize_mid_without_leading_zeroes)
        == normalized_mid
    ]


def build_result(
    mid,
    processed,
    processing_reason,
    merchant_reference="",
    mid_reference="",
    mcc="",
    payment_method="",
    node_type="",
    request_payload="",
    response_status_code="",
    response_body=""
):
    """
    Build result row for result CSV.
    """

    return {
        "mid": mid,
        "processed": processed,
        "processing_reason": processing_reason,
        "merchant_reference": merchant_reference,
        "mid_reference": mid_reference,
        "mcc": mcc,
        "payment_method": payment_method,
        "_type": node_type,
        "request_payload": request_payload,
        "response_status_code": response_status_code,
        "response_body": response_body
    }


def process_mid_mcc_row(row_number, row, mid_merchant_info_df):
    """
    Process one row from mid_mcc.csv.

    Flow:
    1. Read MID and MCC.
    2. Validate MCC.
    3. Find MID in mid_merchant_info.csv.
    4. Check if AMERICAN_EXPRESS already exists.
    5. If exists, mark processed YES.
    6. If not, resolve merchant reference.
    7. Call add_account API.
    """

    mid = normalize_value(row["mids"])
    mcc = normalize_value(row["mcc"])

    logging.info("Started processing row number: %s", row_number)
    logging.info("MID: %s", mid)
    logging.info("MCC: %s", mcc)

    if not mid:
        raise RuntimeError(f"MID is empty at row {row_number}")

    validate_mcc(mid, mcc)

    matching_rows = find_mid_rows_in_merchant_info(
        mid=mid,
        mid_merchant_info_df=mid_merchant_info_df
    )

    if matching_rows.empty:
        raise RuntimeError(f"MID {mid} not found in mid_merchant_info.csv")

    has_payment_method = matching_rows["payment_method"].apply(
        lambda value: normalize_value(value).upper() == PAYMENT_METHOD_TO_ADD
    ).any()

    if has_payment_method:
        logging.info(
            "Skipping MID %s because %s already exists",
            mid,
            PAYMENT_METHOD_TO_ADD
        )

        return build_result(
            mid=mid,
            processed="YES",
            processing_reason=f"{PAYMENT_METHOD_TO_ADD} already exists",
            mcc=mcc,
            payment_method=PAYMENT_METHOD_TO_ADD
        )

    merchant_info_row = matching_rows.iloc[0]

    attached_to_node_reference = normalize_value(
        merchant_info_row["attached_to_node_reference"]
    )
    mid_reference = normalize_value(merchant_info_row["mid_reference"])
    node_type = normalize_value(merchant_info_row["_type"])

    if not attached_to_node_reference:
        raise RuntimeError(f"attached_to_node_reference is empty for MID {mid}")

    if not mid_reference:
        raise RuntimeError(f"mid_reference is empty for MID {mid}")

    if not node_type:
        raise RuntimeError(f"_type is empty for MID {mid}")

    merchant_reference = resolve_merchant_reference(
        attached_to_node_reference=attached_to_node_reference,
        node_type=node_type
    )

    response, payload = ServiceAPI.add_account(
        merchant_reference=merchant_reference,
        mid_reference=mid_reference,
        mcc=mcc,
        payment_method=PAYMENT_METHOD_TO_ADD
    )

    if not response.ok:
        raise RuntimeError(
            f"Add account API failed for MID {mid}. "
            f"Status code: {response.status_code}. "
            f"Response: {response.text}"
        )

    logging.info("Account created successfully for MID: %s", mid)

    return build_result(
        mid=mid,
        processed="YES",
        processing_reason="Account created successfully",
        merchant_reference=merchant_reference,
        mid_reference=mid_reference,
        mcc=mcc,
        payment_method=PAYMENT_METHOD_TO_ADD,
        node_type=node_type,
        request_payload=json.dumps(payload),
        response_status_code=response.status_code,
        response_body=response.text
    )