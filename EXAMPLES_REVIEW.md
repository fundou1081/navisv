# slang-netlist Examples 回顾与 navisv 能力映射

**文档目的**：回顾 `pyslang-netlist-examples/` 中已完成的 example，提取关键 API 和模式，为 navisv 各命令实现提供参考

**依赖版本**：
- slang-netlist：build 后 install 的 `.so` + Python binding
- pyslang：标准 cells/pyslang
- Python：3.9

---

## Example 概览

| # | 文件 | 核心能力 | 对应 navisv 命令 | 成熟度 |
|---|------|----------|------------------|--------|
| 01 | 01_basic_graph.py | NetlistGraph 构建 / 节点遍历 | —（基础设施） | ✅ 成熟 |
| 02 | 02_fanin_fanout.py | 组合 fan-in / fan-out | `related` | ✅ 成熟 |
| 03 | 03_path_finder.py | PathFinder 路径追踪 | `paths`、`trace-cone` | ✅ 成熟 |
| 04 | 04_driver_analysis.py | DriverKind / DriverSource 分析 | `usage`、`sample-condition` | ✅ 成熟 |
| 05 | 05_multi_driver.py | 多驱动冲突检测 | `impact`、`blast-radius` | ✅ 成熟 |
| 06 | 06_pipelined_module.py | Pipeline stage 识别 | `fsm-detect`、`path-profile` | ✅ 成熟 |
| 07 | 07_fsm_analysis.py | 状态机节点推断 | `fsm-detect` | ✅ 成熟 |
| 08 | 08_edge_attributes.py | NetlistEdge 属性分析 | —（参考） | ✅ 成熟 |
| 09 | 09_node_lookup.py | 层级节点查找 / fuzzy find | 所有命令的基础 | ✅ 成熟 |
| 10 | 10_batch_driver_report.py | 批量信号 driver 报表 | —（参考） | ✅ 成熟 |
| 11 | 11_cdc_analysis.py | CDC 路径分析框架 | `path-profile` | ✅ 成熟 |
| 12 | 12_connectivity_report.py | 端口连接性报表 | `protocol-infer` | ✅ 成熟 |
| 13 | 13_coverage_analysis.py | 覆盖点分析框架 | `gen-coverage` | ✅ 成熟 |
| 14 | 14_opentitan_coverage.py | OpenTitan I2C 真实设计验证 | `gen-coverage`、`sample-condition` | ✅ 成熟 |
| 15 | 15_class_support.py | ClassType / ClassProperty / Subroutine 遍历 | —（C++ 局限分析） | ✅ 分析完成 |
| 16 | 16_constraint_explore.py | Constraint 关系提取（Python 层） | `constraints` | ✅ 成熟 |
| 17 | 17_class_arch_analysis.py | slang-netlist C++ 架构分析 | —（设计文档） | ✅ 分析完成 |
| 18 | 18_sv_query_analysis.py | sv_query vs slang-netlist 架构对比 | —（设计文档） | ✅ 分析完成 |
| — | debug_sourcerange.py | always_ff 源码文本提取 | `sample-condition` | ✅ 成熟 |
| — | explore_coverage.py | 覆盖点分析 Demo | `gen-coverage` | ✅ 成熟 |
| — | scan_i2c.py | I2C 模块扫描报表 | —（参考） | ✅ 成熟 |

---

## P0 关键 API（实现任何命令的基础）

### 1. 初始化链路

```python
# Example 01 / 14
import sys
sys.path.insert(0, "/Users/fundou/my_dv_proj/slang-netlist/install")
sys.path.insert(0, "/Users/fundou/my_dv_proj/slang-netlist/install/lib")

import pyslang_netlist as nl
from pyslang import driver as sl_driver

SL_FILE = "design.sv"
d = sl_driver.Driver()
d.addStandardArgs()
d.sourceLoader.addFiles(SL_FILE)
d.parseAllSources()
comp = d.createCompilation()
mgr = d.runAnalysis(comp)
graph = nl.NetlistGraph()
graph.build(comp, mgr)
```

