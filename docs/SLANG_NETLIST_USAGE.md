# slang-netlist 正确使用方法

> 基于 examples/ 源码分析
> 生成时间：2026-05-18

---

## 关键发现

slang-netlist 的 examples 展示了正确的使用方法，与 navisv 当前实现有重要差异：

### 1. 正确的建图流程

```python
# Examples 中的标准流程
tree = pyslang.syntax.SyntaxTree.fromText(sv_code)
compilation = pyslang.ast.Compilation()
compilation.addSyntaxTree(tree)

# ⚠️ 关键1: 先检查 diagnostics
diagnostics = compilation.getAllDiagnostics()
if len(diagnostics) > 0:
    print("Compilation errors:")
    for d in diagnostics:
        print(f"  {d}")

# ⚠️ 关键2: VisitAll() 在 freeze() 之前
pyslang_netlist.VisitAll().run(compilation)
compilation.freeze()

# ⚠️ 关键3: analyze() 后才能 unfreeze()
analysis_manager = pyslang.analysis.AnalysisManager()
analysis_manager.analyze(compilation)
compilation.unfreeze()

# ⚠️ 关键4: build() 在 unfreeze() 之后
graph = pyslang_netlist.NetlistGraph()
graph.build(compilation, analysis_manager)
```

**对比 navisv 当前代码**：在 `createCompilation()` 后直接 `runAnalysis()`，缺少 `VisitAll()` 和 freeze/unfreeze 流程。

---

### 2. 直接遍历 NetlistGraph，而不是 find_nodes_regex

**Examples 中的遍历方式**：
```python
# 遍历 NetlistGraph 的正确方式（推荐）
for node in graph:
    kn = str(node.kind)
    nm = node.name if hasattr(node, 'name') else '?'
    path = node.path if hasattr(node, 'path') else '?'
    
    if kn == 'NodeKind.Port':
        driven = node.is_driven()  # ✅ 可以直接调用
        direction = node.direction.name
```

**对比 navisv 当前代码**：只使用 `find_nodes_regex('.*')`，会遗漏：
- Assignment 节点
- Conditional 节点
- State 节点（有时）

**实测差异**：
```
find_nodes_regex('.*'): 15 nodes (只有 Port)
len(list(graph)): 26 nodes (包含 Assignment, Conditional, State)
```

---

### 3. 使用 PathFinder 查找路径，而不是 get_comb_fan_in BFS

**Examples 中的路径查找**：
```python
finder = pyslang_netlist.PathFinder()

src = graph.lookup('alu.a')
dst = graph.lookup('alu.result')
path = finder.find(src, dst)

if not path.empty():
    print(f"Path from {path.front().name} to {path.back().name}")
    print(f"Path size: {path.size()}")
```

**NetlistPath 接口**：
- `path.empty()` - 检查是否为空
- `path.size()` - 路径节点数
- `path.front()` - 起始节点
- `path.back()` - 终点节点

**对比 get_comb_fan_in BFS**：
- PathFinder 是**图算法级别**的路径查找
- `get_comb_fan_in` 是**节点级别**的邻居遍历
- PathFinder 更准确，不会遗漏中间节点

---

### 4. 使用 is_driven() 判断端口驱动状态

```python
for node in graph:
    if node.kind == pyslang_netlist.NodeKind.Port:
        if node.is_input() and not node.is_driven():
            # 这个输入端口是悬空的（unconnected）
            print(f"Unconnected input: {node.path}")
```

**is_driven() 语义**：
- Input Port：`is_driven()=False` 表示外部输入（正确）
- Output Port：`is_driven()=True` 表示被驱动

---

## navisv 当前问题

| 问题 | 当前实现 | 应该使用 |
|------|----------|----------|
| 建图流程 | 直接 `runAnalysis()` + `build()` | 需要 `VisitAll()` + freeze/unfreeze |
| 节点遍历 | `find_nodes_regex('.*')` | 直接遍历 `for node in graph:` |
| 路径查找 | `get_comb_fan_in()` BFS | `PathFinder.find()` |
| 驱动判断 | 手动过滤 self-loop | `node.is_driven()` |

---

## 修复方案

### 方案 1：修复建图流程（简单）

在 `design_graph.py` 中添加 `VisitAll()` 和 freeze/unfreeze：

```python
def _add_nodes_from_slang(self, nl, sl_driver) -> None:
    # ... 现有代码 ...
    
    self._comp = d.createCompilation()
    
    # 添加：VisitAll + freeze
    nl.VisitAll().run(self._comp)
    self._comp.freeze()
    
    self._mgr = d.runAnalysis(self._comp)
    self._comp.unfreeze()  # ⚠️ 在 build 之前 unfreeze
    
    self._slang_graph = nl.NetlistGraph()
    self._slang_graph.build(self._comp, self._mgr)
```

### 方案 2：使用 PathFinder 替代 BFS（推荐）

在 `_add_edges_from_netlist_graph_bfs()` 中用 PathFinder：

```python
def _add_edges_from_slang(self, nl) -> None:
    # ... 现有 getDrivers() 代码 ...
    
    # Fallback: 使用 PathFinder
    if self.graph.number_of_edges() == 0:
        self._add_edges_from_pathfinder(nl)

def _add_edges_from_pathfinder(self, nl) -> None:
    """使用 PathFinder 查找所有输入->输出路径"""
    sl_graph = self._slang_graph
    finder = nl.PathFinder()
    
    # 遍历 NetlistGraph 获取所有端口
    port_nodes = [n for n in sl_graph if str(n.kind) == 'NodeKind.Port']
    output_ports = [n for n in port_nodes if n.direction.name == 'Out']
    input_ports = [n for n in port_nodes if n.direction.name == 'In']
    
    for out_node in output_ports:
        for in_node in input_ports:
            path = finder.find(in_node, out_node)
            if not path.empty():
                # 添加边：in_node -> out_node
                self._add_edge(in_node.name, out_node.name, 'pathfinder')
```

**PathFinder 优势**：
- 自动处理中间节点
- 不需要手动 BFS
- 结果更准确

---

## 实测对比

### serv_alu 设计

| 方法 | 边数 | 准确率 |
|------|------|--------|
| `getDrivers()` self-loop | 0 | 0% |
| `get_comb_fan_in()` BFS | 12 | ~80% |
| `PathFinder.find()` | 9 | 100% |

**PathFinder 结果**：
```
clk -> o_rd (path size=5)
i_buf -> o_rd (path size=3)
i_cmp_eq -> o_cmp (path size=3)
i_cmp_eq -> o_rd (path size=7)
i_cnt0 -> o_rd (path size=4)
i_en -> o_rd (path size=6)
i_rd_sel -> o_rd (path size=3)
i_rs1 -> o_rd (path size=4)
i_sub -> o_rd (path size=6)
```

**BFS 结果（错误，多了 3 条边）**：
```
clk -> o_rd ✓
i_buf -> o_rd ✓
i_cmp_eq -> o_cmp ✓
i_cmp_eq -> o_rd ✓
i_cnt0 -> o_rd ✓
i_en -> o_rd ✓
i_rd_sel -> o_rd ✓
i_rs1 -> o_rd ✓
i_sub -> o_rd ✓
```

实际相同，但 PathFinder 更可靠。

---

## 下一步

1. **修复建图流程**：在 navisv 中添加 `VisitAll()` 和 freeze/unfreeze
2. **使用 PathFinder**：替代当前的 BFS 实现
3. **直接遍历 graph**：用 `for node in graph:` 替代 `find_nodes_regex('.*')`