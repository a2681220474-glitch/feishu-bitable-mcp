"""Bounded XLSX creation and surgical OOXML cell edits without workbook reserialization."""

from __future__ import annotations

import asyncio
import hashlib
import posixpath
import re
from io import BytesIO
from xml.etree.ElementTree import ParseError
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from openpyxl import Workbook
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter, range_boundaries

from .bitable_changes import name
from .change_policy import OPERATIONS, target_key
from .config import BitableError
from .resources import MAX_DOWNLOAD, ResourceClient
from .sheet_changes import values_matrix

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CELL = re.compile(r"[A-Z]{1,3}[1-9][0-9]{0,6}")


def filename(value):
    name(value, 250)
    if not value.endswith(".xlsx") or any(c in value for c in '/\\:*?"<>|'):
        raise BitableError("file_name must be a plain .xlsx filename, without a directory.")
    return value


def excel_value(value):
    values_matrix([[value]])
    text = value.get("text", "") if isinstance(value, dict) else value
    if isinstance(text, str) and len(text) > (8192 if isinstance(value, dict) else 32767):
        raise BitableError("XLSX text exceeds 32767 characters or formula exceeds 8192 characters.")
    return value


def new_workbook(payload):
    if set(payload) != {"file_name", "worksheets"}:
        raise BitableError("New Excel accepts file_name and worksheets only.")
    filename(payload["file_name"])
    sheets = payload["worksheets"]
    if not isinstance(sheets, list) or not 1 <= len(sheets) <= 20:
        raise BitableError("Provide 1-20 worksheets with name and rectangular values.")
    book = Workbook()
    book.remove(book.active)
    titles, total = set(), 0
    try:
        for sheet in sheets:
            if not isinstance(sheet, dict) or set(sheet) != {"name", "values"}:
                raise BitableError("Each worksheet accepts name and values only.")
            title = name(sheet["name"], 31)
            if any(c in title for c in "/\\?*:[]") or title.casefold() in titles:
                raise BitableError("Worksheet titles must be valid and case-insensitively unique.")
            titles.add(title.casefold())
            values = values_matrix(sheet["values"])
            total += sum(map(len, values))
            if total > 5000:
                raise BitableError("New workbook exceeds 5000 cells.")
            page = book.create_sheet(title)
            for row in values:
                for cell in row:
                    excel_value(cell)
                page.append([v["text"] if isinstance(v, dict) else v for v in row])
        output = BytesIO()
        book.save(output)
        return output.getvalue()
    finally:
        book.close()


def cell_xml(old: str | None, address: str, value, prefix: str):
    # Validation shares the public scalar/formula contract with online Sheets.
    excel_value(value)
    q = prefix + "c"
    if old:
        opening = re.match(r"<[^\s/>]+([^>]*?)/?>", old)
        attrs = re.sub(r'\s+t\s*=\s*["\x27][^"\x27]*["\x27]', "", opening[1])
        attrs = attrs.rstrip().rstrip("/")
    else:
        attrs = f' r="{address}"'
    if value is None:
        return f"<{q}{attrs}/>"
    if isinstance(value, dict):
        content = f"<{prefix}f>{escape(value['text'][1:])}</{prefix}f>"
    elif isinstance(value, str):
        attrs += ' t="inlineStr"'
        content = (
            f'<{prefix}is><{prefix}t xml:space="preserve">{escape(value)}</{prefix}t></{prefix}is>'
        )
    else:
        if type(value) is bool:
            attrs += ' t="b"'
            value = int(value)
        content = f"<{prefix}v>{value}</{prefix}v>"
    return f"<{q}{attrs}>{content}</{q}>"


