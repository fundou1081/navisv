# graph/design_graph.py - 核心图存储
# navisv 架构 v0.9 - Graph Layer

"""
DesignGraph: 持有 networkx DiGraph，是 navisv 的唯一数据存储。

铁律约束：
- [铁律2] networkx DiGraph 是唯一查询接口，不维护自定义索引字典
- [铁律3] slang 是拓扑权威，Python 只做属性补充
- [铁律14] DesignGraph 禁止暴露内部 DiGraph

构建流程（v0.9 基于用户指南的重构）：
1. 从 slang-netlist 添加节点
2. 调用 graph.get_drivers() 创建边（slang 拓扑权威）
3. StatementExplorer 补充边属性（不创建新边）
4. ClassExplorer 补充 class 内 method 调用边（唯一在 Python 创建边的场景）

参考: docs/SLANG_NETLIST_USER_GUIDE.md
"""

from typing import List, Tuple, Optional, Any, Iterator
import os

import networkx as nx

from .schema import bit_width_from_bounds


# 已知需要检查 timing 的 procedural block kinds
PROCEDURAL_BLOCK_KINDS = {
    'AlwaysFF', 'AlwaysComb', 'AlwaysLatch', 'Always',
    'Initial', 'Final'
}


def _get_slang_modules():
    """延迟加载 slang-netlist 模块"""
    import sys
    sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
    sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')
    import pyslang
    import pyslang_netlist
    return pyslang, pyslang_netlist


