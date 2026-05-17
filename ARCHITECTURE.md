# navisv 架构设计文档

**版本**：v0.8
**日期**：2026-05-17
**状态**：正式版（职责分离闭环）

---

## 一、背景与问题

### 1.1 核心问题

AI Agent 在调试 SystemVerilog 设计时，不缺数据（波形、源码、网表），缺的是导航能力：
- 如何快速理解一个信号的全貌？
- 如何判断修改某个信号的影响范围？
- 如何发现信号间的隐含关系？

现有工具（slang-netlist、sv_query）输出了精确的底层关系，但没有提供面向调试场景的语义抽象与自然语言回答。

**navisv 的目标**：将低层网表关系转化为面向调试场景的结构化答案，让 AI Agent 能直接提问并沿着明确的路径高效探索。

### 1.2 设计原则（铁律）

1. **slang-netlist 唯一数据源** — 不重建底层 driver/load 关系，C++ 层的拓扑结果具有最高优先级。
2. **networkx 是唯一查询接口** — 所有查询都通过对 networkx.DiGraph 的 API 完成，不维护独立的自定义索引字典，避免同步问题。
3. **标签不互斥，用集合而非枚举** — 信号属性用可叠加的 `tags: set[str]` 表示，避免分类边界难题。
4. **只翻译，不判断** — navisv 负责将数据组织为可理解的形式，不做设计正确性裁定；置信度低时明确告知，不强行回答。
5. **为 Agent 设计输出** — 所有对外接口返回结构化数据 + 自然语言摘要，优先服务 AI Agent 的消费需求。

---

## 二、分层架构

```
User / AI Agent
     ↓
App Layer          ← 场景应用：组合多个原子查询，生成自然语言答案
     ↓
Query Layer        ← 原子查询：操作 DiGraph，返回结构化数据
     ↓
Graph Layer        ← 数据持有：networkx DiGraph 是唯一存储，构建一次
     ↓
slang-netlist      ← 唯一数据来源：精确 driver/load / 路径追踪
```

**关键约束**：
- 层间单向依赖，上层不可绕过下层直接访问底层数据结构
- **App Layer 禁止直接调用 DesignGraph 的任何方法**，只能通过 QueryService 的原子查询接口获取结构化数据
- DesignGraph 不提供 `self.graph` 的公开访问，只能通过最小接口交互

---

## 三、Graph Layer

### 3.1 DesignGraph（核心类）

`DesignGraph` 持有 networkx.DiGraph，是系统**唯一的数据存储**。

```python
class DesignGraph:
    """
    持有 networkx DiGraph，是 navisv 的唯一数据存储。
    
    构建流程：
    1. 从 slang-netlist 添加节点，附加 SignalNode 属性
    2. 调用 slang AnalysisManager.getDrivers() 创建所有边，标记 source="slang"
    3. StatementExplorer 遍历，补充边的 timing/qualifier/source_location（不创建新边）
    4. ClassExplorer 补充 class 内 method 调用边
    """
    
    def __init__(self, sv_files: List[str], enable_annotators: bool = True):
        self.graph = nx.DiGraph()  # ★ 唯一存储
        self._sv_files = sv_files
        self._build()
    
    # ---- 最小公开接口（仅供 Query Layer 调用）----
    
    def nodes(self) -> List[str]:
        """返回所有节点 ID"""
        return list(self.graph.nodes)
    
    def edges(self) -> List[Tuple[str, str]]:
        """返回所有边的 (src, dst) 元组"""
        return list(self.graph.edges)
    
    def predecessors(self, node_id: str) -> List[str]:
        """返回驱动这个节点的所有源节点"""
        return list(self.graph.predecessors(node_id))
    
    def successors(self, node_id: str) -> List[str]:
        """返回这个节点驱动的所有目标节点"""
        return list(self.graph.successors(node_id))
    
    def edge_attr(self, src: str, dst: str) -> dict:
        """返回边的属性字典"""
        return dict(self.graph.edges[src, dst])
    
    def node_attr(self, node_id: str) -> dict:
        """返回节点的属性字典"""
        return dict(self.graph.nodes[node_id])
    
    def subgraph(self, nodes: List[str]) -> 'nx.DiGraph':
        """返回指定节点的子图（内部用于算法）"""
        return self.graph.subgraph(nodes)
```

**封装约束**：
- `self.graph` 是内部属性，不公开访问
- 所有查询必须通过上述最小接口
- `subgraph()` 是 Query Layer 内部算法使用，不暴露给 App Layer

### 3.2 构建流程

