from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
import json
import os
import re
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from .ai_assistance import collect_openai_stream_text, stream_text_payload


REGION_KEYWORDS = {
    "south_china": ["华南", "广东", "广州", "佛山", "东莞", "深圳", "中山", "惠州"],
    "guangdong": ["广东", "广州", "佛山", "东莞", "深圳", "中山", "惠州"],
    "guangzhou": ["广州"],
    "foshan": ["佛山"],
    "dongguan": ["东莞"],
    "shenzhen": ["深圳"],
}

MATERIAL_ALIASES = {
    "S45C": ["S45C", "45#", "45号钢", "碳结钢", "碳结圆钢"],
    "SKD11": ["SKD11", "冷作模具钢", "模具钢", "D2"],
    "SUS304": ["SUS304", "304", "304不锈钢", "不锈钢"],
    "AL6061": ["AL6061", "6061", "6061-T6", "6061铝", "铝板", "铝棒"],
}

MATERIAL_PRICE_RANGES = {
    "S45C": (2.5, 8.0),
    "SKD11": (20.0, 90.0),
    "SUS304": (10.0, 35.0),
    "AL6061": (15.0, 45.0),
}

PRICE_PATTERNS = (
    re.compile(
        r"(?P<low>\d+(?:\.\d+)?)\s*[-~～至]\s*(?P<high>\d+(?:\.\d+)?)\s*元\s*/?\s*(?P<unit>kg|公斤|千克|吨|t|T)"
    ),
    re.compile(
        r"(?P<price>\d+(?:\.\d+)?)\s*万\s*元\s*/?\s*(?P<unit>吨|t|T)"
    ),
    re.compile(
        r"(?P<price>\d+(?:\.\d+)?)\s*元\s*/?\s*(?P<unit>kg|公斤|千克|吨|t|T)"
    ),
)

MATERIAL_PRICE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "found",
        "material_code",
        "unit_price",
        "unit",
        "price_date",
        "region",
        "title",
        "url",
        "snippet",
        "confidence",
        "reject_reason",
    ],
    "properties": {
        "found": {"type": "boolean"},
        "material_code": {"type": ["string", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "price_date": {"type": ["string", "null"]},
        "region": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "snippet": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"]},
        "reject_reason": {"type": ["string", "null"]},
    },
}

MATERIAL_PRICE_ESTIMATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "found",
        "material_code",
        "unit_price",
        "unit",
        "region",
        "pricing_basis",
        "confidence",
        "reason",
    ],
    "properties": {
        "found": {"type": "boolean"},
        "material_code": {"type": ["string", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "region": {"type": ["string", "null"]},
        "pricing_basis": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"]},
        "reason": {"type": ["string", "null"]},
    },
}

PROCESS_PRICE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "found",
        "operation_code",
        "unit_price",
        "unit",
        "price_date",
        "region",
        "title",
        "url",
        "snippet",
        "confidence",
        "reject_reason",
    ],
    "properties": {
        "found": {"type": "boolean"},
        "operation_code": {"type": ["string", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "price_date": {"type": ["string", "null"]},
        "region": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "snippet": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"]},
        "reject_reason": {"type": ["string", "null"]},
    },
}

SURFACE_TREATMENT_PRICE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "found",
        "treatment_code",
        "unit_price",
        "unit",
        "minimum_charge",
        "price_date",
        "region",
        "region_match",
        "title",
        "url",
        "snippet",
        "confidence",
        "reject_reason",
    ],
    "properties": {
        "found": {"type": "boolean"},
        "treatment_code": {"type": ["string", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "minimum_charge": {"type": ["number", "null"]},
        "price_date": {"type": ["string", "null"]},
        "region": {"type": ["string", "null"]},
        "region_match": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "snippet": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"]},
        "reject_reason": {"type": ["string", "null"]},
    },
}

SURFACE_TREATMENT_ESTIMATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "found",
        "treatment_code",
        "unit_price",
        "unit",
        "minimum_charge",
        "region",
        "pricing_basis",
        "confidence",
        "reason",
    ],
    "properties": {
        "found": {"type": "boolean"},
        "treatment_code": {"type": ["string", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "minimum_charge": {"type": ["number", "null"]},
        "region": {"type": ["string", "null"]},
        "pricing_basis": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"]},
        "reason": {"type": ["string", "null"]},
    },
}

PROCESS_SEARCH_TERMS = {
    "saw_cut": ["锯切下料", "锯床下料", "切割下料"],
    "surface_grinding_rough": ["平面粗磨", "平面磨床加工", "磨削加工"],
    "cnc_milling": ["CNC铣削", "CNC加工中心", "机加工"],
    "drilling": ["钻孔加工", "单孔钻孔", "孔加工"],
    "countersink": ["沉孔加工", "沉头孔加工", "锪孔加工"],
    "tapping": ["攻牙加工", "螺纹孔加工", "攻丝加工"],
    "wire_cut_profile": ["线切割加工", "中走丝线切割", "慢走丝线切割"],
    "heat_treatment": ["热处理加工", "淬火调质", "热处理外协"],
    "finish_grinding": ["精磨加工", "平面精磨", "磨床加工"],
    "precision_hole": ["精孔加工", "铰孔加工", "镗孔加工"],
    "deburr": ["去毛刺加工", "倒角去毛刺", "后处理去毛刺"],
    "inspection": ["尺寸检测", "终检", "外观尺寸检验"],
    "protective_packaging": ["防护包装", "防划伤包装", "工业包装"],
}

PROCESS_PRICE_UNITS = {
    "saw_cut": "CNY/mm2",
    "surface_grinding_rough": "CNY/mm2",
    "cnc_milling": "CNY/hour",
    "drilling": "CNY/pcs",
    "countersink": "CNY/pcs",
    "tapping": "CNY/pcs",
    "wire_cut_profile": "CNY/mm2",
    "heat_treatment": "CNY/kg",
    "finish_grinding": "CNY/mm2",
    "precision_hole": "CNY/pcs",
    "deburr": "CNY/score",
    "inspection": "CNY/pcs",
    "protective_packaging": "CNY/pcs",
}

PROCESS_PRICE_RANGES = {
    "saw_cut": (0.00001, 0.05),
    "surface_grinding_rough": (0.00001, 200.0),
    "cnc_milling": (30.0, 500.0),
    "drilling": (0.5, 80.0),
    "countersink": (0.5, 100.0),
    "tapping": (0.5, 100.0),
    "wire_cut_profile": (0.00001, 200.0),
    "heat_treatment": (1.0, 120.0),
    "finish_grinding": (0.00001, 200.0),
    "precision_hole": (1.0, 200.0),
    "deburr": (0.01, 80.0),
    "inspection": (1.0, 200.0),
    "protective_packaging": (1.0, 200.0),
}

PROCESS_UNIT_HINTS = {
    "CNY/hour": "元/小时 元/时 工时单价",
    "CNY/mm2": "元/mm2 元/平方毫米 加工单价",
    "CNY/pcs": "元/件 元/孔 单件单价 单孔价格",
    "CNY/kg": "元/kg 元/公斤",
    "CNY/score": "元/复杂度分 元/score 去毛刺单价",
}

SURFACE_TREATMENT_SEARCH_TERMS = {
    "chemical_nickel": ["化学镍", "化学镀镍", "镀镍", "Ni-P"],
}

SURFACE_TREATMENT_PRICE_UNITS = {
    "chemical_nickel": "CNY/m2",
}

SURFACE_TREATMENT_PRICE_RANGES = {
    "chemical_nickel": (50.0, 3000.0),
}

SURFACE_TREATMENT_UNIT_HINTS = {
    "CNY/kg": "元/kg 元/公斤 按重量计价",
    "CNY/m2": "元/m2 元/平方米 按面积计价",
    "CNY/dm2": "元/dm2 元/平方分米 按面积计价",
    "CNY/pcs": "元/件 单件处理价",
}


@dataclass(frozen=True)
class MaterialMarketPrice:
    material_code: str
    unit_price: float
    unit: str
    region: str
    query: str
    title: str
    url: str
    snippet: str
    source_domain: str
    searched_at: str
    confidence: float
    provider: str = "searxng"
    rule_id: str = "SEARXNG_MATERIAL_PRICE_SEARCH"
    source_type: str = "market_search"

    @property
    def source_id(self) -> str:
        digest = sha1((self.url or self.query).encode("utf-8")).hexdigest()[:12]
        return f"{self.provider}_{self.material_code.lower()}_{digest}"

    def price_source(self, version: str) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "rule_id": self.rule_id,
            "version": version,
        }


