"""XLSX fidelity and upload-boundary tests; no live Drive files."""

import re
from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill

from feishu_bitable_mcp.change_adapters import ChangeAdapters
from feishu_bitable_mcp.change_store import ChangeStore
from feishu_bitable_mcp.changes import ChangeEngine
from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings
from feishu_bitable_mcp.excel_changes import edit_workbook, new_workbook

FOLDER = "https://example.feishu.cn/drive/folder/DemoFolderToken01"
FILE = "https://example.feishu.cn/file/DemoFileToken001"
EDITS = [
    {"sheet": "Sheet", "cell": "A1", "value": " Changed & <escaped> "},
    {"sheet": "Sheet", "cell": "C3", "value": {"type": "formula", "text": "=B1*3"}},
    {"sheet": "Sheet", "cell": "B12", "value": True},
]


def workbook():
    book = Workbook()
    page = book.active
    page.append(["Before", 2, "=B1*2"])
    page.append(["Second", 3, 4])
    page["A1"].font = Font(bold=True, color="00FF00")
    page["A1"].fill = PatternFill("solid", fgColor="FFFF00")
    page["B1"].number_format = "0.00"
    page.merge_cells("D4:E5")
    page["D4"] = "Merged"
    page.freeze_panes = "B2"
    chart = BarChart()
    chart.add_data(Reference(page, min_col=2, min_row=1, max_row=2))
    page.add_chart(chart, "G1")
    book.create_sheet("Untouched")["A1"] = "Keep me"
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def replace_part(content, part, replacement):
    result = BytesIO()
    with ZipFile(BytesIO(content)) as src, ZipFile(result, "w") as dst:
        for item in src.infolist():
            value = replacement(src.read(item)) if item.filename == part else src.read(item)
            dst.writestr(item, value)
    return result.getvalue()


def test_surgical_edits_preserve_styles_formula_other_sheet_chart_and_zip_parts():
    source = workbook()
    result = edit_workbook(source, EDITS)
    with ZipFile(BytesIO(source)) as before, ZipFile(BytesIO(result)) as after:
        assert before.namelist() == after.namelist()
        changed = [path for path in before.namelist() if before.read(path) != after.read(path)]
        assert set(changed) == {"xl/workbook.xml", "xl/worksheets/sheet1.xml"}
    book = load_workbook(BytesIO(result))
    try:
        page = book["Sheet"]
        assert page["A1"].value == " Changed & <escaped> "
        assert page["A1"].font.bold and page["A1"].font.color.rgb == "0000FF00"
        assert page["A1"].fill.fgColor.rgb == "00FFFF00"
        assert page["B1"].number_format == "0.00" and page["C1"].value == "=B1*2"
        assert page["C3"].value == "=B1*3" and page["B12"].value is True
        assert len(page._charts) == 1 and str(page.merged_cells) == "D4:E5"
        assert page.freeze_panes == "B2" and book["Untouched"]["A1"].value == "Keep me"
        assert book.calculation.fullCalcOnLoad and book.calculation.forceFullCalc
    finally:
        book.close()


@pytest.mark.parametrize(
    "edits",
    [
        [{"sheet": "Sheet", "cell": "E5", "value": "Merged interior"}],
        [{"sheet": "Missing", "cell": "A1", "value": "bad"}],
        [{"sheet": "Sheet", "cell": "XFE1", "value": 1}],
        [{"sheet": "Sheet", "cell": "A1", "value": "=1+2"}],
        [{"sheet": "Sheet", "cell": "A1", "value": 1}] * 2,
    ],
)
def test_invalid_excel_edits_do_not_return_a_file(edits):
    with pytest.raises(BitableError):
        edit_workbook(workbook(), edits)


@pytest.mark.parametrize(
    "part,transform",
    [
        ("xl/worksheets/sheet1.xml", lambda b: b.replace(b"<f>", b'<f t="array">')),
        (
            "xl/worksheets/sheet1.xml",
            lambda b: b.replace(b"<sheetData>", b'<sheetProtection sheet="1"/><sheetData>'),
        ),
        (
            "xl/workbook.xml",
            lambda b: re.sub(
                rb"<workbookProtection\s*/>", b'<workbookProtection lockStructure="1"/>', b
            ),
        ),
    ],
)
def test_reject_unsupported_formula_or_protection(part, transform):
    source = replace_part(workbook(), part, transform)
    with pytest.raises(BitableError):
        edit_workbook(source, EDITS)