class DesignGraph:
    """
    持有 networkx DiGraph，是 navisv 的唯一数据存储。
    
    构建流程（v0.9 重构）：
    1. 从 slang-netlist 添加节点（SignalNode 属性）
    2. 调用 graph.get_drivers() 创建边（拓扑权威）
    3. StatementExplorer 补充边属性（不创建新边）
    4. ClassExplorer 补充 method 边
    """

    def __init__(self, sv_files: List[str], enable_annotators: bool = True):
        # 铁律2：self.graph 是唯一存储，不维护额外的自定义索引
        self.graph = nx.DiGraph()
        self._sv_files = sv_files
        self._enable_annotators = enable_annotators
        self._comp = None
        self._mgr = None
        self._slang_graph = None  # slang NetlistGraph
        self._module_name = None
        self._build()

    def _build(self) -> None:
        """主构建流程（v0.9 基于用户指南重构）"""
        pyslang, pyslang_netlist = _get_slang_modules()

        # 1. 解析语法树（使用 SourceManager 支持 include 路径）
        sm = pyslang.SourceManager()

        # 添加默认 include 目录（如果存在）
        include_dirs = self._find_include_dirs()
        for d in include_dirs:
            if os.path.isdir(d):
                sm.addUserDirectories(d)

        # 使用 fromFiles 一次性加载所有文件（支持跨文件 include 查找）
        valid_files = [f for f in self._sv_files if os.path.exists(f)]
        if len(valid_files) < len(self._sv_files):
            missing = set(self._sv_files) - set(valid_files)
            print(f"Warning: {len(missing)} files not found")
        tree = pyslang.syntax.SyntaxTree.fromFiles(valid_files, sm)

        # 2. 编译（语义分析）
        self._comp = pyslang.ast.Compilation()
        self._comp.addSyntaxTree(tree)

        # 2.5 诊断噪声检查（diagnose noise）
        # 如果有编译错误，分析并输出提示信息
        diagnostics = self._comp.getAllDiagnostics()
        if diagnostics:
            self._diag_noise(diagnostics)

        # 3. 激发 elaboration（新版 slang 必须调用，否则无法分析）
        self._comp.getSemanticDiagnostics()

        # 4. 强制冻结 AST (为多线程安全)
        pyslang_netlist.VisitAll().run(self._comp)

        # 5. 冻结编译，运行数据流分析
        self._comp.freeze()
        self._mgr = pyslang.analysis.AnalysisManager()
        self._mgr.analyze(self._comp)

        # 6. 解冻 (netlist builder 需要继续 elaborate AST)
        self._comp.unfreeze()

        # 7. 构建 netlist 图
        # 注意：resolve_assign_bits=False 避免 picorv32 等大型设计 SIGSEGV
        self._slang_graph = pyslang_netlist.NetlistGraph()
        self._slang_graph.build(self._comp, self._mgr, resolve_assign_bits=False)

        # 获取模块名
        root = self._comp.getRoot()
        inst = list(root)[1] if len(list(root)) > 1 else None
        self._module_name = inst.name if inst else 'top'

        # 8. 从 slang-netlist 添加节点
        self._add_nodes_from_slang(pyslang_netlist)

        # 8.5 从 compilation 添加 Instance 节点（slang-netlist 不提供 Instance 节点）
        self._add_instances_from_comp()

        # 8.6 从 compilation 添加 Net/Variable 节点（slang-netlist 不包含内部 nets）
        self._add_nets_from_comp()

        # 9. graph.get_drivers() 创建边（拓扑权威）
        self._add_edges_from_slang()

        # 10. 使用 PathFinder 补充遗漏的边
        self._add_edges_from_pathfinder()

        # 11. StatementExplorer 注释边属性
        if self._enable_annotators:
            self._annotate_edges_from_statements()

        # 12. ClassExplorer 补充 method 边
        if self._enable_annotators:
            self._add_method_edges()

    def _find_include_dirs(self) -> List[str]:
        """从 _sv_files 推断可能的 include 目录"""
        include_dirs = []
        for f in self._sv_files:
            # 向上查找可能的 include 目录
            parent = os.path.dirname(f)
            for _ in range(3):  # 向上最多3层
                include = os.path.join(parent, 'include')
                if os.path.isdir(include) and include not in include_dirs:
                    include_dirs.append(include)
                vendor = os.path.join(parent, 'vendor')
                if os.path.isdir(vendor):
                    # 添加 vendor 下的所有 include
                    for root, dirs, files in os.walk(vendor):
                        inc = os.path.join(root, 'include')
                        if os.path.isdir(inc) and inc not in include_dirs:
                            include_dirs.append(inc)
                parent = os.path.dirname(parent)
        return include_dirs

    def _diag_noise(self, diagnostics) -> None:
        """分析编译诊断信息，输出有用的提示"""
        # 统计错误类型
        error_codes = {}
        missing_includes = []
        for i in range(len(diagnostics)):
            d = diagnostics[i]
            if d.isError():
                code = str(d.code)
                error_codes[code] = error_codes.get(code, 0) + 1
                # 记录缺失的 include 文件
                if 'CouldNotOpenIncludeFile' in code:
                    args = getattr(d, 'args', None)
                    if args:
                        missing_includes.append(args[0])

        error_count = sum(1 for i in range(len(diagnostics)) if diagnostics[i].isError())
        warning_count = len(diagnostics) - error_count

        # 输出概要
        if error_count > 0:
            print(f"Compilation: {error_count} errors, {warning_count} warnings")

            # 输出主要错误类型
            if error_codes:
                top_errors = sorted(error_codes.items(), key=lambda x: -x[1])[:5]
                print("Top errors:")
                for code, count in top_errors:
                    # 简化错误代码名称
                    simple_name = code.replace('DiagCode(', '').replace(')', '')
                    print(f"  [{count}x] {simple_name}")

            # 输出缺失的 include 文件
            if missing_includes:
                unique_includes = list(set(missing_includes))
                print(f"Missing include files: {', '.join(unique_includes[:5])}")
                if len(unique_includes) > 5:
                    print(f"  ... and {len(unique_includes) - 5} more")

            # 输出 AGENT 提示
            print("\n[AGENT] Suggestion:")
            if missing_includes:
                print("  - Check if include directories are in the search path")
            if 'UnknownModule' in str(error_codes):
                print("  - Verify all module dependencies are included")
            if 'UnknownClassOrPackage' in str(error_codes):
                print("  - Check if package/class definitions are available")
            if 'InvalidMemberAccess' in str(error_codes):
                print("  - Types may be undefined due to missing header files")
        else:
            if warning_count > 50:
                print(f"Compilation: {warning_count} warnings (no errors)")

    def _trace_to_named(self, start_node, max_depth=10) -> List[str]:
        """
        从任意节点追踪到其所有的 Named fan-in 源。
        
        沿着 fan_in 方向向上追踪，找到所有有 path 的 Named Nodes。
        如果遇到组合循环，会被 visited set 停止。
        
        这个函数替代了原来的 _trace_assignment_fan_in()，后者只追踪 Assignment。
        现在追踪所有 unnamed 节点（Assignment/Conditional/Case/Merge）。
        
        Args:
            start_node: 起始节点（可能是 Unnamed）
            max_depth: 最大追踪深度
        
        Returns:
            List[str]: 所有 Named fan-in 源路径列表（去重）
        """
        sl_graph = self._slang_graph
        visited = set()
        queue = [(start_node, 0)]
        named_sources = []
        
        while queue:
            node, depth = queue.pop(0)
            
            if depth > max_depth:
                continue
            
            node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node_path = getattr(node, 'path', None) or getattr(node, 'hierarchicalPath', None)
            if node_path:
                named_sources.append(node_path)
                continue
            
            # 无 path，继续追踪 fan_in
            for src in sl_graph.get_comb_fan_in(node):
                if id(src) not in visited:
                    queue.append((src, depth + 1))
        
        return list(set(named_sources))

    def _trace_from_named(self, start_node, max_depth=10) -> List[str]:
        """
        从任意节点追踪到其所有的 Named fan-out 目标。
        
        沿着 fan_out 方向向下追踪，找到所有有 path 的 Named Nodes。
        
        Args:
            start_node: 起始节点
            max_depth: 最大追踪深度
        
        Returns:
            List[str]: 所有 Named fan-out 目标路径列表（去重）
        """
        sl_graph = self._slang_graph
        visited = set()
        queue = [(start_node, 0)]
        named_targets = []
        
        while queue:
            node, depth = queue.pop(0)
            
            if depth > max_depth:
                continue
            
            node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node_path = getattr(node, 'path', None) or getattr(node, 'hierarchicalPath', None)
            if node_path:
                named_targets.append(node_path)
                continue
            
            # 无 path，继续追踪 fan_out
            for tgt in sl_graph.get_comb_fan_out(node):
                if id(tgt) not in visited:
                    queue.append((tgt, depth + 1))
        
        return list(set(named_targets))

    def _classify_timing(self, src_kind: str, dst_kind: str) -> str:
        """
        分类两个节点之间的时序关系。
        
        为 pipeline 和 delay 分析做准备：
        - combinational: 纯组合逻辑路径（无寄存器）
        - sequential: 包含寄存器的时序路径
        - registered: 路径终点是 State（寄存器输入）
        
        Args:
            src_kind: 源节点 kind 字符串
            dst_kind: 目标节点 kind 字符串
        
        Returns:
            str: 'combinational', 'sequential_input', 'sequential_output', 'sequential'
        """
        # State → State: 时序路径（经过寄存器链）
        if 'State' in src_kind and 'State' in dst_kind:
            return 'sequential'
        
        # State → 其他: 寄存器输出路径
        if 'State' in src_kind:
            return 'sequential_output'
        
        # 其他 → State: 寄存器输入路径
        if 'State' in dst_kind:
            return 'sequential_input'
        
        # Port → Port 或其他: 组合逻辑
        return 'combinational'

    def _add_edges_from_slang(self) -> None:
        """
        从 slang-netlist 的 fan_in 关系统一建边。
        
        方案 B 重构：用 get_comb_fan_in() 替代 get_drivers() + trace。
        
        建边策略：
        1. 直接 Named 边：fan_in 返回的 Named Sources
        2. 追踪边：fan_in 返回的 Unnamed Sources 追踪到 Named
        
        边属性（为 pipeline/delay 分析准备）：
        - relation: 'drives' | 'feeds' | 'fans_to'
        - timing: 'combinational' | 'sequential_input' | 'sequential_output' | 'sequential'
        - source: 'slang_direct' | 'slang_traced'
        - confidence: 'high' | 'medium' | 'low'
        - trace_depth: 追踪深度（用于分析路径复杂度）
        - path_type: 'port_to_port' | 'port_to_reg' | 'reg_to_port' | 'reg_to_reg'
        
        验证标准：
        - len(g.edges()) 应该接近 sl_graph.num_edges()
        """
        sl_graph = self._slang_graph
        
        for node in sl_graph:
            node_path = getattr(node, 'path', None) or getattr(node, 'hierarchicalPath', None)
            if not node_path:
                continue
            
            node_kind = str(node.kind).replace('NodeKind.', '')
            
            # 确保节点存在
            if node_path not in self.graph.nodes():
                self.graph.add_node(node_path,
                    name=node_path.rsplit('.', 1)[-1],
                    module=node_path.rsplit('.', 1)[0] if '.' in node_path else self._module_name,
                    bit_width=self._get_bit_width(node),
                    tags=self._get_tags(node),
                    node_kind=node_kind,
                    meta={})
            
            # 获取 fan_in
            fan_in = list(sl_graph.get_comb_fan_in(node))
            
            for src in fan_in:
                src_path = getattr(src, 'path', None) or getattr(src, 'hierarchicalPath', None)
                src_kind = str(src.kind).replace('NodeKind.', '')
                
                if src_path:
                    # Case 1: 直接 Named 边
                    if src_path != node_path:  # 跳过 self-loop
                        self._add_slang_edge(src_path, node_path, src_kind, node_kind, 'direct')
                else:
                    # Case 2: Unnamed → 追踪到 Named
                    traced_paths = self._trace_to_named(src)
                    for traced_path in traced_paths:
                        if traced_path != node_path:
                            self._add_slang_edge(traced_path, node_path, 'Traced', node_kind, 'traced')

    def _add_slang_edge(self, src_path: str, dst_path: str, src_kind: str, dst_kind: str, edge_type: str) -> None:
        """
        添加来自 slang 的边，带完整属性。
        
        为 pipeline/delay 分析准备以下属性：
        - relation: 驱动关系
        - timing: 时序类型
        - source: 边来源
        - confidence: 可信度
        - trace_depth: 追踪深度
        - path_type: 路径类型
        - pipeline_stage: 流水级（如果能确定）
        - combinational_depth: 组合逻辑深度
        """
        if self.graph.has_edge(src_path, dst_path):
            return
        
        # 判断时序类型
        timing = self._classify_timing(src_kind, dst_kind)
        
        # 判断路径类型
        path_type = self._classify_path_type(src_kind, dst_kind)
        
        self.graph.add_edge(src_path, dst_path,
            relation='drives',
            timing=timing,
            source=f'slang_{edge_type}',
            confidence='high',
            path_type=path_type,
            trace_depth=0,  # 后续可以更新
            pipeline_stage=None,  # 后续分析
            combinational_depth=0,  # 后续分析
            meta={})


    def _classify_path_type(self, src_kind: str, dst_kind: str) -> str:
        """
        分类路径类型。
        
        Args:
            src_kind: 源节点 kind（如 'Port', 'State', 'Traced'）
            dst_kind: 目标节点 kind
        
        Returns:
            str: 'port_to_port' | 'port_to_reg' | 'reg_to_port' | 'reg_to_reg' | 'other'
        """
        src_is_port = 'Port' in src_kind
        src_is_reg = 'State' in src_kind
        dst_is_port = 'Port' in dst_kind
        dst_is_reg = 'State' in dst_kind
        
        if src_is_port and dst_is_port:
            return 'port_to_port'
        elif src_is_port and dst_is_reg:
            return 'port_to_reg'
        elif src_is_reg and dst_is_port:
            return 'reg_to_port'
        elif src_is_reg and dst_is_reg:
            return 'reg_to_reg'
        else:
            return 'other'

    def _get_bit_width(self, node) -> Tuple[int, int]:
        """获取节点的 bit width"""
        bounds = getattr(node, 'bounds', None)
        if bounds:
            return bit_width_from_bounds(bounds)
        return (0, 0)

    def _get_tags(self, node) -> set:
        """获取节点的标签"""
        kind = str(node.kind).replace('NodeKind.', '')
        tags = set()
        
        if kind == 'Port':
            direction = getattr(node, 'direction', None)
            if direction:
                dir_name = str(direction).split('.')[-1]  # 'ArgumentDirection.In' → 'In'
                tags.add(dir_name.lower())
        elif kind == 'State':
            tags.add('register')
        
        return tags

    def _verify_edge_completeness(self) -> None:
        """
        验证边是否完整。
        
        打印覆盖率信息，用于调试。
        
        注意：slang.num_edges() 可能包含 unnamed 边，
        因此覆盖率计算基于 slang 的 named→named 边。
        """
        slang_total_edges = self._slang_graph.num_edges()
        
        # 计算 slang 的 named→named 唯一边数
        slang_named_edges = set()
        for node in self._slang_graph:
            node_path = getattr(node, 'path', None) or getattr(node, 'hierarchicalPath', None)
            if not node_path:
                continue
            for src in self._slang_graph.get_comb_fan_in(node):
                src_path = getattr(src, 'path', None) or getattr(src, 'hierarchicalPath', None)
                if src_path and src_path != node_path:
                    slang_named_edges.add((src_path, node_path))
        
        slang_named_count = len(slang_named_edges)
        navisv_edges = len(self.graph.edges())
        
        # 统计边类型
        edge_types = {}
        for _, _, d in self.graph.edges(data=True):
            src = d.get('source', 'unknown')
            edge_types[src] = edge_types.get(src, 0) + 1
        
        # 统计时序类型
        timing_stats = {}
        for _, _, d in self.graph.edges(data=True):
            t = d.get('timing', 'unknown')
            timing_stats[t] = timing_stats.get(t, 0) + 1
        
        print(f"Edge verification:")
        print(f"  slang num_edges (internal): {slang_total_edges}")
        print(f"  slang named→named edges: {slang_named_count}")
        print(f"  navisv edges: {navisv_edges}")
        if slang_named_count > 0:
            coverage = min(navisv_edges / slang_named_count, 1.0)
            print(f"  coverage: {coverage:.1%}")
        
        print(f"  by source: {edge_types}")
        print(f"  by timing: {timing_stats}")
        
        if slang_named_count > 0 and navisv_edges < slang_named_count:
            missing = slang_named_count - navisv_edges
            print(f"  WARNING: {missing} edges missing from navisv")

    def _add_nodes_from_slang(self, nl) -> None:
        """从 slang-netlist 遍历设计，添加所有信号节点（Named Nodes: Port + State）"""
        sl_graph = self._slang_graph
        module_name = self._module_name

        # Named nodes: Port 和 State 可通过 lookup 查询
        # 组合逻辑中间信号（wire/assign）是透明节点，无法 lookup
        for node in sl_graph:
            kind_name = str(node.kind).replace('NodeKind.', '')

            if kind_name not in ('Port', 'State'):
                continue

            # 获取路径
            path = getattr(node, 'path', None) or getattr(node, 'hierarchicalPath', None)
            if not path:
                continue

            # Port 节点有 direction，可以判断是否为 clock
            name = getattr(node, 'name', '') or path.rsplit('.', 1)[-1]
            is_port = kind_name == 'Port'

            # 自动标记 clk/rst 信号
            tags = set()
            if is_port:
                direction = getattr(node, 'direction', None)
                if direction:
                    if 'In' in direction.name or direction.name == 'In':
                        if 'clk' in name.lower() or 'clock' in name.lower():
                            tags.add('clock')
                        elif 'rst' in name.lower() or 'reset' in name.lower():
                            tags.add('reset')
                    if 'Out' in direction.name or direction.name == 'Out':
                        tags.add('output')
                    else:
                        tags.add('input')

            # 添加节点
            self.graph.add_node(path,
                name=name,
                module=path.rsplit('.', 1)[0] if '.' in path else module_name,
                bit_width=bit_width_from_bounds(getattr(node, 'bounds', None)),
                tags=tags,
                node_kind=kind_name,
                meta={})

    def _add_instances_from_comp(self) -> None:
        """
        从 compilation 的 Instance hierarchy 中添加 Instance 节点。

        slang-netlist 只提供 Port/State/Assignment 等信号节点，
        不包含 Instance（模块实例）节点。需要从 pyslang Compilation 中提取。

        处理的 SymbolKind：
        - Instance: 已实例化并 elaborator 的模块
        - UninstantiatedDef: 引用但未 elaborator 的模块定义（如 bs_mult_slice I0）

        节点属性：
        - kind: 'Instance'
        - tags: {'instance'} 或 {'instance', 'uninstantiated'}
        - definition: 模块定义名
        """
        if not self._comp:
            return

        root = self._comp.getRoot()
        visited = set()

        def add_instance(path, name, definition, is_instantiated, parameters=None) -> None:
            """添加一个 Instance 节点"""
            if path in visited:
                return
            visited.add(path)

            tags = {'instance'}
            if not is_instantiated:
                tags.add('uninstantiated')

            self.graph.add_node(path,
                name=name,
                module=path.rsplit('.', 1)[0] if '.' in path else path,
                bit_width=(0, 0),
                tags=tags,
                node_kind='Instance',
                definition=definition,
                parameters=parameters or {},
                meta={})

        def traverse_scope(scope, prefix='') -> None:
            """递归遍历 scope 中的所有 Instance / UninstantiatedDef"""
            for sym in scope:
                kind_str = str(sym.kind)

                if kind_str == 'SymbolKind.Instance':
                    inst = sym
                    inst_name = getattr(inst, 'name', '')
                    path = f'{prefix}.{inst_name}' if prefix else inst_name

                    defn_name = ''
                    if hasattr(inst, 'body') and hasattr(inst.body, 'definition'):
                        defn_name = getattr(inst.body.definition, 'name', '')

                    # 提取参数值
                    params = {}
                    if hasattr(inst, 'body') and hasattr(inst.body, 'parameters'):
                        for p in inst.body.parameters:
                            p_name = getattr(p, 'name', '')
                            p_value = str(getattr(p, 'value', ''))
                            params[p_name] = p_value

                    add_instance(path, inst_name, defn_name, is_instantiated=True, parameters=params)

                    # 递归遍历 body 中的子 instances
                    if hasattr(inst, 'body'):
                        traverse_scope(inst.body, path)

                elif kind_str == 'SymbolKind.UninstantiatedDef':
                    # 未实例化的定义（如 bs_mult_slice I0）
                    def_name = getattr(sym, 'name', '')
                    path = f'{prefix}.{def_name}' if prefix else def_name

                    # 获取引用的定义名
                    defn_name = ''
                    if hasattr(sym, 'definition'):
                        defn_name = getattr(sym.definition, 'name', '')

                    add_instance(path, def_name, defn_name, is_instantiated=False)

        traverse_scope(root)

    def _add_nets_from_comp(self) -> None:
        """
        从 compilation 的 Instance body 中添加内部 Net/Variable 节点。

        slang-netlist 只提供 Port/State/Assignment 节点，不包含内部 wire 信号。
        需要从 pyslang Compilation 的 body scope 中提取 SymbolKind.Net/Variable。

        处理的类型：
        - SymbolKind.Net: wire 等
        - SymbolKind.Variable: reg 等

        节点属性：
        - node_kind: 'Net'
        - tags: {'net'} 或 {'variable'}
        - net_type: wire, wor, wand 等
        """
        if not self._comp:
            return

        root = self._comp.getRoot()

        def traverse_scope(scope, prefix='') -> None:
            """递归遍历 scope 中的所有 Net/Variable"""
            for sym in scope:
                kind_str = str(sym.kind)

                # 处理 Net 和 Variable
                if kind_str in ('SymbolKind.Net', 'SymbolKind.Variable'):
                    net_name = getattr(sym, 'name', '')
                    path = f'{prefix}.{net_name}' if prefix else net_name

                    # 跳过空名称（如匿名符号）
                    if not net_name:
                        continue

                    # 获取 net_type (wire, wor, wand 等)
                    net_type = 'wire'
                    if hasattr(sym, 'netType'):
                        nt = sym.netType
                        if hasattr(nt, 'name'):
                            net_type = nt.name

                    # 标签
                    tags = {'net'}
                    if kind_str == 'SymbolKind.Variable':
                        tags = {'variable'}

                    # 添加 Net 节点
                    if path not in self.graph.nodes():
                        self.graph.add_node(path,
                            name=net_name,
                            module=prefix or 'top',
                            bit_width=(0, 0),
                            tags=tags,
                            node_kind='Net',
                            net_type=net_type,
                            meta={})

                # 递归遍历 body
                if hasattr(sym, 'body') and sym.body:
                    inst_path = f'{prefix}.{getattr(sym, "name", "")}' if prefix else getattr(sym, 'name', '')
                    if str(sym.kind) == 'SymbolKind.Instance':
                        traverse_scope(sym.body, inst_path)

        traverse_scope(root)

    def _add_edges_from_slang_get_drivers(self) -> None:
        """
        DEPRECATED: Use _add_edges_from_slang() instead.
        
        这个函数保留用于向后兼容，但已经被 _add_edges_from_slang() 替代。
        问题：只追踪 Assignment，跳过了 Conditional/Case/Merge。
        """
        # 新建边逻辑已经移到 _add_edges_from_slang()
        pass

    def _resolve_driver_path(self, drv) -> Optional[str]:
        """
        DEPRECATED: Use _trace_to_named() instead.
        """
        return getattr(drv, 'path', None) or getattr(drv, 'hierarchicalPath', None)

    def _trace_assignment_fan_in(self, assign_node, max_depth=10) -> List[str]:
        """
        DEPRECATED: Use _trace_to_named() instead.
        """
        return self._trace_to_named(assign_node, max_depth)

    def _add_edges_from_pathfinder(self) -> None:
        """
        使用 PathFinder 补充 get_drivers() 遗漏的边。
        
        原理：对每对 Input Port -> Output Port，使用 PathFinder.find() 查找路径。
        如果路径非空，说明该 Input Port 驱动该 Output Port。
        
        适用场景：
        - 一个信号在多个 always block 中赋值（导致 get_drivers 链断裂）
        - 复杂的数据流需要 PathFinder 才能正确追踪
        """
        sl_graph = self._slang_graph
        finder = _get_slang_modules()[1].PathFinder()
        module_name = self._module_name

        # 获取所有端口
        port_nodes = [n for n in sl_graph if str(n.kind) == 'NodeKind.Port']
        output_ports = [n for n in port_nodes if n.direction.name == 'Out']
        input_ports = [n for n in port_nodes if n.direction.name == 'In']

        # 对每个 Output Port，查找所有 Input Port 到它的路径
        for out_node in output_ports:
            dst_path = f'{module_name}.{out_node.name}'
            if dst_path not in self.graph.nodes():
                continue

            for in_node in input_ports:
                src_path = f'{module_name}.{in_node.name}'
                if src_path not in self.graph.nodes():
                    continue

                # 跳过 self-loop
                if src_path == dst_path:
                    continue

                # 跳过已存在的边
                if self.graph.has_edge(src_path, dst_path):
                    continue

                # 使用 PathFinder 查找路径
                path = finder.find(in_node, out_node)
                if path.empty():
                    continue

                # 添加边（带时序分类）
                src_kind = 'Port'
                dst_kind = 'Port'
                timing = self._classify_timing(src_kind, dst_kind)
                path_type = self._classify_path_type(src_kind, dst_kind)
                
                self.graph.add_edge(src_path, dst_path,
                    relation='drives',
                    timing=timing,
                    qualifier=None,
                    bounds=None,
                    source_location=None,
                    source='pathfinder',
                    is_partial=False,
                    confidence='high',
                    path_type=path_type,
                    pipeline_stage=None,
                    combinational_depth=0,
                    meta={})

    def _annotate_edges_from_statements(self) -> None:
        """StatementExplorer 补充边属性"""
        from .statement_explorer import StatementExplorer

        explorer = StatementExplorer(self._comp, self._mgr)
        explorer.annotate(self)

    def _add_method_edges(self) -> None:
        """ClassExplorer 补充 class method 调用边"""
        from .class_explorer import ClassExplorer

        explorer = ClassExplorer()
        explorer.merge_method_edges(self)

    # ---- 最小公开接口（铁律14：禁止暴露内部 DiGraph）----

    def nodes(self) -> List[str]:
        """返回所有节点 ID"""
        return list(self.graph.nodes())

    def edges(self) -> List[Tuple[str, str]]:
        """返回所有边的 (src, dst) 元组"""
        return list(self.graph.edges())

    def predecessors(self, node_id: str) -> List[str]:
        """返回驱动这个节点的所有源节点"""
        return list(self.graph.predecessors(node_id))

    def successors(self, node_id: str) -> List[str]:
        """返回这个节点驱动的所有目标节点"""
        return list(self.graph.successors(node_id))

    def edge_attr(self, src: str, dst: str) -> dict:
        """返回边的属性字典"""
        try:
            return dict(self.graph.edges[src, dst])
        except KeyError:
            return {}

    def node_attr(self, node_id: str) -> dict:
        """返回节点的属性字典"""
        try:
            return dict(self.graph.nodes[node_id])
        except KeyError:
            return {}

    def subgraph(self, node_ids: List[str]) -> nx.DiGraph:
        """返回指定节点的子图（内部用于算法）"""
        return self.graph.subgraph(node_ids)

    def has_node(self, node_id: str) -> bool:
        """检查节点是否存在"""
        return self.graph.has_node(node_id)

    def has_edge(self, src: str, dst: str) -> bool:
        """检查边是否存在"""
        return self.graph.has_edge(src, dst)

    def get_node_kind(self, node_id: str) -> Optional[str]:
        """返回节点的种类（Port/State/Variable）"""
        try:
            return self.graph.nodes[node_id].get('node_kind')
        except KeyError:
            return None

    def find_nodes(self, pattern: str) -> List[str]:
        """
        通配符搜索节点。
        
        Args:
            pattern: 通配符模式，如 "module.*" 或 "*.clk"
            
        Returns:
            匹配的节点 ID 列表
        """
        import fnmatch
        return [n for n in self.graph.nodes() if fnmatch.fnmatch(n, pattern)]

    def find_nodes_regex(self, pattern: str) -> List[str]:
        """
        正则表达式搜索节点。
        
        Args:
            pattern: 正则表达式，如 r"top\.s[0-9]+_.*"
            
        Returns:
            匹配的节点 ID 列表
        """
        import re
        return [n for n in self.graph.nodes() if re.match(pattern, n)]

    def __repr__(self) -> str:
        return f"DesignGraph({len(self.graph.nodes())} nodes, {len(self.graph.edges())} edges)"