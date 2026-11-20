"""Bounded, read-only OOXML parsing. No extraction, macro or formula execution."""

from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .config import BitableError


def read_excel(content: bytes, sheet: str | None, start_row: int, rows: int,
               start_column: int, columns: int, data_only: bool):
    if (
        not 1 <= start_row <= 1_048_576 or not 1 <= start_column <= 16_384
        or rows < 1 or columns < 1 or rows * columns > 5000
        or start_row + rows - 1 > 1_048_576 or start_column + columns - 1 > 16_384
    ):
        raise BitableError("Choose a valid Excel window containing at most 5000 cells.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > 10000 or sum(x.file_size for x in entries) > 100 * 1024 * 1024
                or any(x.flag_bits & 1 for x in entries)
                or "xl/workbook.xml" not in archive.namelist()
                or "xl/vbaProject.bin" in archive.namelist()
            ):
                raise BitableError("Excel is encrypted, invalid or exceeds archive safety limits.")
        book = load_workbook(
            BytesIO(content), read_only=True, data_only=data_only, keep_links=False
        )
        try:
            names = book.sheetnames
            chosen = sheet or names[0]
            if chosen not in names:
                raise BitableError("Requested worksheet is absent; use a name from worksheets.")
            page = book[chosen]
            values = []
            for row in page.iter_rows(
                min_row=start_row, max_row=start_row + rows - 1,
                min_col=start_column, max_col=start_column + columns - 1,
            ):
                record = []
                for cell in row:
                    value = cell.value
                    if isinstance(value, (date, datetime, time)):
                        value = value.isoformat()
                    record.append({
                        "value": value, "data_type": cell.data_type,
                        "number_format": cell.number_format,
                    })
                values.append(record)
            has_more = page.max_row is None or page.max_row >= start_row + rows
            return {
                "worksheets": names, "worksheet": chosen,
                "start_row": start_row, "start_column": start_column,
                "rows": values, "data_only": data_only,
                "declared_max_row": page.max_row, "declared_max_column": page.max_column,
                "has_more": has_more, "next_row": start_row + rows if has_more else None,
                "formula_note": "Formulas are not evaluated; cached values may be absent or stale.",
            }
        finally:
            book.close()
    except BitableError:
        raise
    except (
        BadZipFile, KeyError, ValueError, OSError, IndexError, ParseError,
        DefusedXmlException, InvalidFileException,
    ):
        raise BitableError(
            "Cannot read this .xlsx file; legacy .xls and passwords are unsupported."
        ) from None
