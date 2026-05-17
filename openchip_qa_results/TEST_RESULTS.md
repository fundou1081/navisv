# OpenChip QA 测试结果 - navisv v0.8.0

> 测试日期：2026-05-17
> 测试工具：navisv CLI + Python API
> 测试项目：按 PROJECT_PLAN.md 顺序

---

## Issue 发现记录

| Issue | 描述 | 影响 | 发现项目 |
|-------|------|------|----------|
| **Issue-A** | getDrivers() 对输入端口返回 self-loop 驱动 | 输入端口被视为"自己驱动自己" | clacc/bs_mult, bs_mult_slice |
| **Issue-B** | 实例（bs_mult_slice）未被解析为节点 | 顶层只有 11 个节点，缺少 31 个实例 | clacc/bs_mult |

---

## 功能覆盖度对比（sv_query vs navisv）

| 功能 | sv_query | navisv | 说明 |
|------|----------|--------|------|
| 模块识别 | ✅ | ✅ | |
| 实例解析（bs_mult 31个slice）| ✅ | ❌ | navisv 只解析到 11 个节点 |
| 参数提取 | ✅ | N/A | navisv 未实现 |
| 端口解析（ANSI）| ✅ | ✅ | dual_clock_fifo 10端口正确 |
| 端口解析（非ANSI）| ❌ | ✅ | bs_mult 非ANSI端口正确解析为节点 |
| 驱动关系（内部wire）| ✅ | ⚠️ | self-loop 问题 |
| 连接追踪 | ✅ | ⚠️ | 边数量不足 |

---

## 详细测试记录

### 项目 1: clacc

#### clacc/bs_mult（已完成）

**设计路径**：`~/my_dv_proj/clacc/bs_mult.v`

**设计概况**：
- 乘法器顶层，调用 31 个 bs_mult_slice
- 非ANSI端口声明：`module bs_mult(clk, x, y, p, firstbit, lastbit);`
- 内部 wire：xy, pout[29:0], rout[30:0], cout[30:0]

**navisv 分析结果**：
```
节点数：11
边数：6（全为 self-loop）
模块：bs_mult
```

**预期 vs 实际**：
| 指标 | sv_query 预期 | navisv 实际 |
|------|--------------|-------------|
| 节点数 | ~50+ | 11 |
| 边数 | ~100+ | 6（全 self-loop）|
| 实例数 | 31 | 0 |

**根本原因**：
1. navisv 只解析了当前模块的信号（Variable/Port/Net），未解析实例
2. `_add_edges_from_slang` 中 `body.find(name)` 对内部信号查找结果不准确

**Issue-A 验证**：
```python
mgr.getDrivers(body.find('x'))
# 返回：source=DriverSource.Other, path.rootSymbol=bs_mult.x (self-loop)
# 预期：输入端口 x 应该有 0 个内部驱动
```

**Issue-B 验证**：
```bash
navisv 只添加了 11 个节点（6个端口 + 5个wire）
缺少 31 个 bs_mult_slice 实例
```

**影响分析**：
- 无法通过 navisv 分析 bs_mult 乘法器的内部连接结构
- ImpactAnalysisApp 和 SignalProfileApp 的结果不可靠

---

#### clacc/dual_clock_fifo（已完成）

**设计路径**：`~/my_dv_proj/clacc/dual_clock_fifo.v`

**navisv 分析结果**：
```
节点数：19
边数：19（全为 self-loop）
模块：dual_clock_fifo
端口：10 个（wr_* 和 rd_*）
```

**问题**：所有边都是 self-loop，与 bs_mult 相同

**功能覆盖度**：
| 功能 | 状态 | 说明 |
|------|------|------|
| 端口解析 | ✅ | 10 个端口正确识别 |
| 模块识别 | ✅ | 1 个模块 |
| 内部信号 | ✅ | 9 个内部 wire 节点 |
| 驱动关系 | ❌ | self-loop 问题 |

---

#### clacc/bs_mult_slice（已完成）

**设计路径**：`~/my_dv_proj/clacc/bs_mult_slice.v`

**navisv 分析结果**：
```
节点数：18
边数：17（全为 self-loop）
```

**问题**：同上，所有边 self-loop

---

### 待测试项目

- [ ] clacc/mult_pipe2
- [ ] clacc/pe
- [ ] serv（多个模块）
- [ ] cva6
- [ ] nvdla
- [ ] opentitan（其他模块）
- [ ] verilog-axi
- [ ] 其他

---

## 功能需求发现（navisv 缺失功能）

| Req | 描述 | 优先级 | 说明 |
|-----|------|--------|------|
| **R-1** | 实例节点解析 | P0 | 应将实例添加为节点 |
| **R-2** | 驱动关系修复 | P0 | getDrivers self-loop 需甄别 |
| **R-3** | 参数提取 | P2 | 支持 parameter 解析 |
| **R-4** | 非ANSI端口支持 | ✅ | 已支持 |

---

*持续更新中*