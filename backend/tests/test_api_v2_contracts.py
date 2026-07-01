from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app.main import create_app


class ApiV2ContractTests(unittest.TestCase):
    def test_quote_case_workflow_contract(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            app = create_app(
                db_path=Path(tmp_dir) / "test.db",
                upload_root=Path(tmp_dir) / "uploads",
                export_root=Path(tmp_dir) / "exports",
            )

            with TestClient(app) as client:
                created_case = self._post(
                    client,
                    "/api/v2/quote-cases",
                    {
                        "customer_name": "Acme",
                        "part_name": "Bracket",
                        "part_no": "BR-001",
                        "quantity": 3,
                    },
                    expected_status=201,
                )["quote_case"]
                case_id = created_case["case_id"]
                self.assertEqual(created_case["status"], "created")
                self.assert_stage_contract(created_case, expected_progress=10)

                cases = self._get(client, "/api/v2/quote-cases")["quote_cases"]
                self.assertEqual([item["case_id"] for item in cases], [case_id])

                uploaded_file = self._post_multipart(
                    client,
                    f"/api/v2/quote-cases/{case_id}/files",
                    files={"file": ("drawing.pdf", b"%PDF-1.4", "application/pdf")},
                    data={"file_type": "pdf", "uploaded_by": "tester"},
                    expected_status=201,
                )["file"]
                self.assertEqual(uploaded_file["case_id"], case_id)
                self.assertEqual(uploaded_file["status"], "uploaded")

                files = self._get(client, f"/api/v2/quote-cases/{case_id}/files")["files"]
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0]["filename"], "drawing.pdf")

                analysis_run = self._post(
                    client,
                    f"/api/v2/quote-cases/{case_id}/analysis-runs",
                    {"options": {"parse_pdf": True}},
                    expected_status=201,
                )["analysis_run"]
                run_id = analysis_run["run_id"]
                self.assertEqual(analysis_run["status"], "completed")
                self.assert_stage_contract(analysis_run, expected_progress=100)

                fetched_run = self._get(client, f"/api/v2/analysis-runs/{run_id}")[
                    "analysis_run"
                ]
                self.assertEqual(fetched_run["run_id"], run_id)

                facts = self._get(client, f"/api/v2/analysis-runs/{run_id}/facts")[
                    "facts"
                ]
                self.assertIn("part_name", {fact["field"] for fact in facts})
                self.assertIn("file", {fact["field"] for fact in facts})

                route_plan = self._post(
                    client,
                    f"/api/v2/quote-cases/{case_id}/route-plans",
                    {},
                    expected_status=201,
                )["route_plan"]
                route_plan_id = route_plan["route_plan_id"]
                self.assertEqual(route_plan["status"], "planned")
                self.assert_stage_contract(route_plan, expected_progress=100)
                self.assertEqual(route_plan["operations"][0]["operation_code"], "manual_review")
                self.assertTrue(route_plan["operations"][0]["requires_review"])
                self.assertTrue(route_plan["requires_review"])
                self.assertEqual(route_plan["review_reason"], "UNMAPPED_CATEGORY_REVIEW")
                self.assertEqual(route_plan["planner_type"], "manual_review_fallback")
                self.assertIn("business_category", route_plan)
                self.assertIn("route_profile", route_plan)

                fetched_route_plan = self._get(
                    client,
                    f"/api/v2/route-plans/{route_plan_id}",
                )["route_plan"]
                self.assertEqual(fetched_route_plan["route_plan_id"], route_plan_id)

                route_revision = self._post(
                    client,
                    f"/api/v2/route-plans/{route_plan_id}/revisions",
                    {
                        "action": "change_method",
                        "target_operation_id": None,
                        "payload": {"note": "review route"},
                        "reason": "engineer review",
                    },
                    expected_status=201,
                )["route_revision"]
                self.assertEqual(route_revision["base_route_plan_id"], route_plan_id)

                route_plans = self._get(
                    client,
                    f"/api/v2/analysis-runs/{run_id}/route-plans",
                )["route_plans"]
                self.assertEqual([item["route_plan_id"] for item in route_plans], [route_plan_id])
                collection_route_plans = self._get(
                    client,
                    f"/api/v2/route-plans?run_id={run_id}",
                )["route_plans"]
                self.assertEqual(
                    [item["route_plan_id"] for item in collection_route_plans],
                    [route_plan_id],
                )

                cost_scenario = self._post(
                    client,
                    "/api/v2/cost-scenarios",
                    {"route_plan_id": route_plan_id, "currency": "CNY"},
                    expected_status=201,
                )["cost_scenario"]
                self.assertEqual(cost_scenario["status"], "costed")
                self.assertGreater(cost_scenario["total_amount"], 0)
                self.assert_stage_contract(cost_scenario, expected_progress=100)

                fetched_cost = self._get(
                    client,
                    f"/api/v2/cost-scenarios/{cost_scenario['cost_scenario_id']}",
                )["cost_scenario"]
                self.assertEqual(
                    fetched_cost["cost_scenario_id"],
                    cost_scenario["cost_scenario_id"],
                )

                quote = self._post(
                    client,
                    f"/api/v2/cost-scenarios/{cost_scenario['cost_scenario_id']}/quotes",
                    {},
                    expected_status=201,
                )["quote"]
                approved_quote = self._post(
                    client,
                    f"/api/v2/quotes/{quote['quote_id']}/approve",
                    {"approved_by": "manager", "approval_note": "ok"},
                )["quote"]
                self.assertEqual(approved_quote["status"], "approved")
                self.assertEqual(approved_quote["approved_by"], "manager")

                export_record = self._post(
                    client,
                    f"/api/v2/quotes/{quote['quote_id']}/export",
                    {"format": "json"},
                    expected_status=201,
                )["export"]
                self.assertEqual(export_record["status"], "ready")
                self.assertTrue(export_record["download_url"].startswith("/api/v2/exports/"))

    def test_v2_missing_resource_uses_contract_error_envelope(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            app = create_app(
                db_path=Path(tmp_dir) / "test.db",
                upload_root=Path(tmp_dir) / "uploads",
                export_root=Path(tmp_dir) / "exports",
            )

            with TestClient(app) as client:
                response = client.get("/api/v2/quote-cases/missing/files")

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "QUOTE_CASE_NOT_FOUND")

    def assert_stage_contract(self, payload: dict, *, expected_progress: int) -> None:
        self.assertIn("stages", payload)
        self.assertIsInstance(payload["stages"], list)
        self.assertGreater(len(payload["stages"]), 0)
        self.assertEqual(payload["progress"], expected_progress)
        for stage in payload["stages"]:
            self.assertIn("name", stage)
            self.assertIn("status", stage)
            self.assertIn("progress", stage)

    def _post(
        self,
        client: TestClient,
        path: str,
        payload: dict,
        *,
        expected_status: int = 200,
    ) -> dict:
        response = client.post(path, json=payload)
        self.assertEqual(response.status_code, expected_status, response.text)
        body = response.json()
        self.assertTrue(body["success"], body)
        return body["data"]

    def _post_multipart(
        self,
        client: TestClient,
        path: str,
        *,
        files: dict,
        data: dict,
        expected_status: int,
    ) -> dict:
        response = client.post(path, files=files, data=data)
        self.assertEqual(response.status_code, expected_status, response.text)
        body = response.json()
        self.assertTrue(body["success"], body)
        return body["data"]

    def _get(self, client: TestClient, path: str) -> dict:
        response = client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"], body)
        return body["data"]


if __name__ == "__main__":
    unittest.main()
