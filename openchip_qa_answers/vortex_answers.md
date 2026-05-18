# Vortex GPU (Vortex.sv) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

| 指标 | 数值 |
|------|------|
| 文件数 | 6 (Vortex/hw/rtl/*.sv) |
| 节点数 | 39 |
| 边数 | 0 |

### Instance 节点

```
Vortex_axi (def=Vortex_axi)
├── Vortex_axi.axi_adapter (def=)
├── Vortex_axi.vortex (def=Vortex)
│   ├── Vortex_axi.vortex.__buffer_ex161 (def=)
│   ├── Vortex_axi.vortex.__l3_reset (def=)
│   ├── Vortex_axi.vortex.dcr_bus_if (def=)
│   ├── Vortex_axi.vortex.l3cache (def=)
│   ├── Vortex_axi.vortex.mem_bus_if (def=)
│   └── Vortex_axi.vortex.per_cluster_mem_bus_if (def=)
```

---

## Q1-S: Vortex 基本架构

**问题**: Vortex GPU 的基本架构？

### navisv 分析

**navisv 可以列出 Instance 节点**，展示模块结构：

| Instance | 说明 |
|----------|------|
| Vortex_axi | 顶层 AXI 接口 |
| axi_adapter | AXI 适配器 |
| vortex | GPU 核心 |
| l3cache | L3 缓存 |
| mem_bus_if | 内存总线接口 |

### 回答

**navisv 可以确认**：
- Vortex 是 GPU 架构
- 顶层 Vortex_axi 处理 AXI 总线接口
- 内部 Vortex 核心包含 l3cache, mem_bus_if 等模块

---

## Q2-S: 子模块结构

**问题**: Vortex 内部包含哪些计算资源？

### navisv 分析

```bash
# Instance 节点
Vortex_axi.vortex.__buffer_ex161
Vortex_axi.vortex.__l3_reset
Vortex_axi.vortex.dcr_bus_if
Vortex_axi.vortex.l3cache
Vortex_axi.vortex.mem_bus_if
```

### 回答

**navisv 可以通过 Instance 层级展示**：
- `dcr_bus_if`: DCR 总线接口
- `l3cache`: L3 缓存
- `mem_bus_if`: 内存总线接口
- `per_cluster_mem_bus_if`: 每集群内存接口

---

## 问题分析

### 为什么边数为 0？

可能原因：
1. **设计文件不完整** - 需要更多依赖文件
2. **Vortex 复杂** - 包含大量generate和参数化模块

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: 基本架构 | ✅ | Instance 节点 |
| Q2-S: 子模块结构 | ✅ | Instance 层级 |

### 关键发现

1. **39 节点，0 边**：可能缺少依赖文件
2. **Vortex_axi 顶层**：包含 AXI 接口
3. **内部模块**：l3cache, mem_bus_if 等

---

## Issue 收集

| Issue | 描述 | 来源 |
|-------|------|------|
| - | Vortex 可能需要更多依赖文件 | Q1-Q2 |

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18