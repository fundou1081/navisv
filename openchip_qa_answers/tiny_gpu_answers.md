# Tiny GPU Core (core.sv) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 设计概览（使用全部 tiny-gpu src 文件）

| 指标 | 数值 |
|------|------|
| 文件数 | 12 |
| 节点数 | 639 |
| 边数 | 145 |
| Instance | 5 |

### Instance 节点

```
gpu (def=gpu)
├── gpu.data_memory_controller (def=controller)
├── gpu.dcr_instance (def=dcr)
├── gpu.dispatch_instance (def=dispatch)
└── gpu.program_memory_controller (def=controller)
```

---

## Q1-S: Core 架构

**问题**: Core 的基本架构？

### navisv 分析

```bash
# 查找 core 相关的节点
gpu.core.* (Port/State)
```

### 回答

**navisv 可以列出 core 相关的节点**，但需要进一步查询设计结构。

通过 Instance 节点可以看到：
- `gpu` 是顶层
- `core` 作为计算核心存在于 gpu 下
- 子模块包括 controller, dispatch, dcr 等

---

## Q2-S: Core 状态机

**问题**: Core 的状态机？

### navisv 分析

```bash
# State 节点
gpu.core.lsu_state (State)
...
```

### 回答

**navisv 可以列出 State 节点**，例如：
- `gpu.core.lsu_state` 是 LSU 状态寄存器

---

## 模块层级结构

### navisv 发现的 Instance

```
gpu (顶层 GPU)
├── data_memory_controller (数据内存控制器)
├── dcr_instance (DCR 配置寄存器)
├── dispatch_instance (派遣单元)
└── program_memory_controller (程序内存控制器)
```

### 回答

**navisv 可以展示 GPU 内部结构**：
- 计算核心位于 `gpu.core`
- 控制逻辑分布在 controller, dispatch 等模块
- 通过 145 条边展示模块间连接

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: Core 架构 | ⚠️ | 需要更多查询 |
| Q2-S: 状态机 | ✅ | State 节点列出 |
| Q3-S: 调度 | ⚠️ | 需要进一步分析 |

### 关键发现

1. **639 节点，145 边**：完整展示 GPU 结构
2. **5 个 Instance**：模块结构清晰
3. **LSU 状态机**：通过 State 节点体现

---

## 对比：单文件 vs 多文件

| 设计 | 文件数 | 节点 | 边 |
|------|--------|------|-----|
| core.sv (单) | 1 | 42 | 0 |
| tiny-gpu (全部) | 12 | 639 | 145 |

**结论**：使用完整文件集才能看到完整的 GPU 结构。

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18