from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.app.market_material_pricing import (
    GptMaterialPriceExtractor,
    GptMaterialPriceEstimator,
    GptSurfaceTreatmentPriceEstimator,
    GptSurfaceTreatmentPriceExtractor,
    MaterialMarketPrice,
    SurfaceTreatmentMarketPrice,
    TavilySurfaceTreatmentPriceProvider,
    TavilyMaterialPriceProvider,
    build_material_estimate_provider_from_env,
    build_surface_treatment_estimate_provider_from_env,
    build_tavily_material_price_provider_from_env,
    build_tavily_surface_treatment_price_provider_from_env,
    extract_unit_prices,
    normalize_material_code,
)


class MarketMaterialPricingTests(unittest.TestCase):
    def test_extracts_ton_price_as_kg_price(self) -> None:
        self.assertIn(
            3.76,
            extract_unit_prices("广州45#碳结圆钢20mm 3760元/吨"),
        )

    def test_extracts_range_price_as_average_kg_price(self) -> None:
        self.assertIn(
            45.0,
            extract_unit_prices("东莞SKD11模具钢 30-60元/kg"),
        )

    def test_normalizes_supported_material_codes(self) -> None:
        self.assertEqual(normalize_material_code("45"), "S45C")
        self.assertEqual(normalize_material_code("45#钢"), "S45C")
        self.assertEqual(normalize_material_code("SUS304不锈钢板"), "SUS304")
        self.assertEqual(normalize_material_code("6061-T6铝板"), "AL6061")

    def test_gpt_extractor_accepts_valid_tavily_price(self) -> None:
        extractor = FakeGptExtractor(
            {
                "found": True,
                "material_code": "S45C",
                "unit_price": 3.76,
                "unit": "CNY/kg",
                "price_date": "2026-06-11",
                "region": "广州",
                "title": "广州45#碳结圆钢20mm",
                "url": "https://example.test/price",
                "snippet": "广州45#碳结圆钢20mm 3760元/吨",
                "confidence": 0.84,
                "reject_reason": None,
            }
        )

        price = extractor.extract_price(
            material_code="S45C",
            material_text="45",
            material_spec=None,
            region="south_china",
            queries=["45# 广东 价格 元/吨"],
            search_results=[
                {
                    "title": "广州45#碳结圆钢20mm",
                    "url": "https://example.test/price",
                    "content": "广州45#碳结圆钢20mm 3760元/吨",
                }
            ],
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.provider, "tavily_gpt")
        self.assertEqual(price.rule_id, "TAVILY_GPT_MATERIAL_PRICE_SEARCH")
        self.assertEqual(price.unit_price, 3.76)
        self.assertEqual(price.price_source("v1")["source_type"], "market_search")

    def test_gpt_extractor_rejects_outlier_price(self) -> None:
        extractor = FakeGptExtractor(
            {
                "found": True,
                "material_code": "S45C",
                "unit_price": 120.0,
                "unit": "CNY/kg",
                "price_date": "2026-06-11",
                "region": "广州",
                "title": "错误价格",
                "url": "https://example.test/price",
                "snippet": "错误价格 120元/kg",
                "confidence": 0.9,
                "reject_reason": None,
            }
        )

        price = extractor.extract_price(
            material_code="S45C",
            material_text="45",
            material_spec=None,
            region="south_china",
            queries=["45# 广东 价格 元/kg"],
            search_results=[],
        )

        self.assertIsNone(price)

    def test_tavily_provider_uses_gpt_extractor(self) -> None:
        provider = FakeTavilyProvider(
            extractor=FakeProviderExtractor(),
        )

        price = provider.find_unit_price(
            material_text="45",
            material_spec=None,
            region="south_china",
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.unit_price, 3.76)
        self.assertEqual(provider.extractor.seen_material_code, "S45C")

    def test_tavily_builder_enables_gpt_stream_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TAVILY_API_KEY": "tvly-test",
                "PRICE_AI_API_KEY": "openai-test",
                "PRICE_AI_BASE_URL": "https://example.test/v1",
                "PRICE_AI_API_MODE": "chat_completions",
                "PRICE_AI_MODEL": "test-model",
                "PRICE_AI_STREAM": "true",
            },
        ):
            provider = build_tavily_material_price_provider_from_env()

        self.assertIsNotNone(provider)
        assert provider is not None
        self.assertTrue(provider.extractor.stream)

    def test_surface_treatment_extractor_accepts_compatible_unit(self) -> None:
        extractor = FakeSurfaceTreatmentGptExtractor(
            {
                "found": True,
                "treatment_code": "chemical_nickel",
                "unit_price": 1200.0,
                "unit": "CNY/m2",
                "minimum_charge": None,
                "price_date": "2026-06-11",
                "region": "广东",
                "region_match": "exact",
                "title": "广东化学镀镍加工报价",
                "url": "https://example.test/surface-price",
                "snippet": "化学镀镍加工报价 1200元/m2",
                "confidence": 0.78,
                "reject_reason": None,
            }
        )

        price = extractor.extract_price(
            treatment_code="chemical_nickel",
            treatment_name="化学镍",
            expected_unit="CNY/m2",
            quantity_unit="m2",
            material_text="S45C",
            region="south_china",
            queries=["化学镍 广东 加工费 元/m2"],
            search_results=[
                {
                    "title": "广东化学镀镍加工报价",
                    "url": "https://example.test/surface-price",
                    "content": "化学镀镍加工报价 1200元/m2",
                }
            ],
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.unit_price, 1200.0)
        self.assertEqual(price.unit, "CNY/m2")
        self.assertEqual(price.rule_id, "TAVILY_GPT_SURFACE_TREATMENT_PRICE_SEARCH")

    def test_surface_treatment_extractor_rejects_incompatible_unit(self) -> None:
        extractor = FakeSurfaceTreatmentGptExtractor(
            {
                "found": True,
                "treatment_code": "chemical_nickel",
                "unit_price": 8.0,
                "unit": "CNY/dm2",
                "minimum_charge": None,
                "price_date": "2026-06-11",
                "region": "广东",
                "region_match": "exact",
                "title": "广东化学镀镍加工报价",
                "url": "https://example.test/surface-price",
                "snippet": "化学镀镍加工报价 8元/dm2",
                "confidence": 0.78,
                "reject_reason": None,
            }
        )

        price = extractor.extract_price(
            treatment_code="chemical_nickel",
            treatment_name="化学镍",
            expected_unit="CNY/m2",
            quantity_unit="m2",
            material_text="S45C",
            region="south_china",
            queries=["化学镍 广东 加工费 元/m2"],
            search_results=[],
        )

        self.assertIsNone(price)

    def test_surface_treatment_extractor_accepts_fallback_region_candidate(self) -> None:
        extractor = FakeSurfaceTreatmentGptExtractor(
            {
                "found": True,
                "treatment_code": "chemical_nickel",
                "unit_price": 900.0,
                "unit": "CNY/m2",
                "minimum_charge": None,
                "price_date": None,
                "region": "未标明地区",
                "region_match": "unknown",
                "title": "表面处理化学镍多少钱",
                "url": "https://example.test/surface-price",
                "snippet": "供应表面处理镀化学镍加工 900元/平方米",
                "confidence": 0.78,
                "reject_reason": None,
            }
        )

        price = extractor.extract_price(
            treatment_code="chemical_nickel",
            treatment_name="化学镍",
            expected_unit="CNY/m2",
            quantity_unit="m2",
            material_text="S45C",
            region="south_china",
            queries=["化学镍 广东 加工费 元/m2"],
            search_results=[],
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.region_match, "unknown")
        self.assertEqual(price.unit_price, 900.0)
        self.assertLessEqual(price.confidence, 0.68)

    def test_surface_treatment_provider_uses_gpt_extractor(self) -> None:
        provider = FakeTavilySurfaceTreatmentProvider(
            extractor=FakeSurfaceTreatmentProviderExtractor(),
        )

        price = provider.find_unit_price(
            treatment_code="chemical_nickel",
            treatment_name="化学镍",
            quantity_unit="m2",
            material_text="S45C",
            region="south_china",
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.unit_price, 1200.0)
        self.assertEqual(provider.extractor.seen_treatment_code, "chemical_nickel")

    def test_surface_treatment_builder_enables_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SURFACE_TREATMENT_PRICE_PROVIDER": "tavily",
                "TAVILY_API_KEY": "tvly-test",
                "PRICE_AI_API_KEY": "openai-test",
                "PRICE_AI_BASE_URL": "https://example.test/v1",
                "PRICE_AI_API_MODE": "chat_completions",
                "PRICE_AI_MODEL": "test-model",
                "PRICE_SURFACE_TREATMENT_AI_STREAM": "true",
            },
        ):
            provider = build_tavily_surface_treatment_price_provider_from_env()

        self.assertIsNotNone(provider)
        assert provider is not None
        self.assertTrue(provider.extractor.stream)

    def test_surface_treatment_gpt_only_estimator_returns_ai_estimate(self) -> None:
        estimator = FakeSurfaceTreatmentEstimator(
            {
                "found": True,
                "treatment_code": "chemical_nickel",
                "unit_price": 1300.0,
                "unit": "CNY/m2",
                "minimum_charge": None,
                "region": "south_china",
                "pricing_basis": "m2",
                "confidence": 0.55,
                "reason": "按华南化学镍小批量表面积计价估算，膜厚未知需复核。",
            }
        )

        price = estimator.estimate_price(
            treatment_code="chemical_nickel",
            treatment_name="化学镍",
            expected_unit="CNY/m2",
            quantity_unit="m2",
            material_text="S45C",
            region="south_china",
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.unit_price, 1300.0)
        self.assertEqual(price.source_type, "ai_estimate")
        self.assertEqual(price.rule_id, "GPT_SURFACE_TREATMENT_PRICE_ESTIMATE")
        self.assertLessEqual(price.confidence, 0.6)

    def test_surface_treatment_estimate_builder_enables_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SURFACE_TREATMENT_GPT_ESTIMATE_ENABLED": "true",
                "TAVILY_API_KEY": "tvly-test",
                "PRICE_AI_API_KEY": "openai-test",
                "PRICE_AI_BASE_URL": "https://example.test/v1",
                "PRICE_AI_API_MODE": "chat_completions",
                "PRICE_AI_MODEL": "test-model",
            },
        ):
            provider = build_surface_treatment_estimate_provider_from_env()

        self.assertIsNotNone(provider)

    def test_material_gpt_only_estimator_returns_ai_estimate(self) -> None:
        estimator = FakeMaterialEstimator(
            {
                "found": True,
                "material_code": "S45C",
                "unit_price": 5.25,
                "unit": "CNY/kg",
                "region": "south_china",
                "pricing_basis": "kg",
                "confidence": 0.55,
                "reason": "按华南45号钢首版核价区间估算，规格和含税口径需复核。",
            }
        )

        price = estimator.estimate_price(
            material_text="S45C",
            material_spec="45号钢",
            region="south_china",
        )

        self.assertIsNotNone(price)
        assert price is not None
        self.assertEqual(price.unit_price, 5.25)
        self.assertEqual(price.source_type, "ai_estimate")
        self.assertEqual(price.rule_id, "GPT_MATERIAL_PRICE_ESTIMATE")
        self.assertEqual(price.price_source("v1")["source_type"], "ai_estimate")
        self.assertLessEqual(price.confidence, 0.6)

    def test_material_estimate_builder_enables_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MATERIAL_GPT_ESTIMATE_ENABLED": "true",
                "TAVILY_API_KEY": "tvly-test",
                "PRICE_AI_API_KEY": "openai-test",
                "PRICE_AI_BASE_URL": "https://example.test/v1",
                "PRICE_AI_API_MODE": "chat_completions",
                "PRICE_AI_MODEL": "test-model",
            },
        ):
            provider = build_material_estimate_provider_from_env()

        self.assertIsNotNone(provider)

