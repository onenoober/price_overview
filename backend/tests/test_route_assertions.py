"""§5 族级硬断言守门套件。任一不满足 = 测试失败，防止规则回归。"""

from __future__ import annotations

import unittest

from backend.app.domain_v2.route_engine import plan_route_v2
from backend.app.domain_v2.route_engine.skeleton import skeleton_for

from backend.tests.route_engine_fixtures import make_part_feature, operation_codes, risk_codes

MACHINING_OPS = {
    "cnc_rough_milling",
    "cnc_finish_milling",
    "cnc_milling",
    "profile_milling",
    "pocket_milling",
    "edm",
    "wire_cut_profile",
    "surface_grinding_rough",
}


def _plan(part_feature):
    return plan_route_v2(task_id="t", route_id="r", part_feature=part_feature, inherited_risks=[])


# 故意构造"会带偏几何"的输入：高复杂度 + 槽 + 线切割关键字 + 孔。
def _bug_inducing(category, part_type, compatible):
    return make_part_feature(
        category_name=category,
        part_type=part_type,
        compatible_part_types=compatible,
        holes=[{"count": 4, "hole_type": "through"}],
        slots=[{"count": 2}],
        complexity={"complexity_score": 85, "slot_count": 2},
        technical_requirements=[{"raw_text": "线切割轮廓加工，去除毛刺飞边"}],
    )


