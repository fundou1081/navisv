"""
elk_exporter.py - navisv 图 → elkjs (Eclipse Layout Kernel) JSON

navisv 内部用 networkx.MultiDiGraph 表示设计数据流/控制流/模块层级。
elkjs (https://github.com/kieler/elkjs) 是 Eclipse Layout Kernel 的 JavaScript 实现,
支持层次图、力导向、正交布局等多种算法,带端口对齐和 compound 节点,适合交互式可视化。

设计目标:
- 单一职责: 只做"navisv graph → elkjs JSON"转换,不渲染、不调 JS
- 自描述: 每个节点/边带 `properties` 字段,供 HTML viewer 交互层用
- 可扩展: view-specific 逻辑在 elk_view_*.py 中实现,本文件只做核心映射

典型用法:
    gb = GraphBuilder(...)
    gb.build()
    exporter = ElkExporter(view='dataflow').from_graph_builder(gb)
    json_data = exporter.to_elk_json()
    exporter.export_html('/tmp/out.html')

JSON 输出格式 (elkjs):
    {
        "id": "root",
        "layoutOptions": {"elk.algorithm": "layered", "elk.direction": "DOWN"},
        "children": [
            {"id": "alu.add_inst", "labels": [...], "ports": [...],
             "properties": {"kind": "Instance", "file": "alu.sv", "line": 42}},
            ...
        ],
        "edges": [
            {"id": "e1", "sources": [...], "targets": [...],
             "labels": [...], "properties": {...}},
            ...
        ]
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import networkx as nx

ViewType = Literal["dataflow", "controlflow", "modules"]


# ---------------------------------------------------------------------------
# 常量 - elkjs layout options 默认值
# ---------------------------------------------------------------------------

LAYOUT_OPTIONS: Dict[ViewType, Dict[str, str]] = {
    # 数据流: 层次布局,从上往下,输入端口固定在西边、输出在东边
    "dataflow": {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.layered.spacing.nodeNodeBetweenLayers": "60",
        "elk.spacing.nodeNode": "40",
        "elk.portConstraints": "FIXED_SIDE",
    },
    # 控制流: 层次布局,适合 if/case/loop 嵌套
    "controlflow": {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.layered.crossingMinimization.semiInteractive": "true",
    },
    # 模块层级: 力导向布局,展示 RTL 整体结构
    "modules": {
        "elk.algorithm": "stress",
        "elk.stress.spacing": "80",
    },
}

# 节点类型 → elkjs 节点属性 (颜色/形状)
KIND_COLORS: Dict[str, str] = {
    "State": "#27ae60",     # reg → 绿
    "Reg": "#27ae60",
    "Port": "#3498db",      # 默认蓝
    "Net": "#95a5a6",       # wire → 灰
    "Wire": "#95a5a6",
    "Instance": "#9b59b6",  # module instance → 紫
    "Module": "#34495e",    # top module → 深灰
    "Input": "#2980b9",     # input port → 深蓝
    "Output": "#e67e22",    # output port → 橙
    "Inout": "#8e44ad",
    "Operator": "#e67e22",  # (Stage 2.5) 运算符节点 (if/<=/merge/case) → 橙
    "Literal": "#7f8c8d",   # (Stage 2.5) 字面量 (4'h1 等) → 灰
}

# (Stage 2.5) 节点 kind → 自定义宽高 (默认 160x50)
KIND_SIZES: Dict[str, tuple] = {
    "Operator": (90, 50),   # 菱形运算符，较小
    "Literal": (80, 36),    # 字面量，最小
}

# 边 timing → 颜色
TIMING_COLORS: Dict[str, str] = {
    "combinational": "#2c3e50",
    "sequential": "#2980b9",
    "unknown": "#7f8c8d",
}

# 边 edge_kind → 颜色 (timing 默认之上叠加)
EDGE_KIND_COLORS: Dict[str, str] = {
    "AlwaysFF": "#16a085",  # 时序逻辑块 → 青
    "AlwaysComb": "#27ae60",
    "Assign": "#34495e",
    "Case": "#f39c12",
    "Conditional": "#e67e22",
    "CDC": "#e74c3c",       # CDC 边 → 红
}


# ---------------------------------------------------------------------------
# 核心: ElkExporter
# ---------------------------------------------------------------------------

@dataclass
class ElkExporter:
    """navisv 图 → elkjs JSON 转换器

    Attributes:
        view: 视图类型 ('dataflow' | 'controlflow' | 'modules')
        cdc_highlight: 是否高亮 CDC 边 (在边的 elkjs layoutOptions 中着色)
        max_nodes: 节点上限;超过则截断 (0 = 不限)
        scope: 子模块聚焦路径 (e.g. 'top.cpu.alu');None 表示全图
        graph: 输入的 networkx 图 (MultiDiGraph)
        node_data: 节点属性 dict (从 graph 提取)
        edge_data: 边属性 dict (从 graph 提取)
        cdc_edge_set: CDC 边集合 {(src, tgt), ...}
    """
    view: ViewType = "dataflow"
    cdc_highlight: bool = False
    max_nodes: int = 500
    scope: Optional[str] = None
    # (Stage 2.9) 借鉴 sv_query DATAFLOW_VIZ_SPEC.md §4: 过滤掉 CLOCK/RESET/self-loop 边
    # 让数据流视图更纯净, 时序触发关系不画, 跟 sv_query 一致
    filter_clock_reset: bool = False

    graph: Optional[nx.MultiDiGraph] = field(default=None, init=False)
    node_data: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False)
    edge_data: Dict[Tuple[str, str, Any], Dict[str, Any]] = field(default_factory=dict, init=False)
    cdc_edge_set: Set[Tuple[str, str]] = field(default_factory=set, init=False)
    source_map: Dict[str, str] = field(default_factory=dict, init=False)  # node_id -> 源码片段

    # -----------------------------------------------------------------------
    # 构造入口
    # -----------------------------------------------------------------------

    def from_graph_builder(self, gb: Any) -> "ElkExporter":
        """从 GraphBuilder 加载图

        Args:
            gb: GraphBuilder 实例,需已调用 build() 产生 gb.graph (MultiDiGraph)
        """
        if gb.graph is None:
            raise ValueError("GraphBuilder.build() must be called first")

        self.graph = gb.graph
        self._extract_node_attrs(gb)
        self._extract_edge_attrs(gb)
        return self

    def from_design_graph(self, design_graph: Any) -> "ElkExporter":
        """从 DesignDriver.build().design_graph 加载

        Args:
            design_graph: DesignGraph 实例,内部含 .graph (MultiDiGraph)
        """
        if design_graph.graph is None:
            raise ValueError("DesignGraph.graph is None; call driver.build() first")

        self.graph = design_graph.graph
        # DesignGraph 节点/边属性已嵌入 graph node/edge data
        for nid in self.graph.nodes:
            self.node_data[nid] = dict(self.graph.nodes[nid])
        for u, v, k in self.graph.edges(keys=True):
            self.edge_data[(u, v, k)] = dict(self.graph.edges[u, v, k])
        return self

    def from_networkx(self, graph: nx.MultiDiGraph,
                      node_attrs: Optional[Dict[str, Dict[str, Any]]] = None,
                      edge_attrs: Optional[Dict[Tuple[str, str, Any], Dict[str, Any]]] = None
                      ) -> "ElkExporter":
        """从裸 networkx 图加载 (主要用于测试)

        Args:
            graph: nx.MultiDiGraph
            node_attrs: 可选节点属性覆盖 {node_id: {kind: ..., ...}}
            edge_attrs: 可选边属性 {(src, tgt, key): {timing: ..., ...}}
        """
        self.graph = graph
        # 兼容 None (默认参数场景) — node_attrs/edge_attrs 为 None 时退化为空 dict
        node_attrs = node_attrs or {}
        edge_attrs = edge_attrs or {}

        for nid in graph.nodes:
            # 优先用外部传入的覆盖,否则用 graph 节点内置 data
            if nid in node_attrs:
                self.node_data[nid] = dict(node_attrs[nid])
            else:
                self.node_data[nid] = dict(graph.nodes[nid])

        if edge_attrs:
            for key, attrs in edge_attrs.items():
                self.edge_data[key] = attrs
        else:
            for u, v, k in graph.edges(keys=True):
                self.edge_data[(u, v, k)] = dict(graph.edges[u, v, k])
        return self

    # -----------------------------------------------------------------------
    # 属性提取 (from GraphBuilder)
    # -----------------------------------------------------------------------

    def _extract_node_attrs(self, gb: Any) -> None:
        """从 GraphBuilder._node_attrs 提取节点属性"""
        for path, attr in gb._node_attrs.items():
            self.node_data[path] = attr.to_dict()

    def _extract_edge_attrs(self, gb: Any) -> None:
        """从 GraphBuilder._edge_attrs 提取边属性"""
        for key, attr in gb._edge_attrs.items():
            self.edge_data[key] = attr.to_dict()

    # -----------------------------------------------------------------------
    # 核心: 输出 elkjs JSON
    # -----------------------------------------------------------------------

    def to_elk_json(self) -> Dict[str, Any]:
        """转换为 elkjs 输入 JSON 格式

        返回格式:
            {
                "id": "root",
                "layoutOptions": {...},
                "children": [...],
                "edges": [...]
            }
        """
        if self.graph is None:
            raise ValueError("No graph loaded; call from_graph_builder/from_design_graph/from_networkx first")

        # 1. scope 过滤
        scoped_nodes = self._filter_by_scope()
        if self.max_nodes and len(scoped_nodes) > self.max_nodes:
            scoped_nodes = self._truncate(scoped_nodes)

        # 2. elkjs root 配置
        elk_json: Dict[str, Any] = {
            "id": "root",
            "layoutOptions": dict(LAYOUT_OPTIONS[self.view]),
            "children": [],
            "edges": [],
        }

        # 3. 节点 → elkjs children
        node_ids_in_graph: Set[str] = set()
        for node_path in sorted(scoped_nodes):
            elk_node = self._node_to_elk(node_path)
            if elk_node:
                elk_json["children"].append(elk_node)
                node_ids_in_graph.add(node_path)

        # 4. 边 → elkjs edges (仅 source/target 都在 node_ids_in_graph 中)
        edge_idx = 0
        # (Stage 2.9) 借鉴 sv_query DATAFLOW_VIZ_SPEC.md §4: 过滤 CLOCK/RESET/self-loop/loop-back 边
        # self_loop_count 永远追踪 (默认也会被滤); filtered_edges 只在 filter_clock_reset=True 时 > 0
        self_loop_count = 0
        filtered_count = 0
        kept_srcs: Set[str] = set()
        kept_tgts: Set[str] = set()
        for (src, tgt, key), attrs in self.edge_data.items():
            if src not in node_ids_in_graph or tgt not in node_ids_in_graph:
                continue
            if src == tgt:  # 永远过滤 self-loop (跟旧版兼容)
                self_loop_count += 1
                continue
            if self._should_skip_edge(src, tgt, attrs):
                filtered_count += 1
                continue
            elk_edge = self._edge_to_elk(src, tgt, attrs, edge_idx)
            elk_json["edges"].append(elk_edge)
            edge_idx += 1
            kept_srcs.add(src)
            kept_tgts.add(tgt)

        # (Stage 2.9) 移除 orphan 节点 (过滤后没有任何边的节点)
        if filtered_count > 0:
            kept_nodes = kept_srcs | kept_tgts
            before = len(elk_json["children"])
            elk_json["children"] = [c for c in elk_json["children"] if c["id"] in kept_nodes]
            orphan_count = before - len(elk_json["children"])
        else:
            orphan_count = 0

        # (Stage 2.9) 元数据: viewer 调试用
        elk_json.setdefault("properties", {})
        elk_json["properties"]["filtered_edges"] = filtered_count
        elk_json["properties"]["self_loops_removed"] = self_loop_count
        elk_json["properties"]["orphan_nodes_removed"] = orphan_count

        return elk_json

    # -----------------------------------------------------------------------
    # 节点 → elkjs child
    # -----------------------------------------------------------------------

    def _node_to_elk(self, node_path: str) -> Optional[Dict[str, Any]]:
        """单个节点转 elkjs child 格式

        关键设计:
        - id 用 navisv 的 path (e.g. 'top.cpu.alu.reg_q'), elkjs 直接用
        - labels 显示 "name (file:line)",有源码则附 snippet
        - ports 用于端口对齐 (Port kind 节点,输入/输出方向固定边)
        - properties 嵌入 navisv 完整数据,给 viewer 交互层用
        """
        attrs = self.node_data.get(node_path, {})
        kind = attrs.get("kind", "")
        name = attrs.get("name", node_path.split(".")[-1])
        direction = attrs.get("direction", "")
        location = attrs.get("location") or {}

        # 标签: name + 文件:行号
        file_ = location.get("file", "") if isinstance(location, dict) else ""
        line = location.get("line", 0) if isinstance(location, dict) else 0
        label_text = name
        if file_ and line:
            short_file = file_.split("/")[-1]
            label_text = f"{name} ({short_file}:{line})"
        elif file_:
            short_file = file_.split("/")[-1]
            label_text = f"{name} ({short_file})"

        # 节点颜色 (CSS 变量名由 viewer 解析)
        node_color = KIND_COLORS.get(kind, "#34495e")

        elk_node: Dict[str, Any] = {
            "id": node_path,
            "labels": [{"text": label_text}],
            "width": KIND_SIZES.get(kind, (160, 50))[0],
            "height": KIND_SIZES.get(kind, (160, 50))[1],
            "shape": "diamond" if kind == "Operator" else None,  # elkjs shape hint
            "properties": {
                "kind": kind,
                "name": name,
                "direction": direction,
                "module": attrs.get("module", ""),
                "file": file_,
                "line": line,
                "source": self.source_map.get(node_path, ""),
                "color": node_color,
                "timing": attrs.get("timing", "unknown"),
                # (Stage 2.5) Operator/Literal 特有字段
                "operator_kind": attrs.get("attributes", {}).get("operator_kind", ""),
                "value": attrs.get("attributes", {}).get("value", ""),
            },
        }

        # 输入/输出端口: 固定到 WEST/EAST,elkjs 自动对齐数据流方向
        # (Stage 2.8) layerConstraint FIRST/LAST 强制端口在最左/最右层
        # 参考 sv_query elk_bridge.py: port_in=FIRST (左列), port_out=LAST (右列)
        if kind in ("Port", "Input", "Output", "Inout"):
            is_input = direction in ("input", "inout", "In")
            port_side = "WEST" if is_input else "EAST"
            elk_node["ports"] = [{
                "id": f"{node_path}.port",
                "labels": [{"text": name}],
                "layoutOptions": {"portConstraints.fixedSide": port_side},
            }]
            elk_node["properties"]["portSide"] = port_side
            elk_node["layoutOptions"] = {
                "elk.layered.layering.layerConstraint":
                    "FIRST" if is_input else "LAST",
            }

        return elk_node

    # -----------------------------------------------------------------------
    # 边 → elkjs edge
    # -----------------------------------------------------------------------

    def _edge_to_elk(self, src: str, tgt: str, attrs: Dict[str, Any],
                     idx: int) -> Dict[str, Any]:
        """单条边转 elkjs edge 格式

        关键设计:
        - sources/targets 必须是节点或端口 id
        - 优先用端口连接 (如果有);否则直接用节点 id
        - CDC 高亮: 在 layoutOptions.elk.edge.color 设红色
        - labels 携带 condition/timing 摘要
        """
        # 优先用端口 (Port 节点有 .port 子端口)
        src_port = self._port_id(src, attrs, "source")
        tgt_port = self._port_id(tgt, attrs, "target")

        timing = attrs.get("timing", "unknown")
        edge_kind = attrs.get("edge_kind", "")
        condition = attrs.get("condition", "")
        condition_kind = attrs.get("condition_kind", "")
        condition_signals = attrs.get("condition_signals", [])

        # 边颜色: CDC > edge_kind > timing > 默认
        is_cdc = (src, tgt) in self.cdc_edge_set
        if is_cdc and self.cdc_highlight:
            color = EDGE_KIND_COLORS["CDC"]
        elif edge_kind in EDGE_KIND_COLORS:
            color = EDGE_KIND_COLORS[edge_kind]
        elif timing in TIMING_COLORS:
            color = TIMING_COLORS[timing]
        else:
            color = "#2c3e50"

        # 标签: 条件或 timing
        label_text = ""
        if condition:
            cond_short = condition[:50] + ("..." if len(condition) > 50 else "")
            label_text = f"[{condition_kind}] {cond_short}" if condition_kind else cond_short
        elif edge_kind and edge_kind != "None":
            label_text = edge_kind
        elif timing and timing != "unknown":
            label_text = timing

        elk_edge: Dict[str, Any] = {
            "id": f"e{idx}",
            "sources": [src_port],
            "targets": [tgt_port],
            "labels": [{"text": label_text}] if label_text else [],
            "properties": {
                "timing": timing,
                "edge_kind": edge_kind,
                "condition": condition,
                "condition_kind": condition_kind,
                "condition_signals": condition_signals,
                "cdc": is_cdc,
                "color": color,
                "path_count": attrs.get("path_count", 1),
            },
            "layoutOptions": {"elk.edge.color": color},
        }

        return elk_edge

    @staticmethod
    def _port_id(node_id: str, attrs: Dict[str, Any], role: str) -> str:
        """获取节点对应的端口 id

        如果节点是 Port 类型,用 node_id.port (elkjs 子端口);
        否则直接用 node_id。
        """
        # 这里 attrs 是边的属性,不包含 kind。检查 node_data 需从外部传。
        # 简化: 大部分节点没有 port,直接返回节点 id。
        # Port 类型节点在 _node_to_elk 时会建 port,但边的连接要看 graph topology,
        # 这里我们用 node_id 直连 (elkjs 会自动找最近的端口)。
        return node_id

    # -----------------------------------------------------------------------
    # scope / 截断
    # -----------------------------------------------------------------------

    def _should_skip_edge(self, src: str, tgt: str,
                          attrs: Dict[str, Any]) -> bool:
        """(Stage 2.9) 借鉴 sv_query DATAFLOW_VIZ_SPEC.md §4: 过滤不画 CLOCK/RESET/self-loop

        sv_query spec 原文 (§4 "边分类规则"):
        - kind == CLOCK (时钟边)        → 不入图
        - kind == RESET (复位边)        → 不入图
        - kind == BIT_SELECT (位选边)   → 不入图
        - muxed_pairs (无条件 mux 边)   → 不入图
        - 所有出边都是条件边的节点       → 不入图

        navisv 映射:
        - CLOCK: edge_kind='PosEdge' (posedge clk)
        - RESET: edge_kind='NegEdge' (negedge rst_n) 或 edge_kind='LevelEdge'
        - BIT_SELECT: navisv 目前没有显式分类, 后续添加
        - self-loop: src == tgt (count→count)
        - loop-back from FF: timing='sequential_output'

        Returns:
            True: 过滤掉 (不入图)
            False: 保留
        """
        # 永远过滤 self-loop (由 to_elk_json 独立处理, 这里只管 filter_clock_reset)
        # 借鉴 sv_query: CLOCK/RESET 边只在 filter_clock_reset=True 时过滤
        if not self.filter_clock_reset:
            return False

        edge_kind = attrs.get("edge_kind") or ""
        timing = attrs.get("timing") or ""
        condition = attrs.get("condition") or ""

        # CLOCK 边 (PosEdge = posedge clk)
        if edge_kind == "PosEdge":
            return True
        # RESET 边 (NegEdge = negedge rst_n, LevelEdge = async reset level)
        if edge_kind in ("NegEdge", "LevelEdge"):
            return True
        # FF loop-back (count → count 是 sequential_output)
        if timing == "sequential_output":
            return True
        # sequential_input 到 State (FF enable/load/clear)
        if timing == "sequential_input":
            # 这些边是 always_ff 的 enable/clk-edge 路径
            # sv_query 也会过滤 (muxed_pairs 已经在 scope 表达)
            return True
        # (Stage 2.9 fix) navisv 真实 EdgeAttr 把 always_ff 的 clk/rst/data 都打成
        # timing='unknown' + condition='<signal>' + condition_kind='if'
        # sv_query spec: muxed_pairs (条件 mux 边) 不入图
        # 直接过滤任何带 condition 的边 — 它们都是 FF 路径的 mux
        if condition and (attrs.get("condition_kind") or "") == "if":
            return True

        return False

    def _filter_by_scope(self) -> Set[str]:
        """按 scope 过滤节点;None = 全图"""
        if not self.scope:
            return set(self.graph.nodes)

        # scope 是 path 前缀 (e.g. 'top.cpu.alu')
        prefix = self.scope.rstrip(".")
        return {n for n in self.graph.nodes if n == prefix or n.startswith(prefix + ".")}

    def _truncate(self, nodes: Set[str]) -> Set[str]:
        """节点过多时截断 (按 path 排序,保留前 max_nodes 个)"""
        import logging
        sorted_nodes = sorted(nodes)
        truncated = set(sorted_nodes[: self.max_nodes])
        logging.warning(
            "[ElkExporter] graph truncated from %d to %d nodes (use --max-nodes 0 to disable)",
            len(nodes), self.max_nodes,
        )
        return truncated

    # -----------------------------------------------------------------------
    # 输出: JSON 文件 / dict dump
    # -----------------------------------------------------------------------

    def export_json(self, output_path: str, indent: int = 2) -> Path:
        """导出 .json 文件 (供 elkjs.live 或其他工具使用)"""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_elk_json(), indent=indent))
        return out

    def to_json_string(self, indent: int = 2) -> str:
        """返回 JSON 字符串 (给 HTML 模板嵌入用)"""
        return json.dumps(self.to_elk_json(), indent=indent)

    # -----------------------------------------------------------------------
    # 输出: 自包含 HTML viewer (Stage 2)
    # -----------------------------------------------------------------------

    def export_html(self, output_path: str, title: Optional[str] = None) -> Path:
        """导出自包含 HTML viewer (Stage 2)

        单文件 HTML 含:
          - bundled elkjs.js (≈1.6MB, 离线可用)
          - 嵌入的 elk JSON
          - 嵌入的 CSS + 交互 JS
          - 点击节点/边 → 显示详情到 #info 面板

        Args:
            output_path: 输出 .html 文件路径
            title: 浏览器标签标题 (默认 'navisv × elkjs')

        Returns:
            Path: 写入的文件路径

        Raises:
            FileNotFoundError: 缺少 navisv/data/ 资源文件
        """
        # 延迟导入避免循环依赖 (elk_html_template 独立模块)
        from navisv.graph.elk_html_template import build_html, meta_from_json

        elk_json = self.to_elk_json()

        if title is None:
            n_nodes = len(elk_json.get("children", []))
            n_edges = len(elk_json.get("edges", []))
            scope_part = f" [{self.scope}]" if self.scope else ""
            title = f"navisv: {self.view}{scope_part} ({n_nodes} nodes / {n_edges} edges)"

        html = build_html(
            elk_json=elk_json,
            title=title,
            view=self.view,
            meta=meta_from_json(elk_json, self.view),
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return out


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def elk_from_design_driver(driver: Any, view: ViewType = "dataflow",
                           cdc_highlight: bool = False,
                           max_nodes: int = 500,
                           scope: Optional[str] = None) -> ElkExporter:
    """从 DesignDriver 一键构建 ElkExporter

    Args:
        driver: DesignDriver 实例 (需已 build())
        view: 视图类型
        cdc_highlight: 是否高亮 CDC 边
        max_nodes: 节点上限
        scope: 子模块聚焦路径

    Returns:
        ElkExporter 实例 (未调用 to_elk_json)
    """
    dg = driver.design_graph
    return (ElkExporter(view=view, cdc_highlight=cdc_highlight,
                        max_nodes=max_nodes, scope=scope)
            .from_design_graph(dg))