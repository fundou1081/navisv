# apps/protocol_infer.py - 协议推断 App（实验性）
# navisv 架构 v0.8 - App Layer - Phase 5 实验性功能

"""
ProtocolInferApp: "这些信号之间有什么协议？"

场景：基于命名模式和拓扑关系，推断握手/流控协议。

⚠️ 这是实验性功能，结果仅供参考，不代表协议语义完整识别。

铁律约束：
- [铁律17] App 是唯一生成 summary 的 层
- [铁律13] App 通过 QueryService 获取数据，不直接访问 DesignGraph
"""

import re
from .base import BaseApp, AppResponse


# 协议模式：(名称模式对, 协议名)
PROTOCOL_PATTERNS = [
    (r'valid', r'ready', 'valid/ready 握手'),
    (r'vld', r'rdy', 'valid/ready 握手'),
    (r'req', r'ack', 'req/ack 握手'),
    (r'req', r'grant', 'req/grant 握手'),
    (r'set', r'ack', 'set/ack 握手'),
    (r'sop', r'eop', '包起止标识'),
    (r'start', r'stop', 'I2C 起止'),
    (r'dvld', r'drdy', '数据 valid/ready'),
]


class ProtocolInferApp(BaseApp):
    """
    协议推断（实验性）：基于命名模式推断信号间协议。
    """

    def run(self, signals: list = None, pattern: str = "") -> AppResponse:
        """
        推断信号间的协议关系。

        Args:
            signals: 信号列表（可选）
            pattern: 协议名称模式（如 "valid/ready"）

        Returns:
            AppResponse: structured + summary + confidence
        """
        all_signals = self.query._graph.nodes()

        # 如果没有提供信号，从全图获取所有端口信号
        if not signals:
            signals = [
                s for s in all_signals
                if self.query._graph.node_attr(s).get('tags', set()) & {'port_input', 'port_output'}
            ]

        # 过滤
        if pattern:
            filtered = []
            for p_valid, p_rdy, name in PROTOCOL_PATTERNS:
                if re.search(pattern, name):
                    for sig in signals:
                        sig_name = self.query._graph.node_attr(sig).get('name', '').lower()
                        if re.search(p_valid, sig_name) or re.search(p_rdy, sig_name):
                            filtered.append(sig)
                    break
            if filtered:
                signals = filtered

        # 两两检测协议
        inferred = []
        checked = set()

        for i, sig_a in enumerate(signals):
            for sig_b in signals[i+1:]:
                pair_key = tuple(sorted([sig_a, sig_b]))
                if pair_key in checked:
                    continue
                checked.add(pair_key)

                name_a = self.query._graph.node_attr(sig_a).get('name', '').lower()
                name_b = self.query._graph.node_attr(sig_b).get('name', '').lower()

                for p_valid, p_rdy, proto_name in PROTOCOL_PATTERNS:
                    match_a = re.search(p_valid, name_a)
                    match_b = re.search(p_rdy, name_b)
                    match_b_valid = re.search(p_valid, name_b)
                    match_a_rdy = re.search(p_rdy, name_a)

                    if (match_a and match_b) or (match_b_valid and match_a_rdy):
                        # 检测拓扑关系
                        has_path_ab = bool(self.query.find_path(sig_a, sig_b))
                        has_path_ba = bool(self.query.find_path(sig_b, sig_a))

                        drivers_a = [d.id for d in self.query.get_drivers(sig_a)]
                        drivers_b = [d.id for d in self.query.get_drivers(sig_b)]

                        inferred.append({
                            'signal_a': sig_a,
                            'name_a': name_a,
                            'signal_b': sig_b,
                            'name_b': name_b,
                            'protocol': proto_name,
                            'direction': 'A→B' if has_path_ab else ('B→A' if has_path_ba else 'unknown'),
                            'common_driver': list(set(drivers_a) & set(drivers_b)),
                        })

        # 构建 structured
        structured = {
            'input_signals': signals,
            'input_pattern': pattern,
            'inferred_protocols': inferred,
            'total_inferred': len(inferred),
        }

        # 生成摘要
        summary_parts = []
        summary_parts.append("[实验性功能] 协议推断")

        if inferred:
            summary_parts.append(f"推断出 {len(inferred)} 个协议关系：")
            for inf in inferred[:5]:
                summary_parts.append(
                    f"\n  - {inf['name_a']} ↔ {inf['name_b']}：{inf['protocol']} "
                    f"({inf['direction']})"
                )
            if len(inferred) > 5:
                summary_parts.append(f"\n  ... 还有 {len(inferred) - 5} 个")
        else:
            summary_parts.append("未推断出明显的协议模式")

        summary_parts.append("\n[注意] 本推断仅基于命名和拓扑，结果仅供参考。")

        summary = "".join(summary_parts)

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence="medium",
            experimental=True
        )