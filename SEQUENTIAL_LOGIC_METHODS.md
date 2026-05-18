# slang-netlist 时序逻辑追踪方法调查

> 调查时间：2026-05-18
> navisv 版本：v0.8.0

---

## 结论

**slang-netlist 没有直接支持时序逻辑路径追踪的 API**。

---

## 调查发现

### 1. NetlistGraph 方法（仅组合逻辑）

| 方法 | 用途 | 限制 |
|------|------|------|
| `get_comb_fan_in/out` | 组合逻辑 fan-in/out | 不追踪时序 |
| `PathFinder.find()` | 路径查找 | **仅组合逻辑** |
| `get_drivers(name, lo, hi)` | 获取 driver 列表 | 需要符号名 |

### 2. AnalysisManager 方法

| 方法 | 用途 |
|------|------|
| `getDrivers(symbol)` | 获取变量的所有 driver |
| `addProcListener` | 过程分析（未探索）|
| `addScopeListener` | 作用域分析（未探索）|

### 3. 时序逻辑的 driver 信息

使用 `AnalysisManager.getDrivers()` 可以获取时序逻辑变量的 driver：

```python
drv = mgr.getDrivers(o_alu_sub)[0]
print(drv.source)      # DriverSource.Always
print(drv.kind)        # DriverKind.Procedural
print(drv.path.rootSymbol)  # 返回的是变量自己（self-loop）
```

**问题**：`getDrivers()` 返回的 `path.rootSymbol` 是**被驱动的符号本身**（self-loop），
而不是驱动源。

### 4. serv_decode 的时序逻辑结构

```verilog
// 组合逻辑产生中间信号
wire co_alu_sub = funct3[1] | funct3[0] | ...;

// 时序逻辑 always block
always @(posedge clk) begin
    if (i_wb_en)
        o_alu_sub <= co_alu_sub;  // 寄存器赋值
end
```

**driver 链**：
```
o_alu_sub (<=) <- always block (<-) co_alu_sub
```

但 `getDrivers(o_alu_sub)` 返回：
- `path.rootSymbol = o_alu_sub`（self-loop）
- `source = DriverSource.Always`
- `kind = DriverKind.Procedural`

它没有告诉你 `co_alu_sub` 是驱动源。

### 5. PathFinder 为何有效（对组合逻辑）

PathFinder 对 `o_alu_rd_sel` 有效，因为它是**连续赋值**：

```verilog
assign o_alu_rd_sel = i_wb_rdt ? ... : ...;  // 组合逻辑
```

PathFinder 可以追踪这种 assign 语句的驱动关系。

---

## 现有方法对比

| 方法 | 组合逻辑 | 时序逻辑 | 备注 |
|------|---------|---------|------|
| PathFinder.find() | ✅ | ❌ | 仅追踪连续赋值 |
| get_comb_fan_in/out | ⚠️ | ❌ | 链在 Assignment 断裂 |
| AnalysisManager.getDrivers() | ✅ | ⚠️ | 返回 self-loop，无 driver 源 |

---

## 可行的替代方案

### 方案 1: 使用 ContinuousAssign AST 直接建边

```python
# 遍历 body 中的 ContinuousAssign 符号
for sym in body:
    if sym.kind == SymbolKind.ContinuousAssign:
        # 提取 lhs 和 rhs 信号
        lhs_signals = extract_signals(sym.assignment.left)
        rhs_signals = extract_signals(sym.assignment.right)
        for dst in lhs_signals:
            for src in rhs_signals:
                graph.add_edge(src, dst, source='continuous_assign')
```

**优点**：绕过 PathFinder 和 getDrivers，直接从 AST 提取驱动关系

### 方案 2: 使用 ProceduralAssignStatement 分析

```python
# 遍历 always block 中的赋值
for sym in body:
    if sym.kind == SymbolKind.ProceduralBlock:
        for stmt in sym.body:
            if isinstance(stmt, ProceduralAssignStatement):
                # 提取 `<=` 左边的符号和右边的符号
                dst = stmt.variable.name
                src = extract_expression_symbols(stmt.variable)
```

**注意**：这需要 pyslang 的 Statement AST 支持

### 方案 3: 接受限制，仅处理组合逻辑

**当前 PathFinder 实现已经覆盖**：
- 连续赋值（`assign`）
- 组合逻辑 always block

**未覆盖**：
- 时序逻辑 always block（`always @(posedge clk)`）
- 寄存器输出

**建议**：在文档中明确说明 PathFinder 的限制，或者标记模块类型。

---

## 建议的下一步

1. **调研方案 1**：使用 ContinuousAssign 直接建边
   - 需要遍历 `body` 中的连续赋值符号
   - 需要 `extract_signals()` 函数提取信号名

2. **调研方案 2**：分析 ProceduralAssignStatement
   - 检查 `ProceduralBlockSymbol` 的结构
   - 提取 always block 中的赋值关系

3. **或者接受限制**：
   - PathFinder 适用于组合逻辑模块
   - 对时序逻辑模块，提示用户当前限制
   - 优先实现 R-1（实例节点解析）等其他功能

---

## 参考资料

- slang-netlist examples: `connectivity_check.py`, `unconnected_inputs.py`
- pyslang Statement AST: `Statement`, `ProceduralAssignStatement`, `TimedStatement`
- `AnalysisManager.addProcListener` 可能提供过程分析能力（待探索）