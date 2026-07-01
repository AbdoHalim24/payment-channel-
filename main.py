# main.py

"""
Script entry point.

This script reads:
1. mid_mcc.csv
2. mid_merchant_info.csv

It updates mid_mcc.csv directly by adding/updating:
- processed
- processing_reason

Behavior:
- Main loop is over mid_mcc.csv.
- Rows with processed = YES are skipped.
- Successful rows are saved immediately.
- Failed row is marked FAILED and saved immediately.
- Script stops on first error.
"""

import sys
import logging
import pandas as pd

from datetime import datetime

from business_logic import (
    process_mid_mcc_row,
    normalize_value
)


MID_MCC_FILE_PATH = "mid_mcc.csv"
MID_MERCHANT_INFO_FILE_PATH = "mid_merchant_info.csv"

RESULT_FILE = f"account_creation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
LOG_FILE = "account_creation.log"


def setup_logging():
    """
    Configure logs to be written to:
    1. Console
    2. account_creation.log
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
    Validate required columns exist in a DataFrame.
    """

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            f"Missing columns in file '{file_name}': {missing_columns}"
        )


def ensure_tracking_columns(mid_mcc_df):
    """
    Add tracking columns to mid_mcc.csv if missing.

    processed:
        YES     -> row processed or skipped because account already exists
        FAILED  -> row failed

    processing_reason:
        Explanation of the status.
    """

    if "processed" not in mid_mcc_df.columns:
        mid_mcc_df["processed"] = ""

    if "processing_reason" not in mid_mcc_df.columns:
        mid_mcc_df["processing_reason"] = ""

    return mid_mcc_df


def read_input_files():
    """
    Read and validate input files.
    """

    logging.info("Reading MID MCC CSV file: %s", MID_MCC_FILE_PATH)

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

    mid_mcc_df = ensure_tracking_columns(mid_mcc_df)

    logging.info("Reading merchant info CSV file: %s", MID_MERCHANT_INFO_FILE_PATH)

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

    logging.info("Input files loaded successfully")

    return mid_mcc_df, mid_merchant_info_df


def save_mid_mcc_file(mid_mcc_df):
    """
    Save progress back to mid_mcc.csv.

    This makes the script resumable.
    """

    mid_mcc_df.to_csv(MID_MCC_FILE_PATH, index=False)

    logging.info("MID MCC file updated: %s", MID_MCC_FILE_PATH)


def save_results(results):
    """
    Save result CSV for audit/debugging.
    """

    result_df = pd.DataFrame(results)
    result_df.to_csv(RESULT_FILE, index=False)

    logging.info("Result file created: %s", RESULT_FILE)


def main():
    setup_logging()

    logging.info("Script started")

    results = []

    try:
        mid_mcc_df, mid_merchant_info_df = read_input_files()

        total_rows = len(mid_mcc_df)

        logging.info("Total rows found in mid_mcc.csv: %s", total_rows)

        for index, row in mid_mcc_df.iterrows():
            row_number = index + 2

            processed_value = normalize_value(row.get("processed")).upper()

            if processed_value == "YES":
                logging.info(
                    "Skipping row %s because processed = YES",
                    row_number
                )
                continue

            logging.info("----------------------------------------")
            logging.info(
                "[%s/%s] Processing row: %s",
                index + 1,
                total_rows,
                row_number
            )

            try:
                result = process_mid_mcc_row(
                    row_number=row_number,
                    row=row,
                    mid_merchant_info_df=mid_merchant_info_df
                )

                mid_mcc_df.at[index, "processed"] = result["processed"]
                mid_mcc_df.at[index, "processing_reason"] = result["processing_reason"]

                results.append(result)

                # Save after every successful/skipped row.
                save_mid_mcc_file(mid_mcc_df)

            except Exception as row_error:
                error_message = str(row_error)

                logging.exception(
                    "Error happened while processing row %s: %s",
                    row_number,
                    error_message
                )

                mid_mcc_df.at[index, "processed"] = "FAILED"
                mid_mcc_df.at[index, "processing_reason"] = error_message

                failed_mid = normalize_value(row.get("mids"))

                results.append({
                    "mid": failed_mid,
                    "processed": "FAILED",
                    "processing_reason": error_message
                })

                # Save failure immediately before stopping.
                save_mid_mcc_file(mid_mcc_df)
                save_results(results)

                sys.exit(1)

        save_mid_mcc_file(mid_mcc_df)
        save_results(results)

        logging.info("Script completed successfully")

    except Exception as error:
        logging.exception("Script stopped because an error happened: %s", error)

        if results:
            save_results(results)

        sys.exit(1)


if __name__ == "__main__":
    main()