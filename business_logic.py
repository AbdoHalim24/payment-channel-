# business_logic.py

"""
Business logic for adding AMEX payment channel.

Current logic:
1. Main loop is over NGEN_List.xlsx.
2. NGEN_List.xlsx contains:
   - NI MID
   - AMEX ID
   - processed
   - processing_reason

3. mid_merchant_info.csv is used to get:
   - attached_to_node_reference
   - mid_reference
   - payment_method
   - _type

4. mid_mcc.csv is used to get:
   - mcc

5. If payment_method is already AMERICAN_EXPRESS, mark row as processed.
6. If not, call add AMEX API.
"""

import json
import logging
import pandas as pd

from ServiceApi import ServiceAPI


PAYMENT_METHOD_TO_ADD = "AMERICAN_EXPRESS"


def normalize_value(value):
    """
    Convert any value from CSV/Excel to a clean string.
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_mid(value):
    """
    Keep MID as string because it may contain leading zeros.
    """

    return normalize_value(value)


def normalize_mid_without_leading_zeroes(value):
    """
    Fallback MID normalization.

    Example:
        001000000044 -> 1000000044
    """

    value = normalize_mid(value)

    if not value:
        return ""

    stripped = value.lstrip("0")

    return stripped if stripped else "0"


def strict_fetch(api_function, *args):
    """
    Call API function and return:
        status_code, response_json
    """

    response = api_function(*args)

    try:
        response_body = response.json()
    except ValueError:
        response_body = {}

    return response.status_code, response_body


def to_api_node_type(node_type):
    """
    Convert _type from file to API path type.

    Examples:
        merchant -> merchants
        outlet -> outlets
        merchant_organisation_unit -> organisation-units
    """

    node_type = normalize_value(node_type).lower()

    type_mapping = {
        "merchant": "merchants",
        "outlet": "outlets",
        "merchant_organisation_unit": "organisation-units",
        "tenant": "tenants"
    }

    return type_mapping.get(node_type, "merchants")


def build_mcc_lookup(mid_mcc_df):
    """
    Build MID -> MCC lookup from mid_mcc.csv.

    mid_mcc.csv columns:
        mids
        mcc
    """

    lookup = {}

    for _, row in mid_mcc_df.iterrows():
        mid = normalize_mid(row["mids"])
        mcc = normalize_value(row["mcc"])

        if not mid:
            continue

        lookup[mid] = mcc
        lookup[normalize_mid_without_leading_zeroes(mid)] = mcc

    logging.info("MID MCC lookup created with %s keys", len(lookup))

    return lookup


def get_mcc_for_mid(mid, mcc_lookup):
    """
    Get MCC by MID.

    First tries exact match.
    Then tries match without leading zeros.
    """

    exact_mid = normalize_mid(mid)
    fallback_mid = normalize_mid_without_leading_zeroes(mid)

    mcc = mcc_lookup.get(exact_mid)

    if mcc:
        return mcc

    return mcc_lookup.get(fallback_mid, "")


def validate_mcc(mid, mcc):
    """
    MCC must exist and must be numeric.
    """

    if not mcc:
        raise RuntimeError(f"MCC not found in mid_mcc.csv for MID {mid}")

    if not mcc.isdigit():
        raise RuntimeError(f"Invalid MCC for MID {mid}. MCC value: {mcc}")


def find_merchant_from_parents(parents):
    """
    Find merchant from get_parents response.

    Expected response:
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

    If _type == merchant:
        use attached_to_node_reference directly.

    Else:
        call get_parents and find _type == merchant.
    """

    logging.info("Resolving merchant reference")
    logging.info("Current node type: %s", node_type)
    logging.info("Current attached_to_node_reference: %s", attached_to_node_reference)

    normalized_node_type = normalize_value(node_type).lower()

    if normalized_node_type == "merchant":
        logging.info("Node type is merchant. Using attached_to_node_reference directly.")
        return attached_to_node_reference

    api_node_type = to_api_node_type(normalized_node_type)

    logging.info(
        "Node type is not merchant. Calling parents API using type: %s",
        api_node_type
    )

    code, parents = strict_fetch(
        ServiceAPI.get_parents,
        api_node_type,
        attached_to_node_reference
    )

    logging.info("Parents API status code: %s", code)
    logging.info("Parents API response: %s", parents)

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
    Find matching rows in mid_merchant_info.csv by MID.

    Uses fallback matching without leading zeroes.
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
    amex_mid="",
    mcc="",
    payment_method="",
    node_type="",
    request_payload="",
    response_status_code="",
    response_body=""
):
    """
    Build result object for logging/result CSV.
    """

    return {
        "mid": mid,
        "processed": processed,
        "processing_reason": processing_reason,
        "merchant_reference": merchant_reference,
        "mid_reference": mid_reference,
        "amex_mid": amex_mid,
        "mcc": mcc,
        "payment_method": payment_method,
        "_type": node_type,
        "request_payload": request_payload,
        "response_status_code": response_status_code,
        "response_body": response_body
    }


def process_ngen_row(row_number, ngen_row, mid_merchant_info_df, mcc_lookup):
    """
    Process one row from NGEN_List.xlsx.

    NGEN_List.xlsx columns used:
        NI MID
        AMEX ID

    mid_mcc.csv is still used for MCC.
    """

    mid = normalize_value(ngen_row["NI MID"])
    amex_mid = normalize_value(ngen_row["AMEX ID"])

    logging.info("Started processing NGEN row number: %s", row_number)
    logging.info("NI MID: %s", mid)
    logging.info("AMEX ID: %s", amex_mid)

    if not mid:
        raise RuntimeError(f"NI MID is empty at NGEN row {row_number}")

    if not amex_mid:
        raise RuntimeError(f"AMEX ID is empty for MID {mid} at NGEN row {row_number}")


    matching_rows = find_mid_rows_in_merchant_info(
        mid=mid,
        mid_merchant_info_df=mid_merchant_info_df
    )

    if matching_rows.empty:
        raise RuntimeError(
            f"MID {mid} not found in mid_merchant_info.csv"
        )

    has_amex = matching_rows["payment_method"].apply(
        lambda value: normalize_value(value).upper() == PAYMENT_METHOD_TO_ADD
    ).any()

    if has_amex:
        logging.info(
            "Skipping MID %s because AMERICAN_EXPRESS already exists",
            mid
        )

        return build_result(
            mid=mid,
            processed="YES",
            processing_reason="AMERICAN_EXPRESS already exists"
        )

    row = matching_rows.iloc[0]

    attached_to_node_reference = normalize_value(row["attached_to_node_reference"])
    mid_reference = normalize_value(row["mid_reference"])
    payment_method = normalize_value(row["payment_method"])
    node_type = normalize_value(row["_type"])

    logging.info("MID found in mid_merchant_info.csv")
    logging.info("attached_to_node_reference: %s", attached_to_node_reference)
    logging.info("mid_reference: %s", mid_reference)
    logging.info("_type: %s", node_type)

    if not attached_to_node_reference:
        raise RuntimeError(
            f"attached_to_node_reference is empty for MID {mid}"
        )

    if not mid_reference:
        raise RuntimeError(
            f"mid_reference is empty for MID {mid}"
        )

    if not node_type:
        raise RuntimeError(
            f"_type is empty for MID {mid}"
        )

    mcc = get_mcc_for_mid(mid, mcc_lookup)
    validate_mcc(mid, mcc)

    logging.info("MCC found for MID %s: %s", mid, mcc)

    merchant_reference = resolve_merchant_reference(
        attached_to_node_reference=attached_to_node_reference,
        node_type=node_type
    )

    response, payload = ServiceAPI.add_amex_account(
        merchant_reference=merchant_reference,
        mid_reference=mid_reference,
        amex_mid=amex_mid,
        mcc=mcc
    )

    if not response.ok:
        raise RuntimeError(
            f"Add AMEX API failed for MID {mid}. "
            f"Status code: {response.status_code}. "
            f"Response: {response.text}"
        )

    logging.info(
        "AMERICAN_EXPRESS account created successfully for MID: %s",
        mid
    )

    return build_result(
        mid=mid,
        processed="YES",
        processing_reason="AMERICAN_EXPRESS account created successfully",
        merchant_reference=merchant_reference,
        mid_reference=mid_reference,
        amex_mid=amex_mid,
        mcc=mcc,
        payment_method=payment_method,
        node_type=node_type,
        request_payload=json.dumps(payload),
        response_status_code=response.status_code,
        response_body=response.text
    )