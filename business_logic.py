# business_logic.py

"""
This file contains the main business logic.

Responsibilities:
1. Normalize values from CSV/Excel files.
2. Build lookup maps:
   - NGEN_List.xlsx: NI MID -> AMEX ID
   - mid_mcc.csv: mids -> mcc
3. Process each row from mid_merchant_info.csv.
4. Skip rows that already have AMERICAN_EXPRESS.
5. Resolve the correct merchant reference.
6. Call add_amex_account with:
   - merchant_reference
   - mid_reference
   - amex_mid
   - mcc as merchantType
"""

import json
import logging
import pandas as pd

from ServiceApi import ServiceAPI


PAYMENT_METHOD_TO_ADD = "AMERICAN_EXPRESS"


def normalize_value(value):
    """
    Convert any CSV/Excel cell value into a clean string.

    Handles:
    - NaN
    - None
    - numbers
    - leading/trailing spaces

    Args:
        value: Any cell value from pandas.

    Returns:
        str: Clean string value.
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_mid(value):
    """
    Normalize MID values for matching.

    We keep MID as string because some MIDs may start with leading zeroes.

    Args:
        value: MID value.

    Returns:
        str: Normalized MID.
    """

    return normalize_value(value)


def normalize_mid_without_leading_zeroes(value):
    """
    Normalize MID by removing leading zeroes.

    This is used only as a fallback matching method.

    Example:
        "001000000044" -> "1000000044"

    Args:
        value: MID value.

    Returns:
        str: MID without leading zeroes.
    """

    value = normalize_mid(value)

    if not value:
        return ""

    stripped = value.lstrip("0")

    return stripped if stripped else "0"


def strict_fetch(api_function, *args):
    """
    Call an API function and return status code with JSON response.

    This keeps API handling consistent.

    Args:
        api_function: Function to call, for example ServiceAPI.get_parents.
        *args: Arguments passed to the API function.

    Returns:
        tuple:
            status_code: int
            response_body: dict
    """

    response = api_function(*args)

    try:
        response_body = response.json()
    except ValueError:
        response_body = {}

    return response.status_code, response_body


def to_api_node_type(node_type):
    """
    Convert CSV _type value to the correct API path.

    Example:
        merchant                    -> merchants
        outlet                      -> outlets
        merchant_organisation_unit  -> merchant-organisation-units
        tenant                      -> tenants

    Args:
        node_type (str): Value from _type column.

    Returns:
        str: API path type.
    """

    node_type = normalize_value(node_type).lower()

    type_mapping = {
        "merchant": "merchants",
        "outlet": "outlets",
        "merchant_organisation_unit": "merchant-organisation-units",
        "tenant": "tenants"
    }

    return type_mapping.get(node_type, node_type)


def build_ngen_amex_lookup(ngen_df):
    """
    Build AMEX lookup from NGEN_List.xlsx.

    Source columns:
        NI MID    -> MID
        AMEX ID -> AMEX ID to send as amexMid

    We store two keys:
    1. Exact MID
    2. MID without leading zeroes

    This helps when one file has:
        001000000044

    And another file has:
        1000000044

    Args:
        ngen_df (pandas.DataFrame): Data from NGEN_List.xlsx.

    Returns:
        dict: MID -> AMEX ID
    """

    lookup = {}

    for _, row in ngen_df.iterrows():
        prdf = normalize_mid(row["NI MID"])
        amex_id = normalize_value(row["AMEX ID"])

        if not prdf:
            continue

        lookup[prdf] = amex_id
        lookup[normalize_mid_without_leading_zeroes(prdf)] = amex_id

    logging.info("NGEN AMEX lookup created with %s keys", len(lookup))

    return lookup


def build_mcc_lookup(mid_mcc_df):
    """
    Build MCC lookup from mid_mcc.csv.

    Source columns:
        mids -> MID
        mcc  -> merchant category code

    The mcc value will be sent in the API payload as:
        merchantType

    Args:
        mid_mcc_df (pandas.DataFrame): Data from mid_mcc.csv.

    Returns:
        dict: MID -> MCC
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


def get_amex_mid_for_mid(mid, ngen_amex_lookup):
    """
    Get AMEX ID for a specific MID.

    First tries exact MID match.
    If not found, tries MID without leading zeroes.

    Args:
        mid (str): MID from mid_merchant_info.csv.
        ngen_amex_lookup (dict): Lookup generated from NGEN_List.xlsx.

    Returns:
        str: AMEX ID or empty string if not found.
    """

    exact_mid = normalize_mid(mid)
    fallback_mid = normalize_mid_without_leading_zeroes(mid)

    amex_mid = ngen_amex_lookup.get(exact_mid)

    if amex_mid:
        return amex_mid

    return ngen_amex_lookup.get(fallback_mid, "")


def get_mcc_for_mid(mid, mcc_lookup):
    """
    Get MCC for a specific MID.

    First tries exact MID match.
    If not found, tries MID without leading zeroes.

    Args:
        mid (str): MID from mid_merchant_info.csv.
        mcc_lookup (dict): Lookup generated from mid_mcc.csv.

    Returns:
        str: MCC or empty string if not found.
    """

    exact_mid = normalize_mid(mid)
    fallback_mid = normalize_mid_without_leading_zeroes(mid)

    mcc = mcc_lookup.get(exact_mid)

    if mcc:
        return mcc

    return mcc_lookup.get(fallback_mid, "")


def validate_mcc(mid, mcc):
    """
    Validate MCC value before sending the request.

    MCC must:
    - Exist
    - Be numeric

    Args:
        mid (str): MID being processed.
        mcc (str): MCC value.

    Raises:
        RuntimeError: If MCC is missing or invalid.
    """

    if not mcc:
        raise RuntimeError(f"MCC not found for MID {mid}")

    if not mcc.isdigit():
        raise RuntimeError(f"Invalid MCC for MID {mid}. MCC value: {mcc}")


