# main.py

import sys
import logging
import pandas as pd

from datetime import datetime

from business_logic import process_row, build_ngen_amex_lookup


MID_MERCHANT_INFO_FILE_PATH = "mid_merchant_info.csv"
NGEN_LIST_FILE_PATH = "test.xlsx"

RESULT_FILE = f"amex_account_creation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
LOG_FILE = "amex_account_creation.log"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )


def validate_required_columns(df, required_columns, file_name):
    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            f"Missing columns in file '{file_name}': {missing_columns}"
        )


def read_input_files():
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
            "PRDF",
            "AMEX ID"
        ],
        NGEN_LIST_FILE_PATH
    )

    logging.info("Input files loaded successfully")

    return mid_merchant_info_df, ngen_df


def save_results(results):
    result_df = pd.DataFrame(results)
    result_df.to_csv(RESULT_FILE, index=False)

    logging.info("Result file created: %s", RESULT_FILE)


def main():
    setup_logging()

    logging.info("Script started")

    results = []

    try:
        mid_merchant_info_df, ngen_df = read_input_files()

        ngen_amex_lookup = build_ngen_amex_lookup(ngen_df)

        total_rows = len(mid_merchant_info_df)

        logging.info("Total rows found in mid_merchant_info.csv: %s", total_rows)

        for index, row in mid_merchant_info_df.iterrows():
            row_number = index + 2

            logging.info("----------------------------------------")
            logging.info("[%s/%s] Processing CSV row: %s", index + 1, total_rows, row_number)

            result = process_row(
                row_number=row_number,
                row=row,
                ngen_amex_lookup=ngen_amex_lookup
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

        if results:
            save_results(results)

        sys.exit(1)


if __name__ == "__main__":
    main()