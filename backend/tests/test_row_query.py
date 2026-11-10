"""Multi-source rows HTTP contract and repository delegation."""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import get_current_user, get_rls_session
from repository.row import RowRepository
from router.api.rows import router

WORKSPACE_ID = UUID("11111111-1111-1111-1111-111111111111")
EMPTY_RESULT = {
    "items": [],
    "page": None,
    "page_size": None,
    "has_more": False,
    "total": None,
    "total_pages": None,
}


class TestMultiSourceRows(unittest.TestCase):
    def setUp(self):
        self.session = AsyncMock()
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_current_user] = lambda: None
        app.dependency_overrides[get_rls_session] = lambda: self.session
        self.client = TestClient(app)

    def test_tables_route_passes_defaults_and_returns_all_rows_envelope(self):
        with patch.object(RowRepository, "query_rows", new_callable=AsyncMock) as query:
            query.return_value = EMPTY_RESULT
            response = self.client.get("/api/v1/rows", params={"table_ids": "[12,13,12]"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), EMPTY_RESULT)
        self.assertEqual(query.await_args.kwargs["table_ids"], [12, 13])
        self.assertIsNone(query.await_args.kwargs["workspace_ids"])
        self.assertIsNone(query.await_args.kwargs["page_size"])
        self.assertEqual(query.await_args.kwargs["sort_by"], "row_id")
        self.assertTrue(query.await_args.kwargs["desc"])

    def test_workspace_route_passes_filter_pagination_and_sort(self):
        payload = dict(EMPTY_RESULT, page=1, page_size=25, total=0, total_pages=0)
        params = {
            "workspace_ids": json.dumps([str(WORKSPACE_ID)]),
            "page_size": "25",
            "sort_by": "updated_at",
            "desc": "false",
            "filter_json": '{"city":"Osaka"}',
            "include_total": "true",
        }
        with patch.object(RowRepository, "query_rows", new_callable=AsyncMock) as query:
            query.return_value = payload
            response = self.client.get("/api/v1/rows", params=params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertEqual(query.await_args.kwargs["workspace_ids"], [WORKSPACE_ID])
        self.assertIsNone(query.await_args.kwargs["page"])
        self.assertEqual(query.await_args.kwargs["page_size"], 25)
        self.assertEqual(query.await_args.kwargs["filter_json"], {"city": "Osaka"})
        self.assertTrue(query.await_args.kwargs["include_total"])
        self.assertFalse(query.await_args.kwargs["desc"])

    def test_bad_sources_and_query_arguments_return_422(self):
        bad_params = [
            {},
            {"table_ids": "[1]", "workspace_ids": json.dumps([str(WORKSPACE_ID)])},
            {"table_ids": "[]"},
            {"table_ids": "[true]"},
            {"table_ids": "[0]"},
            {"table_ids": "[1]", "page": "2"},
            {"table_ids": "[1]", "page_size": "201"},
            {"table_ids": "[1]", "sort_by": "row_data"},
            {"table_ids": "[1]", "filter_json": "[]"},
            {"workspace_ids": '["invalid"]'},
        ]
        with patch.object(RowRepository, "query_rows", new_callable=AsyncMock) as query:
            for params in bad_params:
                with self.subTest(params=params):
                    self.assertEqual(self.client.get("/api/v1/rows", params=params).status_code, 422)
            query.assert_not_awaited()

    def test_openapi_describes_new_query_and_deprecates_legacy_list(self):
        spec = self.client.get("/openapi.json").json()
        operation = spec["paths"]["/api/v1/rows"]["get"]
        self.assertIn("page_size", operation["description"])
        query_parameters = [parameter for parameter in operation["parameters"] if parameter["in"] == "query"]
        self.assertEqual(
            {parameter["name"] for parameter in query_parameters},
            {
                "table_ids",
                "workspace_ids",
                "page",
                "page_size",
                "sort_by",
                "desc",
                "filter_json",
                "include_total",
            },
        )
        self.assertTrue(all(parameter.get("description") for parameter in query_parameters))
        self.assertTrue(spec["paths"]["/api/v1/tables/{table_id}/rows"]["get"]["deprecated"])
        fields = spec["components"]["schemas"]["RowQueryResponse"]["properties"]
        self.assertTrue(all(field.get("description") for field in fields.values()))


if __name__ == "__main__":
    unittest.main()
