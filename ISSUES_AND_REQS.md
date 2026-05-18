# OpenChip QA 测试发现 - Issue 与需求清单

> 生成时间：2026-05-18（更新）
> 来源：openchip-qa 测试项目
> navisv 版本：v0.8.0 (with PathFinder fallback)

---

## 测试汇总

| 设计 | 节点数 | 边数 | 边来源 | 回答率 | 状态 |
|------|--------|------|--------|--------|------|
| clacc/bs_mult | 11 | 0 | - | 0% | ❌ |
| serv/serv_alu | 24 | 9 | pathfinder | 58% | ✅ |
| serv/serv_decode | 101 | 3 | pathfinder | 30% | ⚠️ |
| darkriscv/darkriscv | 76 | 0 | - | 0% | ❌ |
| tiny-gpu/core | 42 | 0 | - | 0% | ❌ |
| picorv32/picorv32 | - | - | - | - | 💥 |
| cva6/cva6 | 253 | 0 | - | 0% | ❌ |

**PathFinder vs BFS 对比**：

| 设计 | BFS 边数 | PathFinder 边数 | 变化 |
|------|----------|------------------|------|
| serv/serv_alu | 12 | 9 | -3 |
| serv/serv_decode | 17 | 3 | **-14** |
| clacc/bs_mult | 0 | 0 | 0 |
| cva6/cva6 | 0 | 0 | 0 |

---

## Issue 清单（按严重度排序）

### P0 - 阻塞性问题

| Issue | 描述 | 影响 | 发现项目 | 状态 |
|-------|------|------|----------|------|
| **Issue-B** | 实例（Instance）节点未被解析 | 顶层节点数量远少于实际，无法看到子模块结构 | clacc/bs_mult, serv/top | 待修复 |
| **Issue-C** | slang `getDrivers()` 对 Net 类型信号返回 self-loop | 所有设计的边数归零（已用 PathFinder fallback 解决）| 所有测试设计 | ✅ 已修复 |
| **Issue-O** | 解析崩溃（segfault）| picorv32 解析时崩溃，无法完成测试 | picorv32 | 🔍 调查中 |

### P1 - 严重问题

| Issue | 描述 | 影响 | 发现项目 | 状态 |
|-------|------|------|----------|------|
| **Issue-M** | PathFinder 边数异常减少 | serv_decode 从 17 条降到 3 条，部分驱动关系丢失 | serv/serv_decode | 🔍 调查中 |
| **Issue-N** | 多节点设计无边 | darkriscv(76节点), tiny-gpu(42节点) 边数为 0，PathFinder 未找到路径 | darkriscv, tiny-gpu | 🔍 调查中 |
| **Issue-D** | 设计中所有端口都是 Input（无 Output）时，PathFinder 无法建边 | 组合逻辑模块（如 bs_mult）边数为 0 | clacc/bs_mult | 待修复 |
| **Issue-E** | 部分信号（i_cmp_sig, i_bool_op, result_slt 等）未出现在边列表 | 驱动关系不完整 | serv/serv_alu | 待修复 |
| **Issue-F** | 指令译码控制信号（o_alu_sub, o_alu_cmp_eq 等）未出现在边列表 | 无法完整追踪译码逻辑 | serv/serv_decode | 待修复 |
| **Issue-L** | 大型顶层模块（CVA6）的 NetlistGraph 可见节点数量极少 | 边数为 0，无法分析 | cva6/cva6 | 待修复 |

### P2 - 一般问题

| Issue | 描述 | 影响 | 发现项目 | 状态 |
|-------|------|------|----------|------|
| **Issue-G** | parameter 值无法提取 | 无法获取 W=1, PRE_REGISTER 等参数配置 | serv/serv_alu, serv/serv_decode | 待修复 |
| **Issue-H** | 内部 Net 信号（result_add, result_eq 等）未作为节点 | 驱动关系不完整 | serv/serv_alu | 待修复 |
| **Issue-J** | generate 语句未处理 | 两种配置路径未体现 | serv/serv_decode | 待修复 |

---

## 功能需求清单（按优先级排序）

### R-1: 实例节点解析 [P0]

**描述**：将 Instance 符号添加为节点

**期望行为**：
```
# 当前
bs_mult: 11 nodes (只有信号)
# 期望
bs_mult: 11 signals + 31 instances (bs_mult_slice I0-I30)
```

---

### R-2: 驱动关系修复（替代 getDrivers self-loop）[P0]

**状态**：✅ 已用 PathFinder 解决

---

### R-3: ContinuousAssign 直接建边 [P1]

**描述**：直接从 `ContinuousAssign` AST 节点提取驱动关系，不依赖 PathFinder

**优点**：绕过 `getDrivers()` self-loop 问题，直接用 slang AST

---

### R-4: 端口标签（port_input / port_output）[P1]

**描述**：为每个端口节点添加标签，标识是输入还是输出

**期望行为**：
```
serv_alu.clk (tags={port_input})
serv_alu.o_rd (tags={port_output})
```

---

### R-5: parameter 值提取 [P1]

**描述**：提取模块的 parameter 定义和值

**期望行为**：
```
serv_alu.W = 1
serv_decode.PRE_REGISTER = 1
```

---

### R-6: 内部 Net 信号节点补全 [P1]

**描述**：将内部 Net 信号添加到节点列表

**状态**：NetlistGraph 只显示 Port/State 节点，内部 Net 不可见

---

### R-7: generate 语句处理 [P2]

**描述**：识别和处理 `generate` 语句，支持条件实例化

---

### R-8: 组合逻辑信号驱动关系补全 [P1]

**描述**：i_cmp_sig, i_bool_op, result_slt 等信号的驱动关系

---

### R-9: 跨实例信号追踪 [P2]

**描述**：追踪模块间连接

**前置条件**：先实现 R-1（实例节点解析）

---

### R-10: 结构体/typedef 支持 [P2]

**描述**：支持 SystemVerilog 的结构体和 typedef 类型

---

## Issue → 需求映射

| Issue | 对应需求 |
|-------|----------|
| Issue-B | R-1: 实例节点解析 |
| Issue-C | R-2: 驱动关系修复 ✅ |
| Issue-M | R-3: ContinuousAssign 直接建边 |
| Issue-N | R-3 + R-8: 建边方法 + 组合逻辑 |
| Issue-O | 调试 segfault 原因 |
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

1. **R-3**: ContinuousAssign 直接建边 — 解决 Issue-M, Issue-N
2. **R-1**: 实例节点解析 — 解决 Issue-B
3. **调试 Issue-O**: picorv32 segfault

### 中期（1 个月）

4. **R-5**: parameter 值提取
5. **R-6**: 内部 Net 信号节点补全
6. **R-8**: 组合逻辑信号驱动关系补全

### 长期（持续）

7. **R-7**: generate 语句处理
8. **R-9**: 跨实例信号追踪
9. **R-10**: 结构体/typedef 支持

---

## 测试记录文件

各设计的详细测试记录位于：
- `openchip_qa_results/serv_alu/` (v2)
- `openchip_qa_results/serv_decode/` (v2)
- `openchip_qa_results/darkriscv/` (新增)
- `openchip_qa_results/tiny-gpu/` (新增)
- `openchip_qa_results/clacc_bs_mult/` (v2)

---

*更新：2026-05-18 v3 测试后*