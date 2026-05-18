# OpenChip QA - cva6/cva6 测试记录

> 测试时间：2026-05-18
> 设计路径：~/my_dv_proj/cva6/core/cva6.sv
> navisv 版本：v0.8.0 (with NetlistGraph BFS fallback)

---

## 设计基本信息

| 属性 | 值 |
|------|-----|
| navisv 节点数 | 253 |
| navisv 边数 | 0 |
| NetlistGraph 内部节点 | 11 |
| NetlistGraph 可见节点 | 10 (全部 Input Port) |

---

## navisv 结果分析

### 为什么边数为 0？

**原因**：
1. NetlistGraph 只有 10 个可见节点，全部是 Input Port
2. 没有 Output Port，因此没有信号被"驱动"
3. 即使有内部信号，也无法追踪到外部驱动源
4. 这是一个 **大型顶层模块**，内部有大量子模块实例

### NetlistGraph 可见节点

| 类型 | 数量 |
|------|------|
| Input Port | 10 |
| Output Port | 0 |

---

## Issue 发现

| Issue | 描述 | 影响 |
|-------|------|------|
| **Issue-L** | cva6 是大型顶层模块，NetlistGraph 只看到 10 个 Input Port | 边数为 0，无法回答任何问题 |
| **Issue-B** | 子模块实例未被解析 | 无法看到 decoder, alu, csr 等内部结构 |

---

## 问题回答记录

### Q1-S: CVA6 架构

**问题**: CVA6 是什么类型的处理器？

**navisv 提取**: 无法提取

**回答**: navisv 无法回答。CVA6 是 64-bit RISC-V 超标量应用处理器，支持 RV64GC 指令集和 Linux。

**来源**: VERIFICATION_QUESTIONS.md

---

### Q2-S: 流水线结构

**问题**: CVA6 的流水线是如何组织的？

**navisv 提取**: 无法提取

**回答**: navisv 无法回答。4 级流水线：Fetch → Decode → Execute → Writeback。

**来源**: VERIFICATION_QUESTIONS.md

---

### Q3-S: 分支预测

**问题**: CVA6 如何处理分支？

**navisv 提取**: 无法提取

**回答**: navisv 无法回答。硬件分支预测，Scoreboard 追踪预测状态。

**来源**: VERIFICATION_QUESTIONS.md

---

### Q4-S: 异常处理

**问题**: `exception_t` 结构包含什么？

**navisv 提取**: 无法提取

**回答**: navisv 无法回答。包含 cause, tval, tval2, tinst, gva, valid 字段。

**来源**: VERIFICATION_QUESTIONS.md

---

### Q5-C: 缓存接口

**问题**: I-Cache 和 D-Cache 的请求/响应格式？

**navisv 提取**: 无法提取

**回答**: navisv 无法回答。

**来源**: VERIFICATION_QUESTIONS.md

---

## navisv 限制总结

1. **大型顶层模块**：253 个节点，0 条边
2. **NetlistGraph 可见性**：只看到 10 个 Input Port
3. **缺少实例解析**：无法看到子模块结构
4. **结构复杂度高**：SystemVerilog 类型众多

---

## 功能需求

| Req | 描述 | 优先级 |
|-----|------|--------|
| R-1 | 实例节点解析 | P0 |
| R-5 | parameter 提取 | P1 |
| R-10 | 结构体/typedef 支持 | P2 |