```python
def _build(self):
    # 1. 从 slang-netlist 添加节点
    self._add_nodes_from_slang()
    
    # 2. slang getDrivers() 创建边（拓扑权威）
    self._add_edges_from_slang()
    
    # 3. StatementExplorer 注释边（不创建新边）
    self._annotate_edges_from_statements()
    
    # 4. ClassExplorer 补充 class 边
    self._add_method_edges()
    
    # 5. 可选标注（annotators）
    if self._enable_annotators:
        self._load_annotators()
```

### 3.3 StatementExplorer（边注释者）

```python
class StatementExplorer:
    """
    遍历 always/assign 语句，为已存在的边补充 timing/qualifier/location。
    不创建新边，边已由 slang getDrivers() 创建。
    """
    
    def annotate(self, graph: DesignGraph):
        """
        遍历 procedural block，更新已有边的属性。
        返回 (src, dst, timing, qualifier, location) 元组。
        """
        # 遍历 always_ff / always_comb / assign
        # 对每个赋值语句，提取 timing（blocking/non_blocking/continuous）
        # 检查 graph 是否有 (src, dst) 边
        # 如果有，更新 timing/qualifier/source_location
```

**角色约束**（铁律）：StatementExplorer 不调用 `graph.add_edge()`，只更新已有边的属性。

### 3.4 ClassExplorer（Python 层边补充）

```python
class ClassExplorer:
    """
    补充 class 内 method 驱动关系。
    slang 不处理 class，这是唯一在 Python 层创建边的场景。
    """
    
    def merge_method_edges(self, graph: DesignGraph):
        """
        合并 class method 边。
        - 如果边已存在（source="slang"）：只补充 Python 独有的字段
        - 如果边不存在：创建新边，标记 source="python"
        """
        for src, dst, info in self._extract_method_drives():
            if graph.has_edge(src, dst):
                existing = graph.edges[src, dst]
                if existing.get("source") == "slang":
                    # slang 拓扑优先，只补充 source_location
                    if not existing.get("source_location") and info.get("source_location"):
                        existing["source_location"] = info["source_location"]
                    if existing.get("relation") == "drives" and info.get("relation") == "calls":
                        existing.setdefault("meta", {})["python_relation"] = "calls"
            else:
                # 新边，slang 不知道
                graph.add_edge(src, dst, **info, source="python", confidence="medium")
```

---

## 四、Query Layer

### 4.1 职责

提供**原子查询**，每个方法做一件事，返回**纯结构化数据**，不组合多个查询，不生成自然语言。

### 4.2 接口定义

```python
class QueryService:
    """
    原子查询接口。
    所有方法返回纯结构化数据（list / dict），不包含 summary。
    App 层负责生成自然语言摘要。
    """
    
    def __init__(self, graph: DesignGraph):
        self._graph = graph  # 不暴露给 App
    
    def get_drivers(self, signal: str) -> List[DriverInfo]:
        """返回驱动这个信号的所有源"""
        return [DriverInfo(id=src, **self._graph.edge_attr(src, signal))
                for src in self._graph.predecessors(signal)]
    
    def get_loads(self, signal: str) -> List[LoadInfo]:
        """返回这个信号驱动的所有目标"""
        return [LoadInfo(id=dst, **self._graph.edge_attr(signal, dst))
                for dst in self._graph.successors(signal)]
    
    def find_path(self, src: str, dst: str) -> List[str]:
        """
        返回从 src 到 dst 的节点路径列表（包含 src 和 dst）。
        如果无路径，返回空列表。
        """
        try:
            pf = nl.PathFinder(self._graph.graph)
            result = pf.find(src, dst)
            if result and not result.empty():
                return list(result)
        except Exception:
            pass
        try:
            return nx.shortest_path(self._graph.graph, src, dst)
        except nx.NetworkXNoPath:
            return []
    
    def fanin_cone(self, signal: str, max_depth: int = 5) -> List[str]:
        """BFS 向上追踪，最多 max_depth 层"""
        visited = set()
        queue = [(signal, 0)]
        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for pred in self._graph.predecessors(curr):
                if pred not in visited:
                    visited.add(pred)
                    queue.append((pred, depth + 1))
        return list(visited)
    
    def fanout_cone(self, signal: str, max_depth: int = 5) -> List[str]:
        """BFS 向下追踪，最多 max_depth 层"""
        visited = set()
        queue = [(signal, 0)]
        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for succ in self._graph.successors(curr):
                if succ not in visited:
                    visited.add(succ)
                    queue.append((succ, depth + 1))
        return list(visited)
    
    def scc_analysis(self) -> List[List[str]]:
        """返回所有强连通分量"""
        return list(nx.strongly_connected_components(self._graph.graph))
    
    def search_signals(self, name_pattern: str = "", tags: List[str] = None) -> List[str]:
        """按名称模式或 tags 搜索信号"""
        results = []
        for node_id in self._graph.nodes():
            attr = self._graph.node_attr(node_id)
            if name_pattern and name_pattern.lower() not in attr.get("name", "").lower():
                continue
            if tags and not any(t in attr.get("tags", set()) for t in tags):
                continue
            results.append(node_id)
        return results
```

