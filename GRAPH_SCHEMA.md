# navisv 图 Schema 统一设计

**版本**：v0.1  
**日期**：2026-05-17  
**目的**：基于 18 个命令的实际需求，确定需要构建哪些图，以及如何统一 schema

---

## 1. 命令到底需要什么样的"图"

逐个分析 18 个命令对图的需求：

| 命令 | 需要的图 | 节点 | 边 |
|------|----------|------|-----|
| `trace-cone` | 子图（锥） | signal 节点 | DRIVES / CONNECTS |
| `usage` | 扇出 | signal 节点 | DRIVES / CONNECTS |
| `related` | 扇入 + 扇出 + 评分 | signal 节点 | DRIVES + 评分 |
| `sample-condition` | 单信号上下文 | signal + timing | DRIVES（带 timing） |
| `paths` | 路径（data + control） | signal 节点 | DRIVES + 类型标记 |
| `gen-coverage` | 单信号分析 | signal 节点 | 关联信号（cross） |
| `impact` | 扇出锥 | signal 节点 | DRIVES |
| `blast-radius` | 双向 BFS | signal 节点 | DRIVES |
| `fsm-detect` | SCC 图 | state 节点 | DRIVES（状态转移） |
| `stability` | 模块内子图 | module 节点 | 内部/外部边比 |
| `path-profile` | 路径 + CDC | signal + clock | DRIVES + CDC 标记 |
| `protocol-infer` | 端口连接图 | port 节点 | CONNECTS（握手模式） |
| `constraints` | constraint 关系图 | signal 变量 | constraint 关系（implication/inside/dist） |
| `assert` | 信号 + timing | signal + clock | DRIVES（带 timing） |
| `grade` | 全局指标 | signal 节点 | 各种边 |
| `sample-condition` | 扇入（采样条件） | signal + clock | DRIVES（带 qualifier） |
| `gen-coverage` | 单信号 | signal 节点 | 值域边界 |

**发现**：
- **14/18 个命令**只需要一种图：**Signal Netlist Graph**（信号 + driver/load 关系）
- **3 个命令**需要额外信息：constraint 关系、protocol 连接、coverage 值域
- **1 个命令**需要 SCC 图：fsm-detect

---

## 2. 需要构建的图种类

基于需求分析，只需要 **2 种图**：

### 图 1：Signal Netlist Graph（统一信号关系图）

```
节点类型：Signal / Port / State / Assignment / Constant / Clock
边类型：   DRIVES / CONNECTS / CONTROLS / DATA_FLOW
```

### 图 2：Constraint Graph（类约束关系图）

```
节点类型：Signal（class property）/ ConstraintBlock / ConstraintExpr
边类型：   IMPLIES / INSIDE / DIST / IF_ELSE / CROSS
```

**注意**：Constraint Graph 是 **Class 内部专用**，不是全局的。

---

## 3. 统一 Signal Netlist Graph Schema

### 3.1 节点定义

