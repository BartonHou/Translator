"""Verify metrics use the route template (low cardinality), not the raw URL.

A path parameter like a job UUID must collapse to ``/items/{item_id}`` so
Prometheus does not get one time series per distinct id.
"""
import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.main import _route_label


class RouteLabelTests(unittest.TestCase):
    def test_path_param_collapses_to_template(self):
        app = FastAPI()
        seen = {}

        @app.middleware("http")
        async def capture(request: Request, call_next):
            resp = await call_next(request)
            seen["label"] = _route_label(request)
            return resp

        @app.get("/items/{item_id}")
        def get_item(item_id: str):
            return {"id": item_id}

        client = TestClient(app)
        client.get("/items/abc-123-uuid")
        self.assertEqual(seen["label"], "/items/{item_id}")

        client.get("/items/totally-different")
        self.assertEqual(seen["label"], "/items/{item_id}")  # same series


if __name__ == "__main__":
    unittest.main()