def build_result(
    row_number,
    mid,
    status,
    reason,
    attached_to_node_reference="",
    mid_reference="",
    payment_method="",
    node_type="",
    merchant_reference="",
    amex_mid="",
    mcc="",
    request_payload="",
    response_status_code="",
    response_body=""
):
    """
    Build one result row for the output CSV.

    Returns:
        dict: Result data.
    """

    return {
        "row_number": row_number,
        "mid": mid,
        "status": status,
        "reason": reason,
        "attached_to_node_reference": attached_to_node_reference,
        "mid_reference": mid_reference,
        "payment_method": payment_method,
        "_type": node_type,
        "merchant_reference": merchant_reference,
        "amex_mid": amex_mid,
        "mcc": mcc,
        "request_payload": request_payload,
        "response_status_code": response_status_code,
        "response_body": response_body
    }


def find_merchant_from_parents(parents):
    """
    Find merchant object from parents API response.

    Expected response structure:
        {
            "_links": {},
            "items": [
                {
                    "reference": "merchant-reference",
                    "_type": "merchant"
                }
            ]
        }

    Args:
        parents (dict): JSON response from get_parents API.

    Returns:
        dict or None: Merchant object if found.
    """

    items = parents.get("items", [])

    merchant = next(
        (
            item for item in items
            if normalize_value(item.get("_type")).lower() == "merchant"
        ),
        None
    )

    return merchant


def resolve_merchant_reference(attached_to_node_reference, node_type):
    """
    Resolve the merchant reference needed for add_amex_account API.

    Logic:
    1. If _type == merchant:
       - Use attached_to_node_reference directly.

    2. If _type != merchant:
       - Call get_parents API.
       - Find item where _type == merchant.
       - Use merchant["reference"].

    Args:
        attached_to_node_reference (str): Current row node reference.
        node_type (str): Current row _type.

    Returns:
        str: Merchant reference.

    Raises:
        RuntimeError: If parent API fails or merchant is not found.
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


def process_row(row_number, row, ngen_amex_lookup, mcc_lookup):
    """
    Process one row from mid_merchant_info.csv.

    Main flow:
    1. Read row data.
    2. Validate required row values.
    3. If payment_method is AMERICAN_EXPRESS, skip row.
    4. Find AMEX ID from NGEN_List.xlsx using MID.
    5. Find MCC from mid_mcc.csv using MID.
    6. Resolve merchant reference.
    7. Call add_amex_account API.
    8. Return result row.

    Args:
        row_number (int): Actual CSV row number for logging.
        row (pandas.Series): Row from mid_merchant_info.csv.
        ngen_amex_lookup (dict): MID -> AMEX ID lookup.
        mcc_lookup (dict): MID -> MCC lookup.

    Returns:
        dict: Result row.

    Raises:
        RuntimeError: If any validation or API call fails.
    """

    mid = normalize_value(row["mid"])
    attached_to_node_reference = normalize_value(row["attached_to_node_reference"])
    mid_reference = normalize_value(row["mid_reference"])
    payment_method = normalize_value(row["payment_method"])
    node_type = normalize_value(row["_type"])

    logging.info("Started processing row number: %s", row_number)
    logging.info("mid: %s", mid)
    logging.info("attached_to_node_reference: %s", attached_to_node_reference)
    logging.info("mid_reference: %s", mid_reference)
    logging.info("payment_method: %s", payment_method)
    logging.info("_type: %s", node_type)

    if not mid:
        raise RuntimeError(f"mid is empty at row {row_number}")

    if not attached_to_node_reference:
        raise RuntimeError(
            f"attached_to_node_reference is empty for MID {mid} at row {row_number}"
        )

    if not mid_reference:
        raise RuntimeError(
            f"mid_reference is empty for MID {mid} at row {row_number}"
        )

    if not node_type:
        raise RuntimeError(
            f"_type is empty for MID {mid} at row {row_number}"
        )

    # If AMEX already exists, do not create another AMEX account.
    if payment_method.upper() == PAYMENT_METHOD_TO_ADD:
        logging.info(
            "Skipping MID %s because AMERICAN_EXPRESS already exists",
            mid
        )

        return build_result(
            row_number=row_number,
            mid=mid,
            status="SKIPPED",
            reason="AMERICAN_EXPRESS already exists",
            attached_to_node_reference=attached_to_node_reference,
            mid_reference=mid_reference,
            payment_method=payment_method,
            node_type=node_type
        )

    # Get AMEX ID from NGEN_List.xlsx
    amex_mid = get_amex_mid_for_mid(mid, ngen_amex_lookup)

    if not amex_mid:
        raise RuntimeError(
            f"AMEX ID not found in NGEN_List.xlsx for MID {mid} at row {row_number}"
        )

    # Get MCC from mid_mcc.csv
    # It will be sent as merchantType in request payload.
    mcc = get_mcc_for_mid(mid, mcc_lookup)
    validate_mcc(mid, mcc)

    logging.info("AMEX ID found for MID %s: %s", mid, amex_mid)
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
        row_number=row_number,
        mid=mid,
        status="SUCCESS",
        reason="AMERICAN_EXPRESS account created successfully",
        attached_to_node_reference=attached_to_node_reference,
        mid_reference=mid_reference,
        payment_method=payment_method,
        node_type=node_type,
        merchant_reference=merchant_reference,
        amex_mid=amex_mid,
        mcc=mcc,
        request_payload=json.dumps(payload),
        response_status_code=response.status_code,
        response_body=response.text
    )