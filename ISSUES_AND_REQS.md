# OpenChip QA 测试发现 - Issue 与需求清单

> 生成时间：2026-05-18
> 来源：openchip-qa 测试项目
> navisv 版本：v0.8.0 (with NetlistGraph BFS fallback)

---

## 测试汇总

| 设计 | 节点数 | 边数 | 回答率 | 状态 |
|------|--------|------|--------|------|
| clacc/bs_mult | 11 | 0 | 0% | ❌ |
| serv/serv_alu | 24 | 12 | 58% | ⚠️ |
| serv/serv_decode | 101 | 17 | 43% | ⚠️ |
| serv/serv_top | 124 | 0 | 0% | ❌ |
| cva6/cva6 | 253 | 0 | 0% | ❌ |

---

## Issue 清单（按严重度排序）

### P0 - 阻塞性问题

| Issue | 描述 | 影响 | 发现项目 | 状态 |
|-------|------|------|----------|------|
| **Issue-B** | 实例（Instance）节点未被解析 | 顶层节点数量远少于实际，无法看到子模块结构 | clacc/bs_mult, serv/top | 待修复 |
| **Issue-C** | slang `getDrivers()` 对 Net 类型信号返回 self-loop | 所有设计的边数归零（已用 NetlistGraph BFS 作为 fallback 临时解决）| 所有测试设计 | ⚠️ 临时解决 |

### P1 - 严重问题

| Issue | 描述 | 影响 | 发现项目 | 状态 |
|-------|------|------|----------|------|
| **Issue-D** | 设计中所有端口都是 Input（无 Output）时，NetlistGraph BFS 无法建边 | 组合逻辑模块（如 bs_mult）边数为 0 | clacc/bs_mult | 待修复 |
| **Issue-E** | 部分信号（i_cmp_sig, i_bool_op, result_slt 等）未出现在边列表 | 驱动关系不完整 | serv/serv_alu | 待修复 |
| **Issue-F** | 指令译码控制信号（o_alu_sub, o_alu_cmp_eq 等）未出现在边列表 | 无法完整追踪译码逻辑 | serv/serv_decode | 待修复 |
| **Issue-L** | 大型顶层模块（CVA6）的 NetlistGraph 可见节点数量极少（仅 10 个 Input Port）| 边数为 0，无法分析 | cva6/cva6 | 待修复 |

### P2 - 一般问题

| Issue | 描述 | 影响 | 发现项目 | 状态 |
|-------|------|------|----------|------|
| **Issue-G** | parameter 值无法提取 | 无法获取 W=1, PRE_REGISTER 等参数配置 | serv/serv_alu, serv/serv_decode | 待修复 |
| **Issue-H** | 内部 Net 信号（result_add, result_eq 等）未作为节点 | 驱动关系不完整 | serv/serv_alu | 待修复 |
| **Issue-J** | generate 语句未处理 | 两种配置路径未体现 | serv/serv_decode | 待修复 |

---

## 功能需求清单（按优先级排序）

### R-1: 实例节点解析 [P0]

**描述**：将 Instance 符号（如 `bs_mult_slice`, `serv_decode`, `serv_alu`）添加为节点

**当前状态**：navisv 只解析 Net/Port/Variable 类型符号，Instance 类型被忽略

**期望行为**：
```
# 当前
bs_mult: 11 nodes (只有信号)
# 期望
bs_mult: 11 signals + 31 instances (bs_mult_slice I0-I30)
```

**实现思路**：
1. 在 `_add_nodes_from_slang()` 中添加对 `Instance` 类型的处理
2. 实例节点 ID：`{module}.{instance_name}`
3. 实例节点属性：`type=instance`, `module={def_name}`

---

### R-2: 驱动关系修复（替代 getDrivers self-loop）[P0]

**描述**：当 `getDrivers()` 返回 self-loop 时，使用备选方案提取驱动关系

**当前状态**：
- ✅ 已实现 NetlistGraph BFS fallback
- ⚠️ 只对有 Output Port 的设计有效

**实现思路**：
1. **优先使用 `getDrivers()` 结果**（跨信号驱动）
2. **Fallback 到 ContinuousAssign 直接解析**（见 R-3）
3. **处理全 Input 设计的特殊情况**

---

### R-3: ContinuousAssign 直接建边 [P1]

**描述**：直接从 `ContinuousAssign` AST 节点提取驱动关系，不依赖 `getDrivers()`

**当前状态**：未实现

**实现思路**：
```python
for sym in body:
    if sym.kind.name == 'ContinuousAssign':
        assgn = sym.assignment
        lhs_signals = _extract_signals(assgn.left)
        rhs_signals = _extract_signals(assgn.right)
        for dst in lhs_signals:
            for src in rhs_signals:
                if src != dst:
                    graph.add_edge(src, dst, source='continuous_assign')
```

**优点**：
- 绕过 `getDrivers()` self-loop 问题
- 直接用 slang AST，驱动关系准确

