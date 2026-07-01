"""分层路线引擎的特性开关。

默认走新引擎 (``v2``)。设置环境变量 ``PRICE_AGENT_ROUTE_ENGINE=legacy`` 可回退到旧追加链
``build_process_route``，作为安全降级路径。
"""

from __future__ import annotations

import os


ROUTE_ENGINE_ENV = "PRICE_AGENT_ROUTE_ENGINE"
ROUTE_DETAILING_ENV = "PRICE_AGENT_ROUTE_DETAILING"


def route_engine_v2_enabled() -> bool:
    return os.environ.get(ROUTE_ENGINE_ENV, "v2").strip().lower() != "legacy"


def route_detailing_enabled() -> bool:
    return os.environ.get(ROUTE_DETAILING_ENV, "on").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