**关键发现**：
- `graph.build(comp, mgr)` 是唯一正确的构建方式
- `find_nodes_regex('.*')` 才能找到所有节点（`find_nodes('')` 返回空 list）
- `lookup()` 按完整路径查找有效

---

### 2. 节点查找（所有命令的第一步）

```python
# Example 09 - fuzzy find
def fuzzy_find_signal(inst_name, graph, body, hint):
    candidates = []
    for m in body:
        name = getattr(m, 'name', '') or getattr(m, 'name', '')
        if hint.lower() in name.lower():
            candidates.append(name)
    return candidates

# Example 14 - hierarchical lookup
target = inst_name + "." + hint
nodes = graph.find_nodes_regex(".*" + hint.replace(".", "\\.") + ".*")
```

---

### 3. Driver / Load 分析

```python
# Example 04
drivers = mgr.getDrivers(variable_sym)
for d_ in drivers:
    print(f"  kind={d_.kind.name}")      # Procedural / Continuous / Port
    print(f"  source={d_.source.name}")  # always_ff / assign / port name

# Example 04 - DriverSource
print(f"  source={d_.source.name}")
```

**关键发现**：
- `mgr.getDrivers(sym)` 只接受 `ValueSymbol`（Variable / Port / Parameter）
- ClassProperty 不支持 → 在 Python 层用 Statement walk 绕过（example 16）
- `DriverKind`：`Procedural`、`Continuous`、`Port`、`Parameter`

---

### 4. PathFinder 路径追踪

```python
# Example 03
finder = nl.PathFinder(graph)
path = finder.find(start_node, end_node)
print(f"  path.empty()={path.empty()}, path.size()={path.size()}")
nodes = list(path)
print(f"  nodes: {[n.name for n in nodes]}")

# Example 03 - comb-only
comb_path = finder.find_comb(start_node, end_node)
```

**关键发现**：
- `path.empty()` 判断是否有路径
- `path.size()` 获取路径节点数
- `find_comb()` 过滤纯组合逻辑路径

---

### 5. 源码文本提取

```python
# Example 14 / debug_sourcerange.py
def extract_timing_and_qualifiers(sym, mgr, sm):
    syn = sym.getSyntax()
    lines = []
    for i in range(syn.sourceRange.start.line, syn.sourceRange.end.line + 1):
        line = sm.getSourceLine(i)
        lines.append(f"[{i:03d}] {line}")
    return "\n".join(lines)
```

---

## P1 各命令实现参考

---

### `trace-cone` → Example 02 + 03

**核心逻辑**：
```python
# fanin_cone: 反向追踪
fanin = graph.get_comb_fan_in(target_node)
# fanout_cone: 正向追踪
fanout = graph.get_comb_fan_out(target_node)

# 或用 PathFinder 追踪完整路径
paths = finder.find(source_node, target_node)
```

**输出格式**：
```python
{
    "signal": "top.data_vld",
    "fanin_cone": {"depth": 3, "paths": [...]},
    "fanout_cone": {"depth": 5, "loads": [...]}
}
```

---

### `usage` → Example 04 + 10

**核心逻辑**：
```python
drivers = list(mgr.getDrivers(sym))
loads = []
for n in graph.get_comb_fan_out(node):
    loads.append({"path": n.name, "kind": n.kind.name})
```

**use 分类**（example 04 DriverKind）：
- `Procedural` → always_ff/always_comb 驱动
- `Continuous` → assign 驱动
- `Port` → 模块端口连接

---

### `related` → Example 02

**核心逻辑**：
```python
# 扇入 + 扇出 + 共同驱动源
fanin = graph.get_comb_fan_in(node)
fanout = graph.get_comb_fan_out(node)
# 相关性评分：同 always_ff 驱动 = 高分
score = len(shared_drivers) * 0.3 + fan_weight * 0.4 + fanout_weight * 0.3
```

---

### `sample-condition` → Example 14 + debug_sourcerange.py

