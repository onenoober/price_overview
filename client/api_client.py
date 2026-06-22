from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        self.status_code = status_code
        super().__init__(f"{code}: {message}")


class PriceOverviewClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        parse_timeout: float = 300.0,
        price_timeout: float = 300.0,
    ) -> None:
        if base_url is None:
            base_url = os.getenv("PRICE_BACKEND_URL", "http://127.0.0.1:8000")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.parse_timeout = parse_timeout
        self.price_timeout = price_timeout

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._api_json("GET", f"/api/quote-tasks/{task_id}")["data"]

    def list_tasks(self) -> list[dict[str, Any]]:
        return self._api_json("GET", "/api/quote-tasks")["data"]["tasks"]

    def create_task(
        self,
        *,
        customer_name: str,
        part_name: str,
        part_no: str = "",
        quantity: int = 1,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "customer_name": customer_name,
            "part_name": part_name,
            "part_no": part_no,
            "quantity": quantity,
        }
        if task_id:
            payload["task_id"] = task_id

        return self._api_json(
            "POST",
            "/api/quote-tasks",
            json=payload,
        )["data"]["task"]

    def upload_file(
        self,
        task_id: str,
        file_type: str,
        file_path: Path,
        uploaded_by: str = "user_001",
    ) -> dict[str, Any]:
        with file_path.open("rb") as source:
            response = self._api_json(
                "POST",
                f"/api/quote-tasks/{task_id}/files",
                data={
                    "file_type": file_type,
                    "uploaded_by": uploaded_by,
                },
                files={
                    "file": (
                        file_path.name,
                        source,
                        "application/octet-stream",
                    )
                },
            )
        return response["data"]

    def parse_task(
        self,
        task_id: str,
        *,
        parse_pdf: bool = True,
        parse_step: bool = True,
        use_ai: bool = False,
        pdf_file_id: str | None = None,
        step_file_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parse_pdf": parse_pdf,
            "parse_step": parse_step,
            "use_ai": use_ai,
        }
        if pdf_file_id:
            payload["pdf_file_id"] = pdf_file_id
        if step_file_id:
            payload["step_file_id"] = step_file_id

        return self._api_json(
            "POST",
            f"/api/quote-tasks/{task_id}/parse",
            json=payload,
            timeout=self.parse_timeout,
        )["data"]

    def get_parse_result(self, task_id: str) -> dict[str, Any]:
        return self._api_json(
            "GET",
            f"/api/quote-tasks/{task_id}/parse-result",
        )["data"]

    def invalidate_file(self, task_id: str, file_id: str) -> dict[str, Any]:
        return self._api_json(
            "POST",
            f"/api/quote-tasks/{task_id}/files/{file_id}/invalidate",
        )["data"]

    def delete_file(self, task_id: str, file_id: str) -> dict[str, Any]:
        return self._api_json(
            "DELETE",
            f"/api/quote-tasks/{task_id}/files/{file_id}",
        )["data"]

    def price_task(
        self,
        task_id: str,
        *,
        price_version: str = "a-basic-v1",
        use_ai: bool = False,
        use_market_price_search: bool = False,
        process_route_mode: str = "rule",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._api_json(
            "POST",
            f"/api/quote-tasks/{task_id}/price",
            json={
                "price_version": price_version,
                "rounding_rule": "a_basic_rounding_ui_only",
                "use_ai": use_ai,
                "use_market_price_search": use_market_price_search,
                "process_route_mode": process_route_mode,
            },
            timeout=timeout if timeout is not None else self.price_timeout,
        )["data"]

    def get_quote(self, quote_id: str) -> dict[str, Any]:
        return self.get_quote_bundle(quote_id)["quote_result"]

    def get_quote_bundle(self, quote_id: str) -> dict[str, Any]:
        return self._api_json(
            "GET",
            f"/api/quotes/{quote_id}",
        )["data"]

    def save_override(
        self,
        quote_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._api_json(
            "POST",
            f"/api/quotes/{quote_id}/overrides",
            json=payload,
        )["data"]

    def confirm_quote(
        self,
        quote_id: str,
        *,
        confirmed_total_amount: float,
        confirmed_by: str,
        confirm_note: str,
    ) -> dict[str, Any]:
        return self._api_json(
            "POST",
            f"/api/quotes/{quote_id}/confirm",
            json={
                "confirmed_total_amount": confirmed_total_amount,
                "confirmed_by": confirmed_by,
                "confirm_note": confirm_note,
            },
        )["data"]

    def export_quote(
        self,
        quote_id: str,
        *,
        export_format: str = "json",
    ) -> dict[str, Any]:
        return self._api_json(
            "POST",
            f"/api/quotes/{quote_id}/export",
            json={
                "format": export_format,
                "include_initial_quote": True,
                "include_manual_overrides": True,
                "include_risks": True,
            },
        )["data"]

    def download_export(self, export_id: str) -> str:
        content = self._raw_text("GET", f"/api/exports/{export_id}/download")
        if not content:
            raise ApiError("EMPTY_EXPORT_FILE", "导出文件内容为空。")
        return content

    def _api_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        payload = self._raw_json(method, path, **kwargs)
        if not isinstance(payload, dict) or "success" not in payload:
            raise ApiError(
                "INVALID_RESPONSE",
                "Backend response does not use success/data/error envelope.",
            )
        if payload["success"] is not True:
            error = payload.get("error") or {}
            raise ApiError(
                error.get("code", "API_ERROR"),
                error.get("message", "Request failed."),
                error.get("details", []),
            )
        return payload

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            return httpx.request(
                method,
                url,
                timeout=timeout,
                trust_env=False,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            timeout_text = (
                f"{timeout:g}" if isinstance(timeout, (int, float)) else str(timeout)
            )
            raise ApiError(
                "REQUEST_TIMEOUT",
                (
                    f"请求超过 {timeout_text} 秒未返回。"
                    "后端任务可能仍在继续执行，请稍后刷新任务或结果。"
                ),
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError("NETWORK_ERROR", str(exc)) from exc

    def _raw_text(self, method: str, path: str, **kwargs: Any) -> str:
        response = self._request(method, path, **kwargs)
        if response.is_error:
            self._raise_http_error(response)
        return response.text

    def _raw_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, path, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                "INVALID_JSON",
                self._invalid_json_message(response),
                status_code=response.status_code,
            ) from exc

        if response.is_error:
            self._raise_http_error(response, payload)

        return payload

    def _raise_http_error(
        self,
        response: httpx.Response,
        payload: Any | None = None,
    ) -> None:
        if payload is None:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ApiError(
                    "HTTP_ERROR",
                    response.text or f"HTTP {response.status_code} returned no body.",
                    status_code=response.status_code,
                ) from exc

        if isinstance(payload, dict) and payload.get("success") is False:
            error = payload.get("error") or {}
            raise ApiError(
                error.get("code", "HTTP_ERROR"),
                error.get("message", "Request failed."),
                error.get("details", []),
                status_code=response.status_code,
            )
        raise ApiError(
            "HTTP_ERROR",
            str(payload),
            status_code=response.status_code,
        )

    def _invalid_json_message(self, response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "unknown")
        body = response.text.strip()
        if len(body) > 500:
            body = f"{body[:500]}..."
        if not body:
            body = "(empty response body)"
        return (
            "后端响应不是 JSON。"
            f" 请求：{response.request.method} {response.request.url};"
            f" 状态码：{response.status_code};"
            f" Content-Type：{content_type};"
            f" 响应内容：{body}"
        )
