from typing import Any

from .api.client import OseonAPIClient


def _field(item: dict[str, Any], name: str) -> Any:
    return item.get(name, item.get(name[0].lower() + name[1:]))


def _select(item: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {
        name: _field(item, name) for name in names if _field(item, name) is not None
    }


class ReadOnlyWorkflows:
    def __init__(self, client: OseonAPIClient):
        self.client = client

    async def _get(self, path: str, query: dict[str, Any]) -> Any:
        result = await self.client.invoke("GET", path, query_parameters=query)
        return result["data"]

    async def work_orders(self, page: int = 0, size: int = 20) -> dict[str, Any]:
        if page < 0 or not 1 <= size <= 100:
            raise ValueError("Page must be nonnegative and size must be 1–100")
        data = await self._get(
            "/api/v2/pps/productionOrders/full/search",
            {"page": page, "size": size},
        )
        if not isinstance(data, dict):
            raise ValueError("Unexpected work order response")
        orders = _field(data, "Collection")
        if not isinstance(orders, list):
            raise ValueError("Unexpected work order collection")
        fields = (
            "Id",
            "OrderNo",
            "PartNo",
            "PartDescription",
            "Description",
            "DesiredQuantity",
            "ProcessedParts",
            "ScrapParts",
            "Status",
            "Material",
            "DueDate",
            "PlannedEndDate",
            "ActualStartDate",
        )
        return {
            "page": _field(data, "CurrentPage"),
            "pages": _field(data, "Pages"),
            "records": _field(data, "Records"),
            "orders": [_select(order, fields) for order in orders],
        }

    async def nestings(
        self, workplace_id: int | None = None, max_count: int = 20
    ) -> dict[str, Any]:
        if workplace_id is not None and workplace_id < 0:
            raise ValueError("Workplace ID must be nonnegative")
        if not 1 <= max_count <= 100:
            raise ValueError("Max count must be 1–100")
        if workplace_id is None:
            workplaces = await self._get("/api/v2/masterdata/workplaces", {})
            if not isinstance(workplaces, list):
                raise ValueError("Unexpected workplaces response")
            ids = [_field(place, "Id") for place in workplaces]
            ids = [value for value in ids if isinstance(value, int)]
        else:
            ids = [workplace_id]
        fields = (
            "TaskId",
            "Name",
            "ProgramName",
            "WorkplaceId",
            "WorkplaceName",
            "DisplayState",
            "CountSheetsToSeparate",
            "CurrentIteration",
            "Iterations",
            "StartDatePlanned",
            "DueDatePlanned",
            "RawSheet",
        )
        orders: list[dict[str, Any]] = []
        for current_id in dict.fromkeys(ids):
            data = await self._get(
                "/api/v2/fabrication/manufacturingOrders/listData",
                {"workplaceId": current_id, "maxCount": max_count},
            )
            if not isinstance(data, list):
                raise ValueError("Unexpected nesting response")
            orders.extend(_select(item, fields) for item in data)
        return {"workplaces_checked": len(set(ids)), "nestings": orders}

    async def stock(self, article: str = "") -> list[dict[str, Any]]:
        data = await self._get(
            "/api/v2/bffStorage/stock/stocksForOverview", {"article": article}
        )
        if not isinstance(data, list):
            raise ValueError("Unexpected stock response")
        fields = (
            "ArticleName",
            "ArticleNameExt",
            "ArticleDescription",
            "BatchNo",
            "Quantity",
            "QuantityUnit",
            "StorageLocationStoreName",
            "StorageLocationName",
            "StorageLocationStatus",
            "StockStatus",
            "ContainerStatus",
            "OverallStatus",
            "OverallStatusMessage",
        )
        return [_select(item, fields) for item in data]

    async def remainder_sheets(self, filter: str = "") -> dict[str, Any]:
        sheets = await self._get(
            "/api/v2/bffStorage/article/GetRawSheets", {"filter": filter}
        )
        if not isinstance(sheets, list):
            raise ValueError("Unexpected raw sheet response")
        rows = []
        remainder_count = 0
        for sheet in sheets:
            if (
                not isinstance(sheet, dict)
                or _field(sheet, "IsRemainderSheet") is not True
            ):
                continue
            name = _field(sheet, "Name")
            if not isinstance(name, str) or not name:
                continue
            remainder_count += 1
            for item in await self.stock(name):
                quantity = item.get("Quantity")
                article = item.get("ArticleName")
                if (
                    not isinstance(article, str)
                    or article.casefold() != name.casefold()
                ):
                    continue
                if not isinstance(quantity, (int, float)) or quantity <= 0:
                    continue
                rows.append(
                    {
                        **_select(
                            sheet,
                            (
                                "Name",
                                "NameExt",
                                "Description",
                                "DimensionX",
                                "DimensionY",
                            ),
                        ),
                        **item,
                    }
                )
        return {
            "raw_sheets_returned": len(sheets),
            "remainder_articles_checked": remainder_count,
            "stock_rows": rows,
        }
