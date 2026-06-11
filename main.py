# main.py

"""
Script entry point.

Input files:
1. mid_merchant_info.csv
   Required columns:
   - mid
   - attached_to_node_reference
   - mid_reference
   - payment_method
   - _type

2. NGEN_List.xlsx
   Required columns:
   - NI MID
   - AMEX ID

3. mid_mcc.csv
   Required columns:
   - mids
   - mcc

Output:
1. amex_account_creation_result_YYYYMMDD_HHMMSS.csv
2. amex_account_creation.log

Behavior:
- Loops over mid_merchant_info.csv row by row.
- Skips rows that already have AMERICAN_EXPRESS.
- For eligible rows:
  - Gets AMEX ID from NGEN_List.xlsx.
  - Gets MCC from mid_mcc.csv.
  - Resolves merchant reference.
  - Calls API to create AMEX account.
- If any unexpected error happens, the script stops immediately.
"""

import sys
import logging
import pandas as pd

from datetime import datetime

from business_logic import (
    process_row,
    build_ngen_amex_lookup,
    build_mcc_lookup
)


MID_MERCHANT_INFO_FILE_PATH = "mid_merchant_info.csv"
NGEN_LIST_FILE_PATH = "NGEN_MCC_AMEX_PAYFAC_test.xlsx"
MID_MCC_FILE_PATH = "mid_mcc.csv"

RESULT_FILE = f"amex_account_creation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
LOG_FILE = "amex_account_creation.log"


def setup_logging():
    """
    Configure logging to write to both:
    1. Console
    2. Log file

    Log format example:
        2026-06-04 14:00:34,338 | INFO | Script started
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )


def validate_required_columns(df, required_columns, file_name):
    """
    Validate that a DataFrame contains all required columns.

    Args:
        df (pandas.DataFrame): Loaded file data.
        required_columns (list): Required column names.
        file_name (str): File name used in error message.

    Raises:
        RuntimeError: If any required column is missing.
    """

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            f"Missing columns in file '{file_name}': {missing_columns}"
        )


def read_input_files():
    """
    Read and validate all input files.

    Returns:
        tuple:
            mid_merchant_info_df
            ngen_df
            mid_mcc_df
    """

    logging.info("Reading CSV file: %s", MID_MERCHANT_INFO_FILE_PATH)

    mid_merchant_info_df = pd.read_csv(
        MID_MERCHANT_INFO_FILE_PATH,
        dtype=str
    )

    validate_required_columns(
        mid_merchant_info_df,
        [
            "mid",
            "attached_to_node_reference",
            "mid_reference",
            "payment_method",
            "_type"
        ],
        MID_MERCHANT_INFO_FILE_PATH
    )

    logging.info("Reading NGEN Excel file: %s", NGEN_LIST_FILE_PATH)

    ngen_df = pd.read_excel(
        NGEN_LIST_FILE_PATH,
        dtype=str
    )

    validate_required_columns(
        ngen_df,
        [
            "NI MID",
            "AMEX ID"
        ],
        NGEN_LIST_FILE_PATH
    )

    logging.info("Reading MCC CSV file: %s", MID_MCC_FILE_PATH)

    mid_mcc_df = pd.read_csv(
        MID_MCC_FILE_PATH,
        dtype=str
    )

    validate_required_columns(
        mid_mcc_df,
        [
            "mids",
            "mcc"
        ],
        MID_MCC_FILE_PATH
    )

    logging.info("Input files loaded successfully")

    return mid_merchant_info_df, ngen_df, mid_mcc_df


def save_results(results):
    """
    Save processing results to output CSV.

    Args:
        results (list): List of result dictionaries.
    """

    result_df = pd.DataFrame(results)
    result_df.to_csv(RESULT_FILE, index=False)

    logging.info("Result file created: %s", RESULT_FILE)


def main():
    """
    Main execution function.
    """

    setup_logging()

    logging.info("Script started")

    results = []

    try:
        mid_merchant_info_df, ngen_df, mid_mcc_df = read_input_files()

        # Build fast lookup dictionaries before processing rows.
        ngen_amex_lookup = build_ngen_amex_lookup(ngen_df)
        mcc_lookup = build_mcc_lookup(mid_mcc_df)

        total_rows = len(mid_merchant_info_df)

        logging.info("Total rows found in mid_merchant_info.csv: %s", total_rows)

        for index, row in mid_merchant_info_df.iterrows():
            # +2 because CSV row 1 is the header, and pandas index starts from 0.
            row_number = index + 2

            logging.info("----------------------------------------")
            logging.info(
                "[%s/%s] Processing CSV row: %s",
                index + 1,
                total_rows,
                row_number
            )

            result = process_row(
                row_number=row_number,
                row=row,
                ngen_amex_lookup=ngen_amex_lookup,
                mcc_lookup=mcc_lookup
            )

            logging.info(
                "Result for row %s, MID %s: %s - %s",
                row_number,
                result["mid"],
                result["status"],
                result["reason"]
            )

            results.append(result)

        save_results(results)

        logging.info("Script completed successfully")

    except Exception as error:
        logging.exception("Script stopped because an error happened: %s", error)

        # Save whatever results were completed before the failure.
        if results:
            save_results(results)

        sys.exit(1)


if __name__ == "__main__":
    main()