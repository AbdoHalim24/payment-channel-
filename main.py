# main.py

"""
Main script.

Current behavior:
1. Read NGEN Excel file.
2. Add processed column if missing.
3. Add processing_reason column if missing.
4. Loop over NGEN rows.
5. Skip rows where processed == YES.
6. Use NI MID as MID.
7. Use AMEX ID as amexMid.
8. Use mid_merchant_info.csv to get merchant/mid details.
9. Use mid_mcc.csv to get MCC.
10. Add AMEX account.
11. Update the same NGEN Excel file with processing status.
12. Save progress after every row.
13. Stop immediately if any error happens.

Important:
- This script updates the same NGEN file directly.
- Keep a backup of the original file before running.
"""

import sys
import logging
import pandas as pd

from datetime import datetime

from business_logic import (
    process_ngen_row,
    build_mcc_lookup,
    normalize_value
)


# Main third-party NGEN file.
# The script will read from and write back to this same file.
NGEN_LIST_FILE_PATH = "amex_task.xlsx"

#Database iformation
MID_MERCHANT_INFO_FILE_PATH = "MID-merchant-Info.csv"
MID_MCC_FILE_PATH = "MID-MCC.csv"

RESULT_FILE = f"amex_account_creation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
LOG_FILE = "amex_account_creation.log"


def setup_logging():
    """
    Configure logging to console and file.
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
    Check that required columns exist in the file.
    """

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            f"Missing columns in file '{file_name}': {missing_columns}"
        )


def ensure_tracking_columns(ngen_df):
    """
    Add tracking columns to the NGEN file if missing.

    processed:
        YES     -> row already processed successfully or skipped because AMEX exists
        FAILED  -> row failed

    processing_reason:
        Human-readable reason.
    """

    if "processed" not in ngen_df.columns:
        ngen_df["processed"] = ""

    if "processing_reason" not in ngen_df.columns:
        ngen_df["processing_reason"] = ""

    return ngen_df


def read_input_files():
    """
    Read all input files:
    - NGEN Excel file
    - mid_merchant_info.csv
    - mid_mcc.csv
    """

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

    ngen_df = ensure_tracking_columns(ngen_df)

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

    return ngen_df, mid_merchant_info_df, mid_mcc_df


def save_ngen_file(ngen_df):
    """
    Save updated processing status back to the same NGEN file.
    """

    ngen_df.to_excel(NGEN_LIST_FILE_PATH, index=False)

    logging.info("NGEN file updated: %s", NGEN_LIST_FILE_PATH)


def save_results(results):
    """
    Save processing results to CSV.
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
    logging.info("NGEN file: %s", NGEN_LIST_FILE_PATH)

    results = []

    try:
        ngen_df, mid_merchant_info_df, mid_mcc_df = read_input_files()

        mcc_lookup = build_mcc_lookup(mid_mcc_df)

        total_rows = len(ngen_df)

        logging.info("Total rows found in NGEN file: %s", total_rows)

        for index, row in ngen_df.iterrows():
            row_number = index + 2

            processed_value = normalize_value(row.get("processed")).upper()

            if processed_value == "YES":
                logging.info(
                    "Skipping NGEN row %s because processed = YES",
                    row_number
                )
                continue

            logging.info("----------------------------------------")
            logging.info(
                "[%s/%s] Processing NGEN row: %s",
                index + 1,
                total_rows,
                row_number
            )

            try:
                result = process_ngen_row(
                    row_number=row_number,
                    ngen_row=row,
                    mid_merchant_info_df=mid_merchant_info_df,
                    mcc_lookup=mcc_lookup
                )

                ngen_df.at[index, "processed"] = result["processed"]
                ngen_df.at[index, "processing_reason"] = result["processing_reason"]

                logging.info(
                    "Result for NGEN row %s, MID %s: %s - %s",
                    row_number,
                    result["mid"],
                    result["processed"],
                    result["processing_reason"]
                )

                results.append(result)

                # Save after every processed/skipped row.
                # This prevents losing progress if the script stops later.
                save_ngen_file(ngen_df)

            except Exception as row_error:
                error_message = str(row_error)

                logging.exception(
                    "Error happened while processing NGEN row %s: %s",
                    row_number,
                    error_message
                )

                ngen_df.at[index, "processed"] = "FAILED"
                ngen_df.at[index, "processing_reason"] = error_message

                failed_mid = normalize_value(row.get("NI MID"))

                results.append({
                    "mid": failed_mid,
                    "processed": "FAILED",
                    "processing_reason": error_message
                })

                save_ngen_file(ngen_df)
                save_results(results)

                logging.error("Script stopped because an error happened.")
                sys.exit(1)

        save_ngen_file(ngen_df)
        save_results(results)

        logging.info("Script completed successfully")

    except Exception as error:
        logging.exception("Script stopped because an error happened: %s", error)

        if results:
            save_results(results)

        sys.exit(1)


if __name__ == "__main__":
    main()