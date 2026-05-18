# apps/sample_signal.py - 采样条件查询
# navisv v0.9

"""
SampleSignalApp: 查询信号的采样条件

采样条件 = 信号在什么条件下被采样/更新
通常指 always_ff/always_latch/always 块中寄存器赋值的条件

用法：
    navisv sample <signal>    # 查询单个信号
    navisv sample -m <module>  # 列出模块所有 State 的采样条件
"""

from typing import Optional, Dict, List
from .base import AppResponse


class SampleSignalApp:
    """采样条件查询应用"""

    def __init__(self, query_service):
        self.qs = query_service
        self.comp = None
        self.mgr = None

    def run(self, signal: Optional[str] = None, module: str = '') -> AppResponse:
        """
        查询信号的采样条件

        Args:
            signal: 信号路径（可选）
            module: 模块名（可选）

        Returns:
            AppResponse 包含采样条件信息
        """
        graph = self.qs._graph
        self.comp = graph._comp

        if signal:
            return self._query_signal(signal)
        elif module:
            return self._query_module(module)
        else:
            return AppResponse(
                structured=[],
                summary="请提供 signal 或 module 参数",
                confidence="high",
                experimental=False
            )

    def _query_signal(self, signal: str) -> AppResponse:
        """查询单个信号的采样条件"""
        graph = self.qs._graph

        if not graph.has_node(signal):
            return AppResponse(
                structured={'error': f'信号不存在: {signal}'},
                summary=f"信号不存在: {signal}",
                confidence="high",
                experimental=False
            )

        kind = graph.get_node_kind(signal)
        if kind != 'State':
            return AppResponse(
                structured={'kind': kind, 'sampling': None},
                summary=f"{signal} 是 {kind} 类型，不是 State（无采样条件）",
                confidence="high",
                experimental=False
            )

        sampling = self._get_sampling_condition(signal)

        structured = {
            'signal': signal,
            'kind': kind,
            'sampling': sampling
        }

        summary = f"{signal}: {sampling['timing']}"
        if sampling.get('condition'):
            summary += f" if ({sampling['condition']})"

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence="high",
            experimental=False
        )

    def _query_module(self, module: str) -> AppResponse:
        """列出模块所有 State 的采样条件"""
        graph = self.qs._graph

        results = []
        for node in graph.nodes():
            kind = graph.get_node_kind(node)
            if kind == 'State' and module in node:
                sampling = self._get_sampling_condition(node)
                results.append({
                    'signal': node,
                    'timing': sampling['timing'],
                    'condition': sampling.get('condition')
                })

        if not results:
            return AppResponse(
                structured={'module': module, 'signals': []},
                summary=f"模块 {module} 中没有 State 节点",
                confidence="high",
                experimental=False
            )

        summary = f"模块 {module} 的 State 采样条件 ({len(results)} 个)\n"
        for r in results:
            cond = f" if ({r['condition']})" if r['condition'] else ""
            summary += f"  {r['signal']}: {r['timing']}{cond}\n"

        return AppResponse(
            structured={'module': module, 'signals': results},
            summary=summary.strip(),
            confidence="high",
            experimental=False
        )

    def _get_sampling_condition(self, signal: str) -> Dict:
        """
        获取信号的采样条件

        从 ProceduralBlock 的 timing control 提取：
        - timing: @(posedge clk) 等
        - condition: if (i_en) 等
        """
        if not self.comp:
            return {'timing': 'unknown', 'condition': None}

        root = self.comp.getRoot()
        module_name = signal.rsplit('.', 1)[0] if '.' in signal else signal
        signal_name = signal.rsplit('.', 1)[-1] if '.' in signal else signal

        # 遍历模块查找对应的 ProceduralBlock
        for inst in root:
            inst_name = getattr(inst, 'name', '')
            inst_path = inst_name

            if hasattr(inst, 'body'):
                body = inst.body

                for item in body:
                    item_kind = getattr(item, 'kind', None)
                    if not item_kind or not hasattr(item_kind, 'name'):
                        continue

                    if item_kind.name == 'ProceduralBlock':
                        block_body = getattr(item, 'body', None)
                        if not block_body:
                            continue

                        timing = getattr(block_body, 'timing', None)
                        timing_str = self._extract_timing(timing)

                        stmt = getattr(block_body, 'stmt', None)
                        if not stmt:
                            continue

                        list_body = getattr(stmt, 'body', None)
                        if not list_body or not hasattr(list_body, 'list'):
                            continue

                        for s in list_body.list:
                            targets = self._extract_targets(s)
                            if any(signal_name in t for t in targets):
                                cond = self._extract_condition(s)
                                return {
                                    'timing': timing_str,
                                    'condition': cond
                                }

        return {'timing': 'unknown', 'condition': None}

    def _extract_timing(self, timing) -> str:
        """提取 timing control 字符串"""
        if not timing:
            return 'unknown'

        # 直接使用 syntax（包含 @(posedge clk) 等）
        syn = getattr(timing, 'syntax', None)
        if syn:
            return str(syn).strip()

        return str(timing)

    def _extract_targets(self, stmt) -> List[str]:
        """从 statement 提取赋值目标信号"""
        results = []
        sk = getattr(stmt, 'kind', None)
        if not sk or not hasattr(sk, 'name'):
            return results

        kn = sk.name

        if 'ExpressionStatement' in kn:
            e = getattr(stmt, 'expr', None)
            if e and hasattr(e, 'kind') and hasattr(e.kind, 'name'):
                if 'Assignment' in e.kind.name:
                    lhs = getattr(e, 'left', None)
                    if lhs:
                        sym = getattr(lhs, 'symbol', None)
                        if sym:
                            hp = getattr(sym, 'hierarchicalPath', None)
                            if hp:
                                results.append(hp)
                            else:
                                results.append(getattr(sym, 'name', ''))

        elif 'Conditional' in kn:
            ifTrue = getattr(stmt, 'ifTrue', None)
            if ifTrue:
                results.extend(self._extract_targets(ifTrue))

        return results

    def _extract_condition(self, stmt) -> Optional[str]:
        """从 statement 提取额外条件（if 等）"""
        sk = getattr(stmt, 'kind', None)
        if not sk or not hasattr(sk, 'name'):
            return None

        kn = sk.name

        if 'Conditional' in kn:
            check = getattr(stmt, 'check', None)
            if check:
                syn = getattr(check, 'syntax', None)
                if syn:
                    return syn.strip()

            # 从 syntax 提取 if 条件
            syn = getattr(stmt, 'syntax', None)
            if syn and 'if' in str(syn):
                # 简单提取 if (...) 中的内容
                syn_str = str(syn)
                start = syn_str.find('if')
                if start >= 0:
                    paren_start = syn_str.find('(', start)
                    paren_end = syn_str.find(')', paren_start)
                    if paren_start >= 0 and paren_end >= 0:
                        return syn_str[paren_start+1:paren_end].strip()

        return None