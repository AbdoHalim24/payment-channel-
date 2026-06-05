# business_logic.py

import json
import logging
import pandas as pd

from ServiceApi import ServiceAPI


PAYMENT_METHOD_TO_ADD = "AMERICAN_EXPRESS"


def normalize_value(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_mid(value):
    """
    Normalize MID/PRDF for matching.

    Keeps the original value as string, but removes spaces.
    """
    return normalize_value(value)


def normalize_mid_without_leading_zeroes(value):
    """
    Used as fallback matching only.

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
    Calls API function and returns:
        status_code, response_json
    """

    response = api_function(*args)

    try:
        response_body = response.json()
    except ValueError:
        response_body = {}

    return response.status_code, response_body


def to_api_node_type(node_type):
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
    Build lookup from NGEN_List.xlsx.

    PRDF    -> MID
    AMEX ID -> amexMid value

    Stores two lookup keys:
        1. Exact PRDF, e.g. 001110255270
        2. Fallback PRDF without leading zeroes, e.g. 1110255270
    """

    lookup = {}

    for _, row in ngen_df.iterrows():
        prdf = normalize_mid(row["PRDF"])
        amex_id = normalize_value(row["AMEX ID"])

        if not prdf:
            continue

        if not amex_id:
            continue

        # Exact key: keeps leading zeroes
        lookup[prdf] = amex_id

        # Fallback key: removes only leading zeroes
        normalized_prdf = normalize_mid_without_leading_zeroes(prdf)

        if normalized_prdf and normalized_prdf not in lookup:
            lookup[normalized_prdf] = amex_id

    logging.info("NGEN AMEX lookup created with %s keys", len(lookup))

    return lookup


def get_amex_mid_for_mid(mid, ngen_amex_lookup):
    """
    Fetch AMEX ID for a MID.

    Matching order:
        1. Exact MID match, e.g. 001110255270
        2. Fallback MID without leading zeroes, e.g. 1110255270
    """

    exact_mid = normalize_mid(mid)

    if not exact_mid:
        return ""

    # First try exact match with leading zeroes
    amex_mid = ngen_amex_lookup.get(exact_mid)

    if amex_mid:
        return amex_mid

    # Then try fallback without leading zeroes
    fallback_mid = normalize_mid_without_leading_zeroes(exact_mid)

    if not fallback_mid:
        return ""

    return ngen_amex_lookup.get(fallback_mid, "")

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
    request_payload="",
    response_status_code="",
    response_body=""
):
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
        "request_payload": request_payload,
        "response_status_code": response_status_code,
        "response_body": response_body
    }


def find_merchant_from_parents(parents):
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


def process_row(row_number, row, ngen_amex_lookup):
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

    amex_mid = get_amex_mid_for_mid(mid, ngen_amex_lookup)

    if not amex_mid:
        raise RuntimeError(
            f"AMEX ID not found in NGEN_List.xlsx for MID {mid} at row {row_number}"
        )

    logging.info("AMEX ID found for MID %s: %s", mid, amex_mid)

    merchant_reference = resolve_merchant_reference(
        attached_to_node_reference=attached_to_node_reference,
        node_type=node_type
    )

    response, payload = ServiceAPI.add_amex_account(
        merchant_reference=merchant_reference,
        mid_reference=mid_reference,
        amex_mid=amex_mid
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
        request_payload=json.dumps(payload),
        response_status_code=response.status_code,
        response_body=response.text
    )