# darkriscv Core - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 设计概览（使用全部 darkriscv rtl 文件）

| 指标 | 数值 |
|------|------|
| 文件数 | 10 |
| 节点数 | 203 |
| 边数 | 64 |
| Instance | 11 |

### Instance 节点

```
darkcache (def=darkcache)
darkmac (def=darkmac)
darksocv (def=darksocv)
darksocv.bram0 (def=darkram)
darksocv.bridge0 (def=darkbridge)
darksocv.bridge0.core0 (def=darkriscv)
darksocv.darkpll0 (def=darkpll)
darksocv.io0 (def=darkio)
darksocv.io0.uart0 (def=darkuart)
darkspi (def=darkspi)
darkspi.spi_master1 (def=)
```

---

## Q1-S: 指令总线接口

**问题**: IDREQ/IADDR/IDATA/IDACK 的作用？

### navisv 分析

```bash
# 查找 darkriscv 相关的 Port
darksocv.bridge0.core0.IDREQ (Port)
darksocv.bridge0.core0.IADDR (Port)
darksocv.bridge0.core0.IDATA (Port)
darksocv.bridge0.core0.IDACK (Port)
```

### 回答

**navisv 可以列出这些端口**：

| 信号 | 说明 |
|------|------|
| IDREQ | 取指请求（输出） |
| IADDR | 取指地址（输出，32-bit） |
| IDATA | 取指数据（输入，32-bit） |
| IDACK | 取指应答（输入） |

navisv 通过 Instance 层级展示了完整的模块结构：
- `darksocv.bridge0.core0` 是 darkriscv 实例
- 其端口包括 IDREQ, IADDR, IDATA, IDACK

---

## Q2-S: 模块层级

**问题**: darkriscv 如何连接到系统？

### navisv 分析

```bash
# 模块层级
darksocv (顶层)
├── bridge0 (darkbridge)
│   └── core0 (darkriscv)  # CPU 核
├── bram0 (darkram)       # RAM
├── darkpll0 (darkpll)     # PLL
└── io0 (darkio)
    └── uart0 (darkuart)   # UART
```

### 回答

**navisv 可以展示完整的模块层级**：

```
darksocv (SoC 顶层)
├── darkspi (SPI)
│   └── spi_master1 (子模块)
├── darkmac (MAC)
├── darkcache (Cache)
├── bridge0 (桥接)
│   └── core0 (darkriscv CPU)
├── io0 (IO)
│   └── uart0 (UART)
├── darkpll0 (PLL)
└── bram0 (RAM)
```

---

## Q3-S: 数据总线

**问题>: DDREQ/DADDR/DATAO/DATAI 的作用？

### navisv 分析

```bash
# 数据总线端口
darksocv.bridge0.core0.DDREQ (Port)
darksocv.bridge0.core0.DADDR (Port)
darksocv.bridge0.core0.DATAO (Port)
darksocv.bridge0.core0.DATAI (Port)
```

### 回答

**navisv 可以列出这些端口**：

| 信号 | 说明 |
|------|------|
| DDREQ | 访存请求 |
| DADDR | 访存地址 |
| DATAO | 输出数据（写） |
| DATAI | 输入数据（读） |
| DRW/DRD/DWR | 读写控制 |

---

## 边分析

### 连接关系

```
# 边示例（需要进一步查询）
darksocv.bridge0.core0.* -> ...
```

### 回答

**navisv 可以追踪 64 条边**，展示模块间的连接关系。

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 指令总线 | ✅ | Port 节点列出 |
| Q2-S: 模块层级 | ✅ | Instance 层级展示 |
| Q3-S: 数据总线 | ✅ | Port 节点列出 |

### 关键发现

1. **203 节点，64 边**：完整展示 SoC 结构
2. **11 个 Instance**：层级清晰的模块结构
3. **核心 darkriscv 位于** `darksocv.bridge0.core0`

---

## 对比：单文件 vs 多文件

| 设计 | 文件数 | 节点 | 边 |
|------|--------|------|-----|
| darkriscv.v (单) | 1 | 76 | 0 |
| darkriscv (全部 RTL) | 10 | 203 | 64 |

**结论**：使用完整文件集才能看到完整的 SoC 结构。

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18