def test_new_workbook_includes_formulas_without_executing_them():
    content = new_workbook(
        {
            "file_name": "Example.xlsx",
            "worksheets": [
                {
                    "name": "Data",
                    "values": [["Value", "Double"], [2, {"type": "formula", "text": "=A2*2"}]],
                },
            ],
        }
    )
    book = load_workbook(BytesIO(content))
    try:
        assert book.sheetnames == ["Data"] and book["Data"]["B2"].value == "=A2*2"
    finally:
        book.close()


def test_xlsx_text_is_never_silently_truncated():
    with pytest.raises(BitableError, match="32767"):
        new_workbook(
            {
                "file_name": "Demo.xlsx",
                "worksheets": [
                    {"name": "Data", "values": [["x" * 32768]]},
                ],
            }
        )
    with pytest.raises(BitableError, match="32767"):
        edit_workbook(workbook(), [{"sheet": "Sheet", "cell": "A1", "value": "x" * 32768}])


@pytest.mark.parametrize("operation", ["excel.create", "excel.edit"])
async def test_upload_after_confirmation_only_and_same_token_for_overwrite(tmp_path, operation):
    source = workbook()
    calls = []

    def upstream(request):
        if request.url.path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "fictional", "expire": 3600}
            )
        if request.method == "GET":
            return httpx.Response(
                200, content=source, headers={"Content-Type": "application/octet-stream"}
            )
        calls.append(request)
        body = request.content
        assert b'name="size"' in body and b'name="file"' in body
        if operation == "excel.edit":
            assert b'name="file_token"' in body and b"DemoFileToken001" in body
        else:
            assert b'name="file_token"' not in body
        return httpx.Response(200, json={"code": 0, "data": {"file_token": "DemoFileToken001"}})

    url = FOLDER if operation == "excel.create" else FILE
    settings = Settings(
        "fictional-app",
        "fictional-secret",
        auth_token="x" * 40,
        enable_changes=True,
        change_policy={operation: [url]},
        excel_overwrite_folder_url=FOLDER,
    )
    api = FeishuClient(settings, transport=httpx.MockTransport(upstream))
    engine = ChangeEngine(settings, ChangeAdapters(api), ChangeStore(str(tmp_path / "receipts.db")))
    payload = (
        {"file_name": "Example.xlsx", "cells": EDITS}
        if operation == "excel.edit"
        else {
            "file_name": "Example.xlsx",
            "worksheets": [{"name": "Data", "values": [[1, 2]]}],
        }
    )
    try:
        plan = await engine.prepare(operation, url, payload, "excel-example-01")
        assert not calls
        result = await engine.commit(plan["plan_id"], plan["confirmation_digest"], True)
        assert result["receipt"]["file_token"] == "DemoFileToken001" and len(calls) == 1
    finally:
        await api.close()


async def test_overwrite_is_disabled_without_operator_upload_folder():
    settings = Settings("fictional-app", "fictional-secret", auth_token="x" * 40)
    api = FeishuClient(settings)
    try:
        with pytest.raises(BitableError, match="disabled"):
            await ChangeAdapters(api).prepare(
                "excel.edit", FILE, {"file_name": "Example.xlsx", "cells": EDITS}, "excel-01"
            )
    finally:
        await api.close()


async def test_changed_file_and_mismatched_response_token_are_not_reported_success(tmp_path):
    state = {"content": workbook(), "writes": 0}

    def reply(request):
        if request.url.path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "fictional", "expire": 3600}
            )
        if request.method == "GET":
            return httpx.Response(200, content=state["content"])
        state["writes"] += 1
        return httpx.Response(200, json={"code": 0, "data": {"file_token": "DifferentFileToken01"}})

    settings = Settings(
        "fictional-app",
        "fictional-secret",
        auth_token="x" * 40,
        enable_changes=True,
        change_policy={"excel.edit": [FILE]},
        excel_overwrite_folder_url=FOLDER,
    )
    api = FeishuClient(settings, transport=httpx.MockTransport(reply))
    engine = ChangeEngine(settings, ChangeAdapters(api), ChangeStore(str(tmp_path / "receipts.db")))
    payload = {"file_name": "Example.xlsx", "cells": EDITS}
    try:
        plan = await engine.prepare("excel.edit", FILE, payload, "excel-conflict-01")
        state["content"] += b"changed"
        with pytest.raises(BitableError, match="changed after preview"):
            await engine.commit(plan["plan_id"], plan["confirmation_digest"], True)
        assert state["writes"] == 0
        plan = await engine.prepare("excel.edit", FILE, payload, "excel-mismatch-01")
        with pytest.raises(BitableError, match="expected file token"):
            await engine.commit(plan["plan_id"], plan["confirmation_digest"], True)
        assert engine.status("excel-mismatch-01")["status"] == "unknown"
        await engine.commit(plan["plan_id"], plan["confirmation_digest"], True)
        assert state["writes"] == 1
    finally:
        await api.close()