class FakeGptExtractor(GptMaterialPriceExtractor):
    def __init__(self, content: dict) -> None:
        super().__init__(
            api_key="test",
            model="test-model",
            base_url="https://example.test/v1",
            api_mode="chat_completions",
        )
        self.content = content

    def request_json(self, _system_prompt: str, _user_payload: dict) -> dict:
        return self.content


class FakeMaterialEstimator(GptMaterialPriceEstimator):
    def __init__(self, content: dict) -> None:
        super().__init__(
            api_key="test",
            model="test-model",
            base_url="https://example.test/v1",
            api_mode="chat_completions",
        )
        self.content = content

    def request_estimate_json(
        self,
        _system_prompt: str,
        _user_payload: dict,
    ) -> dict:
        return self.content


class FakeSurfaceTreatmentGptExtractor(GptSurfaceTreatmentPriceExtractor):
    def __init__(self, content: dict) -> None:
        super().__init__(
            api_key="test",
            model="test-model",
            base_url="https://example.test/v1",
            api_mode="chat_completions",
        )
        self.content = content

    def request_surface_treatment_json(
        self,
        _system_prompt: str,
        _user_payload: dict,
    ) -> dict:
        return self.content


class FakeSurfaceTreatmentEstimator(GptSurfaceTreatmentPriceEstimator):
    def __init__(self, content: dict) -> None:
        super().__init__(
            api_key="test",
            model="test-model",
            base_url="https://example.test/v1",
            api_mode="chat_completions",
        )
        self.content = content

    def request_estimate_json(
        self,
        _system_prompt: str,
        _user_payload: dict,
    ) -> dict:
        return self.content