def replace_cell(xml: str, address: str, value):
    data = re.search(r"<((?:\w+:)?)sheetData\b[^>]*(?:/>|>.*?</\1sheetData>)", xml, re.S)
    if not data:
        raise BitableError("Unsupported worksheet XML: no sheetData.")
    prefix = data[1]
    content = data[0]
    row_num, col = coordinate_to_tuple(address)
    rows = list(
        re.finditer(
            rf'<{prefix}row\b[^>]*\br=["\x27](\d+)["\x27][^>]*(?:/>|>.*?</{prefix}row>)',
            content,
            re.S,
        )
    )
    row = next((r for r in rows if int(r[1]) == row_num), None)
    if row:
        cells = list(
            re.finditer(
                rf'<{prefix}c\b[^>]*\br=["\x27]([A-Z]+\d+)["\x27][^>]*(?:/>|>.*?</{prefix}c>)',
                row[0],
                re.S,
            )
        )
        cell = next((c for c in cells if c[1] == address), None)
        replacement = cell_xml(cell[0] if cell else None, address, value, prefix)
        if cell:
            updated = row[0][: cell.start()] + replacement + row[0][cell.end() :]
        else:
            after = next((c for c in cells if coordinate_to_tuple(c[1])[1] > col), None)
            if row[0].endswith("/>"):
                updated = row[0][:-2] + ">" + replacement + f"</{prefix}row>"
            else:
                at = after.start() if after else row[0].rfind(f"</{prefix}row>")
                updated = row[0][:at] + replacement + row[0][at:]
        content = content[: row.start()] + updated + content[row.end() :]
    else:
        replacement = (
            f'<{prefix}row r="{row_num}">{cell_xml(None, address, value, prefix)}</{prefix}row>'
        )
        after = next((r for r in rows if int(r[1]) > row_num), None)
        if content.endswith("/>"):
            content = content[:-2] + ">" + replacement + f"</{prefix}sheetData>"
        else:
            at = after.start() if after else content.rfind(f"</{prefix}sheetData>")
            content = content[:at] + replacement + content[at:]
    result = xml[: data.start()] + content + xml[data.end() :]
    # Include inserted cells in the declared used range (no sheet structure recreation).
    dim = re.search(r'<(?:\w+:)?dimension\b[^>]*\bref=["\x27]([^"\x27]+)["\x27][^>]*/>', result)
    if dim:
        min_col, min_row, max_col, max_row = range_boundaries(dim[1])
        new_range = (
            f"{get_column_letter(min(min_col, col))}{min(min_row, row_num)}:"
            f"{get_column_letter(max(max_col, col))}{max(max_row, row_num)}"
        )
        result = result[: dim.start(1)] + new_range + result[dim.end(1) :]
    return result


