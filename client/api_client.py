from __future__ import annotations

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
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        use_ai: bool = True,
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
    ) -> dict[str, Any]:
        return self._api_json(
            "POST",
            f"/api/quote-tasks/{task_id}/price",
            json={
                "price_version": price_version,
                "rounding_rule": "a_basic_rounding_ui_only",
            },
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

    def download_export(self, export_id: str) -> dict[str, Any]:
        return self._raw_json("GET", f"/api/exports/{export_id}/download")

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

    def _raw_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(method, url, timeout=self.timeout, **kwargs)
        except httpx.RequestError as exc:
            raise ApiError("NETWORK_ERROR", str(exc)) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                "INVALID_JSON",
                response.text or "Backend response is not JSON.",
                status_code=response.status_code,
            ) from exc

        if response.is_error:
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

        return payload
