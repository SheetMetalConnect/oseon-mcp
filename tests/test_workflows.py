import pytest

from trumpf_oseon_mcp.workflows import ReadOnlyWorkflows


class FakeClient:
    def __init__(self):
        self.calls = []

    async def invoke(self, method, path, query_parameters):
        self.calls.append((method, path, query_parameters))
        if path.endswith("GetRawSheets"):
            return {
                "data": [
                    {
                        "Name": "OFFCUT-A",
                        "IsRemainderSheet": True,
                        "DimensionX": 500,
                        "ImageBase64": "excluded",
                    },
                    {"Name": "FULL-B", "IsRemainderSheet": False},
                ]
            }
        if path.endswith("stocksForOverview"):
            return {
                "data": [
                    {
                        "ArticleName": "OFFCUT-A",
                        "Quantity": 2,
                        "QuantityUnit": "pcs",
                        "StorageLocationName": "Rack",
                        "ImageBase64": "excluded",
                    },
                    {"ArticleName": "OFFCUT-A", "Quantity": 0},
                    {"ArticleName": "FULL-B", "Quantity": 3},
                ]
            }
        if path.endswith("/workplaces"):
            return {"data": [{"Id": 1}, {"Id": 2}]}
        if path.endswith("listData"):
            return {
                "data": [{"TaskId": query_parameters["workplaceId"], "Name": "JOB"}]
            }
        return {
            "data": {
                "CurrentPage": 0,
                "Pages": 1,
                "Records": 1,
                "Collection": [{"OrderNo": "WO", "ImageBase64": "excluded"}],
            }
        }


@pytest.mark.asyncio
async def test_read_only_workflows_project_core_data():
    client = FakeClient()
    workflows = ReadOnlyWorkflows(client)
    assert (await workflows.work_orders())["orders"] == [{"OrderNo": "WO"}]
    assert len((await workflows.nestings())["nestings"]) == 2
    assert await workflows.remainder_sheets() == {
        "raw_sheets_returned": 2,
        "remainder_articles_checked": 1,
        "stock_rows": [
            {
                "Name": "OFFCUT-A",
                "DimensionX": 500,
                "ArticleName": "OFFCUT-A",
                "Quantity": 2,
                "QuantityUnit": "pcs",
                "StorageLocationName": "Rack",
            }
        ],
    }
    assert all(call[0] == "GET" for call in client.calls)
