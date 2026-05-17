# apps/impact_analysis.py - 信号影响分析 App
# navisv 架构 v0.8 - App Layer

"""
ImpactAnalysisApp: "动这个信号会影响到谁？"

场景：分析修改某个信号会影响的范围：
- 下游逻辑锥（fanout cone）
- 跨模块影响
- 组合逻辑环路检测
- 是否影响顶层输出端口

铁律约束：
- [铁律17] App 是唯一生成 summary 的层
- [铁律13] App 通过 QueryService 获取数据，不直接访问 DesignGraph
"""

from .base import BaseApp, AppResponse


class ImpactAnalysisApp(BaseApp):
    """
    信号影响分析：修改一个信号会波及哪些地方。
    
    输入：信号路径
    输出：下游影响范围 + 环路警告 + 自然语言摘要
    """

    def run(self, signal: str, max_depth: int = 10) -> AppResponse:
        """
        分析信号影响范围。
        
        Args:
            signal: 信号路径
            max_depth: 最大追踪深度，默认 10
            
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

        # 节点属性
        attr = self.query._graph.node_attr(signal)
        node_name = attr.get('name', signal)
        signal_module = attr.get('module', '')

        # 1. 下游逻辑锥
        descendants = self.query.fanout_cone(signal, max_depth)
        descendants = [d for d in descendants if d != signal]  # 排除自己

        # 2. 跨模块影响
        cross_module = [
            d for d in descendants
            if self.query._graph.node_attr(d).get('module', '') != signal_module
        ]

        # 3. 端口输出影响
        port_outputs = [
            d for d in descendants
            if 'port_output' in self.query._graph.node_attr(d).get('tags', set())
        ]

        # 4. 环路检测（通过 SCC 分析）
        sccs = self.query.scc_analysis()
        # 筛选涉及当前信号的 SCC
        loops = [scc for scc in sccs if signal in scc and len(scc) > 1]

        # 5. 按模块分组
        modules_hit = {}
        for d in descendants:
            mod = self.query._graph.node_attr(d).get('module', 'unknown')
            if mod not in modules_hit:
                modules_hit[mod] = []
            modules_hit[mod].append(d)

        # 构建 structured
        structured = {
            "signal": signal,
            "name": node_name,
            "module": signal_module,
            "total_affected": len(descendants),
            "descendants": descendants,
            "cross_module_count": len(cross_module),
            "cross_module": cross_module,
            "port_outputs": port_outputs,
            "loops": loops,
            "modules_hit": {mod: list(sig_ids) for mod, sig_ids in modules_hit.items()},
        }

        # 生成摘要
        summary_parts = []
        summary_parts.append(f"信号 {signal} 的影响范围分析")

        if descendants:
            summary_parts.append(f"影响 {len(descendants)} 个下游信号")
        else:
            summary_parts.append("无下游负载（可能未连接）")
            return AppResponse(
                structured=structured,
                summary="，".join(summary_parts) + "。",
                confidence="high",
                experimental=False
            )

        if cross_module:
            summary_parts.append(f"其中跨模块影响 {len(cross_module)} 个")

        if port_outputs:
            port_names = [self.query._graph.node_attr(p).get('name', p) for p in port_outputs[:3]]
            summary_parts.append(f"[注意] 影响顶层输出端口：{', '.join(port_names)}{'...' if len(port_outputs) > 3 else ''}")

        if loops:
            loop_summaries = []
            for loop in loops:
                # 简化环路节点为短名称
                short_names = [
                    self.query._graph.node_attr(n).get('name', n.rsplit('.', 1)[-1])
                    for n in loop[:4]
                ]
                loop_summaries.append(f"{'→'.join(short_names)}...")
            summary_parts.append(f"[警告] 检测到 {len(loops)} 个潜在组合逻辑环路：{' | '.join(loop_summaries[:2])}")

        if len(modules_hit) > 1:
            summary_parts.append(f"涉及 {len(modules_hit)} 个模块")

        summary = "，".join(summary_parts) + "。"

        # 置信度
        if loops:
            confidence = "medium"  # 环路表示可能有额外依赖
        elif any(self.query._graph.edge_attr(signal, d).get('confidence') == 'uncertain'
                 for d in descendants[:5] if self.query._graph.has_edge(signal, d)):
            confidence = "medium"
        else:
            confidence = "high"

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence=confidence,
            experimental=False
        )