class FakeProviderExtractor:
    seen_material_code: str | None = None

    def extract_price(self, **kwargs) -> MaterialMarketPrice:
        self.seen_material_code = kwargs["material_code"]
        return MaterialMarketPrice(
            material_code=kwargs["material_code"],
            unit_price=3.76,
            unit="CNY/kg",
            region=kwargs["region"],
            query=" | ".join(kwargs["queries"]),
            title="广州45#碳结圆钢20mm",
            url="https://example.test/price",
            snippet="广州45#碳结圆钢20mm 3760元/吨",
            source_domain="example.test",
            searched_at="2026-06-11T14:30:00+08:00",
            confidence=0.84,
            provider="tavily_gpt",
            rule_id="TAVILY_GPT_MATERIAL_PRICE_SEARCH",
        )


class FakeTavilyProvider(TavilyMaterialPriceProvider):
    def __init__(self, extractor: FakeProviderExtractor) -> None:
        super().__init__(
            api_key=None,
            extractor=extractor,  # type: ignore[arg-type]
            access_mode="keyless",
        )

    def search_query(self, query: str) -> list[dict]:
        return [
            {
                "title": "广州45#碳结圆钢20mm",
                "url": "https://example.test/price",
                "content": "广州45#碳结圆钢20mm 3760元/吨",
                "query": query,
            }
        ]


