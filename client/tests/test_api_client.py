from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from client.api_client import ApiError, PriceOverviewClient


def response(
    status_code: int,
    text: str,
    *,
    url: str = "http://127.0.0.1:8000/api/exports/export_001/download",
) -> httpx.Response:
    return httpx.Response(
        status_code,
        text=text,
        request=httpx.Request("GET", url),
    )


class PriceOverviewClientTests(unittest.TestCase):
    def test_download_export_returns_text_without_json_parsing(self) -> None:
        client = PriceOverviewClient()

        with patch(
            "client.api_client.httpx.request",
            return_value=response(200, "downloaded file content"),
        ):
            content = client.download_export("export_001")

        self.assertEqual(content, "downloaded file content")

    def test_download_export_preserves_backend_json_error(self) -> None:
        client = PriceOverviewClient()
        error_body = (
            '{"success": false, "error": {'
            '"code": "EXPORT_NOT_FOUND", '
            '"message": "导出记录不存在", '
            '"details": [{"field": "export_id", "message": "export_missing"}]'
            "}}"
        )

        with patch(
            "client.api_client.httpx.request",
            return_value=response(404, error_body),
        ):
            with self.assertRaises(ApiError) as context:
                client.download_export("export_missing")

        self.assertEqual(context.exception.code, "EXPORT_NOT_FOUND")
        self.assertEqual(context.exception.message, "导出记录不存在")
        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(
            context.exception.details,
            [{"field": "export_id", "message": "export_missing"}],
        )

    def test_download_export_rejects_empty_file_response(self) -> None:
        client = PriceOverviewClient()

        with patch(
            "client.api_client.httpx.request",
            return_value=response(200, ""),
        ):
            with self.assertRaises(ApiError) as context:
                client.download_export("export_empty")

        self.assertEqual(context.exception.code, "EMPTY_EXPORT_FILE")

    def test_backend_requests_ignore_environment_proxy(self) -> None:
        client = PriceOverviewClient()

        with patch(
            "client.api_client.httpx.request",
            return_value=response(
                200,
                '{"success": true, "data": {"tasks": []}}',
                url="http://127.0.0.1:8000/api/quote-tasks",
            ),
        ) as request:
            self.assertEqual(client.list_tasks(), [])

        self.assertFalse(request.call_args.kwargs["trust_env"])


if __name__ == "__main__":
    unittest.main()