**核心逻辑**：
```python
# 1. 找到信号的 driver（always_ff）
drivers = mgr.getDrivers(sym)
for d_ in drivers:
    # 2. 从 always_ff statement 提取 timing control
    always_syn = d_.source.getSyntax()
    timing_ctrl = extract_timing_control(always_syn)
    # 3. 从 if 语句提取 qualifier
    qualifiers = extract_qualifiers(always_syn)
```

**源码文本提取模式**（debug_sourcerange.py）：
```python
# always_ff 块 → 提取时钟
timing_lines = []
for i in range(syn.start.line, syn.end.line + 1):
    line = sm.getSourceLine(i)
    timing_lines.append(f"[{i:03d}] {line}")
```

---

### `gen-coverage` → Example 13 + 14

**核心逻辑**：
```python
# 1. 位宽分析
bit_width = bounds[0] - bounds[1] + 1

# 2. toggle coverage
toggle_bins = [f"{name}[{i}]" for i in range(bit_width)]

# 3. boundary coverage（从源码提取合法值域）
boundaries = extract_boundaries_from_rtl(sym, mgr)

# 4. 交叉覆盖
cross_pairs = find_correlated_signals(sym, graph)

# 5. 生成 covergroup 代码
def gen_cov_code(target_name, sig_type, bit_width):
    return f"""covergroup cg_{target_name} @(posedge clk);
  cp_{target_name}: coverpoint {target_name} {{
    bins zero = {{0}};
    bins max = {{{2**bit_width - 1}}};
  }}
endgroup"""
```

---

### `fsm-detect` → Example 07

**核心逻辑**：
```python
# 1. 找到 State 节点（NodeKind.State）
state_nodes = [n for n in graph.find_nodes_regex(".*") if n.kind == nl.NodeKind.State]

# 2. 构建 SCC（强连通分量）检测状态机
# 3. 识别状态位 + 控制信号
# 4. 反馈环识别
```

---

### `constraints` → Example 16

**核心逻辑**（Python 层实现，不依赖 slang-netlist C++）：
```python
# 1. 获取 class 的 ConstraintBlock
constraint_blocks = [m for m in class_body if m.kind == SymbolKind.ConstraintBlock]

# 2. 遍历 ConstraintDeclarationSyntax
def parse_constraint_block(cb):
    syn = cb.syntax  # ConstraintDeclarationSyntax
    for child in syn.children:
        if "implication" in child.kind.name.lower():
            return parse_implication(child)
        elif "inside" in child.kind.name.lower():
            return parse_inside(child)
        elif "dist" in child.kind.name.lower():
            return parse_distribution(child)
```

**约束关系类型**：
- `implication` → `valid == 1 -> data != 0`
- `inside` → `data inside {[1:100]}`
- `conditional` → `if (valid) data > 8'h10 else data == 0`
- `distribution` → `id dist {0:=20, 1:=30, [2:3]:=50}`

---

### `impact` / `blast-radius` → Example 05

**核心逻辑**：
```python
# 双向 BFS
def blast_radius(signal, graph, depth=3):
    fanin_nodes = bfs_fanin(signal, depth)
    fanout_nodes = bfs_fanout(signal, depth)
    return {
        "fanin": fanin_nodes,
        "fanout": fanout_nodes,
        "affected_modules": extract_modules(fanin_nodes + fanout_nodes)
    }
```

---

### `path-profile` → Example 11

**核心逻辑**：
```python
# 1. 组合路径深度
def comb_depth(path):
    depth = 0
    for i in range(len(path) - 1):
        if graph.is_combinational(path[i], path[i+1]):
            depth += 1
    return depth

# 2. CDC 检测：跨时钟域路径识别
def find_cdc_paths(graph, clocks):
    cdc = []
    for path in all_paths:
        if path跨越不同时钟域(clocks):
            cdc.append(path)
    return cdc
```

---

### `protocol-infer` → Example 12

**核心逻辑**：
```python
# 1. 端口列表
ports = [m for m in body if m.kind == SymbolKind.Port]

# 2. 握手模式识别
# valid/ready → AXI valid-ready
# req/ack → 握手协议

# 3. 数据有效窗口提取
def infer_data_valid_window(port, always_blk):
    # 从 always_ff 的 if 条件中提取
    pass
```