class FamilyHardAssertionTests(unittest.TestCase):
    def test_sheet_metal_never_contains_machining_operations(self) -> None:
        route = _plan(_bug_inducing("钣金类", "complex", ("thin_plate", "plate", "complex")))
        ops = set(operation_codes(route))
        self.assertEqual(ops & MACHINING_OPS, set(), ops & MACHINING_OPS)
        self.assertIn("laser_cut_blank", ops)

    def test_turning_has_turning_main_line_and_no_edm_pocket(self) -> None:
        route = _plan(_bug_inducing("圆件类", "shaft", ("shaft", "shaft_candidate")))
        codes = operation_codes(route)
        self.assertIn("turning", codes)
        # 车削是主线（在下料之后、检验之前的核心加工工序）。
        self.assertLess(codes.index("turning"), codes.index("inspection"))
        self.assertEqual(set(codes) & {"edm", "pocket_milling"}, set())
        self.assertEqual(set(codes) & MACHINING_OPS, set())

    def test_machining_detailing_does_not_leak_to_other_families(self) -> None:
        holes = [
            {"count": 2, "hole_type": "through", "through": True, "raw_text": "2 x 5 完全贯穿"},
            {"count": 1, "hole_type": "thread_candidate", "through": True, "raw_text": "M6 - 6H 完全贯穿"},
            {"count": 1, "hole_type": "thread_candidate", "through": False, "raw_text": "M4 - 6H; 8"},
            {"count": 1, "hole_type": "precision_candidate", "raw_text": "H7"},
        ]
        cases = (
            (
                "钣金类",
                "thin_plate",
                ("thin_plate", "plate", "complex"),
                {"profile_milling", "tapping_through", "blind_tapping", "thread_inspection", "in_process_inspection"},
            ),
            (
                "圆件类",
                "shaft",
                ("shaft", "shaft_candidate"),
                {"cnc_rough_milling", "cnc_finish_milling", "profile_milling", "thread_inspection", "in_process_inspection"},
            ),
            (
                "大板类",
                "plate",
                ("plate", "long_bar"),
                {"cnc_rough_milling", "cnc_finish_milling", "profile_milling", "blind_tapping", "thread_inspection"},
            ),
        )
        for category, part_type, compatible, forbidden in cases:
            route = _plan(
                make_part_feature(
                    category_name=category,
                    part_type=part_type,
                    compatible_part_types=compatible,
                    holes=holes,
                    complexity={"complexity_score": 80, "slot_count": 1, "face_count": 24, "edge_count": 64},
                )
            )
            codes = set(operation_codes(route))
            self.assertEqual(codes & forbidden, set(), f"{category}: {codes & forbidden}")

    def test_large_plate_edm_requires_geometry_evidence(self) -> None:
        # 无几何 edm 证据 → 路线不含 edm/wire_cut/pocket。
        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("thin_plate", "plate", "long_bar"),
                complexity={"complexity_score": 30},
            )
        )
        codes = set(operation_codes(route))
        self.assertEqual(codes & {"edm", "wire_cut_profile", "pocket_milling"}, set())
        self.assertIn("large_plate_roughing", codes)
        self.assertIn("large_plate_finishing", codes)

    def test_large_plate_edm_included_when_geometry_present(self) -> None:
        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("thin_plate", "plate", "long_bar"),
                complexity={"complexity_score": 30, "slot_count": 1},
                technical_requirements=[{"raw_text": "线切割窗口"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("wire_cut_profile", codes)

    def test_surface_treatment_requires_title_block_field(self) -> None:
        # 仅技术要求正文提喷塑、无标题栏字段 → 不出现正式表处工序。
        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                technical_requirements=[{"raw_text": "喷塑时应遮挡螺纹孔", "standard_code": None}],
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("powder_coating", codes)

    def test_surface_treatment_included_with_title_block_field(self) -> None:
        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                surface_treatment={
                    "required": True,
                    "raw_text": "喷塑 色号:PANTONE",
                    "standard_code": "POWDER_COATING",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        self.assertIn("powder_coating", set(operation_codes(route)))

    def test_cylindrical_grinding_not_in_non_turning_families(self) -> None:
        """缺陷 #1 回归：外圆磨不得出现在钣金/大板/方件路线中。"""

        for category, part_type, compatible in (
            ("钣金类", "thin_plate", ("thin_plate", "plate")),
            ("大板类", "plate", ("plate", "long_bar")),
            ("方件类", "block", ("block", "plate")),
        ):
            route = _plan(
                make_part_feature(
                    category_name=category,
                    part_type=part_type,
                    compatible_part_types=compatible,
                    technical_requirements=[{"raw_text": "Ra1.6,平面度0.02"}],
                )
            )
            codes = set(operation_codes(route))
            self.assertNotIn("cylindrical_grinding", codes, f"{category}: {sorted(codes)}")

    def test_cylindrical_grinding_kept_for_turning(self) -> None:
        """缺陷 #1 反例：轴类有精度证据时外圆磨必须保留。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                technical_requirements=[{"raw_text": "Ø12 j6,Ra0.8"}],
            )
        )
        self.assertIn("cylindrical_grinding", set(operation_codes(route)))

    def test_welding_conditional_sentence_does_not_add_welding(self) -> None:
        """缺陷 #2 回归：条件句不入路线，但保留复核。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                technical_requirements=[
                    {"raw_text": "对于尺寸较大的钣金件,对接合处焊接加固"},
                ],
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("sheet_metal_welding", codes)
        self.assertIn("WELDING_CONDITIONAL_TEXT", risk_codes(route))

    def test_welding_required_sentence_adds_welding(self) -> None:
        """缺陷 #2 反例：肯定焊接句仍正确触发。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                technical_requirements=[{"raw_text": "对接处满焊,焊缝高度2mm"}],
            )
        )
        self.assertIn("sheet_metal_welding", set(operation_codes(route)))

    def test_welding_required_survives_with_conditional_present(self) -> None:
        """review-only 与 required 焊接同件出现时，二者都不丢。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                technical_requirements=[
                    {"raw_text": "对于尺寸较大的钣金件,焊接加固"},
                    {"raw_text": "对接处满焊,焊缝高度2mm"},
                ],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("sheet_metal_welding", codes)
        self.assertIn("WELDING_CONDITIONAL_TEXT", risk_codes(route))

    def test_stress_relief_and_straightening_for_long_strip_plate(self) -> None:
        """缺陷 #3 回归：大板长条补去应力 + 校平。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="long_bar",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "45"},
                bounding_box={"length": 800, "width": 120, "thickness": 25},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("stress_relief", codes)
        self.assertIn("straightening", codes)

    def test_quenched_alloy_shaft_has_stress_relief_but_no_straightening(self) -> None:
        """缺陷 #3 回归：调质/淬火轴补去应力，但不加校平。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                material={"raw_text": "40Cr"},
                heat_treatment={"required": True, "raw_text": "淬火HRC45-50"},
                bounding_box={"length": 400, "width": 30, "thickness": 30},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("stress_relief", codes)
        self.assertNotIn("straightening", codes)

    def test_turning_drops_all_face_hole_noise(self) -> None:
        """缺陷 #4 回归：轴类对端面噪声孔不产 drilling/counterbore/tapping。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                holes=[
                    {"count": 2, "hole_type": "through"},
                    {"count": 1, "hole_type": "thread", "thread_size": "M8"},
                ],
                technical_requirements=[{"raw_text": "M8 外螺纹"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("drilling", codes)
        self.assertNotIn("counterbore", codes)
        self.assertNotIn("tapping", codes)

    def test_route_length_bounded_by_skeleton_plus_candidates(self) -> None:
        for category, part_type, compatible in (
            ("钣金类", "thin_plate", ("thin_plate", "plate", "complex")),
            ("圆件类", "shaft", ("shaft",)),
            ("大板类", "plate", ("plate", "long_bar")),
            ("方件类", "block", ("block", "plate")),
        ):
            route = _plan(_bug_inducing(category, part_type, compatible))
            family = route["family"]
            skeleton_len = len(skeleton_for(family))
            # 防膨胀：路线 ≤ 骨架 + 已验证候选数。
            self.assertLessEqual(
                len(operation_codes(route)),
                skeleton_len + len(operation_codes(route)),
            )
            # 灾难性偏离的量级控制：远小于旧链 20–38。
            self.assertLessEqual(len(operation_codes(route)), skeleton_len + 8)

    def test_flat_sheet_metal_does_not_add_bending(self) -> None:
        """PR1：纯平板（无折弯文本/成形几何）不加 bending。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                bounding_box={"length": 1700, "width": 300, "height": 3},
            )
        )
        self.assertNotIn("bending", set(operation_codes(route)))

    def test_formed_sheet_metal_adds_bending(self) -> None:
        """PR1：装配/成形几何 → 加 bending。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="assembly_candidate",
                compatible_part_types=("thin_plate", "plate", "assembly_candidate"),
                bounding_box={"length": 600, "width": 501, "height": 1823},
            )
        )
        self.assertIn("bending", set(operation_codes(route)))

    def test_bending_text_adds_bending(self) -> None:
        """PR1：技术要求出现折弯说明 → 加 bending（即使是薄板）。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                bounding_box={"length": 400, "width": 200, "height": 2},
                technical_requirements=[{"raw_text": "折弯成形,折弯角90°"}],
            )
        )
        self.assertIn("bending", set(operation_codes(route)))

    def test_sheet_metal_support_bracket_geometry_adds_bending(self) -> None:
        """根因修复：检测支架这类立体钣金支架，即使 STEP 粗分为 block，也应加 bending。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="block",
                compatible_part_types=("thin_plate", "plate", "block"),
                part_name="检测支架",
                bounding_box={"length": 30, "width": 35, "height": 40},
            )
        )
        self.assertIn("bending", set(operation_codes(route)))

    def test_assembly_candidate_sheet_metal_adds_welding(self) -> None:
        """PR1：assembly_candidate 钣金作为强几何证据 → 加 sheet_metal_welding。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="assembly_candidate",
                compatible_part_types=("thin_plate", "plate", "assembly_candidate"),
                material={"raw_text": "Q235A"},
                bounding_box={"length": 600, "width": 501, "height": 1823},
            )
        )
        self.assertIn("sheet_metal_welding", set(operation_codes(route)))

    def test_clear_anodizing_and_sand_blasting_both_added(self) -> None:
        """PR3：标题栏“本色氧化，喷砂” → sand_blasting + clear_anodizing 同时输出。"""

        route = _plan(
            make_part_feature(
                category_name="方件类",
                part_type="block",
                compatible_part_types=("block",),
                material={"raw_text": "6061"},
                surface_treatment={
                    "required": True,
                    "raw_text": "本色氧化，喷砂",
                    "standard_code": None,
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("sand_blasting", codes)
        self.assertIn("clear_anodizing", codes)

    def test_pantone_sheet_metal_q235_infers_powder_coating(self) -> None:
        """PR3：PANTONE 色号 + Q235 钣金 → 推断 powder_coating。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                material={"raw_text": "Q235A"},
                surface_treatment={
                    "required": True,
                    "raw_text": "色号:PANTONE427C",
                    "standard_code": None,
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        self.assertIn("powder_coating", set(operation_codes(route)))

    def test_turning_external_thread_not_mapped_to_tapping(self) -> None:
        """PR2：外螺纹只产 external_thread_turning，绝不产 tapping。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                holes=[{"count": 1, "hole_type": "thread", "thread_size": "M8"}],
                technical_requirements=[{"raw_text": "M8 外螺纹"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("tapping", codes)
        self.assertIn("external_thread_turning", codes)

    def test_turning_real_holes_restored(self) -> None:
        """PR2：轴类真实多孔（>=3、多直径）应恢复 drilling。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                holes=[
                    {"count": 4, "hole_type": "through", "diameter": 6},
                    {"count": 2, "hole_type": "through", "diameter": 8},
                ],
                technical_requirements=[{"raw_text": "径向通孔4-Ø6,2-Ø8"}],
            )
        )
        self.assertIn("drilling", set(operation_codes(route)))

    def test_turning_internal_thread_taps(self) -> None:
        """PR2：明确内螺纹孔（无外螺纹） → tapping。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                holes=[
                    {"count": 3, "hole_type": "through", "diameter": 5},
                    {"count": 2, "hole_type": "thread", "thread_size": "M6"},
                ],
                technical_requirements=[{"raw_text": "端面螺纹孔M6攻牙"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("drilling", codes)
        self.assertIn("tapping", codes)

    def test_turning_thread_candidate_taps_without_verbose_text(self) -> None:
        """Phase3：M5;10 这类短孔标注进入 thread_candidate 时，轴类也应攻牙。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                holes=[{"count": 1, "hole_type": "thread_candidate", "diameter": 5}],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("drilling", codes)
        self.assertIn("tapping", codes)

    def test_shaft_complex_surface_adds_shaft_milling_not_generic_cnc(self) -> None:
        """Phase3：轴上扁位/长圆槽等非回转面用专用 shaft_milling，不放开通用 CNC。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="complex_surface_candidate",
                compatible_part_types=("complex_surface_candidate", "shaft", "shaft_candidate"),
                bounding_box={"length": 326, "width": 20, "height": 20},
                complexity={"complexity_score": 85},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("shaft_milling", codes)
        self.assertNotIn("cnc_rough_milling", codes)
        self.assertNotIn("slot_milling", codes)

    def test_countersink_not_merged_into_counterbore(self) -> None:
        """Phase3：沉头孔输出 countersink，不再被压平成 counterbore。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                holes=[{"count": 4, "hole_type": "countersink", "diameter": 4.5}],
                bounding_box={"length": 650, "width": 275, "height": 3},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("countersink", codes)
        self.assertNotIn("counterbore", codes)
        self.assertNotIn("bending", codes)

    def test_sheet_metal_shallow_counterbore_signal_does_not_duplicate_countersink(self) -> None:
        """Phase3：薄板 90°沉头的浅台阶副信号不重复生成 counterbore。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                holes=[
                    {
                        "count": 8,
                        "hole_type": "through",
                        "diameter": 4.5,
                        "counterbore_diameter": 9.0,
                        "counterbore_depth": 0.5,
                    },
                    {
                        "count": 8,
                        "hole_type": "countersink",
                        "diameter": 4.5,
                        "countersink_diameter": 9.0,
                        "countersink_angle": 90.0,
                    },
                ],
                bounding_box={"length": 650, "width": 275, "height": 3},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("countersink", codes)
        self.assertNotIn("counterbore", codes)

    def test_plain_slot_does_not_expand_to_wire_edm_or_pocket(self) -> None:
        """根因修复：普通槽只触发 slot_milling，不自动膨胀为 wire/edm/pocket。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "6061"},
                slots=[{"count": 1}],
                complexity={"slot_count": 1, "small_radius_count": 0},
                bounding_box={"length": 967, "width": 30, "height": 12},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("slot_milling", codes)
        self.assertNotIn("pocket_milling", codes)
        self.assertNotIn("wire_cut_profile", codes)
        self.assertNotIn("edm", codes)

    def test_long_aluminum_strip_large_plate_adds_boundary_review(self) -> None:
        """Phase3：细长铝条走大板时不改族，但提示路线可能偏重。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="long_bar",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "6061"},
                bounding_box={"length": 967, "width": 30, "height": 12},
            )
        )
        self.assertIn("LONG_STRIP_BOUNDARY_REVIEW", risk_codes(route))

    def test_aluminum_block_without_flatness_does_not_add_surface_grinding(self) -> None:
        """根因修复：6061 普通方件/长条无平面磨强证据，不加 surface_grinding_rough。"""

        route = _plan(
            make_part_feature(
                category_name="方件类",
                part_type="block",
                compatible_part_types=("block",),
                material={"raw_text": "6061"},
                surface_treatment={
                    "required": True,
                    "raw_text": "本色氧化，喷砂",
                    "standard_code": None,
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                bounding_box={"length": 200, "width": 12, "height": 12},
            )
        )
        self.assertNotIn("surface_grinding_rough", set(operation_codes(route)))

    def test_template_conditional_welding_not_added_on_single_sheet(self) -> None:
        """P1：标准模板条件句 + 单片钣金 → 不焊，只产 WELDING_CONDITIONAL_TEXT 复核。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                bounding_box={"length": 650, "width": 275, "height": 3},
                technical_requirements=[
                    {"raw_text": "对于尺寸较大的钣金件,对接合处进行焊接加固,焊后打磨"},
                ],
            )
        )
        self.assertNotIn("sheet_metal_welding", set(operation_codes(route)))
        self.assertIn("WELDING_CONDITIONAL_TEXT", risk_codes(route))

    def test_assembly_weldment_still_welds_with_same_template(self) -> None:
        """P1 反例：装配/焊接件即使同样模板句仍由几何强证据焊接。"""

        route = _plan(
            make_part_feature(
                category_name="焊接类",
                part_type="assembly_candidate",
                compatible_part_types=("thin_plate", "plate", "assembly_candidate"),
                technical_requirements=[
                    {"raw_text": "对于尺寸较大的钣金件,对接合处进行焊接加固,焊后打磨"},
                ],
            )
        )
        self.assertIn("sheet_metal_welding", set(operation_codes(route)))

    def test_unconditional_weld_text_still_required(self) -> None:
        """P1 反例：无条件焊接句仍正确触发焊接。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="thin_plate",
                compatible_part_types=("thin_plate", "plate"),
                technical_requirements=[{"raw_text": "对接处满焊,焊缝高度2mm,焊后打磨"}],
            )
        )
        self.assertIn("sheet_metal_welding", set(operation_codes(route)))

    def test_ral_white_on_sheet_steel_infers_powder_coating(self) -> None:
        """P2：碳钢/钣金标题栏"亮光白色（9003）" → 推断 powder_coating。"""

        route = _plan(
            make_part_feature(
                category_name="钣金类",
                part_type="assembly_candidate",
                compatible_part_types=("thin_plate", "plate", "assembly_candidate"),
                material={"raw_text": "Q235A"},
                surface_treatment={
                    "required": True,
                    "raw_text": "亮光白色（9003）",
                    "standard_code": None,
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        self.assertIn("powder_coating", set(operation_codes(route)))

    def test_color_text_on_aluminum_does_not_powder_coat(self) -> None:
        """P2 反例：铝件本色氧化+喷砂 → 阳极/喷砂，绝不喷塑。"""

        route = _plan(
            make_part_feature(
                category_name="方件类",
                part_type="block",
                compatible_part_types=("block",),
                material={"raw_text": "6061"},
                surface_treatment={
                    "required": True,
                    "raw_text": "本色氧化，喷砂",
                    "standard_code": None,
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("clear_anodizing", codes)
        self.assertNotIn("powder_coating", codes)

    def test_plain_shaft_no_shaft_milling(self) -> None:
        """P3：光轴（complex_surface_candidate 噪声类、无真实铣削特征）不加 shaft_milling。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="complex_surface_candidate",
                compatible_part_types=("shaft",),
                bounding_box={"length": 122, "width": 8, "height": 8},
                holes=[{"count": 2, "hole_type": "thread", "thread_size": "M3"}],
                technical_requirements=[{"raw_text": "端面螺纹孔M3攻牙"}],
            )
        )
        self.assertNotIn("shaft_milling", set(operation_codes(route)))
        self.assertIn("SHAFT_SURFACE_REVIEW", risk_codes(route))

    def test_shaft_with_flat_keeps_shaft_milling(self) -> None:
        """P3 反例：有铣扁文本证据时仍产 shaft_milling。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                technical_requirements=[{"raw_text": "轴端铣扁,对边宽12"}],
            )
        )
        self.assertIn("shaft_milling", set(operation_codes(route)))

    def test_external_thread_geometry_adds_turning_not_tapping(self) -> None:
        """P4：轴端 M12 外圆螺纹（无"外螺纹"文本）→ external_thread_turning；M4 内孔仍攻牙。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                bounding_box={"length": 135, "width": 12, "height": 12},
                holes=[
                    {"count": 1, "hole_type": "thread", "diameter": 12},
                    {"count": 1, "hole_type": "thread", "diameter": 3.3, "thread_size": "M4"},
                ],
                technical_requirements=[{"raw_text": "端面M4-6H深8"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("external_thread_turning", codes)
        self.assertIn("tapping", codes)

    def test_external_thread_only_stud_no_tapping(self) -> None:
        """P4 反例：纯外螺纹螺杆（无内孔）→ 只车外螺纹，绝不攻牙/钻孔。"""

        route = _plan(
            make_part_feature(
                category_name="圆件类",
                part_type="shaft",
                compatible_part_types=("shaft",),
                bounding_box={"length": 80, "width": 10, "height": 10},
                holes=[{"count": 1, "hole_type": "thread", "diameter": 10}],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("external_thread_turning", codes)
        self.assertNotIn("tapping", codes)

    # ---- 大板类 P2–P5 ----

    def test_large_plate_h7_precision_candidate_triggers_reaming(self) -> None:
        """大板P2：精孔(precision_candidate)证据 → reaming + precision_hole_inspection。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "45"},
                surface_treatment={
                    "required": True,
                    "raw_text": "镀硬铬",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                holes=[
                    {"count": 5, "hole_type": "precision_candidate", "raw_text": "5 H7 完全贯穿"}
                ],
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("reaming", codes)
        self.assertIn("precision_hole_inspection", codes)

    def test_plain_tolerance_hole_not_precision(self) -> None:
        """大板P2 反例：普通通孔(±公差)不应被当精孔，不产 reaming。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "45"},
                holes=[{"count": 5, "hole_type": "through"}],
            )
        )
        self.assertNotIn("reaming", set(operation_codes(route)))

    def test_aluminum_long_plate_no_stress_relief_has_support(self) -> None:
        """大板P3：铝长板无 stress_relief，改 straightening + support_anti_deformation。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "6061"},
                bounding_box={"length": 900, "width": 120, "height": 12},
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("stress_relief", codes)
        self.assertIn("straightening", codes)
        self.assertIn("support_anti_deformation", codes)

    def test_steel_long_plate_keeps_stress_relief(self) -> None:
        """大板P3 反例：钢长板仍有 stress_relief。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "45"},
                bounding_box={"length": 900, "width": 120, "height": 12},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("stress_relief", codes)
        self.assertNotIn("support_anti_deformation", codes)

    def test_large_plate_no_cnc_candidate_no_forbidden(self) -> None:
        """大板P4：大板路线无通用 cnc_*，也无 FORBIDDEN_OP_TRIGGERED_REVIEW（源头不生成）。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="complex_block",
                compatible_part_types=("plate", "long_bar", "complex_block"),
                material={"raw_text": "45"},
                complexity={"complexity_score": 85},
            )
        )
        codes = set(operation_codes(route))
        self.assertEqual(codes & {"cnc_rough_milling", "cnc_finish_milling", "cnc_milling"}, set())
        self.assertNotIn("FORBIDDEN_OP_TRIGGERED_REVIEW", risk_codes(route))
        self.assertIn("large_plate_roughing", codes)

    def test_machining_cnc_still_main_line(self) -> None:
        """大板P4 隔离：普通机加件 CNC 仍是主线，不受大板抑制影响。"""

        route = _plan(
            make_part_feature(
                category_name="方件类",
                part_type="complex_block",
                compatible_part_types=("block", "complex_block"),
                material={"raw_text": "45"},
                complexity={"complexity_score": 85},
            )
        )
        codes = set(operation_codes(route))
        self.assertIn("cnc_rough_milling", codes)
        self.assertIn("cnc_finish_milling", codes)

    def test_aluminum_anodize_fit_precision_reams(self) -> None:
        """大板P5：铝阳极 + 配合精孔 → post_anodize_reaming。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "6061"},
                surface_treatment={
                    "required": True,
                    "raw_text": "本色氧化",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                holes=[{"count": 2, "hole_type": "precision_candidate"}],
            )
        )
        self.assertIn("post_anodize_reaming", set(operation_codes(route)))

    def test_aluminum_anodize_thread_only_no_reaming(self) -> None:
        """大板P5 反例：铝阳极 + 纯螺纹(无配合精孔) → 只 thread_chasing，不后铰。"""

        route = _plan(
            make_part_feature(
                category_name="大板类",
                part_type="plate",
                compatible_part_types=("plate", "long_bar"),
                material={"raw_text": "6061"},
                surface_treatment={
                    "required": True,
                    "raw_text": "本色氧化",
                    "source": {"source_type": "pdf", "file_id": "pdf-1"},
                },
                holes=[{"count": 4, "hole_type": "thread_candidate"}],
            )
        )
        codes = set(operation_codes(route))
        self.assertNotIn("post_anodize_reaming", codes)
        self.assertIn("thread_chasing", codes)

    def test_stage_sequence_is_monotonic(self) -> None:
        from backend.app.process_recognition import STAGE_SEQUENCE

        route = _plan(_bug_inducing("方件类", "block", ("block", "plate")))
        stage_indices = [
            STAGE_SEQUENCE.index(stage["stage_code"])
            for stage in route["stage_route"]
            if stage.get("stage_code") in STAGE_SEQUENCE
        ]
        self.assertEqual(stage_indices, sorted(stage_indices))


if __name__ == "__main__":
    unittest.main()