```python
# graph/signal_node.py

class NodeKind(Enum):
    """统一节点类型"""
    # ---- 基础类型 ----
    PORT_INPUT = "port_input"
    PORT_OUTPUT = "port_output"
    PORT_INOUT = "port_inout"
    SIGNAL = "signal"           # 通用信号（wire / reg）
    STATE = "state"             # 状态寄存器（always_ff）
    CONSTANT = "constant"       # 字面量
    ASSIGNMENT = "assignment"   # assign 语句节点

    # ---- 扩展类型 ----
    CLOCK = "clock"             # 时钟信号
    RESET = "reset"             # 复位信号
    INTERFACE = "interface"     # 接口实例


@dataclass
class SignalNode:
    """
    统一信号节点 schema（navisv + sv_query 共用）

    与 sv_query SignalGraph 节点对照：
    - sv_query 用 networkx 属性 dict，navisv 用 dataclass
    - 核心字段完全兼容
    """
    # 身份
    id: str                      # 层级路径 "top.axi.clk"
    name: str                    # 信号名 "clk"

    # 类型
    kind: NodeKind               # 节点类型

    # 时序属性
    bit_width: Tuple[int, int]  # (msb, lsb)，例 (31, 0)
    bit_range_str: str          # "[31:0]"
    is_register: bool           # 是否为寄存器（always_ff 驱动）

    # 时钟/复位
    clock_domain: Optional[str]  # "aclk" / "pclk" / None
    reset_value: Optional[str]   # "1'b0 @ negedge rst_n"

    # 驱动信息（冗余存储，加速查询）
    driver_count: int            # 驱动源数量（0=未驱动，1=正常，2+=多驱动）
    driver_type: Optional[str]   # "Procedural" / "Continuous" / "Port"

    # 层级
    module: str                  # 所在模块 "top.axi"
    hierarchical_path: str        # 完整路径，同 id

    # 额外属性（dict，允许扩展）
    attrs: Dict[str, Any] = field(default_factory=dict)

    # ---- 兼容 sv_query ----
    @classmethod
    def from_sv_query_node(cls, node) -> 'SignalNode':
        """从 sv_query networkx 节点导入"""
        attrs = node.attrs
        return cls(
            id=node.name,
            name=node.name.split('.')[-1],
            kind=NodeKind(attrs.get('kind', 'signal')),
            bit_width=attrs.get('width'),
            bit_range_str=attrs.get('width_str', ''),
            is_register=attrs.get('is_register', False),
            clock_domain=attrs.get('clock_domain'),
            reset_value=attrs.get('reset_value'),
            driver_count=attrs.get('driver_count', 0),
            driver_type=attrs.get('driver_type'),
            module=attrs.get('module', ''),
            hierarchical_path=node.name,
            attrs=attrs
        )
```

### 3.2 边定义

```python
# graph/signal_edge.py

class EdgeKind(Enum):
    """统一边类型"""
    DRIVES = "drives"           # 驱动（always_ff / assign / port）
    CONNECTS = "connects"        # 连接（端口连接）
    CONTROLS = "controls"        # 控制（FSM 状态控制）
    DATA_FLOW = "data_flow"       # 数据流（组合逻辑）
    PROVIDES = "provides"        # 提供（module 提供端口）
    USES = "uses"               # 使用（load）


@dataclass
class SignalEdge:
    """
    统一信号边 schema

    与 sv_query SignalGraph 边对照：
    - sv_query 用 networkx 边的属性 dict
    - navisv 用 dataclass，字段更丰富
    """
    # 身份
    src: str                     # 驱动端节点 id
    dst: str                     # 负载端节点 id

    # 类型
    kind: EdgeKind               # 边类型

    # 时序属性（关键！）
    timing: str                  # "blocking" / "non_blocking" / "continuous"
    clock_domain: Optional[str]  # "aclk" / None

    # 条件（if 门控）
    qualifier: Optional[str]     # "xfer_en" / None

    # 位宽
    bounds: Optional[Tuple[int, int]]  # 位选时记录 [15:8]

    # 层级
    is_cross_module: bool         # 是否跨模块

    # 额外属性
    attrs: Dict[str, Any] = field(default_factory=dict)
```

### 3.3 统一 Signal Netlist Graph Schema