class FakeSurfaceTreatmentProviderExtractor:
    seen_treatment_code: str | None = None

    def extract_price(self, **kwargs) -> SurfaceTreatmentMarketPrice:
        self.seen_treatment_code = kwargs["treatment_code"]
        return SurfaceTreatmentMarketPrice(
            treatment_code=kwargs["treatment_code"],
            treatment_name=kwargs["treatment_name"],
            unit_price=1200.0,
            unit=kwargs["expected_unit"],
            minimum_charge=None,
            region=kwargs["region"],
            region_match="exact",
            query=" | ".join(kwargs["queries"]),
            title="广东化学镀镍加工报价",
            url="https://example.test/surface-price",
            snippet="化学镀镍加工报价 1200元/m2",
            source_domain="example.test",
            searched_at="2026-06-11T14:30:00+08:00",
            confidence=0.78,
        )


class FakeTavilySurfaceTreatmentProvider(TavilySurfaceTreatmentPriceProvider):
    def __init__(self, extractor: FakeSurfaceTreatmentProviderExtractor) -> None:
        super().__init__(
            api_key=None,
            extractor=extractor,  # type: ignore[arg-type]
            access_mode="keyless",
        )

    def search_query(self, query: str) -> list[dict]:
        return [
            {
                "title": "广东化学镀镍加工报价",
                "url": "https://example.test/surface-price",
                "content": "化学镀镍加工报价 1200元/m2",
                "query": query,
            }
        ]


if __name__ == "__main__":
    unittest.main()
