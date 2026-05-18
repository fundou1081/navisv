# slang-netlist 使用指南

本指南基于 Windows 本地构建的实测文档，帮助使用者快速上手 slang-netlist 库，用于对 SystemVerilog 设计进行数据流分析和结构性检查。

---

## 1. 环境设置

### Python 路径配置

构建产物位于 `build/win-release/...`，在编写脚本时，需要在开头添加 Python 路径，并引入所需模块。

```python
import sys
sys.path.insert(0, 'D:/Project_DV_2026/slang-netlist/build/win-release/_deps/slang-build/lib/')
sys.path.insert(0, 'D:/Project_DV_2026/slang-netlist/build/win-release/bindings/python/')

import pyslang
import pyslang_netlist
```

⚠️ **特别注意：** 必须使用 CPython 3.11（如 `D:/Programs/Python/Python311/python.exe`），不能使用 Conda base 的 PyPy 或其他版本。

---

## 2. 核心概念

slang-netlist 将 SystemVerilog 设计解析为一个有向依赖图 (Directed Graph)。图中的节点包含两种含义：

### 图的"切割点" (Named Nodes, 可被 lookup)

这些节点是图界的边界，路径分析在这里终止或穿过：

- **Port**: 模块端口（含子模块端口）
- **State**: always_ff 中非阻塞赋值的目标变量（寄存器/FF），可作为路径分析的目标。

**重要设计原则：**
纯组合逻辑中间信号（如 `wire w = a & b;` 中的 `w`）在图中没有独立命名节点。它们在图里面是"透明"的，路径会穿过它们，但无法直接用 `lookup("mod.w")` 查找到。

### 图的"操作节点" (Anonymous Nodes, 不可直接 lookup)

这些节点表示逻辑操作，存在于路径中但没有名字：

- **Assignment**: assign 语句、阻塞赋值。
- **Conditional**: if/else 语句。
- **Case**: case 语句。
- **Merge**: 多条件合并点。
- **Constant**: 常量驱动源。

---

## 3. 构建 Netlist 的标准流程

以下是标准流程代码（将源代码字符流转化为网表图对象）：

```python
def build_netlist(sv_source: str) -> pyslang_netlist.NetlistGraph:
    # Step 1: 解析语法树
    tree = pyslang.syntax.SyntaxTree.from_text(sv_source)
    # 也可以从文件加载：tree = pyslang.syntax.SyntaxTree.from_file("design.sv")

    # Step 2: 编译（语义分析）
    comp = pyslang.ast.Compilation()
    comp.addSyntaxTree(tree)

    # Step 3: 激发 elaboration（新版 slang 必须调用，否则无法分析）
    comp.getSemanticDiagnostics()

    # Step 4: 强制冻结 AST (为多线程安全)
    pyslang_netlist.visitAll().run(comp)

    # Step 5: 冻结编译，运行数据流分析
    comp.freeze()
    am = pyslang.analysis.AnalysisManager()
    am.analyze(comp)

    # Step 6: 解冻 (netlist builder 需要继续 elaborate AST)
    comp.unfreeze()

    # Step 7: 构建 netlist 图
    graph = pyslang_netlist.NetlistGraph()
    graph.build(comp, am)

    return graph
```

---

## 4. 节点类型参考

### 节点查找方法

```python
# 1. 按层次路径精准查找 (返回 None 如果不存在)
node = graph.lookup("top.sub.signal_name")

# 2. 按路径 + 位置范围查找 (返回列表，用于切片信号)
nodes = graph.lookup_by_range("top.bus_signal", lower=0, upper=3)

# 3. 通配符搜索 (支持 * 和 ?)
nodes = graph.find_nodes("top.stage1.*")

# 4. 正则表达式搜索
nodes = graph.find_nodes_regex(r"top\.s1_.*")

# 5. 遍历所有节点
for node in graph:
    kind = node.kind
    print(node.ID, kind)
```

### 判断节点类型与属性

通过 `node.kind` 与 `pyslang_netlist.NodeKind` 枚举进行比较：

