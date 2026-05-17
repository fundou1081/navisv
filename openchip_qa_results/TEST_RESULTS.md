# OpenChip QA 测试结果 - navisv v0.8.0

> 测试日期：2026-05-17
> 测试工具：navisv CLI + Python API
> 测试项目：按 PROJECT_PLAN.md 顺序

---

## 测试设计汇总

| 设计 | 节点数 | 边数 | 实际边 | Self边 | 模块数 |
|------|--------|------|--------|--------|--------|
| i2c_core | 161 | 0 | 0 | 0 | 1 |
| serv_decode | 101 | 0 | 0 | 0 | 1 |
| serv_alu | 24 | 0 | 0 | 0 | 1 |
| serv_top | 124 | 0 | 0 | 0 | 1 |
| bs_mult | 11 | 0 | 0 | 0 | 1 |
| dual_clock_fifo | 19 | 0 | 0 | 0 | 1 |
| cva6 | 253 | 0 | 0 | 0 | 1 |

---

## Issue 发现记录

| Issue | 描述 | 影响 | 发现项目 |
|-------|------|------|----------|
| **Issue-C** | getDrivers() 对 Net 全返回 self-loop | **所有设计的边数归零**，无法进行驱动关系分析 | 所有测试设计 |
| **Issue-B** | 实例（bs_mult_slice）未被解析为节点 | 顶层节点数量远少于实际 | clacc/bs_mult |

---

## 功能覆盖度分析

| 功能 | 状态 | 说明 |
|------|------|------|
| 模块识别 | ✅ | 正确识别所有设计模块 |
| 端口解析（ANSI/非ANSI）| ✅ | 非ANSI bs_mult 端口正确解析 |
| 实例解析 | ❌ | 缺少 bs_mult_slice 等实例节点 |
| 节点解析 | ✅ | 信号节点（Net/Port/Variable）正确添加 |
| 驱动关系（跨信号）| ❌ | slang getDrivers() 全返回 self-loop |
| 逻辑锥（fanin/fanout）| ⚠️ | 节点存在，但无边时结果为空 |
| 信号搜索（FindSignalsApp）| ✅ | 正常工作 |
| 信号属性（tags/模块）| ⚠️ | 节点存在但 tags 大多为空集 |

---

## 详细测试记录

### clacc/bs_mult

**设计路径**：`~/my_dv_proj/clacc/bs_mult.v`

**问题**：
- 预期 31 个 bs_mult_slice 实例未被解析为节点
- slang getDrivers() 返回 self-loop，修复后边数归零

**navisv 结果**：11 nodes, 0 edges

**根本原因**：slang getDrivers() 的局限性

---

### clacc/dual_clock_fifo

**设计路径**：`~/my_dv_proj/clacc/dual_clock_fifo.v`

**navisv 结果**：19 nodes, 0 edges

**功能覆盖**：
| 功能 | 状态 |
|------|------|
| 端口解析 | ✅ 10 个端口正确 |
| 节点解析 | ✅ 9 个 wire |
| 驱动关系 | ❌ 全 self-loop |

---

### serv_alu

**设计路径**：`~/my_dv_proj/serv/rtl/serv_alu.v`

**分析**：
```
24 signals: clk, i_en, i_cnt0, o_cmp, i_sub, i_bool_op, ...
24 nodes, 0 edges

所有 signals 都是 self-loop:
- result_add: driver=result_add (self)
- add_cy: driver=add_cy (self)
- o_rd: driver=o_rd (self)
- ...
```

**根本原因**：slang getDrivers() 对 Net 类型信号的返回值 driver.path.rootSymbol == self

---

## 功能需求发现

| Req | 描述 | 优先级 | 说明 |
|-----|------|--------|------|
| **R-1** | 实例节点解析 | P0 | 将 Instance 添加为节点（当前只有 Net/Port/Variable）|
| **R-2** | 驱动关系修复 | P0 | slang getDrivers() self-loop 问题的替代方案 |
| **R-3** | StatementExplorer 完善 | P1 | 补全端口 tags、wire 类型标签 |
| **R-4** | 参数提取 | P2 | 支持 parameter 解析 |

---

## 后续行动

### 短期（Issue 修复）
1. 确认 self-loop 是 slang getDrivers() 行为还是 navisv 解析问题
2. 考虑通过 StatementExplorer 直接从 always/assign 语句提取驱动关系
3. 实现实例节点解析

### 长期
1. 完善端口标签系统（port_input / port_output）
2. 添加参数解析支持
3. 完善信号类型标签（wire/register/reg）

---

*持续更新中*
*每测试一个项目，在此记录结果和发现的问题*