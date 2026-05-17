# apps/fsm_detect.py - FSM 检测 App（实验性）
# navisv 架构 v0.8 - App Layer - Phase 5 实验性功能

"""
FsmDetectApp: "这段设计里有状态机吗？"

场景：基于 SCC（强连通分量）检测可能的状态寄存器闭环。

⚠️ 这是实验性功能，结果仅供参考，不代表完整的 FSM 识别。

铁律约束：
- [铁律17] App 是唯一生成 summary 的层
- [铁律13] App 通过 QueryService 获取数据，不直接访问 DesignGraph
"""

from .base import BaseApp, AppResponse


class FsmDetectApp(BaseApp):
    """
    FSM 检测（实验性）：检测设计中的状态寄存器闭环。

    方法：基于 SCC 分析，筛选涉及 register 类型标签节点的闭环。
    局限性：仅基于拓扑结构，无法识别状态语义。
    """

    def run(self, signal: str = None, module: str = "", max_scc_size: int = 20) -> AppResponse:
        """
        检测可能的 FSM 闭环。

        Args:
            signal: 可选，限定从某信号开始分析
            module: 可选，限定在某个模块内分析
            max_scc_size: SCC 最大节点数（防止全连通大环路）

        Returns:
            AppResponse: structured + summary + confidence
        """
        sccs = self.query.scc_analysis()

        # 过滤：只保留涉及 register 标签的 SCC
        fsm_candidates = []
        for scc in sccs:
            if len(scc) < 2 or len(scc) > max_scc_size:
                continue
            # 至少有一个节点带有 register 标签
            has_register = any(
                'register' in self.query._graph.node_attr(n).get('tags', set())
                for n in scc
            )
            if has_register:
                fsm_candidates.append(scc)

        # 如果指定了 signal，过滤
        if signal:
            fsm_candidates = [scc for scc in fsm_candidates if signal in scc]

        # 如果指定了 module，过滤
        if module:
            fsm_candidates = [
                scc for scc in fsm_candidates
                if any(self.query._graph.node_attr(n).get('module', '') == module for n in scc)
            ]

        # 构建 structured
        structured = {
            "total_sccs": len(sccs),
            "fsm_candidates": [
                {
                    "nodes": scc,
                    "size": len(scc),
                    "names": [
                        self.query._graph.node_attr(n).get('name', n.rsplit('.', 1)[-1])
                        for n in scc
                    ],
                }
                for scc in fsm_candidates
            ],
            "module": module or "all",
        }

        # 生成摘要
        summary_parts = []
        summary_parts.append("[实验性功能] FSM 检测")

        if fsm_candidates:
            summary_parts.append(f"检测到 {len(fsm_candidates)} 个可能的 FSM 闭环（基于 SCC + register 标签）")
            for i, cand in enumerate(fsm_candidates[:3]):
                names = [n.rsplit('.', 1)[-1] for n in cand[:4]]
                summary_parts.append(f"\n  候选 {i+1}：{' → '.join(names)}...（{len(cand)} 个节点）")
        else:
            summary_parts.append("未检测到明显的 FSM 闭环")

        summary_parts.append("\n[注意] 本检测仅基于拓扑结构，不代表真实的 FSM 识别，建议人工确认。")

        summary = "".join(summary_parts)

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence="medium",
            experimental=True
        )