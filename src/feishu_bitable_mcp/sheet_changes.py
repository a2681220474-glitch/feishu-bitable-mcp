"""Named Sheets writes, exact worksheet boundaries and bounded cells/formatting."""

from __future__ import annotations

import math
import re
from urllib.parse import quote

from .bitable_changes import name
from .change_policy import OPERATIONS, target_key
from .changes import fingerprint
from .config import BitableError


def rectangle(area):
    if not isinstance(area, str):
        raise BitableError("range must be a string.")
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6}):([A-Z]{1,3})([1-9][0-9]{0,6})", area or "")
    if not match:
        raise BitableError("range must be an explicit A1 rectangle, e.g. A1:B2.")

    def col(value):
        result = 0
        for char in value:
            result = result * 26 + ord(char) - 64
        return result

    width, height = col(match[3]) - col(match[1]) + 1, int(match[4]) - int(match[2]) + 1
    if width < 1 or height < 1 or width > 100 or height * width > 5000:
        raise BitableError("Use at most 100 columns and 5000 cells in a forward rectangle.")
    return height, width


def values_matrix(value):
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(x, list) and x for x in value)
    ):
        raise BitableError("values must be a nonempty rectangular matrix.")
    width = len(value[0])
    if width > 100 or len(value) * width > 5000 or any(len(x) != width for x in value):
        raise BitableError("values must be rectangular, at most 100 columns and 5000 cells.")
    for row in value:
        for cell in row:
            if cell is None or type(cell) is bool:
                continue
            if type(cell) in {int, float}:
                try:
                    if math.isfinite(cell):
                        continue
                except OverflowError:
                    pass
            if isinstance(cell, str) and len(cell) <= 40000:
                if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", cell):
                    raise BitableError("Cell text contains invalid XML control characters.")
                if cell.startswith("="):
                    raise BitableError(
                        'Use explicit {"type":"formula","text":"=..."} for formulas.'
                    )
                continue
            if isinstance(cell, dict) and set(cell) == {"type", "text"}:
                text = cell["text"]
                if cell["type"] == "formula" and isinstance(text, str) and text.startswith("="):
                    if len(text) <= 40000 and not re.search(
                        r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]",
                        text,
                    ):
                        continue
            raise BitableError(
                "Cells accept null, bool, finite numbers, text or explicit formula objects."
            )
    return value


def basic_style(style):
    if (
        not isinstance(style, dict)
        or not style
        or set(style)
        - {
            "font",
            "formatter",
            "hAlign",
            "vAlign",
            "foreColor",
            "backColor",
        }
    ):
        raise BitableError(
            "Only font, formatter, alignment and foreground/background colors are supported."
        )
    for key, value in style.items():
        if key == "font":
            if (
                not isinstance(value, dict)
                or not value
                or set(value) - {"bold", "italic", "fontSize"}
            ):
                raise BitableError("font supports bold, italic and fontSize only.")
            for item, v in value.items():
                if item == "fontSize":
                    if type(v) is not int or not 9 <= v <= 36:
                        raise BitableError("fontSize must be an integer from 9 to 36.")
                elif type(v) is not bool:
                    raise BitableError("bold and italic must be booleans.")
        elif key in {"foreColor", "backColor"}:
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise BitableError("Colors must be #RRGGBB.")
        elif key in {"hAlign", "vAlign"}:
            if type(value) is not int or value not in {0, 1, 2}:
                raise BitableError("Alignment must be 0, 1 or 2.")
        elif not isinstance(value, str) or not 1 <= len(value) <= 200:
            raise BitableError("formatter must be 1-200 characters.")
    return style