```python
NodeKind = pyslang_netlist.NodeKind

if node.kind == NodeKind.Port:
    pass  # 处理端口
elif node.kind == NodeKind.State:
    pass  # 处理寄存器/FF
elif node.kind == NodeKind.Assignment:
    pass  # assign 或阻塞赋值操作
elif node.kind == NodeKind.Case:
    pass  # case 语句
elif node.kind == NodeKind.Conditional:
    pass  # if/else 语句
```

---

## 5. 路径查找 API

### 全路径查找 `find(src, dst)` (可穿过 FF)

```python
finder = pyslang_netlist.PathFinder()
src = graph.lookup("top.i_data")
dst = graph.lookup("top.o_result")
path = finder.find(src, dst)

if not path.empty():
    print(f"路径存在，共 {path.size()} 步")
    # path.front() / path.back() / path[i] 获取节点
else:
    print("不存在路径")
```

**特点：** 可以穿过 State 节点（寄存器），适合分析多周期的时序路径（如 RTL 级时序分析）。

### 纯组合路径查找 `find_comb(src, dst)` (遇 FF 停止)

```python
path = finder.find_comb(src, dst)
```

**特点：** 遇到 State 节点（FF）立即停止，不穿过。适合分析组合逻辑时序路径，检查 comb loop。目标节点不能是 State 节点（必须落在 FF 之前）。

---

## 6. 驱动关系分析 API

### `get_drivers()` —— 直接驱动节点

获取驱动 signal 位置的节点列表。返回的是直接赋值节点（通常是 Assignment 操作节点）。

```python
drivers = graph.get_drivers("top.out_port", lower=0, upper=3)
for d in drivers:
    print(f"驱动节点: {getattr(d, 'path', '')}")
```

### `get_comb_fan_in()` —— 组合扇入（逆向追踪）

向上游追踪组合逻辑的所有源节点（State 或 Port），遇到 State 停止。

```python
node = graph.lookup("top.q")  # 可以是 State 或 Port
fan_in = graph.get_comb_fan_in(node)  # 返回所有驱动该节点的路径尾节点
named = [n for n in fan_in if hasattr(n, 'path') and n.path]
for n in named:
    print(f"{n.path}")
```

**分析 FF 的完整驱动来源时，注意 FF 的下一级通常是 State 节点本身。**

### `get_comb_fan_out()` —— 组合扇出（正向追踪）

向下游追踪组合逻辑的所有受影响的节点。遇到 State 节点停止。

```python
fan_out = graph.get_comb_fan_out(node)
named = [n for n in fan_out if hasattr(n, 'path') and n.path]
for n in named:
    print(n.path)
```

---

## 7. 节点搜索 API

```python
# 获取所有有名节点 (Port + State)
all_named = graph.find_nodes("*")

# 通配符搜索
s1_nodes = graph.find_nodes("top.s1.*")

# 正则表达式
ff_nodes = graph.find_nodes_regex(r"top\.s[0-9]+_ff_*")

# 遍历统计
ports = [n for n in graph if n.kind == NodeKind.Port]
states = [n for n in graph if n.kind == NodeKind.State]
print(f"总节点数: {graph.num_nodes()}, 总边数: {graph.num_edges()}")
```

---

## 8. 完整使用示例

### 示例 A: 检查两点之间是否存在路径

```python
def check_connectivity(graph, src_name, dst_name, comb_only=False):
    finder = pyslang_netlist.PathFinder()
    src = graph.lookup(src_name)
    dst = graph.lookup(dst_name)
    if not src or not dst:
        raise ValueError("节点不存在")
    path = finder.find_comb(src, dst) if comb_only else finder.find(src, dst)
    return not path.empty()
```

### 示例 B: 枚举所有寄存器及其驱动

