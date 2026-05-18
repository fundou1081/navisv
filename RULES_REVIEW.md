# RULES.md 审查报告

**日期**：2026-05-18
**依据**：slang-netlist 用户指南 v0.9 + 项目实际测试结果
**目的**：发现与实际行为不符的铁律，提出修改建议

---

## 核心发现：slang-netlist 的真实能力边界

### 1. 路径追踪能力

| API | 能力 | 限制 |
|-----|------|------|
| `PathFinder.find()` | **可穿过 State 节点** | 同一信号在两个 always block 赋值时失败 |
| `PathFinder.find_comb()` | 纯组合逻辑，遇 State 停止 | **Python 绑定未暴露** |
| `graph.get_drivers()` | 返回直接驱动节点 | Assignment 节点无 path |
| `graph.get_comb_fan_in/out()` | 组合扇入/扇出 | **Python 绑定未暴露** |
| `getSensitivity()` | 获取 State 的 clock/reset | **Python 绑定未暴露** |

### 2. 已知设计限制

**限制 A**：当同一信号在两个 always block 中赋值时，PathFinder 追踪失败

```verilog
always @(posedge clk)
    b = a;           // combinational =
always_ff @(posedge clk)
    b <= a;          // sequential <=
```

验证：PathFinder 报告 `a -> b` 不可达，但 `a -> b` 的时序路径确实存在。

**限制 B**：组合逻辑中间信号（wire）不是 Named Node，无法 lookup

```
wire w = a & b;  // w 无法 graph.lookup("mod.w")
```

Path 会穿过 w，但无法直接查询 w 的 driver。

---

## 问题铁律清单

### ❌ 铁律 1（部分）：正则分析限制过严

**原文**：
> 严禁直接正则分析 SV 源码

**问题**：
- 铁律 1 的自动化测试禁止导入 `re` 模块，但实际代码中 `service.py` 的 `find_nodes_regex` 方法需要使用正则表达式
- 用户指南中明确记录了 `find_nodes_regex()` 是合法 API

**建议修改**：
```
# 修改为：
# 允许在 Query Layer 使用 re 模块进行节点搜索（slang 已完成语义分析）
# 禁止在 Graph Layer 使用正则分析源码重新理解语义
```

---

### ❌ 铁律 3（需要补充）：Python 层实际可以创建边

**原文**：
> Python 层（StatementExplorer、ClassExplorer）只补充属性，不覆盖 slang 的拓扑

**问题**：
- `design_graph.py` 中 `_add_edges_from_pathfinder()` 是 Python 层创建的边
- `source='pathfinder'` 的边不是 slang 创建的
- 用户指南记录了 `find()` 返回的路径可以作为建边依据

**实际情况**：
```python
# design_graph.py v0.9 中的实际代码
def _add_edges_from_pathfinder(self) -> None:
    # 使用 PathFinder 查找路径，Python 创建边
    path = finder.find(in_node, out_node)
    if not path.empty():
        self.graph.add_edge(src_path, dst_path, source='pathfinder', ...)
```

**建议修改**：
```
# 铁律 3 补充说明：
# Python 层可以使用 PathFinder 结果创建边（source='pathfinder'）
# 这些边的 confidence 是 'high'，仅次于 'slang'
# slang 拓扑优先原则仍然有效：只有 slang 源创建的边（source='slang'）
# 不能被 Python 覆盖
```

---

### ❌ 铁律 15（需要补充）：StatementExplorer 角色的扩展

**原文**：
> StatementExplorer 不调用 `graph.add_edge()`

**问题**：
- 用户指南记录了 `StatementExplorer` 可以使用 `comp.getSemanticDiagnostics()` 等方式直接分析 AST
- 实际上 `statement_explorer.py` 是边注释者，但 Graph Layer 整体可以在注释前创建边

**建议**：
```
# 铁律 15 应改为：
# Graph Layer 整体作为边构建者，StatementExplorer 是边注释者
# 但 StatementExplorer 自身不调用 add_edge
```

---

### ❌ 铁律 20（过严）：Visitor 模式限制

**原文**：
> 对 pyslang SyntaxNode 的遍历必须使用 Visitor 模式，禁止 if-elif 链

**问题**：
- 用户指南示例代码大量使用 `if/elif` 判断 `kind_name`
- `ExpressionVisitor` 在用户指南和实际代码中都是简单的类，不是严格的 Visitor 模式
- pyslang 自己的示例代码也使用 if/elif

**建议修改**：
```
# 铁律 20 改为：
# 优先使用 Visitor 模式处理复杂语法树
# 简单场景（如表达式解析）允许使用 if/elif 判断 kind
# 禁止在 Graph Layer 核心逻辑中使用 if-elif kind 链处理语句级遍历
```

---

### ❌ 铁律 16（需要验证）：annotators 可选性

**原文**：
> `DesignGraph._build()` 不调用任何 annotators

**问题**：
- v0.9 代码中 `_build()` 确实不调用 annotators（`enable_annotators` 控制）
- 但 Issue-F 等问题说明当前 annotator（StatementExplorer）可能不够完善
- 用户指南记录了完整的 elaboration 流程，这本身就是一种"annotation"

**建议**：
```
# 铁律 16 确认：
# 当前实现已经满足：enable_annotators=False 时能正常构建
# 建议补充：StatementExplorer 是可选的边属性补充器
```

---

## 需要新增的铁律

### ✅ 铁律 26（新增）：PathFinder 限制声明

**内容**：
```
当信号在两个 always block 中赋值时，PathFinder 可能无法追踪到该路径。
这是 slang-netlist 的设计限制，不是实现 bug。
需要向用户说明此限制，并建议改善 design。
```

---

### ✅ 铁律 27（新增）：Combination Logic 透明性

**内容**：
```
组合逻辑中间信号（wire/assign）在图中是"透明"的。
Path 会穿过它们，但它们不是 Named Node（无法 lookup）。
在查找路径时，默认跳过这些中间节点。
```

---

### ✅ 铁律 28（新增）：Python 绑定限制声明

**内容**：
```
部分 slang-netlist C++ API 未暴露到 Python 绑定：
- PathFinder.find_comb() 不可用
- graph.getSensitivity() 不可用
- graph.get_comb_fan_in/out() 不可直接用
如需这些功能，需要扩展 Python 绑定或使用 C++ 直接调用。
```

---

## 铁律修改汇总

| 铁律 | 当前状态 | 建议 | 原因 |
|------|----------|------|------|
| 1 | 禁止正则 | **修改** | 节点搜索需要正则 |
| 3 | Python 不创建边 | **补充** | PathFinder 结果可创建边 |
| 15 | SE 不调用 add_edge | **澄清** | Graph Layer 整体可创建边 |
| 20 | 必须 Visitor | **放宽** | 简单场景允许 if/elif |
| 16 | annotators 可选 | **确认** | 已满足，无需修改 |
| 26 | 新增 | **新增** | PathFinder 限制声明 |
| 27 | 新增 | **新增** | 组合逻辑透明性 |
| 28 | 新增 | **新增** | Python 绑定限制 |

---

## 总结

1. **RULES.md v0.6 的主要问题**：过度严格的限制（铁律 1、20）与用户指南的实践不符

2. **缺失的限制声明**：没有记录 slang-netlist 本身的已知限制（PathFinder 无法处理混合 always block）

3. **建议行动**：
   - 更新 RULES.md 到 v0.7，反映实际限制
   - 新增铁律 26-28 记录 slang-netlist 限制
   - 放宽铁律 1、20 的限制范围