@dataclass(frozen=True)
class ProcessMarketPrice:
    operation_code: str
    operation_name: str
    unit_price: float
    unit: str
    region: str
    query: str
    title: str
    url: str
    snippet: str
    source_domain: str
    searched_at: str
    confidence: float
    provider: str = "tavily_gpt"
    rule_id: str = "TAVILY_GPT_PROCESS_PRICE_SEARCH"

    @property
    def source_id(self) -> str:
        digest = sha1(self.url.encode("utf-8")).hexdigest()[:12]
        return f"{self.provider}_{self.operation_code.lower()}_{digest}"

    def price_source(self, version: str) -> dict[str, Any]:
        return {
            "source_type": "market_search",
            "source_id": self.source_id,
            "rule_id": self.rule_id,
            "version": version,
        }


@dataclass(frozen=True)
class SurfaceTreatmentMarketPrice:
    treatment_code: str
    treatment_name: str
    unit_price: float
    unit: str
    minimum_charge: float | None
    region: str
    region_match: str
    query: str
    title: str
    url: str
    snippet: str
    source_domain: str
    searched_at: str
    confidence: float
    provider: str = "tavily_gpt"
    rule_id: str = "TAVILY_GPT_SURFACE_TREATMENT_PRICE_SEARCH"
    source_type: str = "market_search"

    @property
    def source_id(self) -> str:
        digest = sha1((self.url or self.query).encode("utf-8")).hexdigest()[:12]
        return f"{self.provider}_{self.treatment_code.lower()}_{digest}"

    def price_source(self, version: str) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "rule_id": self.rule_id,
            "version": version,
        }


class MaterialPriceProvider(Protocol):
    def find_unit_price(
        self,
        *,
        material_text: Any,
        material_spec: Any = None,
        region: str = "south_china",
    ) -> MaterialMarketPrice | None:
        ...


class MaterialEstimateProvider(Protocol):
    def find_unit_price(
        self,
        *,
        material_text: Any,
        material_spec: Any = None,
        region: str = "south_china",
    ) -> MaterialMarketPrice | None:
        ...


class ProcessPriceProvider(Protocol):
    def find_unit_price(
        self,
        *,
        operation_code: str,
        operation_name: str,
        quantity_unit: Any,
        material_text: Any = None,
        region: str = "south_china",
    ) -> ProcessMarketPrice | None:
        ...    


class SurfaceTreatmentPriceProvider(Protocol):
    def find_unit_price(
        self,
        *,
        treatment_code: str,
        treatment_name: str,
        quantity_unit: Any,
        material_text: Any = None,
        region: str = "south_china",
    ) -> SurfaceTreatmentMarketPrice | None:
        ...


class SearxngMaterialPriceProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 8.0,
        max_results: int = 12,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    def find_unit_price(
        self,
        *,
        material_text: Any,
        material_spec: Any = None,
        region: str = "south_china",
    ) -> MaterialMarketPrice | None:
        material_code = normalize_material_code(material_text)
        if material_code is None:
            return None

        candidates: list[MaterialMarketPrice] = []
        for query in build_queries(material_code, material_spec, region):
            candidates.extend(self.search_query(query, material_code, region))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item.confidence, reverse=True)
        return candidates[0]

    def search_query(
        self,
        query: str,
        material_code: str,
        region: str,
    ) -> list[MaterialMarketPrice]:
        try:
            response = httpx.get(
                f"{self.base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "language": "zh-CN",
                    "safesearch": "1",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            return []

        candidates: list[MaterialMarketPrice] = []
        searched_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        for result in results[: self.max_results]:
            if not isinstance(result, dict):
                continue
            title = str(result.get("title") or "")
            url = str(result.get("url") or "")
            snippet = str(result.get("content") or result.get("snippet") or "")
            text = " ".join(part for part in (title, snippet, url) if part)
            unit_prices = extract_unit_prices(text)
            if not unit_prices:
                continue
            domain = urlparse(url).netloc
            for unit_price in unit_prices:
                confidence = score_candidate(
                    text=text,
                    material_code=material_code,
                    region=region,
                    unit_price=unit_price,
                    domain=domain,
                )
                if confidence <= 0:
                    continue
                candidates.append(
                    MaterialMarketPrice(
                        material_code=material_code,
                        unit_price=round(unit_price, 4),
                        unit="CNY/kg",
                        region=region,
                        query=query,
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_domain=domain,
                        searched_at=searched_at,
                        confidence=round(confidence, 4),
                        provider="searxng",
                        rule_id="SEARXNG_MATERIAL_PRICE_SEARCH",
                    )
                )
        return candidates


class TavilyMaterialPriceProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        extractor: "GptMaterialPriceExtractor",
        search_url: str = "https://api.tavily.com/search",
        timeout_seconds: float = 20.0,
        max_results: int = 5,
        search_depth: str = "basic",
        access_mode: str = "api_key",
    ) -> None:
        self.api_key = api_key
        self.extractor = extractor
        self.search_url = search_url
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.search_depth = search_depth
        self.access_mode = access_mode

    def find_unit_price(
        self,
        *,
        material_text: Any,
        material_spec: Any = None,
        region: str = "south_china",
    ) -> MaterialMarketPrice | None:
        material_code = normalize_material_code(material_text)
        if material_code is None:
            return None

        all_results: list[dict[str, Any]] = []
        queries = build_queries(material_code, material_spec, region)
        for query in queries:
            all_results.extend(self.search_query(query))
            if len(all_results) >= self.max_results * 2:
                break
        if not all_results:
            return None

        return self.extractor.extract_price(
            material_code=material_code,
            material_text=material_text,
            material_spec=material_spec,
            region=region,
            queries=queries,
            search_results=all_results[: self.max_results * 2],
        )

    def search_query(self, query: str) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.access_mode == "keyless":
            headers["X-Tavily-Access-Mode"] = "keyless"
        else:
            return []
        try:
            response = httpx.post(
                self.search_url,
                headers=headers,
                json={
                    "query": query,
                    "search_depth": self.search_depth,
                    "topic": "general",
                    "include_answer": False,
                    "include_raw_content": False,
                    "max_results": self.max_results,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            return []
        compact_results: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            compact_results.append(
                {
                    "title": str(result.get("title") or ""),
                    "url": str(result.get("url") or ""),
                    "content": str(result.get("content") or ""),
                    "score": result.get("score"),
                    "query": query,
                }
            )
        return compact_results


class TavilyProcessPriceProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        extractor: "GptProcessPriceExtractor",
        search_url: str = "https://api.tavily.com/search",
        timeout_seconds: float = 20.0,
        max_results: int = 5,
        search_depth: str = "basic",
        access_mode: str = "api_key",
    ) -> None:
        self.api_key = api_key
        self.extractor = extractor
        self.search_url = search_url
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.search_depth = search_depth
        self.access_mode = access_mode

    def find_unit_price(
        self,
        *,
        operation_code: str,
        operation_name: str,
        quantity_unit: Any,
        material_text: Any = None,
        region: str = "south_china",
    ) -> ProcessMarketPrice | None:
        expected_unit = PROCESS_PRICE_UNITS.get(operation_code)
        if expected_unit is None:
            return None

        all_results: list[dict[str, Any]] = []
        queries = build_process_queries(
            operation_code=operation_code,
            operation_name=operation_name,
            expected_unit=expected_unit,
            material_text=material_text,
            region=region,
        )
        for query in queries:
            all_results.extend(self.search_query(query))
            if len(all_results) >= self.max_results * 2:
                break
        if not all_results:
            return None

        return self.extractor.extract_price(
            operation_code=operation_code,
            operation_name=operation_name,
            expected_unit=expected_unit,
            quantity_unit=quantity_unit,
            material_text=material_text,
            region=region,
            queries=queries,
            search_results=all_results[: self.max_results * 2],
        )

    def search_query(self, query: str) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.access_mode == "keyless":
            headers["X-Tavily-Access-Mode"] = "keyless"
        else:
            return []
        try:
            response = httpx.post(
                self.search_url,
                headers=headers,
                json={
                    "query": query,
                    "search_depth": self.search_depth,
                    "topic": "general",
                    "include_answer": False,
                    "include_raw_content": False,
                    "max_results": self.max_results,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            return []
        compact_results: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            compact_results.append(
                {
                    "title": str(result.get("title") or ""),
                    "url": str(result.get("url") or ""),
                    "content": str(result.get("content") or ""),
                    "score": result.get("score"),
                    "query": query,
                }
            )
        return compact_results


class TavilySurfaceTreatmentPriceProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        extractor: "GptSurfaceTreatmentPriceExtractor",
        search_url: str = "https://api.tavily.com/search",
        timeout_seconds: float = 20.0,
        max_results: int = 5,
        search_depth: str = "basic",
        access_mode: str = "api_key",
    ) -> None:
        self.api_key = api_key
        self.extractor = extractor
        self.search_url = search_url
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.search_depth = search_depth
        self.access_mode = access_mode

    def find_unit_price(
        self,
        *,
        treatment_code: str,
        treatment_name: str,
        quantity_unit: Any,
        material_text: Any = None,
        region: str = "south_china",
    ) -> SurfaceTreatmentMarketPrice | None:
        expected_unit = SURFACE_TREATMENT_PRICE_UNITS.get(treatment_code)
        if expected_unit is None:
            return None

        all_results: list[dict[str, Any]] = []
        queries = build_surface_treatment_queries(
            treatment_code=treatment_code,
            treatment_name=treatment_name,
            expected_unit=expected_unit,
            material_text=material_text,
            region=region,
        )
        for query in queries:
            all_results.extend(self.search_query(query))
            if len(all_results) >= self.max_results * 2:
                break
        if not all_results:
            return None

        return self.extractor.extract_price(
            treatment_code=treatment_code,
            treatment_name=treatment_name,
            expected_unit=expected_unit,
            quantity_unit=quantity_unit,
            material_text=material_text,
            region=region,
            queries=queries,
            search_results=all_results[: self.max_results * 2],
        )

    def search_query(self, query: str) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.access_mode == "keyless":
            headers["X-Tavily-Access-Mode"] = "keyless"
        else:
            return []
        try:
            response = httpx.post(
                self.search_url,
                headers=headers,
                json={
                    "query": query,
                    "search_depth": self.search_depth,
                    "topic": "general",
                    "include_answer": False,
                    "include_raw_content": False,
                    "max_results": self.max_results,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            return []
        compact_results: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            compact_results.append(
                {
                    "title": str(result.get("title") or ""),
                    "url": str(result.get("url") or ""),
                    "content": str(result.get("content") or ""),
                    "score": result.get("score"),
                    "query": query,
                }
            )
        return compact_results


class GptSurfaceTreatmentEstimateProvider:
    def __init__(self, *, estimator: "GptSurfaceTreatmentPriceEstimator") -> None:
        self.estimator = estimator

    def find_unit_price(
        self,
        *,
        treatment_code: str,
        treatment_name: str,
        quantity_unit: Any,
        material_text: Any = None,
        region: str = "south_china",
    ) -> SurfaceTreatmentMarketPrice | None:
        expected_unit = SURFACE_TREATMENT_PRICE_UNITS.get(treatment_code)
        if expected_unit is None:
            return None
        return self.estimator.estimate_price(
            treatment_code=treatment_code,
            treatment_name=treatment_name,
            expected_unit=expected_unit,
            quantity_unit=quantity_unit,
            material_text=material_text,
            region=region,
        )


class GptMaterialEstimateProvider:
    def __init__(self, *, estimator: "GptMaterialPriceEstimator") -> None:
        self.estimator = estimator

    def find_unit_price(
        self,
        *,
        material_text: Any,
        material_spec: Any = None,
        region: str = "south_china",
    ) -> MaterialMarketPrice | None:
        return self.estimator.estimate_price(
            material_text=material_text,
            material_spec=material_spec,
            region=region,
        )


class GptMaterialPriceExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        api_mode: str,
        timeout_seconds: float = 60.0,
        stream: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_mode = api_mode
        self.timeout_seconds = timeout_seconds
        self.stream = stream

    def extract_price(
        self,
        *,
        material_code: str,
        material_text: Any,
        material_spec: Any,
        region: str,
        queries: list[str],
        search_results: list[dict[str, Any]],
    ) -> MaterialMarketPrice | None:
        payload = {
            "material_code": material_code,
            "material_text": material_text,
            "material_spec": material_spec,
            "region": region,
            "region_keywords": REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"]),
            "allowed_aliases": MATERIAL_ALIASES.get(material_code, [material_code]),
            "reasonable_price_range_cny_per_kg": MATERIAL_PRICE_RANGES.get(material_code),
            "queries": queries,
            "search_results": search_results,
            "today": datetime.now(timezone.utc).astimezone().date().isoformat(),
        }
        prompt = (
            "You extract one current South China material unit price from search results. "
            "Use only the supplied search_results. Do not invent prices. "
            "Return JSON only with keys: found, material_code, unit_price, unit, "
            "price_date, region, title, url, snippet, confidence, reject_reason. "
            "The accepted unit must be CNY/kg. Convert CNY/ton to CNY/kg by dividing by 1000. "
            "Reject if there is no source URL, no material match, no South China/Guangdong-area match, "
            "no explicit price, or the price is outside the reasonable range."
        )
        try:
            content = self.request_json(prompt, payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        if not content.get("found"):
            return None
        unit_price = parse_float(content.get("unit_price"))
        if unit_price is None:
            return None
        confidence = clamp(parse_float(content.get("confidence")), 0.0, 1.0, default=0.0)
        if not validate_extracted_price(
            material_code=material_code,
            unit_price=unit_price,
            unit=str(content.get("unit") or ""),
            url=str(content.get("url") or ""),
            confidence=confidence,
        ):
            return None
        url = str(content.get("url") or "")
        title = str(content.get("title") or "")
        snippet = str(content.get("snippet") or "")
        domain = urlparse(url).netloc
        searched_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return MaterialMarketPrice(
            material_code=material_code,
            unit_price=round(unit_price, 4),
            unit="CNY/kg",
            region=str(content.get("region") or region),
            query=" | ".join(queries[:3]),
            title=title,
            url=url,
            snippet=snippet,
            source_domain=domain,
            searched_at=searched_at,
            confidence=round(confidence, 4),
            provider="tavily_gpt",
            rule_id="TAVILY_GPT_MATERIAL_PRICE_SEARCH",
        )

    def request_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if self.api_mode == "chat_completions":
            response = self.post_json(
                f"{self.base_url}/chat/completions",
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            text = extract_chat_completion_text(response)
        else:
            response = self.post_json(
                f"{self.base_url}/responses",
                {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "material_price_extraction",
                            "schema": MATERIAL_PRICE_EXTRACTION_SCHEMA,
                            "strict": True,
                        }
                    },
                },
            )
            text = extract_response_text(response)
        content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError("material price extraction response must be an object")
        return content

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_payload = dict(payload)
        if self.stream:
            request_payload["stream"] = True
        with httpx.Client(timeout=self.timeout_seconds) as client:
            if self.stream:
                with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=request_payload,
                ) as response:
                    response.raise_for_status()
                    response_text = collect_openai_stream_text(response.iter_lines())
                    return stream_text_payload(self.api_mode, response_text)
            response = client.post(
                url,
                headers=headers,
                json=request_payload,
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("AI response must be a JSON object")
        return data


class GptMaterialPriceEstimator(GptMaterialPriceExtractor):
    def estimate_price(
        self,
        *,
        material_text: Any,
        material_spec: Any = None,
        region: str = "south_china",
    ) -> MaterialMarketPrice | None:
        material_code = normalize_material_code(material_text)
        if material_code is None:
            material_code = normalize_material_code(material_spec)
        if material_code is None:
            return None

        low, high = MATERIAL_PRICE_RANGES.get(material_code, (0.1, 1000.0))
        payload = {
            "material_code": material_code,
            "material_text": material_text,
            "material_spec": material_spec,
            "region": region,
            "region_keywords": REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"]),
            "allowed_aliases": MATERIAL_ALIASES.get(material_code, [material_code]),
            "reasonable_price_range_cny_per_kg": [low, high],
            "default_midpoint": round((low + high) / 2, 4),
            "constraints": [
                "This is an estimate, not a real-time market quotation.",
                "Do not claim web/source verification.",
                "Use CNY/kg only.",
                "Stay within the supplied reasonable price range.",
                "Set confidence <= 0.6 because supplier, brand, specification, tax basis, and date source are not verified.",
            ],
            "today": datetime.now(timezone.utc).astimezone().date().isoformat(),
        }
        prompt = (
            "You estimate one conservative South China material unit price for first-pass quoting. "
            "This is GPT-only estimation, not real-time market data. Do not claim it is today's market price. "
            "Use only the provided material code, reasonable price range, and constraints. "
            "Return JSON only with keys: found, material_code, unit_price, unit, region, "
            "pricing_basis, confidence, reason. The accepted unit must be CNY/kg. "
            "Choose a practical first-pass value in the range, normally near the midpoint unless "
            "the material family or specification justifies otherwise."
        )
        try:
            content = self.request_estimate_json(prompt, payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        if not content.get("found"):
            return None
        unit_price = parse_float(content.get("unit_price"))
        if unit_price is None:
            return None
        confidence = clamp(parse_float(content.get("confidence")), 0.0, 0.6, default=0.45)
        if not validate_extracted_price(
            material_code=material_code,
            unit_price=unit_price,
            unit=str(content.get("unit") or ""),
            url="ai://material-price-estimate",
            confidence=max(confidence, 0.5),
            allow_ai_url=True,
        ):
            return None

        reason = str(content.get("reason") or "材料实时行情搜索未提供可用单价，使用 AI 估算价。")
        return MaterialMarketPrice(
            material_code=material_code,
            unit_price=round(unit_price, 4),
            unit="CNY/kg",
            region=str(content.get("region") or region),
            query=reason,
            title="AI 材料估算价",
            url=f"ai://material-price-estimate/{material_code.lower()}",
            snippet=reason,
            source_domain="ai_estimate",
            searched_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            confidence=round(confidence, 4),
            provider="gpt_estimate",
            rule_id="GPT_MATERIAL_PRICE_ESTIMATE",
            source_type="ai_estimate",
        )

    def request_estimate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.api_mode == "chat_completions":
            response = self.post_json(
                f"{self.base_url}/chat/completions",
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            text = extract_chat_completion_text(response)
        else:
            response = self.post_json(
                f"{self.base_url}/responses",
                {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "material_price_estimate",
                            "schema": MATERIAL_PRICE_ESTIMATE_SCHEMA,
                            "strict": True,
                        }
                    },
                },
            )
            text = extract_response_text(response)
        content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError("material price estimate response must be an object")
        return content


class GptProcessPriceExtractor(GptMaterialPriceExtractor):
    def extract_price(
        self,
        *,
        operation_code: str,
        operation_name: str,
        expected_unit: str,
        quantity_unit: Any,
        material_text: Any,
        region: str,
        queries: list[str],
        search_results: list[dict[str, Any]],
    ) -> ProcessMarketPrice | None:
        payload = {
            "operation_code": operation_code,
            "operation_name": operation_name,
            "expected_unit": expected_unit,
            "quantity_unit": quantity_unit,
            "material_text": material_text,
            "region": region,
            "region_keywords": REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"]),
            "operation_search_terms": PROCESS_SEARCH_TERMS.get(operation_code, [operation_name]),
            "reasonable_price_range": PROCESS_PRICE_RANGES.get(operation_code),
            "queries": queries,
            "search_results": search_results,
            "today": datetime.now(timezone.utc).astimezone().date().isoformat(),
        }
        prompt = (
            "You extract one current South China manufacturing process unit price "
            "from search results. Use only supplied search_results. Do not invent prices. "
            "Return JSON only with keys: found, operation_code, unit_price, unit, "
            "price_date, region, title, url, snippet, confidence, reject_reason. "
            f"The accepted unit must be {expected_unit}. "
            "Reject if there is no source URL, no operation match, no South China/Guangdong-area match, "
            "no explicit price, or the price is outside the reasonable range. "
            "If source price uses an incompatible pricing unit, reject it."
        )
        try:
            content = self.request_process_json(prompt, payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        if not content.get("found"):
            return None
        unit_price = parse_float(content.get("unit_price"))
        if unit_price is None:
            return None
        confidence = clamp(parse_float(content.get("confidence")), 0.0, 1.0, default=0.0)
        if not validate_process_price(
            operation_code=operation_code,
            unit_price=unit_price,
            unit=str(content.get("unit") or ""),
            expected_unit=expected_unit,
            url=str(content.get("url") or ""),
            confidence=confidence,
        ):
            return None
        url = str(content.get("url") or "")
        title = str(content.get("title") or "")
        snippet = str(content.get("snippet") or "")
        domain = urlparse(url).netloc
        searched_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return ProcessMarketPrice(
            operation_code=operation_code,
            operation_name=operation_name,
            unit_price=round(unit_price, 6),
            unit=expected_unit,
            region=str(content.get("region") or region),
            query=" | ".join(queries[:3]),
            title=title,
            url=url,
            snippet=snippet,
            source_domain=domain,
            searched_at=searched_at,
            confidence=round(confidence, 4),
        )

    def request_process_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.api_mode == "chat_completions":
            response = self.post_json(
                f"{self.base_url}/chat/completions",
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            text = extract_chat_completion_text(response)
        else:
            response = self.post_json(
                f"{self.base_url}/responses",
                {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "process_price_extraction",
                            "schema": PROCESS_PRICE_EXTRACTION_SCHEMA,
                            "strict": True,
                        }
                    },
                },
            )
            text = extract_response_text(response)
        content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError("process price extraction response must be an object")
        return content


class GptSurfaceTreatmentPriceExtractor(GptMaterialPriceExtractor):
    def extract_price(
        self,
        *,
        treatment_code: str,
        treatment_name: str,
        expected_unit: str,
        quantity_unit: Any,
        material_text: Any,
        region: str,
        queries: list[str],
        search_results: list[dict[str, Any]],
    ) -> SurfaceTreatmentMarketPrice | None:
        payload = {
            "treatment_code": treatment_code,
            "treatment_name": treatment_name,
            "expected_unit": expected_unit,
            "quantity_unit": quantity_unit,
            "material_text": material_text,
            "region": region,
            "region_keywords": REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"]),
            "treatment_search_terms": SURFACE_TREATMENT_SEARCH_TERMS.get(treatment_code, [treatment_name]),
            "reasonable_price_range": SURFACE_TREATMENT_PRICE_RANGES.get(treatment_code),
            "queries": queries,
            "search_results": search_results,
            "today": datetime.now(timezone.utc).astimezone().date().isoformat(),
        }
        prompt = (
            "You extract one current South China surface treatment unit price "
            "from search results. Use only supplied search_results. Do not invent prices. "
            "Return JSON only with keys: found, treatment_code, unit_price, unit, minimum_charge, "
            "price_date, region, region_match, title, url, snippet, confidence, reject_reason. "
            f"The accepted unit must be {expected_unit}. "
            "Also include region_match with one of exact, fallback, unknown. "
            "Prefer South China/Guangdong-area matches and set region_match=exact. "
            "If no South China/Guangdong-area result has an explicit compatible price, you may use a China-wide "
            "or unstated-region surface treatment service price and set region_match=fallback or unknown. "
            "Reject if there is no source URL, no surface treatment match, no explicit service price, "
            "or the price is outside the reasonable range. "
            "If source price uses an incompatible pricing unit such as CNY/m2, CNY/dm2, CNY/pcs, or CNY/batch, reject it."
        )
        try:
            content = self.request_surface_treatment_json(prompt, payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        if not content.get("found"):
            return None
        unit_price = parse_float(content.get("unit_price"))
        if unit_price is None:
            return None
        confidence = clamp(parse_float(content.get("confidence")), 0.0, 1.0, default=0.0)
        if not validate_surface_treatment_price(
            treatment_code=treatment_code,
            unit_price=unit_price,
            unit=str(content.get("unit") or ""),
            expected_unit=expected_unit,
            url=str(content.get("url") or ""),
            confidence=confidence,
        ):
            return None
        url = str(content.get("url") or "")
        title = str(content.get("title") or "")
        snippet = str(content.get("snippet") or "")
        domain = urlparse(url).netloc
        searched_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        minimum_charge = parse_float(content.get("minimum_charge"))
        region_match = normalize_region_match(content.get("region_match"))
        if region_match != "exact":
            confidence = min(confidence, 0.68)
        return SurfaceTreatmentMarketPrice(
            treatment_code=treatment_code,
            treatment_name=treatment_name,
            unit_price=round(unit_price, 6),
            unit=expected_unit,
            minimum_charge=minimum_charge,
            region=str(content.get("region") or region),
            region_match=region_match,
            query=" | ".join(queries[:3]),
            title=title,
            url=url,
            snippet=snippet,
            source_domain=domain,
            searched_at=searched_at,
            confidence=round(confidence, 4),
        )

    def request_surface_treatment_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.api_mode == "chat_completions":
            response = self.post_json(
                f"{self.base_url}/chat/completions",
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            text = extract_chat_completion_text(response)
        else:
            response = self.post_json(
                f"{self.base_url}/responses",
                {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "surface_treatment_price_extraction",
                            "schema": SURFACE_TREATMENT_PRICE_EXTRACTION_SCHEMA,
                            "strict": True,
                        }
                    },
                },
            )
            text = extract_response_text(response)
        content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError("surface treatment price extraction response must be an object")
        return content


class GptSurfaceTreatmentPriceEstimator(GptMaterialPriceExtractor):
    def estimate_price(
        self,
        *,
        treatment_code: str,
        treatment_name: str,
        expected_unit: str,
        quantity_unit: Any,
        material_text: Any,
        region: str,
    ) -> SurfaceTreatmentMarketPrice | None:
        if normalize_unit(expected_unit) != normalize_unit(unit_to_price_unit(quantity_unit)):
            return None
        low, high = SURFACE_TREATMENT_PRICE_RANGES.get(treatment_code, (1.0, 200.0))
        payload = {
            "treatment_code": treatment_code,
            "treatment_name": treatment_name,
            "expected_unit": expected_unit,
            "quantity_unit": quantity_unit,
            "material_text": material_text,
            "region": region,
            "region_keywords": REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"]),
            "reasonable_price_range": [low, high],
            "default_midpoint": round((low + high) / 2, 4),
            "constraints": [
                "This is an estimate, not a real-time market quotation.",
                "Do not claim web/source verification.",
                "Use the expected unit only.",
                "Set confidence <= 0.6 when plating thickness, masked area, supplier, and tax basis are unknown.",
                "Return found=false if the expected unit is incompatible with the quantity unit.",
            ],
            "today": datetime.now(timezone.utc).astimezone().date().isoformat(),
        }
        prompt = (
            "You estimate one conservative South China surface treatment unit price for first-pass quoting. "
            "This is GPT-only estimation, not real-time market data. Do not claim it is today's market price. "
            "Use only the provided reasonable_price_range and constraints. "
            "Return JSON only with keys: found, treatment_code, unit_price, unit, minimum_charge, "
            "region, pricing_basis, confidence, reason. "
            f"The accepted unit must be {expected_unit}. "
            "For low-information small-batch chemical nickel area pricing, choose a conservative value in the range, "
            "normally near the midpoint unless the constraints justify otherwise."
        )
        try:
            content = self.request_estimate_json(prompt, payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        if not content.get("found"):
            return None
        unit_price = parse_float(content.get("unit_price"))
        if unit_price is None:
            return None
        confidence = clamp(parse_float(content.get("confidence")), 0.0, 0.6, default=0.45)
        if not validate_surface_treatment_price(
            treatment_code=treatment_code,
            unit_price=unit_price,
            unit=str(content.get("unit") or ""),
            expected_unit=expected_unit,
            url="ai://surface-treatment-estimate",
            confidence=max(confidence, 0.5),
            allow_ai_url=True,
        ):
            return None
        reason = str(content.get("reason") or "表面处理价格库和市场搜索未提供可用单价，使用 AI 估算价。")
        minimum_charge = parse_float(content.get("minimum_charge"))
        return SurfaceTreatmentMarketPrice(
            treatment_code=treatment_code,
            treatment_name=treatment_name,
            unit_price=round(unit_price, 6),
            unit=expected_unit,
            minimum_charge=minimum_charge,
            region=str(content.get("region") or region),
            region_match="estimate",
            query=reason,
            title="AI 表面处理估算价",
            url="ai://surface-treatment-estimate",
            snippet=reason,
            source_domain="ai_estimate",
            searched_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            confidence=round(confidence, 4),
            provider="gpt_estimate",
            rule_id="GPT_SURFACE_TREATMENT_PRICE_ESTIMATE",
            source_type="ai_estimate",
        )

    def request_estimate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.api_mode == "chat_completions":
            response = self.post_json(
                f"{self.base_url}/chat/completions",
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            text = extract_chat_completion_text(response)
        else:
            response = self.post_json(
                f"{self.base_url}/responses",
                {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "surface_treatment_price_estimate",
                            "schema": SURFACE_TREATMENT_ESTIMATE_SCHEMA,
                            "strict": True,
                        }
                    },
                },
            )
            text = extract_response_text(response)
        content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError("surface treatment estimate response must be an object")
        return content


def build_material_price_provider_from_env() -> MaterialPriceProvider | None:
    provider = os.environ.get("MATERIAL_PRICE_PROVIDER", "").strip().lower()
    if provider in {"tavily", "tavily_gpt", "gpt_tavily"}:
        return build_tavily_material_price_provider_from_env()

    base_url = os.environ.get("SEARXNG_BASE_URL") or os.environ.get("PRICE_OVERVIEW_SEARXNG_BASE_URL")
    if not base_url:
        return None
    timeout = parse_float(os.environ.get("SEARXNG_TIMEOUT_SECONDS")) or 8.0
    return SearxngMaterialPriceProvider(base_url=base_url, timeout_seconds=timeout)


def build_tavily_material_price_provider_from_env() -> TavilyMaterialPriceProvider | None:
    config = tavily_gpt_config_from_env()
    if config is None:
        return None
    extractor = GptMaterialPriceExtractor(
        api_key=config["ai_key"],
        model=config["model"],
        base_url=config["base_url"],
        api_mode=config["api_mode"],
        timeout_seconds=config["ai_timeout_seconds"],
        stream=config["stream"],
    )
    return TavilyMaterialPriceProvider(
        api_key=config["tavily_key"],
        extractor=extractor,
        search_url=config["search_url"],
        timeout_seconds=config["tavily_timeout_seconds"],
        max_results=config["max_results"],
        search_depth=config["search_depth"],
        access_mode=config["access_mode"],
    )


def build_material_estimate_provider_from_env() -> MaterialEstimateProvider | None:
    enabled = bool_env("MATERIAL_GPT_ESTIMATE_ENABLED", True)
    if not enabled:
        return None
    config = tavily_gpt_config_from_env()
    if config is None:
        return None
    estimator = GptMaterialPriceEstimator(
        api_key=config["ai_key"],
        model=os.environ.get("PRICE_MATERIAL_ESTIMATE_MODEL")
        or os.environ.get("PRICE_MATERIAL_PRICE_AI_MODEL")
        or config["model"],
        base_url=config["base_url"],
        api_mode=config["api_mode"],
        timeout_seconds=config["ai_timeout_seconds"],
        stream=bool_env(
            "PRICE_MATERIAL_ESTIMATE_STREAM",
            bool_env("PRICE_MATERIAL_PRICE_AI_STREAM", bool_env("PRICE_AI_STREAM", False)),
        ),
    )
    return GptMaterialEstimateProvider(estimator=estimator)


def build_process_price_provider_from_env() -> ProcessPriceProvider | None:
    provider = os.environ.get("PROCESS_PRICE_PROVIDER") or os.environ.get("MATERIAL_PRICE_PROVIDER")
    if (provider or "").strip().lower() not in {"tavily", "tavily_gpt", "gpt_tavily"}:
        return None
    return build_tavily_process_price_provider_from_env()


def build_tavily_process_price_provider_from_env() -> TavilyProcessPriceProvider | None:
    config = tavily_gpt_config_from_env()
    if config is None:
        return None
    extractor = GptProcessPriceExtractor(
        api_key=config["ai_key"],
        model=os.environ.get("PRICE_PROCESS_PRICE_AI_MODEL") or config["model"],
        base_url=config["base_url"],
        api_mode=config["api_mode"],
        timeout_seconds=config["ai_timeout_seconds"],
        stream=bool_env(
            "PRICE_PROCESS_PRICE_AI_STREAM",
            bool_env("PRICE_AI_STREAM", False),
        ),
    )
    return TavilyProcessPriceProvider(
        api_key=config["tavily_key"],
        extractor=extractor,
        search_url=config["search_url"],
        timeout_seconds=config["tavily_timeout_seconds"],
        max_results=config["max_results"],
        search_depth=config["search_depth"],
        access_mode=config["access_mode"],
    )


def build_surface_treatment_price_provider_from_env() -> SurfaceTreatmentPriceProvider | None:
    provider = (
        os.environ.get("SURFACE_TREATMENT_PRICE_PROVIDER")
        or os.environ.get("MATERIAL_PRICE_PROVIDER")
    )
    if (provider or "").strip().lower() not in {"tavily", "tavily_gpt", "gpt_tavily"}:
        return None
    return build_tavily_surface_treatment_price_provider_from_env()


def build_tavily_surface_treatment_price_provider_from_env() -> TavilySurfaceTreatmentPriceProvider | None:
    config = tavily_gpt_config_from_env()
    if config is None:
        return None
    extractor = GptSurfaceTreatmentPriceExtractor(
        api_key=config["ai_key"],
        model=os.environ.get("PRICE_SURFACE_TREATMENT_AI_MODEL") or config["model"],
        base_url=config["base_url"],
        api_mode=config["api_mode"],
        timeout_seconds=config["ai_timeout_seconds"],
        stream=bool_env(
            "PRICE_SURFACE_TREATMENT_AI_STREAM",
            bool_env("PRICE_AI_STREAM", False),
        ),
    )
    return TavilySurfaceTreatmentPriceProvider(
        api_key=config["tavily_key"],
        extractor=extractor,
        search_url=config["search_url"],
        timeout_seconds=config["tavily_timeout_seconds"],
        max_results=config["max_results"],
        search_depth=config["search_depth"],
        access_mode=config["access_mode"],
    )


def build_surface_treatment_estimate_provider_from_env() -> SurfaceTreatmentPriceProvider | None:
    enabled = bool_env("SURFACE_TREATMENT_GPT_ESTIMATE_ENABLED", True)
    if not enabled:
        return None
    config = tavily_gpt_config_from_env()
    if config is None:
        return None
    estimator = GptSurfaceTreatmentPriceEstimator(
        api_key=config["ai_key"],
        model=os.environ.get("PRICE_SURFACE_TREATMENT_ESTIMATE_MODEL")
        or os.environ.get("PRICE_SURFACE_TREATMENT_AI_MODEL")
        or config["model"],
        base_url=config["base_url"],
        api_mode=config["api_mode"],
        timeout_seconds=config["ai_timeout_seconds"],
        stream=bool_env(
            "PRICE_SURFACE_TREATMENT_ESTIMATE_STREAM",
            bool_env("PRICE_SURFACE_TREATMENT_AI_STREAM", bool_env("PRICE_AI_STREAM", False)),
        ),
    )
    return GptSurfaceTreatmentEstimateProvider(estimator=estimator)


def tavily_gpt_config_from_env() -> dict[str, Any] | None:
    tavily_key = os.environ.get("TAVILY_API_KEY") or os.environ.get("PRICE_TAVILY_API_KEY")
    access_mode = (os.environ.get("TAVILY_ACCESS_MODE") or "").strip().lower()
    keyless_enabled = access_mode == "keyless" or bool_env("TAVILY_KEYLESS", False)
    ai_key = os.environ.get("PRICE_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if (not tavily_key and not keyless_enabled) or not ai_key:
        return None
    base_url = (
        os.environ.get("PRICE_AI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    api_mode = (
        os.environ.get("PRICE_AI_API_MODE")
        or os.environ.get("OPENAI_API_MODE")
        or infer_ai_api_mode(base_url)
    ).strip().lower()
    if api_mode not in {"responses", "chat_completions"}:
        api_mode = "chat_completions"
    return {
        "tavily_key": tavily_key,
        "access_mode": "keyless" if keyless_enabled and not tavily_key else "api_key",
        "ai_key": ai_key,
        "base_url": base_url,
        "api_mode": api_mode,
        "model": (
            os.environ.get("PRICE_MATERIAL_PRICE_AI_MODEL")
            or os.environ.get("PRICE_AI_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-5.5"
        ),
        "ai_timeout_seconds": parse_float(os.environ.get("PRICE_AI_TIMEOUT_SECONDS")) or 60.0,
        "stream": bool_env(
            "PRICE_MATERIAL_PRICE_AI_STREAM",
            bool_env("PRICE_AI_STREAM", False),
        ),
        "search_url": os.environ.get("TAVILY_SEARCH_URL") or "https://api.tavily.com/search",
        "tavily_timeout_seconds": parse_float(os.environ.get("TAVILY_TIMEOUT_SECONDS")) or 20.0,
        "max_results": int(parse_float(os.environ.get("TAVILY_MAX_RESULTS")) or 5),
        "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH") or "basic",
    }


def build_queries(
    material_code: str,
    material_spec: Any,
    region: str,
) -> list[str]:
    region_terms = " ".join(REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"])[:4])
    aliases = MATERIAL_ALIASES.get(material_code, [material_code])
    spec_text = str(material_spec or "").strip()
    primary = aliases[0]
    material_terms = " ".join(aliases[:3])
    queries = [
        f"{material_terms} {region_terms} 钢材 有色 行情 价格 元/kg",
        f"{material_terms} {region_terms} 今日价格 元/吨",
    ]
    if len(aliases) > 1:
        queries.append(f"{aliases[1]} {aliases[-1]} {region_terms} 材料价格 行情")
    if spec_text:
        queries.insert(0, f"{primary} {spec_text} {region_terms} 材料价格 元/kg")
    return queries


def build_process_queries(
    *,
    operation_code: str,
    operation_name: str,
    expected_unit: str,
    material_text: Any,
    region: str,
) -> list[str]:
    region_terms = " ".join(REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"])[:4])
    terms = PROCESS_SEARCH_TERMS.get(operation_code, [operation_name])
    unit_hint = PROCESS_UNIT_HINTS.get(expected_unit, expected_unit)
    material_part = str(material_text or "").strip()
    material_clause = f"{material_part} " if material_part else ""
    primary = terms[0]
    queries = [
        f"{region_terms} {material_clause}{primary} 加工费 {unit_hint}",
        f"{region_terms} {primary} 加工报价 {unit_hint}",
    ]
    if len(terms) > 1:
        queries.append(f"{region_terms} {' '.join(terms[:3])} 单价 报价")
    return queries


def build_surface_treatment_queries(
    *,
    treatment_code: str,
    treatment_name: str,
    expected_unit: str,
    material_text: Any,
    region: str,
) -> list[str]:
    region_terms = " ".join(REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"])[:4])
    terms = SURFACE_TREATMENT_SEARCH_TERMS.get(treatment_code, [treatment_name])
    unit_hint = SURFACE_TREATMENT_UNIT_HINTS.get(expected_unit, expected_unit)
    material_part = str(material_text or "").strip()
    material_clause = f"{material_part} " if material_part else ""
    primary = terms[0]
    queries = [
        f"{region_terms} {material_clause}{primary} 表面处理 加工费 {unit_hint}",
        f"{region_terms} {primary} 加工报价 {unit_hint}",
    ]
    if len(terms) > 1:
        queries.append(f"{region_terms} {' '.join(terms[:3])} 表面处理 单价 报价")
    return queries


def extract_unit_prices(text: str) -> list[float]:
    prices: list[float] = []
    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(text):
            if "low" in match.groupdict() and match.group("low"):
                low = parse_float(match.group("low"))
                high = parse_float(match.group("high"))
                if low is None or high is None:
                    continue
                raw_price = (low + high) / 2
            else:
                raw_price = parse_float(match.group("price"))
                if raw_price is None:
                    continue
                if "万" in match.group(0):
                    raw_price *= 10000
            unit_price = normalize_price_to_kg(raw_price, match.group("unit"))
            if unit_price is not None:
                prices.append(unit_price)
    return prices


def normalize_price_to_kg(price: float, unit: str) -> float | None:
    normalized_unit = unit.strip().lower()
    if normalized_unit in {"kg", "公斤", "千克"}:
        return price
    if normalized_unit in {"吨", "t"}:
        return price / 1000
    return None


def validate_extracted_price(
    *,
    material_code: str,
    unit_price: float,
    unit: str,
    url: str,
    confidence: float,
    allow_ai_url: bool = False,
) -> bool:
    if not url.startswith(("http://", "https://")) and not (
        allow_ai_url and url.startswith("ai://")
    ):
        return False
    if unit.strip().upper() not in {"CNY/KG", "元/KG", "元/公斤"}:
        return False
    if confidence < 0.5:
        return False
    low, high = MATERIAL_PRICE_RANGES.get(material_code, (0.1, 1000.0))
    return low <= unit_price <= high


def validate_process_price(
    *,
    operation_code: str,
    unit_price: float,
    unit: str,
    expected_unit: str,
    url: str,
    confidence: float,
) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    if normalize_unit(unit) != normalize_unit(expected_unit):
        return False
    if confidence < 0.5:
        return False
    low, high = PROCESS_PRICE_RANGES.get(operation_code, (0.000001, 100000.0))
    return low <= unit_price <= high


def validate_surface_treatment_price(
    *,
    treatment_code: str,
    unit_price: float,
    unit: str,
    expected_unit: str,
    url: str,
    confidence: float,
    allow_ai_url: bool = False,
) -> bool:
    if not url.startswith(("http://", "https://")) and not (
        allow_ai_url and url.startswith("ai://")
    ):
        return False
    if normalize_unit(unit) != normalize_unit(expected_unit):
        return False
    if confidence < 0.5:
        return False
    low, high = SURFACE_TREATMENT_PRICE_RANGES.get(treatment_code, (0.000001, 100000.0))
    return low <= unit_price <= high


def unit_to_price_unit(value: Any) -> str:
    normalized = normalize_unit(str(value or ""))
    mapping = {
        "kg": "cny/kg",
        "hour": "cny/hour",
        "pcs": "cny/pcs",
        "mm2": "cny/mm2",
        "m2": "cny/m2",
        "score": "cny/score",
    }
    return mapping.get(normalized, normalized)


def normalize_unit(value: str) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "元/小时": "cny/hour",
        "元/时": "cny/hour",
        "元/h": "cny/hour",
        "cny/h": "cny/hour",
        "rmb/hour": "cny/hour",
        "元/mm2": "cny/mm2",
        "元/mm²": "cny/mm2",
        "元/平方毫米": "cny/mm2",
        "rmb/mm2": "cny/mm2",
        "元/m2": "cny/m2",
        "元/m²": "cny/m2",
        "元/平方米": "cny/m2",
        "cny/㎡": "cny/m2",
        "元/㎡": "cny/m2",
        "rmb/m2": "cny/m2",
        "元/件": "cny/pcs",
        "元/个": "cny/pcs",
        "元/孔": "cny/pcs",
        "元/pcs": "cny/pcs",
        "rmb/pcs": "cny/pcs",
        "元/kg": "cny/kg",
        "元/公斤": "cny/kg",
        "rmb/kg": "cny/kg",
        "元/score": "cny/score",
        "元/分": "cny/score",
        "rmb/score": "cny/score",
    }
    return replacements.get(text, text.upper().replace("RMB", "CNY").lower())


def normalize_region_match(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"exact", "fallback", "unknown"}:
        return text
    if text in {"south_china", "guangdong", "matched", "match"}:
        return "exact"
    if text in {"china", "national", "全国", "fallback_region"}:
        return "fallback"
    return "unknown"


def score_candidate(
    *,
    text: str,
    material_code: str,
    region: str,
    unit_price: float,
    domain: str,
) -> float:
    low, high = MATERIAL_PRICE_RANGES.get(material_code, (0.1, 1000.0))
    if unit_price < low or unit_price > high:
        return 0.0

    normalized_text = normalize_text(text)
    aliases = MATERIAL_ALIASES.get(material_code, [material_code])
    score = 0.35
    if any(normalize_text(alias) in normalized_text for alias in aliases):
        score += 0.3
    if any(keyword in text for keyword in REGION_KEYWORDS.get(region, REGION_KEYWORDS["south_china"])):
        score += 0.15
    if any(keyword in text for keyword in ("今日", "价格", "行情", "报价", "市场")):
        score += 0.1
    if domain and any(trusted in domain for trusted in ("mysteel", "smm", "anhuida", "100ppi", "steel")):
        score += 0.1
    return min(score, 0.95)


def normalize_material_code(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    if "SKD11" in text:
        return "SKD11"
    if "SUS304" in text or "304" in text and "不锈钢" in str(value):
        return "SUS304"
    if "AL6061" in text or "6061" in text:
        return "AL6061"
    if (
        "S45C" in text
        or text == "45"
        or "45#" in str(value)
        or "45号钢" in str(value)
    ):
        return "S45C"
    return None


def normalize_text(value: Any) -> str:
    return (
        str(value or "")
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("/", "")
    )


def infer_ai_api_mode(base_url: str) -> str:
    normalized = base_url.lower()
    if "dashscope" in normalized or "compatible-mode" in normalized:
        return "chat_completions"
    return "responses"


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def extract_chat_completion_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat completion response did not contain choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("chat completion choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("chat completion response did not contain a message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("chat completion response did not contain message content")
    return content


def extract_response_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    chunks: list[str] = []
    for item in response_payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    response_text = "".join(chunks).strip()
    if not response_text:
        raise ValueError("responses API payload did not contain output text")
    return response_text


def clamp(
    value: float | None,
    minimum: float,
    maximum: float,
    *,
    default: float,
) -> float:
    if value is None:
        return default
    return min(maximum, max(minimum, value))


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