def edit_workbook(content: bytes, edits):
    if not isinstance(edits, list) or not 1 <= len(edits) <= 5000:
        raise BitableError("Provide 1-5000 explicit cell edits.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = archive.namelist()
            if (
                len(content) > MAX_DOWNLOAD
                or len(entries) > 10000
                or len(set(names)) != len(names)
                or sum(x.file_size for x in entries) > 100 * 1024 * 1024
                or any(x.flag_bits & 1 for x in entries)
                or any("vba" in x.lower() or "_xmlsignatures" in x.lower() for x in names)
            ):
                raise BitableError("Unsupported encrypted, signed, macro or oversized workbook.")
            workbook = archive.read("xl/workbook.xml")
            content_types = archive.read("[Content_Types].xml").lower()
            if b"macroenabled" in content_types or b"vba" in content_types:
                raise BitableError("Macro workbooks are unsupported.")
            book = fromstring(workbook)
            protection = book.find(f"{{{NS}}}workbookProtection")
            if book.tag != f"{{{NS}}}workbook" or protection is not None and protection.attrib:
                raise BitableError("Only unprotected, standard transitional XLSX is supported.")
            relations = fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            paths = {
                item.attrib["Id"]: posixpath.normpath(posixpath.join("xl", item.attrib["Target"]))
                if not item.attrib["Target"].startswith("/")
                else item.attrib["Target"].lstrip("/")
                for item in relations
                if item.attrib.get("TargetMode") != "External"
            }
            sheets = {
                s.attrib["name"]: paths.get(s.attrib[f"{{{REL}}}id"])
                for s in book.find(f"{{{NS}}}sheets")
            }
            updated, parsed, seen = {}, {}, set()
            for edit in edits:
                if not isinstance(edit, dict) or set(edit) != {"sheet", "cell", "value"}:
                    raise BitableError("Each edit needs sheet, cell and value only.")
                title, address, value = edit["sheet"], edit["cell"], edit["value"]
                if not isinstance(title, str) or title not in sheets:
                    raise BitableError("Choose an existing worksheet name.")
                if not isinstance(address, str) or not CELL.fullmatch(address):
                    raise BitableError("Use an uppercase cell address such as B2.")
                row, col = coordinate_to_tuple(address)
                if row > 1048576 or col > 16384 or (title, address) in seen:
                    raise BitableError("Cell is out of bounds or repeated in this change.")
                seen.add((title, address))
                part = sheets[title]
                if not part or not re.fullmatch(r"xl/worksheets/[A-Za-z0-9_.-]+\.xml", part):
                    raise BitableError("Unsupported worksheet relationship target.")
                if part not in parsed:
                    source = archive.read(part)
                    root = fromstring(source)
                    if root.find(f"{{{NS}}}sheetProtection") is not None:
                        raise BitableError("Protected worksheets cannot be edited.")
                    if any(f.attrib for f in root.iter(f"{{{NS}}}f")):
                        raise BitableError(
                            "Shared, array and data-table formulas are not editable yet."
                        )
                    parsed[part] = root
                    updated[part] = source.decode("utf-8")
                root = parsed[part]
                for merged in root.iter(f"{{{NS}}}mergeCell"):
                    left, top, right, bottom = range_boundaries(merged.attrib["ref"])
                    if left <= col <= right and top <= row <= bottom and (row, col) != (top, left):
                        raise BitableError("Edit the top-left cell of a merged range only.")
                old = next(
                    (c for c in root.iter(f"{{{NS}}}c") if c.attrib.get("r") == address), None
                )
                if old is not None and any(
                    c.tag not in {f"{{{NS}}}{t}" for t in ("v", "f", "is")} for c in old
                ):
                    raise BitableError("The selected cell has unsupported extended content.")
                if "xl/calcChain.xml" in names and (
                    isinstance(value, dict)
                    or old is not None
                    and old.find(f"{{{NS}}}f") is not None
                ):
                    raise BitableError(
                        "Formula edits with calcChain are not supported; no upload performed."
                    )
                updated[part] = replace_cell(updated[part], address, value)
            # Keep every unrelated ZIP entry byte-identical after decompression, including charts.
            book_xml = workbook.decode("utf-8")
            calc = re.search(r"<(?:\w+:)?calcPr\b[^>]*/>", book_xml)
            prefix_match = re.search(r"<((?:\w+:)?)workbook\b", book_xml)
            prefix = prefix_match[1]
            replacement = f'<{prefix}calcPr calcId="0" fullCalcOnLoad="1" forceFullCalc="1"/>'
            if calc:
                # Preserve iteration and other existing calculation settings.
                replacement = calc[0]
                for key, value in {
                    "calcId": "0",
                    "fullCalcOnLoad": "1",
                    "forceFullCalc": "1",
                }.items():
                    pattern = rf'\s+{key}\s*=\s*["\x27][^"\x27]*["\x27]'
                    replacement = re.sub(pattern, "", replacement)
                    replacement = replacement[:-2] + f' {key}="{value}"/>'
                book_xml = book_xml[: calc.start()] + replacement + book_xml[calc.end() :]
            else:
                successor = re.search(
                    rf"<{prefix}(?:oleSize|customWorkbookViews|pivotCaches|smartTagPr|smartTagTypes|"
                    rf"webPublishing|fileRecoveryPr|webPublishObjects|extLst)\b",
                    book_xml,
                )
                at = successor.start() if successor else book_xml.rfind(f"</{prefix}workbook>")
                book_xml = book_xml[:at] + replacement + book_xml[at:]
            updated["xl/workbook.xml"] = book_xml
            output = BytesIO()
            with ZipFile(output, "w") as destination:
                for item in entries:
                    value = updated.get(item.filename)
                    if value is not None:
                        fromstring(value)
                    destination.writestr(
                        item, value.encode("utf-8") if value is not None else archive.read(item)
                    )
            result = output.getvalue()
            if len(result) > MAX_DOWNLOAD:
                raise BitableError("Edited workbook exceeds the 20 MiB upload limit.")
            return result
    except BitableError:
        raise
    except (
        BadZipFile,
        KeyError,
        ValueError,
        TypeError,
        AttributeError,
        DefusedXmlException,
        ParseError,
        UnicodeError,
    ):
        raise BitableError("Cannot safely edit this XLSX; no upload was performed.") from None


class ExcelChanges:
    def __init__(self, api):
        self.api = api
        self.resources = ResourceClient(api)

    async def prepare(self, operation, url, payload, request_id):
        _, token, _ = target_key(url, OPERATIONS[operation].target_kind)
        original_hash, existing = None, None
        if operation == "excel.create":
            content = await asyncio.to_thread(new_workbook, payload)
            folder = token
        elif operation == "excel.edit":
            folder_url = self.api.settings.excel_overwrite_folder_url
            if not folder_url:
                raise BitableError(
                    "Excel overwrite is experimental and disabled; configure its upload folder."
                )
            _, folder, _ = target_key(folder_url, "folder")
            if set(payload) != {"file_name", "cells"}:
                raise BitableError("Excel edit accepts file_name and explicit cells only.")
            filename(payload["file_name"])
            original = await self.resources.download_excel(url)
            original_hash = hashlib.sha256(original).hexdigest()
            content = await asyncio.to_thread(edit_workbook, original, payload["cells"])
            existing = token
        else:
            raise BitableError("Unsupported Excel operation.")
        return {
            "operation": operation,
            "url": url,
            "content": content,
            "memory_bytes": len(content),
            "file_name": payload["file_name"],
            "folder": folder,
            "existing": existing,
            "snapshot": original_hash,
            "preconditions": {
                "original_sha256": original_hash,
                "upload_sha256": hashlib.sha256(content).hexdigest(),
                "upload_bytes": len(content),
                "upload_folder_url": self.api.settings.excel_overwrite_folder_url
                if existing
                else url,
                "atomic_compare_and_swap": False,
                "note": "No formulas executed. Recalculate in Excel to refresh caches. Uses "
                "the official CLI's file_token transport, not document version creation. "
                "This transport still needs live acceptance testing; external writers may race.",
            },
        }

    async def check(self, prepared):
        if prepared["existing"]:
            content = await self.resources.download_excel(prepared["url"])
            if hashlib.sha256(content).hexdigest() != prepared["snapshot"]:
                raise BitableError("Excel changed after preview; prepare again.")

    async def dispatch(self, prepared):
        form = {
            "file_name": prepared["file_name"],
            "parent_type": "explorer",
            "parent_node": prepared["folder"],
            "size": str(len(prepared["content"])),
        }
        if prepared["existing"]:
            form["file_token"] = prepared["existing"]
        data = await self.api.request(
            "POST",
            "/drive/v1/files/upload_all",
            data=form,
            files={
                "file": (
                    prepared["file_name"],
                    prepared["content"],
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        token = data.get("file_token")
        if (
            not isinstance(token, str)
            or not token
            or prepared["existing"]
            and token != prepared["existing"]
        ):
            raise BitableError(
                "Upload did not confirm the expected file token; inspect before retrying."
            )
        return {
            "operation": prepared["operation"],
            "file_token": token,
            "upload_sha256": prepared["preconditions"]["upload_sha256"],
        }