```python
def analyze_all_ffs(graph):
    finder = pyslang_netlist.PathFinder()

    # 收集所有 primary_inputs (顶层输入端口，排除 clk/rst)
    primary_inputs = {
        n for n in graph
        if n.kind == NodeKind.Port and n.is_input()
        and 'clk' not in n.path and 'rst' not in n.path
    }

    results = []
    for state in sorted(graph.find_nodes("*"), key=lambda n: n.path):
        if state.kind != NodeKind.State:
            continue

        fan_in = graph.get_comb_fan_in(state)
        named = [n for n in fan_in
                 if hasattr(n, 'path') and n.path and n.path != state.path]

        # 提取具体驱动类型
        seq_src = [n.path for n in named if n.kind == NodeKind.State]  # 直接驱动：来自 Stage-N 的 FF
        comb_src = [n.path for n in named
                    if n.kind == NodeKind.Port and 'clk' not in n.path]  # 组合驱动：来自输入端口

        # 检查是否能到达 primary input
        pi_reach = [n.path for n in primary_inputs
                    if not finder.find(n, state).empty()]

        results.append({
            'ff': state.path,
            'bits': f"[{state.bounds.lower}:{state.bounds.upper}]",
            'seq_src': seq_src,
            'comb_src': comb_src,
            'pi_reach': pi_reach,
        })

    return results
```

### 示例 C: 检测未连接/无驱动的输出端口

```python
def find_undriven_outputs(graph):
    undriven = []
    for node in graph:
        if node.kind == NodeKind.Port and node.is_output():
            if not node.is_driven():
                undriven.append(node.path)
    return undriven
```

---

## 9. 重要限制与注意事项

### 1. 命名节点限制

- 只有 Port 和 State 具有命名节点（可通过 lookup 查询）。像 `mod.intermediate_wire` 这样的组合逻辑中间信号查找将返回 None。
- `always_ff` 的 `<=` 目标是 State 节点；`always_comb`、`assign` 中的 `=` 目标是透明信号。

### 2. find_comb 的限制

- 不能以 State 节点为目标（必须在组合路径遇到 FF 前停止）。如果需要分析 FF 的输入逻辑，应使用 `get_comb_fan_in`。

### 3. 新版本需要手动触发 Elaboration

- 必须在 `comp.freeze()` 之前调用 `comp.getSemanticDiagnostics()` 和 `pyslang_netlist.visitAll().run(comp)`，否则无法正确构建图。

### 4. Python 绑定兼容性

- 仅与 CPython 3.11 兼容。不能用于 PyPy (即使版本号是 3.8/3.11) 和 CPython 3.9/3.10/3.12。

### 5. Windows 编码问题

- 如果在 Windows 下打印中文出现乱码，需要在脚本开头设置标准输出编码：
  ```python
  import io
  sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
  ```

### 6. get_comb_fan_in 行为

- API 返回的集包含节点自身。在遍历时需要手动过滤 `n.path != node.path`。

---

## 10. 典型应用场景

| 应用 | API 组合 |
|------|----------|
| 连通性检查 (到处到底是否有路径) | `finder.find()` |
| 组合环检测 | `finder.find_comb()` + 源==目标 |
| 时序路径估算 (跨几级 FF) | `finder.find()` 计数 State 节点 |
| 寄存器驱动分析 (什么信号驱动某 FF) | `get_comb_fan_in(state)` |
| 信号影响范围 (某信号会影响哪些输出) | `get_comb_fan_out()` + `finder.find()` |
| 未连接/悬浮信号检查 | `port.is_driven()` |
| CDC 检查 (同时钟域) | 识别不同 clk 驱动的 State 节点间的路径 |
| 黑盒子模块处理 | `graph.build(..., black_boxes=["fifo_*"])` |

---

## 11. 已知限制：混合 always 块模式

slang-netlist 在以下情况下**无法追踪时序逻辑路径**：

```verilog
// 当同一信号在两个 always block 中赋值时
always @(posedge clk)
    b = a;           // combinational style =
always_ff @(posedge clk)
    b <= a;          // sequential style <=
```

**验证测试结果：**

| 测试用例 | `pathExists(a→b)` |
|----------|-------------------|
| only `always_ff` | ✅ 可达 |
| `always` + `always_ff` (同一信号) | ❌ 不可达 |
| `always_ff` with wire | ✅ 可达 |

**根本原因：** 当信号在两个 always block 中赋值时，NetlistBuilder 创建的 fan_in 链在 Assignment 节点断裂，导致 PathFinder 无法追踪。

**建议：** 如果需要追踪时序逻辑路径，避免一个信号在多个 always block 中赋值。