---

### R-4: 端口标签（port_input / port_output）[P1]

**描述**：为每个端口节点添加标签，标识是输入还是输出

**当前状态**：所有节点 tags 为空集

**期望行为**：
```
# 期望
serv_alu.clk (tags={port_input})
serv_alu.o_rd (tags={port_output})
```

**实现思路**：
1. 在 `_add_nodes_from_slang()` 中检查端口方向
2. 从 `Port.direction` 获取方向（Input/Output/InOut）
3. 添加对应 tag

---

### R-5: parameter 值提取 [P1]

**描述**：提取模块的 parameter 定义和值

**当前状态**：无法获取参数值

**期望行为**：
```
# 期望
serv_alu.W = 1
serv_decode.PRE_REGISTER = 1
cva6.VLEN = 64
```

**实现思路**：
1. 遍历 `body` 中的 `Parameter` 类型符号
2. 提取 `sym.name` 和 `sym.value`
3. 存储在节点的 `meta` 字段或独立结构中

---

### R-6: 内部 Net 信号节点补全 [P1]

**描述**：将内部 Net 信号（如 `result_add`, `result_eq`）添加到节点列表

**当前状态**：NetlistGraph 只显示 Port/State 节点，内部 Net 不可见

**期望行为**：
```
# 当前
serv_alu: 24 nodes (Port/State only)
# 期望
serv_alu: 24 + N nodes (包含内部 Net)
```

**实现思路**：
1. 在 `_add_nodes_from_slang()` 中对所有 `Net` 类型符号建节点
2. 不依赖 NetlistGraph 的可见性，直接从 body 遍历

---

### R-7: generate 语句处理 [P2]

**描述**：识别和处理 `generate` 语句，支持条件实例化

**当前状态**：`PRE_REGISTER=0/1` 两种配置未体现

**实现思路**：
1. 遍历 `body` 中的 `GenerateBlock` 类型符号
2. 提取 generate 条件（`if`, `case`, `for`）
3. 根据条件确定激活的实例

---

### R-8: 组合逻辑信号驱动关系补全 [P1]

**描述**：i_cmp_sig, i_bool_op, result_slt 等信号的驱动关系

**当前状态**：这些信号未出现在边列表中

**实现思路**：
1. 检查 NetlistGraph 的 `find_nodes_regex` 是否遗漏
2. 如果遗漏，使用 ContinuousAssign 直接解析（R-3）

---

### R-9: 跨实例信号追踪 [P2]

**描述**：追踪模块间连接（如 `serv_top` 中 `serv_decode` → `serv_alu` 的信号）

**当前状态**：实例未解析，跨实例信号无法追踪

**实现思路**：
1. 先实现 R-1（实例节点解析）
2. 从实例端口连接中提取信号关系
3. 构建跨实例的驱动图

---

### R-10: 结构体/typedef 支持 [P2]

**描述**：支持 SystemVerilog 的结构体和 typedef 类型

**当前状态**：复杂类型无法解析

**实现思路**：
1. 在 `schema.py` 中添加对结构体类型的支持
2. 识别 `struct` 和 `union` 类型
3. 提取字段作为子节点

---

## Issue → 需求映射

| Issue | 对应需求 |
|-------|----------|
| Issue-B | R-1: 实例节点解析 |
| Issue-C | R-2: 驱动关系修复 |
| Issue-D | R-3: ContinuousAssign 直接建边 |
| Issue-E | R-8: 组合逻辑信号驱动关系补全 |
| Issue-F | R-8: 组合逻辑信号驱动关系补全 |
| Issue-G | R-5: parameter 值提取 |
| Issue-H | R-6: 内部 Net 信号节点补全 |
| Issue-J | R-7: generate 语句处理 |
| Issue-L | R-1 + R-9: 实例解析 + 跨实例追踪 |

---

## 修复优先级建议

### 短期（1-2 周）

1. **R-1**: 实例节点解析 — 解决 Issue-B, Issue-L
2. **R-3**: ContinuousAssign 直接建边 — 解决 Issue-D, Issue-C
3. **R-4**: 端口标签 — 提高节点信息完整度

### 中期（1 个月）

4. **R-5**: parameter 值提取 — Issue-G
5. **R-6**: 内部 Net 信号节点补全 — Issue-H
6. **R-8**: 组合逻辑信号驱动关系补全 — Issue-E, Issue-F

### 长期（持续）

7. **R-7**: generate 语句处理
8. **R-9**: 跨实例信号追踪
9. **R-10**: 结构体/typedef 支持

---

## 测试记录文件

各设计的详细测试记录位于：
- `openchip_qa_results/clacc_bs_mult/TEST_LOG.md`
- `openchip_qa_results/serv_alu/TEST_LOG.md`
- `openchip_qa_results/serv_decode/TEST_LOG.md`
- `openchip_qa_results/serv_top/TEST_LOG.md`
- `openchip_qa_results/cva6_cva6/TEST_LOG.md`