### 4.3 性能策略

- **Phase 1 不加缓存**：`get_drivers()` 直接调用 `graph.predecessors()`
- **Phase 2**：根据 profiling 决定是否添加内部索引，但索引仍通过 networkx 数据结构实现，不建外部字典

### 4.4 数据模型

```python
@dataclass
class DriverInfo:
    id: str
    relation: str = "drives"
    timing: str = "unknown"
    qualifier: Optional[str] = None
    bounds: Optional[Tuple[int, int]] = None
    source_location: Optional[str] = None
    source: str = "slang"
    is_partial: bool = False
    confidence: str = "high"

@dataclass
class LoadInfo:
    id: str
    relation: str = "drives"
    timing: str = "unknown"
    qualifier: Optional[str] = None
    bounds: Optional[Tuple[int, int]] = None
    source_location: Optional[str] = None
    source: str = "slang"
    is_partial: bool = False
    confidence: str = "high"
```

---

## 五、App Layer

### 5.1 职责

**场景应用**：组合 Query Layer 的原子查询，组装成完整的场景答案，并生成自然语言摘要。

### 5.2 核心约束

- App Layer **禁止直接调用 DesignGraph** 的任何方法，只能通过 QueryService 的原子查询接口获取数据
- App Layer 是**唯一生成自然语言摘要**的层
- Query Layer 返回纯结构化数据，App 负责生成 `summary`

### 5.3 AppResponse

```python
@dataclass
class AppResponse:
    structured: Any         # 结构化数据
    summary: str            # 自然语言摘要，始终非空
    confidence: str         # "high" | "medium" | "uncertain"
    experimental: bool      # 实验性标记（默认 False）
```

### 5.4 首批 App 清单

| App | 场景 | 输入 | 组合的原子查询 |
|-----|------|------|---------------|
| SignalProfileApp | "这个信号到底是怎么回事？" | 信号路径 | get_drivers, get_loads, fanin_cone, 时钟域/复位标注 |
| ImpactAnalysisApp | "改了它会怎样？" | 信号路径 | fanout_cone, 跨模块过滤, 组合环路检测 |
| RelationshipApp | "A 和 B 有什么关系？" | 两个信号路径 | find_path, 共同源/负载分析 |
| FindSignalsApp | "和时钟门控相关的信号有哪些？" | 模糊描述 | search_signals |
| SampleConditionApp | "什么时候采样这个信号？" | 信号路径 | get_drivers, 门控条件提取 |
| FsmDetectApp (实验性) | "这个模块里有哪些状态机？" | 模块范围 | scc_analysis + 状态寄存器 pattern |
| ProtocolInferApp (实验性) | "这些信号是不是握手协议？" | 信号列表 | 结构相似度 + 协议模板匹配 |

### 5.5 实现示例

```python
class SignalProfileApp:
    def __init__(self, query: QueryService):
        self.query = query
    
    def run(self, signal: str) -> AppResponse:
        drivers = self.query.get_drivers(signal)
        loads = self.query.get_loads(signal)
        fanin = self.query.fanin_cone(signal, max_depth=3)
        fanout = self.query.fanout_cone(signal, max_depth=3)
        
        summary = (
            f"信号 {signal} 由 {len(drivers)} 个源驱动，"
            f"连接到 {len(loads)} 个负载。"
            f"上游涉及 {len(fanin)} 个信号，下游涉及 {len(fanout)} 个信号。"
        )
        
        return AppResponse(
            structured={
                "signal": signal,
                "drivers": [asdict(d) for d in drivers],
                "loads": [asdict(l) for l in loads],
                "fanin": fanin,
                "fanout": fanout,
            },
            summary=summary,
            confidence="high"
        )
```

### 5.6 扩展性

- 新增场景只需添加新的 App 类，不改动下层
- AI Agent 可绕过 App Layer 直接使用 Query Layer 进行自主分析
- AI Agent 也可直接组合多个 Query 调用进行自主探索

---

## 六、算法来源

