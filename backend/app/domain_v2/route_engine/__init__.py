"""分层工艺路线引擎 (route_engine).

按《工艺路线系统改造方案》实现 L0-L6 分层路由 + 策略矩阵 + 复核旁路，替代旧的
``build_process_route`` 追加式单链。本包消费现有 ``part_feature`` dict，产出与
``finalize_route`` 同构的路线 dict（``schema_version/operations/stage_route/risks/requires_review``），
通过 ``pricing_core`` 的特性开关并行接入，旧追加链保留为可回退路径。
"""

from __future__ import annotations

from .config import route_engine_v2_enabled
from .engine import plan_route_v2

__all__ = ["plan_route_v2", "route_engine_v2_enabled"]