---

### Class 内 driver 关系 → Example 15 + 16 + 17

**关键发现**：
- `mgr.getDrivers(ClassProperty)` 返回空 → slang-netlist C++ 不支持
- **Python 层绕过方案**（example 16 已验证）：
```python
# 从 SubroutineSymbol.body 遍历 Statement tree
for method in class_body:
    if method.kind == SymbolKind.Subroutine:
        body = method.body  # Statement
        for stmt in walk_statements(body):
            if is_assignment_to(stmt, prop_name):
                yield {'method': method.name, 'stmt': stmt}
```

---

## navisv 命令与 Example 映射表

| navisv 命令 | 主要参考 Example | 关键 API |
|-------------|-----------------|----------|
| `trace-cone` | 02, 03 | `get_comb_fan_in/out`, `PathFinder.find` |
| `usage` | 04, 10 | `mgr.getDrivers`, `get_comb_fan_out` |
| `sample-condition` | 14, debug_sourcerange.py | 源码文本提取 + timing control 解析 |
| `related` | 02 | fanin + fanout + 评分 |
| `gen-coverage` | 13, 14 | 位宽分析 + 值域提取 + covergroup 生成 |
| `paths` | 03 | `PathFinder.find` + control/data path 区分 |
| `fsm-detect` | 07 | State 节点 + SCC 检测 |
| `impact` | 05 | 双向 BFS + fanout 锥 |
| `blast-radius` | 05 | 双向 BFS |
| `stability` | 07 | fanout 宽度 + 耦合密度 |
| `path-profile` | 11 | 组合深度 + CDC 检测 |
| `protocol-infer` | 12 | 端口 handshake 模式识别 |
| `constraints` | 16 | Python ConstraintVisitor |
| `assert` | 14 (timing extraction) | SVA 模板生成 |
| `grade` | 10 (批量报表) | 多维评分指标 |

---

## 关键技术点

### 1. find_nodes vs find_nodes_regex

```python
# ❌ find_nodes('') 返回空 list
nodes = graph.find_nodes('')

# ✅ find_nodes_regex('.*') 才返回所有节点
nodes = graph.find_nodes_regex('.*')
```

### 2. NodeKind 枚举值

```python
# Example 08
[NodeKind.Port, NodeKind.State, NodeKind.Variable,
 NodeKind.Assignment, NodeKind.Constant, ...]
```

### 3. SourceRange / 源码文本提取

```python
# Example 14 / debug_sourcerange.py
syn = sym.getSyntax()
start_line = syn.sourceRange.start.line
end_line = syn.sourceRange.end.line
source_text = sm.getSourceText(syn.sourceRange)
```

### 4. Symbol 层级路径

```python
# Example 09
inst = list(comp.getRoot())[1]  # top instance
body = inst.body
sym = body.lookup("out_data")     # 精确路径
hier_path = sym.getHierarchicalPath()
```

### 5. always_ff timing control 提取

```python
# debug_sourcerange.py
always_stmt = syn  # always_ff 的 statement body
tc = always_stmt.timingControl  # TimingControl
event = tc.expr  # EventControl
edge = event.expr.edge  # 'posedge' / 'negedge'
clock_sig = event.expr.expr  # 时钟信号名
```

---

## navisv 尚不支持需 Python 层实现的功能

| 功能 | 原因 | 实现方案 |
|------|------|----------|
| ClassProperty driver | slang-netlist C++ 不支持 | Python Statement walk（example 16 模式） |
| Constraint 关系 | slang-netlist C++ 无 Syntax walk | Python ConstraintVisitor（example 16） |
| Class 方法内 driver 链 | graph 不捕获 SubroutineSymbol | Python 层追踪 method call |
| 源码文本语义解析 | getDrivers 不返回完整上下文 | 源码文本分析（debug_sourcerange.py 模式） |

---

*文档版本：v0.1*  
*创建日期：2026-05-17*  
*来源：pyslang-netlist-examples/examples/*