```python
# graph/signal_netlist_graph.py

@dataclass
class SignalNetlistGraph:
    """
    统一信号关系图 schema

    - 基于 slang-netlist NetlistGraph 提取
    - 映射到 networkx DiGraph（可视化）
    - 与 sv_query SignalGraph 字段兼容

    与 sv_query 对比：
    ┌────────────────┬──────────────────┬──────────────────┐
    │ 属性           │ sv_query         │ navisv            │
    ├────────────────┼──────────────────┼──────────────────┤
    │ 节点 schema    │ networkx attr    │ SignalNode       │
    │ 边 schema      │ networkx attr    │ SignalEdge       │
    │ 存储           │ networkx         │ slang + networkx  │
    │ driver 来源    │ Python AST       │ slang C++        │
    │ 路径算法       │ Python 实现      │ slang PathFinder  │
    │ 图算法         │ networkx         │ networkx         │
    └────────────────┴──────────────────┴──────────────────┘
    """

    # ---- 图数据 ----
    nodes: Dict[str, SignalNode]     # node_id → SignalNode
    edges: List[SignalEdge]          # 所有边（无重复）

    # ---- 索引（加速查询）----
    _kind_index: Dict[NodeKind, Set[str]]     # kind → node_ids
    _module_index: Dict[str, Set[str]]         # module → node_ids
    _clock_index: Dict[str, Set[str]]          # clock → node_ids
    _driver_index: Dict[str, List[str]]        # node_id → driver node_ids

    # ---- 网络视图 ----
    _nx_view: Optional[nx.DiGraph] = None

    # =================================================================
    # 节点操作
    # =================================================================

    def add_node(self, node: SignalNode) -> None:
        self.nodes[node.id] = node
        self._rebuild_index(node)

    def get_node(self, node_id: str) -> Optional[SignalNode]:
        return self.nodes.get(node_id)

    def get_nodes_by_kind(self, kind: NodeKind) -> List[SignalNode]:
        return [self.nodes[nid] for nid in self._kind_index.get(kind, set())
                if nid in self.nodes]

    def get_nodes_by_module(self, module: str) -> List[SignalNode]:
        return [self.nodes[nid] for nid in self._module_index.get(module, set())
                if nid in self.nodes]

    # =================================================================
    # 边操作
    # =================================================================

    def add_edge(self, edge: SignalEdge) -> None:
        self.edges.append(edge)
        # driver 索引
        if edge.dst not in self._driver_index:
            self._driver_index[edge.dst] = []
        self._driver_index[edge.dst].append(edge.src)

    def get_drivers(self, node_id: str) -> List[SignalNode]:
        """获取信号的所有驱动源"""
        driver_ids = self._driver_index.get(node_id, [])
        return [self.nodes[did] for did in driver_ids if did in self.nodes]

    def get_loads(self, node_id: str) -> List[SignalNode]:
        """获取信号的所有负载（fan-out）"""
        return [self.nodes[e.dst] for e in self.edges
                if e.src == node_id and e.dst in self.nodes]

    # =================================================================
    # 图算法
    # =================================================================

    def fanin_cone(self, node_id: str, depth: int = -1) -> List[SignalNode]:
        """fan-in 锥（反向）"""
        if depth < 0:
            # 无限深度：收集所有祖先
            visited = set()
            queue = self.get_drivers(node_id)
            while queue:
                driver = queue.pop(0)
                if driver.id not in visited:
                    visited.add(driver.id)
                    queue.extend(self.get_drivers(driver.id))
            return [self.nodes[nid] for nid in visited if nid in self.nodes]
        else:
            # BFS 限制深度
            result = []
            visited = {node_id}
            queue = [(node_id, 0)]
            while queue:
                nid, d = queue.pop(0)
                if d >= depth:
                    continue
                for driver in self.get_drivers(nid):
                    if driver.id not in visited:
                        visited.add(driver.id)
                        result.append(driver)
                        queue.append((driver.id, d + 1))
            return result

    def fanout_cone(self, node_id: str, depth: int = -1) -> List[SignalNode]:
        """fan-out 锥（正向）"""
        if depth < 0:
            visited = set()
            queue = self.get_loads(node_id)
            while queue:
                load = queue.pop(0)
                if load.id not in visited:
                    visited.add(load.id)
                    queue.extend(self.get_loads(load.id))
            return [self.nodes[nid] for nid in visited if nid in self.nodes]
        else:
            result = []
            visited = {node_id}
            queue = [(node_id, 0)]
            while queue:
                nid, d = queue.pop(0)
                if d >= depth:
                    continue
                for load in self.get_loads(nid):
                    if load.id not in visited:
                        visited.add(load.id)
                        result.append(load)
                        queue.append((load.id, d + 1))
            return result

    def find_paths(self, src_id: str, dst_id: str, max_len: int = 10) -> List[List[str]]:
        """找所有路径（用于 paths 命令）"""
        paths = []
        visited = {src_id}
        stack = [(src_id, [src_id])]
        while stack:
            nid, path = stack.pop()
            if len(path) > max_len:
                continue
            if nid == dst_id:
                paths.append(path)
            for load in self.get_loads(nid):
                if load.id not in visited or len(path) < max_len:
                    visited.add(load.id)
                    stack.append((load.id, path + [load.id]))
        return paths

    # =================================================================
    # 网络视图（映射到 networkx）
    # =================================================================

    def to_networkx(self) -> nx.DiGraph:
        """将当前图映射到 networkx DiGraph（用于可视化）"""
        G = nx.DiGraph()
        for nid, node in self.nodes.items():
            G.add_node(nid,
                       kind=node.kind.value,
                       bit_width=node.bit_width,
                       is_register=node.is_register,
                       clock_domain=node.clock_domain,
                       **node.attrs)

        for edge in self.edges:
            G.add_edge(edge.src, edge.dst,
                       kind=edge.kind.value,
                       timing=edge.timing,
                       qualifier=edge.qualifier,
                       **edge.attrs)

        return G

    # =================================================================
    # sv_query 兼容
    # =================================================================

    def from_sv_query(self, sv_graph) -> 'SignalNetlistGraph':
        """
        从 sv_query SignalGraph 导入数据。
        用于共享 sv_query 已构建的图。
        """
        for node_name in sv_graph.nodes():
            node = SignalNode.from_sv_query_node(sv_graph.nodes[node_name])
            self.add_node(node)

        for src, dst in sv_graph.edges():
            edge = SignalEdge(
                src=src, dst=dst,
                kind=EdgeKind.DRIVES,
                timing=sv_graph.edges[src, dst].get('timing', 'unknown')
            )
            self.add_edge(edge)

        return self

    def to_sv_query_format(self) -> nx.DiGraph:
        """导出为 sv_query 兼容的 networkx 图"""
        return self.to_networkx()
```

