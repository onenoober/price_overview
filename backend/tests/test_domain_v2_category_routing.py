from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app.domain_v2.facts import FactSnapshot, FactValue
from backend.app.domain_v2.planning import build_route_for_snapshot
from backend.app.main import create_app


class DomainV2CategoryRoutingTests(unittest.TestCase):
    def test_j004_sheet_metal_includes_sheet_welding_without_generic_cnc(self) -> None:
        result = build_route_for_snapshot(snapshot(business_category_code="J004"))

        operation_codes = operation_codes_from_result(result)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.category_decision.business_category_code, "J004")
        self.assertEqual(result.route_profile.profile, "sheet_metal")
        self.assertIn("sheet_metal_welding", operation_codes)
        self.assertNotIn("cnc_milling", operation_codes)
        self.assertNotIn("wire_cut_profile", operation_codes)
        self.assertNotIn("welding", operation_codes)

    def test_j007_rejects_sheet_metal_primary_conflict(self) -> None:
        result = build_route_for_snapshot(
            snapshot(
                business_category_code="J007",
                part_type_raw="sheet metal welded bracket",
            )
        )

        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.review_reason, "CATEGORY_PROFILE_CONFLICT")

    def test_unknown_j008_returns_unmapped_category_review(self) -> None:
        result = build_route_for_snapshot(snapshot(business_category_code="J008"))

        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.review_reason, "UNMAPPED_CATEGORY_REVIEW")
        self.assertEqual(result.category_decision.business_category_code, "J008")
        self.assertEqual(operation_codes_from_result(result), set())

    def test_j012_rework_does_not_use_generic_machining(self) -> None:
        result = build_route_for_snapshot(snapshot(business_category_code="J012"))

        operation_codes = operation_codes_from_result(result)

        self.assertEqual(result.status, "planned")
        self.assertLessEqual(
            operation_codes,
            {"incoming_check", "rework_difference_review", "local_rework", "final_reinspection"},
        )
        self.assertNotIn("cnc_milling", operation_codes)

    def test_j001_j003_uses_500mm_business_boundary_when_code_missing(self) -> None:
        j001 = build_route_for_snapshot(
            snapshot(part_form="prismatic", max_dimension_mm=500)
        )
        j003 = build_route_for_snapshot(
            snapshot(part_form="prismatic", max_dimension_mm=500.1)
        )

        self.assertEqual(j001.category_decision.business_category_code, "J001")
        self.assertEqual(j003.category_decision.business_category_code, "J003")

    def test_j003_granite_branch_is_exposed_for_audit(self) -> None:
        result = build_route_for_snapshot(
            snapshot(
                business_category_code="J003",
                material="granite",
            )
        )

        operation_codes = operation_codes_from_result(result)

        self.assertEqual(result.metadata["large_base_branch"], "granite_or_stone_base")
        self.assertIn("large_base_branch=granite_or_stone_base", result.assumptions)
        self.assertIn("granite_grinding", operation_codes)
        self.assertNotIn("large_plate_roughing", operation_codes)

    def test_api_metadata_category_uses_real_route_planner(self) -> None:
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
                        "part_name": "Sheet metal bracket",
                        "part_no": "SM-001",
                        "quantity": 1,
                        "metadata": {"business_category_code": "J004"},
                    },
                    expected_status=201,
                )["quote_case"]
                run = self._post(
                    client,
                    f"/api/v2/quote-cases/{created_case['case_id']}/analysis-runs",
                    {},
                    expected_status=201,
                )["analysis_run"]
                route_plan = self._post(
                    client,
                    f"/api/v2/analysis-runs/{run['run_id']}/route-plans",
                    {},
                    expected_status=201,
                )["route_plan"]

        operation_codes = {operation["operation_code"] for operation in route_plan["operations"]}
        self.assertFalse(route_plan["requires_review"])
        self.assertEqual(route_plan["business_category"]["code"], "J004")
        self.assertEqual(route_plan["route_profile"]["profile"], "sheet_metal")
        self.assertEqual(route_plan["planner_type"], "planner")
        self.assertIn("sheet_metal_welding", operation_codes)
        self.assertNotIn("cnc_milling", operation_codes)

    def test_api_default_without_subcategory_returns_manual_review_fallback(self) -> None:
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
                        "part_name": "Default review part",
                        "part_no": "DF-001",
                        "quantity": 1,
                    },
                    expected_status=201,
                )["quote_case"]
                run = self._post(
                    client,
                    f"/api/v2/quote-cases/{created_case['case_id']}/analysis-runs",
                    {},
                    expected_status=201,
                )["analysis_run"]
                route_plan = self._post(
                    client,
                    f"/api/v2/analysis-runs/{run['run_id']}/route-plans",
                    {},
                    expected_status=201,
                )["route_plan"]

        operation_codes = {operation["operation_code"] for operation in route_plan["operations"]}
        self.assertEqual(route_plan["planner_type"], "manual_review_fallback")
        self.assertTrue(route_plan["requires_review"])
        self.assertEqual(route_plan["review_reason"], "UNMAPPED_CATEGORY_REVIEW")
        self.assertNotIn("cnc_milling", operation_codes)
        self.assertNotIn("wire_cut_profile", operation_codes)

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


def snapshot(**values: object) -> FactSnapshot:
    return FactSnapshot.from_values(
        FactValue(key=key, value=value)
        for key, value in values.items()
    )


def operation_codes_from_result(result) -> set[str]:
    return {node.operation_code for node in result.selected_operations()}


if __name__ == "__main__":
    unittest.main()

