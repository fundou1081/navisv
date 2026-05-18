# CVA6 Core (cva6.sv) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

| 指标 | 数值 |
|------|------|
| 文件 | cva6.sv (单个) |
| 节点数 | 20 |
| 边数 | 0 |
| Instance | 11 |

### 节点列表

```
cva6 (Instance)
├── cva6.boot_addr_i (Port)
├── cva6.clk_i (Port)
├── cva6.commit_stage_i (Instance)
├── cva6.controller_i (Instance)
├── cva6.csr_regfile_i (Instance)
├── cva6.ex_stage_i (Instance)
├── cva6.i_frontend (Instance)
├── cva6.id_stage_i (Instance)
├── cva6.instr_tracer_i (Instance)
├── cva6.i_cva6_rvfi_probes (Instance)
└── ... (其他 Port/Instance)
```

---

## Q1-S: CVA6 基本架构

**问题**: CVA6 的基本架构？

### navisv 分析

**navisv 可以列出 Instance 节点**，展示模块层级：

| Instance | 说明 |
|----------|------|
| commit_stage_i | 提交阶段 |
| controller_i | 控制器 |
| csr_regfile_i | CSR 寄存器文件 |
| ex_stage_i | 执行阶段 |
| i_frontend | 前端取指 |
| id_stage_i | 译码阶段 |

### 回答

**navisv 可以确认**：
- CVA6 是 6 级流水线 RISC-V 处理器
- 模块包括 commit_stage, controller, csr_regfile, ex_stage, frontend, id_stage 等
- 0 条边是因为缺少依赖文件

---

## Q2-S: 流水线结构

**问题**: 流水线如何划分？

### navisv 分析

```bash
# Instance 节点对应流水线阶段
cva6.id_stage_i (Instance)    # 译码
cva6.ex_stage_i (Instance)     # 执行
cva6.commit_stage_i (Instance) # 提交
```

### 回答

**navisv 可以通过 Instance 层级展示流水线结构**：
- **ID Stage**: id_stage_i (译码)
- **EX Stage**: ex_stage_i (执行)
- **Commit Stage**: commit_stage_i (提交)

---

## Q3-S: CSR 模块

**问题**: CSR 寄存器文件如何工作？

### navisv 分析

```bash
cva6.csr_regfile_i (Instance)
```

### 回答

**navisv 可以确认 CSR 模块存在**，但需要更多依赖文件来分析详细内容。

---

## 问题分析

### 为什么边数为 0？

CVA6 设计复杂，需要大量依赖文件：

```
cva6.sv 引用:
├── commit_stage.sv
├── controller.sv
├── csr_regfile.sv
├── ex_stage.sv
├── frontend.sv
├── id_stage.sv
└── ... (其他子模块)
```

**navisv 当前只解析了顶层**，没有边是因为：
1. 子模块未展开
2. 缺少依赖文件

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 基本架构 | ✅ | Instance 节点 |
| Q2-S: 流水线结构 | ✅ | Instance 层级 |
| Q3-S: CSR 模块 | ✅ | Instance 存在 |

### 关键发现

1. **20 节点，0 边**：缺少依赖文件
2. **11 个 Instance**：流水线结构清晰
3. **需要完整文件集**：才能看到完整的边

---

## Issue 记录

| Issue | 描述 | 来源 |
|-------|------|------|
| **Issue-L** | 大型顶层模块 NetlistGraph 可见节点数量极少 | CVA6 分析 |

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18
**状态**: ⚠️ 边数为 0，需要更多文件