---

## 4. Constraint Graph Schema（独立图）

```python
# graph/constraint_graph.py

class ConstraintKind(Enum):
    IMPLIES = "implies"           # 蕴含 valid -> data != 0
    INSIDE = "inside"            # 范围 inside {[1:100]}
    DIST = "dist"                # 分布 dist {0:=20, 1:=30}
    IF_ELSE = "if_else"           # 条件 if (cond) .. else ..
    CROSS = "cross"              # 交叉 cross {a * b}


@dataclass
class ConstraintNode:
    """constraint 图节点"""
    id: str                      # "class_name.prop_name" 或 "class_name.cb_name"
    name: str                    # "c_valid"
    kind: ConstraintKind          # 约束类型
    class_name: str              # 所属 class
    source_line: int             # 源码行号
    expression: str              # 原始表达式字符串
    related_signals: List[str]   # 涉及的信号 ["valid", "data"]


@dataclass
class ConstraintEdge:
    """constraint 图边"""
    src: str                     # 源节点（信号或约束块）
    dst: str                     # 目标节点（约束块或约束表达式）
    kind: ConstraintKind          # 关系类型
    antecedent: Optional[str]    # implication 前件（条件）
    consequent: Optional[str]    # implication 后件（结果）


@dataclass
class ConstraintGraph:
    """
    类约束关系图（独立于 SignalNetlistGraph）

    用于：
    - constraints 命令
    - gen-coverage 命令（值域边界）
    - assert 命令（约束推导）
    """
    nodes: Dict[str, ConstraintNode]
    edges: List[ConstraintEdge]
    class_name: str              # 所属 class

    def get_related_signals(self, signal: str) -> List[str]:
        """获取与 signal 有约束关系的信号"""
        result = []
        for node in self.nodes.values():
            if signal in node.related_signals:
                result.extend(node.related_signals)
        return list(set(result) - {signal})
```

---

## 5. 图种类汇总

| 图 | 用途 | 节点 | 边 |
|---|------|------|-----|
| **SignalNetlistGraph** | 14 个命令的核心 | Signal / Port / State / Assignment / Constant / Clock | DRIVES / CONNECTS / CONTROLS / DATA_FLOW |
| **ConstraintGraph** | constraints / gen-coverage | Signal（property）/ ConstraintBlock | IMPLIES / INSIDE / DIST / IF_ELSE / CROSS |

**结论**：只需要 **2 种图**，不是 18 种。

---

## 6. 与 sv_query 的统一方案

### 6.1 统一节点 Schema

```
sv_query 节点属性：
  networkx attr dict: {
    'kind': 'Variable',
    'width': (31, 0),
    'is_register': False,
    'module': 'top',
    'fullpath': 'top.data'
  }

navisv SignalNode 字段：
  id = fullpath
  name = fullpath.split('.')[-1]
  kind = NodeKind(kinds_map['Variable'])
  bit_width = width
  is_register = is_register
  module = module
  hierarchical_path = fullpath
```

**映射表**：

