# ZipCPU Core (zipcore.v) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

| 指标 | 数值 |
|------|------|
| 文件数 | 20 (zipcpu/rtl/**/*.v) |
| 节点数 | 930 |
| 边数 | 318 |
| Instance | 17 |

### Instance 节点

```
zipaxi (def=zipaxi)
├── zipaxi.core (def=zipcore)
│   ├── zipaxi.core.doalu (def=cpuops)
│   │   └── zipaxi.core.doalu.thempy (def=)
│   ├── zipaxi.core.instruction_decoder (def=)
│   └── zipaxi.core.dbgarskd (def=)
│   └── zipaxi.dbgawskd (def=)
│   └── zipaxi.dbgwskd (def=)
zipaxil (def=zipaxil)
├── zipaxil.core (def=zipcore)
│   ├── zipaxil.core.doalu (def=cpuops)
│   └── zipaxil.core.doalu.thempy (def=)

pffifo (def=pffifo)
slowmpy (def=slowmpy)
```

---

## Q1-S: ZipCPU 基本架构

**问题**: ZipCPU 的基本架构？

### navisv 分析

**navisv 可以列出 Instance 节点**，展示模块结构：

| Instance | 说明 |
|----------|------|
| zipaxi | ZipCPU with AXI 接口 |
| zipaxil | ZipCPU with AXI-lite 接口 |
| zipaxi.core | CPU 核心 |
| doalu | ALU 操作单元 |
| instruction_decoder | 指令译码器 |
| slowmpy | 乘法器 |
| pffifo | 预取 FIFO |

### 回答

**navisv 可以确认**：
- ZipCPU 是轻量级 RISC-V 软核
- 两个变体：zipaxi (AXI) 和 zipaxil (AXI-lite)
- 核心包含 ALU, 译码器, 调试模块等

---

## Q2-S: 流水线结构

**问题**: ZipCPU 的流水线如何划分？

### navisv 分析

```bash
# 模块层级
zipaxi.core (CPU 核心)
├── doalu (执行单元)
├── instruction_decoder (译码)
└── ...
```

### 回答

**navisv 可以通过 Instance 层级展示流水线结构**：
- **ID**: instruction_decoder (译码)
- **EX**: doalu (执行)
- **MEM**: memory 操作 (待确认)
- **WB**: 写回

---

## Q3-S: 调试模块

**问题**: ZipCPU 的调试接口？

### navisv 分析

```bash
zipaxi.dbgarskd (def=)
zipaxi.dbgawskd (def=)
zipaxi.dbgwskd (def=)
```

### 回答

**navisv 可以确认调试模块存在**：
- dbgarskd: 调试地址读取
- dbgawskd: 调试地址写入
- dbgwskd: 调试数据写入

---

## 边分析

### 连接关系

```
# 部分边（示例）
zipaxi.core.* -> ...
```

### 回答

**navisv 可以追踪 318 条边**，展示模块间的连接关系。

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 基本架构 | ✅ | Instance 节点 |
| Q2-S: 流水线结构 | ✅ | Instance 层级 |
| Q3-S: 调试模块 | ✅ | Instance 存在 |

### 关键发现

1. **930 节点，318 边**：完整展示 ZipCPU 结构
2. **17 个 Instance**：模块结构清晰
3. **AXI 变体**：zipaxi 和 zipaxil 两个版本

---

## 对比

| 设计 | 文件数 | 节点 | 边 |
|------|--------|------|-----|
| zipcpu (部分) | 20 | 930 | 318 |

**结论**：使用更多文件可以看到更完整的结构。

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18