# apps/signal_profile.py - 信号身份证 App
# navisv 架构 v0.8 - App Layer

"""
SignalProfileApp: "这个信号到底是怎么回事？"

场景：给一个信号，返回它的完整档案：
- 被哪些信号驱动（drivers）
- 驱动哪些信号（loads）
- 上游逻辑锥（fanin）
- 下游逻辑锥（fanout）
- 时钟域、复位等属性

铁律约束：
- [铁律17] App 是唯一生成 summary 的层
- [铁律13] App 通过 QueryService 获取数据，不直接访问 DesignGraph
"""

from typing import List
from .base import BaseApp, AppResponse


class SignalProfileApp(BaseApp):
    """
    信号身份证：全面了解一个信号的全貌。
    
    输入：信号路径
    输出：该信号的 drivers、loads、fanin、fanout 等信息 + 自然语言摘要
    """

    def run(self, signal: str, max_depth: int = 3) -> AppResponse:
        """
        获取信号完整档案。
        
        Args:
            signal: 信号路径，如 "i2c_core.scl_i"
            max_depth: fanin/fanout 追踪深度，默认 3
            
        Returns:
            AppResponse: structured + summary + confidence
        """
        # 检查信号是否存在
        if not self._check_signal_exists(signal):
            return AppResponse(
                structured={"signal": signal, "error": "signal_not_found"},
                summary=f"信号 {signal} 不存在",
                confidence="uncertain",
                experimental=False
            )

        # 获取驱动源
        drivers = self.query.get_drivers(signal)
        # 获取负载
        loads = self.query.get_loads(signal)
        # 获取 fanin/fanout
        fanin = self.query.fanin_cone(signal, max_depth)
        fanout = self.query.fanout_cone(signal, max_depth)

        # 节点属性
        attr = self.query._graph.node_attr(signal)
        node_name = attr.get('name', signal)
        module = attr.get('module', '')
        bit_width = attr.get('bit_width', (0, 0))
        tags = attr.get('tags', set())

        # 构建 structured 结果
        structured = {
            "signal": signal,
            "name": node_name,
            "module": module,
            "bit_width": bit_width,
            "tags": list(tags),
            "drivers": [
                {
                    "id": d.id,
                    "timing": d.timing,
                    "relation": d.relation,
                    "source": d.source,
                    "confidence": d.confidence
                }
                for d in drivers
            ],
            "loads": [
                {
                    "id": l.id,
                    "timing": l.timing,
                    "relation": l.relation,
                    "source": l.source,
                    "confidence": l.confidence
                }
                for l in loads
            ],
            "fanin": fanin,
            "fanout": fanout,
            "fanin_count": len(fanin),
            "fanout_count": len(fanout)
        }

        # 生成自然语言摘要（铁律17：App 是唯一生成 summary 的层）
        summary_parts = []
        summary_parts.append(f"信号 {signal}")

        if module:
            summary_parts.append(f"位于模块 {module}")

        # 驱动信息
        if drivers:
            driver_ids = [d.id for d in drivers]
            if len(driver_ids) == 1:
                summary_parts.append(f"被 {driver_ids[0]} 驱动")
            else:
                summary_parts.append(f"被 {len(driver_ids)} 个源驱动：{', '.join(driver_ids[:3])}{'...' if len(driver_ids) > 3 else ''}")
        else:
            summary_parts.append("无驱动源（可能未连接）")

        # 负载信息
        if loads:
            load_ids = [l.id for l in loads]
            if len(load_ids) == 1:
                summary_parts.append(f"驱动 {load_ids[0]}")
            else:
                summary_parts.append(f"驱动 {len(load_ids)} 个负载：{', '.join(load_ids[:3])}{'...' if len(load_ids) > 3 else ''}")

        # 逻辑锥信息
        if fanin:
            summary_parts.append(f"上游涉及 {len(fanin)} 个信号")
        if fanout:
            summary_parts.append(f"下游涉及 {len(fanout)} 个信号")

        # 位宽
        if bit_width and bit_width != (0, 0):
            msb, lsb = bit_width
            bw = abs(msb - lsb) + 1 if msb != lsb else 1
            summary_parts.append(f"位宽 {bw} bit")

        summary = "，".join(summary_parts) + "。"

        # 计算置信度
        if not drivers and not loads:
            confidence = "uncertain"
        elif any(d.confidence == "uncertain" for d in drivers) or any(l.confidence == "uncertain" for l in loads):
            confidence = "medium"
        else:
            confidence = "high"

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence=confidence,
            experimental=False
        )