class SheetChanges:
    def __init__(self, api):
        self.api = api

    async def snapshot(self, spec):
        if not spec:
            return None
        token = spec["token"]
        metadata = await self.api.request("GET", f"/sheets/v3/spreadsheets/{token}/sheets/query")
        if not isinstance(metadata.get("sheets"), list):
            raise BitableError("Cannot verify worksheet metadata.")
        result = {"sheets": metadata["sheets"]}
        if spec.get("range"):
            sheet = spec["range"].split("!", 1)[0]
            if not any(x.get("sheet_id") == sheet for x in metadata["sheets"]):
                raise BitableError("Requested worksheet is absent.")
            result["cells"] = await self.api.request(
                "GET",
                f"/sheets/v2/spreadsheets/{token}/values/{quote(spec['range'], safe='')}",
                params={"valueRenderOption": "Formula", "dateTimeRenderOption": "FormattedString"},
            )
            if not isinstance(result["cells"].get("valueRange"), dict):
                raise BitableError("Cannot verify current cell values.")
        return result

    async def prepare(self, operation, url, payload, request_id):
        _, token, url_sheet = target_key(url, OPERATIONS[operation].target_kind)
        query, snapshot_spec, snapshot = {}, None, None
        if operation == "sheets.create":
            if set(payload) != {"title"}:
                raise BitableError("Spreadsheet creation accepts title only.")
            method, route = "POST", "/sheets/v3/spreadsheets"
            body = {"title": name(payload["title"]), "folder_token": token}
        elif operation == "sheets.add_worksheet":
            if url_sheet or set(payload) - {"title", "index"} or "title" not in payload:
                raise BitableError("Add worksheet needs a workbook URL, title and optional index.")
            props = {"title": name(payload["title"], 100)}
            if "index" in payload:
                if type(payload["index"]) is not int or payload["index"] < 0:
                    raise BitableError("index must be a nonnegative integer.")
                props["index"] = payload["index"]
            method, route = "POST", f"/sheets/v2/spreadsheets/{token}/sheets_batch_update"
            body = {"requests": [{"addSheet": {"properties": props}}]}
            snapshot_spec = {"token": token}
        else:
            required = {"range", "style" if operation == "sheets.format_cells" else "values"}
            if set(payload) - required - {"sheet_id"} or not required <= set(payload):
                raise BitableError("Provide range, values (or style), and optional sheet_id only.")
            sheet = payload.get("sheet_id", url_sheet)
            if not isinstance(sheet, str) or not re.fullmatch(r"[A-Za-z0-9]{1,100}", sheet):
                raise BitableError("Choose a worksheet in URL sheet= or payload sheet_id.")
            if url_sheet and sheet != url_sheet:
                raise BitableError(
                    "sheet_id cannot escape the worksheet authorized in the target URL."
                )
            height, width = rectangle(payload["range"])
            area = f"{sheet}!{payload['range']}"
            route = f"/sheets/v2/spreadsheets/{token}"
            if operation == "sheets.format_cells":
                method, route = "PUT", route + "/style"
                body = {"appendStyle": {"range": area, "style": basic_style(payload["style"])}}
            elif operation in {"sheets.write_cells", "sheets.append_cells"}:
                values = values_matrix(payload["values"])
                if len(values) > height or len(values[0]) > width:
                    raise BitableError("values exceed the confirmed target rectangle.")
                if operation == "sheets.write_cells" and (len(values), len(values[0])) != (
                    height,
                    width,
                ):
                    raise BitableError("Write values must exactly fill the confirmed rectangle.")
                body = {"valueRange": {"range": area, "values": values}}
                method = "PUT" if operation == "sheets.write_cells" else "POST"
                route += "/values" if method == "PUT" else "/values_append"
                if method == "POST":
                    query["insertDataOption"] = "INSERT_ROWS"
            else:
                raise BitableError("Unsupported Sheets change.")
            snapshot_spec = {"token": token, "range": area}
        if snapshot_spec:
            snapshot = await self.snapshot(snapshot_spec)
        return {
            "operation": operation,
            "method": method,
            "route": route,
            "body": body,
            "query": query,
            "snapshot_spec": snapshot_spec,
            "snapshot": fingerprint(snapshot),
            "preconditions": {
                "optimistic_snapshot": fingerprint(snapshot),
                "atomic_compare_and_swap": False,
                "note": "External editors may race after snapshot check. Append inserts rows and "
                "may shift cells below the selected area. Formatting snapshots cover values "
                "and worksheet metadata, not every existing cell style.",
            },
        }

    async def check(self, prepared):
        if fingerprint(await self.snapshot(prepared["snapshot_spec"])) != prepared["snapshot"]:
            raise BitableError("Spreadsheet changed after preview; prepare again.")

    async def dispatch(self, prepared):
        data = await self.api.request(
            prepared["method"], prepared["route"], params=prepared["query"], json=prepared["body"]
        )
        operation = prepared["operation"]
        receipt = {"operation": operation}
        if operation == "sheets.create":
            token = data.get("spreadsheet", {}).get("spreadsheet_token")
            if not isinstance(token, str) or not token:
                raise BitableError("No confirmed spreadsheet ID; inspect before retrying.")
            return receipt | {"spreadsheet_token": token}
        if operation == "sheets.add_worksheet":
            replies = data.get("replies", [])
            ids = [x.get("addSheet", {}).get("properties", {}).get("sheetId") for x in replies]
            if len(ids) != 1 or not isinstance(ids[0], str) or not ids[0]:
                raise BitableError("No confirmed worksheet ID; inspect before retrying.")
            return receipt | {"sheet_id": ids[0]}
        if operation == "sheets.format_cells":
            updates = data.get("updates", {})
            if (
                type(updates.get("revision")) is not int
                or updates.get("updatedRange") != prepared["body"]["appendStyle"]["range"]
            ):
                raise BitableError("No confirmed format revision; inspect before retrying.")
            return receipt | {"revision": updates["revision"]}
        updates = data.get("updates", data)
        if not isinstance(updates, dict) or not isinstance(updates.get("updatedRange"), str):
            raise BitableError("No confirmed updated range; inspect before retrying.")
        requested = prepared["body"]["valueRange"]["range"]
        actual = updates["updatedRange"]
        if operation == "sheets.write_cells" and actual != requested:
            raise BitableError("Response does not confirm the exact requested range.")
        if actual.split("!", 1)[0] != requested.split("!", 1)[0]:
            raise BitableError("Response refers to a different worksheet; inspect before retrying.")
        expected = sum(len(row) for row in prepared["body"]["valueRange"]["values"])
        if type(updates.get("updatedCells")) is not int or updates["updatedCells"] != expected:
            raise BitableError("Response does not confirm the requested cell count.")
        return receipt | {
            key: updates[key]
            for key in (
                "updatedRange",
                "updatedRows",
                "updatedColumns",
                "updatedCells",
                "revision",
            )
            if key in updates
        }