| sv_query attr | navisv field | 映射 |
|-------------|-------------|------|
| `'Variable'` | `kind = SIGNAL` | kinds_map |
| `'Port'` | `kind = PORT_INPUT/OUTPUT` | direction map |
| `'Register'` | `kind = STATE + is_register=True` | 组合 |
| `'fullpath'` | `id / hierarchical_path` | 直接 |
| `'width'` | `bit_width` | 直接 |
| `'module'` | `module` | 直接 |
| `'driver_type'` | `driver_type` | 直接 |

### 6.2 统一边 Schema

| sv_query edge attr | navisv field | 映射 |
|------------------|-------------|------|
| `'type'` = `'drives'` | `kind = DRIVES` | kinds_map |
| `'type'` = `'connects'` | `kind = CONNECTS` | 直接 |
| `'timing'` | `timing` | 直接 |
| `'condition'` | `qualifier` | 直接 |

### 6.3 转换函数

```python
# graph/unified_converter.py

class UnifiedConverter:
    """sv_query ↔ navisv 图 schema 互转"""

    KINDS_MAP_SVQUERY_TO_NAVISV = {
        'Variable': NodeKind.SIGNAL,
        'Port': NodeKind.PORT_INPUT,
        'Register': NodeKind.STATE,
        'Signal': NodeKind.SIGNAL,
        'Net': NodeKind.SIGNAL,
    }

    EDGE_KINDS_MAP = {
        'drives': EdgeKind.DRIVES,
        'connects': EdgeKind.CONNECTS,
        'controls': EdgeKind.CONTROLS,
        'dataflow': EdgeKind.DATA_FLOW,
    }

    # ---- sv_query → navisv ----

    def from_sv_query(self, sv_graph: nx.DiGraph) -> SignalNetlistGraph:
        """将 sv_query SignalGraph 转换为 navisv SignalNetlistGraph"""
        graph = SignalNetlistGraph()

        for node_name in sv_graph.nodes():
            attrs = sv_graph.nodes[node_name]
            node = SignalNode(
                id=node_name,
                name=node_name.split('.')[-1],
                kind=self.KINDS_MAP_SVQUERY_TO_NAVISV.get(
                    attrs.get('kind', 'Signal'), NodeKind.SIGNAL),
                bit_width=attrs.get('width'),
                is_register=attrs.get('is_register', False),
                module=attrs.get('module', ''),
                hierarchical_path=node_name,
                attrs=dict(attrs)
            )
            graph.add_node(node)

        for src, dst in sv_graph.edges():
            edge_attrs = sv_graph.edges[src, dst]
            edge = SignalEdge(
                src=src,
                dst=dst,
                kind=self.EDGE_KINDS_MAP.get(edge_attrs.get('type', 'drives'),
                       EdgeKind.DRIVES),
                timing=edge_attrs.get('timing', 'unknown'),
                attrs=dict(edge_attrs)
            )
            graph.add_edge(edge)

        return graph

    # ---- navisv → sv_query ----

    def to_sv_query(self, graph: SignalNetlistGraph) -> nx.DiGraph:
        """将 navisv SignalNetlistGraph 导出为 sv_query 格式"""
        return graph.to_sv_query_format()
```

---

## 7. 实际数据流

```
[SV 源码]
    │
    ├─── slang-netlist ─────────────────────────────┐
    │      NetlistGraph + getDrivers                │
    │      → SignalNetlistGraph (navisv 格式)       │
    │      → ConstraintGraph (navisv 格式)        │
    │                                             │
    └─── sv_query (已有图) ────────────────────────┘
           SignalGraph (networkx)
           → UnifiedConverter.from_sv_query()
           → SignalNetlistGraph (navisv 格式)
```

**关键**：两个来源最终都输出到 `SignalNetlistGraph`，统一存储，统一查询。

---

## 8. 架构决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 图种类 | 2 种（SignalNetlistGraph + ConstraintGraph） | 需求分析：14+3+1 个命令只需这两种 |
| 节点 schema | SignalNode dataclass | 结构化，有类型，比 dict 安全 |
| 边 schema | SignalEdge dataclass | 同上 |
| storage | slang-netlist NetlistGraph（主）+ networkx（视图） | 铁律1不变，sl 提供精确 driver |
| sv_query 兼容 | UnifiedConverter | 按需转换，不强耦合 |
| ConstraintGraph | 独立图 | class 内部专用，非全局 |

---

*文档版本：v0.1*  
*下一步：确认后开始实现 SignalNetlistGraph + UnifiedConverter*