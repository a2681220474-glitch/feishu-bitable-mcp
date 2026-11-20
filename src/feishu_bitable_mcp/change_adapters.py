"""Fixed operation routing; no shell, arbitrary URL fetching or Raw API forwarding."""

from .bitable_changes import BitableChanges
from .document_changes import DocumentChanges
from .excel_changes import ExcelChanges
from .sheet_changes import SheetChanges


class ChangeAdapters:
    def __init__(self, api):
        self.adapters = {
            "bitable": BitableChanges(api),
            "document": DocumentChanges(api),
            "sheets": SheetChanges(api),
            "excel": ExcelChanges(api),
        }

    def adapter(self, operation):
        return self.adapters[operation.split(".", 1)[0]]

    async def prepare(self, operation, url, payload, request_id):
        return await self.adapter(operation).prepare(operation, url, payload, request_id)

    async def check(self, prepared):
        await self.adapter(prepared["operation"]).check(prepared)

    async def dispatch(self, prepared):
        return await self.adapter(prepared["operation"]).dispatch(prepared)
