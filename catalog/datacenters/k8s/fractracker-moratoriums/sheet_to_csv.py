"""Write one tab of an .xlsx workbook to CSV, dates as ISO 8601.

usage: sheet_to_csv.py WORKBOOK SHEET OUT_CSV
"""
import csv
import datetime
import sys

import openpyxl


def main(book, sheet, out):
    ws = openpyxl.load_workbook(book, read_only=True, data_only=True)[sheet]
    rows = [r for r in ws.iter_rows(values_only=True) if any(v not in (None, '') for v in r)]
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(['' if v is None else v.date().isoformat() if isinstance(v, datetime.datetime)
                        else str(v).strip() for v in r])
    print(f'{len(rows) - 1} data rows from {sheet!r}')


if __name__ == '__main__':
    main(*sys.argv[1:4])