| 能力 | 实现方式 | 所在层 |
|------|----------|--------|
| 精确 driver/load | slang AnalysisManager | Graph（构建时）|
| 路径追踪 | slang PathFinder | Query（find_path 内部）|
| 图遍历（fanin/fanout）| networkx BFS | Query |
| SCC 检测 | networkx | Query |
| 自然语言摘要 | App 内部模板 | App |
| 时钟域/复位标注 | 启发式 + tags | App 或 Annotator |

**原则**：slang 有的用 slang，slang 没有的用 networkx，两者都没有的用 Python 实现（标记来源 "python"）。

---

## 七、目录结构

```
navisv/
├── graph/
│   ├── design_graph.py       ★ 核心：DesignGraph（唯一存储）
│   ├── statement_explorer.py  # 边属性注释（不创建边）
│   ├── class_explorer.py      # class 边补充
│   └── schema.py               # SignalNode / SignalEdge / DriverInfo / LoadInfo
│
├── query/
│   ├── service.py             # QueryService（原子查询）
│   └── models.py              # DriverInfo / LoadInfo
│
├── apps/
│   ├── base.py                # BaseApp + AppResponse
│   ├── signal_profile.py       # 信号身份证
│   ├── impact_analysis.py      # 修改影响分析
│   ├── relationship.py         # 信号关系分析
│   ├── find_signals.py         # 模糊信号查找
│   ├── sample_condition.py     # 采样条件推理
│   ├── fsm_detect.py           # FSM 检测（实验性）
│   └── protocol_infer.py       # 协议推断（实验性）
│
├── annotators/                # 可选标注（按需加载）
│   ├── clock_domain.py
│   └── reset_detector.py
│
├── examples/
│   ├── signal_profile_demo.py
│   ├── impact_analysis_demo.py
│   └── agent_integration.py
│
├── tests/
│   ├── test_graph.py
│   ├── test_query.py
│   └── test_apps/
│
└── docs/
    └── ARCHITECTURE.md
```

---

## 八、架构决策记录

| ID | 决策 | 理由 | 版本 |
|----|------|------|------|
| D1 | slang-netlist 唯一数据源 | 避免重建 driver/load，保证精度 | v0.4 |
| D2 | networkx 唯一查询接口，不维护独立索引 | 消除同步负担，简化代码 | v0.7 |
| D3 | 标签 tags 替代枚举分类 | 避免边界分类错误，可叠加 | v0.7 |
| D4 | 边关系用 relation 字符串，仅三种值 | 减少下游分支判断 | v0.7 |
| D5 | StatementExplorer 只注释边，不创建边 | 拓扑权威来源唯一 | v0.7 |
| D6 | ClassExplorer 补充边时 slang 优先 | 保持底层精度 | v0.7 |
| D7 | App Layer 处理场景编排与自然语言生成 | 职责分离，Query 保持原子性 | v0.8 |
| D8 | Phase 1 不加驱动索引缓存 | 避免过早优化 | v0.7 |
| D9 | App Layer 禁止直接调用 DesignGraph | 单向依赖，封装保护 | v0.8 |
| D10 | find_path 返回 list[str]，不含边属性 | Query Layer 保持简单 | v0.8 |

---

## 九、待讨论 / 风险

1. **自然语言摘要质量**：App Layer 使用模板生成，需持续打磨避免机械感。计划在 examples/agent_integration.py 中与真实 LLM 联调验证。
2. **模糊查找精度**：FindSignalsApp 当前依赖命名模式 + tags，未来可集成 LLM 解析自然语言描述。
3. **实验性 App 边界**：FsmDetectApp / ProtocolInferApp 输出带 `experimental=True`，需在文档中明确局限性。
4. **大规模设计性能**：OpenTitan 级别设计的 `fanout_cone(..., max_depth=10)` 可能引入性能压力，Phase 2 结合 profiling 决定截断与缓存策略。

---

## 十、版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v0.4 | 2026-05-17 | 初始设计，核心架构 |
| v0.6 | 2026-05-17 | 细化 RHS 提取、networkx 视图分离、driver_index 合并 |
| v0.7 | 2026-05-17 | 砍掉枚举分类，networkx 成为唯一存储，引入 Query Layer 原子查询 |
| v0.7.1 | 2026-05-17 | 三个澄清点落地（铁律2表述、性能假设、ClassExplorer合并逻辑）|
| v0.8 | 2026-05-17 | 新增 App Layer，职责分离闭环；明确 find_path 返回值；禁止 App 直接调用 DesignGraph |

---

*架构版本：v0.8*
*日期：2026-05-17*
*状态：正式版*
*下一步：OpenTitan I2C 模块原型验证（DesignGraph + SignalProfileApp）*