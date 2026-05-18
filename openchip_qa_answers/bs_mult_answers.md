# bs_mult (Booth Serial Multiplier) - navisv 回答

> 用 navisv 分析设计，回答验证问题

---

## 设计概览（使用全部 clacc 文件）

| 指标 | 数值 |
|------|------|
| 文件数 | 9 |
| 节点数 | 598 |
| 边数 | 172 |

### bs_mult 相关节点

```
bs_mult (Instance)
  ├── clk, x, y, p, firstbit, lastbit (Port)
  ├── I0 (Instance) - 31 个 slice
  │   └── I0 (Instance) - 子实例
  ├── I1 (Instance)
  │   └── I0 (Instance)
  ├── ...
  └── I30 (Instance)
      └── I0 (Instance)
```

---

## Q1-S: Booth 乘法原理

**问题**: Booth 编码如何减少部分积数量？

### navisv 分析

```bash
# bs_mult_slice 内部信号
bs_mult.I0.xy (Port)  # x & y
bs_mult.I0.x (Port)
bs_mult.I0.y (Port)
```

### 回答

**navisv 可以列出内部信号**：
- `bs_mult.I0.xy` 是 Booth 编码乘积项 (x & y)
- 每个 slice 有 x, y, xy 端口

但 Booth 编码的具体逻辑（00/01/10/11 编码表）需要理解表达式语义，navisv 主要追踪连接关系。

---

## Q2-S: Slice 数量 (31 个)

**问题**: 为什么有 31 个 slice 实例？

### navisv 分析

```bash
# Instance 节点
bs_mult.I0 (Instance)
bs_mult.I1 (Instance)
...
bs_mult.I30 (Instance)

# 每个 slice 有子实例
bs_mult.I0.I0 (Instance)
bs_mult.I1.I0 (Instance)
...
```

### navisv 完整实例列表

```
bs_mult.I0  - slice 0
bs_mult.I1  - slice 1
bs_mult.I2  - slice 2
...
bs_mult.I29 - slice 29
bs_mult.I30 - slice 30 (最后一个，处理 pin_last)
```

### 回答

**navisv 可以确认**：
- 存在 31 个 slice 实例：I0 - I30
- 每个 slice 有子实例 I0（bs_mult_slice 的实现）
- 结构：`bs_mult.I0.I0` 表示 slice I0 的子模块

---

## Q3-S: 数据流

**问题**: 数据如何在 slice 之间流动？

### navisv 边分析

```bash
# 查找 I0 -> I1 之间的连接
# pout[0] -> pin, cout -> cin 等
```

### 回答

**navisv 可以追踪连接关系**：
- 每个 slice 有 pin, pout, cin, cout 端口
- 通过边追踪 p = f(x, y) 数据流
- 172 条边展示了完整的内部连接

---

## 实例层级结构

### navisv 发现

```
bs_mult (顶层)
├── I0 (slice 0)
│   └── I0 (bs_mult_slice 子模块)
├── I1 (slice 1)
│   └── I0
├── I2 (slice 2)
│   └── I0
├── ...
├── I29 (slice 29)
│   └── I0
└── I30 (slice 30, 最后一个)
    └── I0
```

### 每个 Slice 的信号

| 信号类型 | 名称 | 说明 |
|----------|------|------|
| 输入 | x, y, xy | Booth 编码输入 |
| 输入 | pin, rin, cin | 前级传递 |
| 输出 | pout, rout, cout | 传递给下级 |
| 状态 | x_delay, y_delay | 延迟寄存器 |
| 状态 | pin_delay, cout1_delay | 延迟状态 |

---

## navisv 分析总结

| 问题 | navisv 可回答 | 限制 |
|------|---------------|------|
| Q1-S: Booth 原理 | ⚠️ | 信号可见，逻辑需理解 |
| Q2-S: 31 个 slice | ✅ | Instance 节点确认 |
| Q3-S: 数据流 | ✅ | 边追踪 |

### 关键发现

1. **598 节点，172 边**：完整展示了乘法器内部结构
2. **31 个 slice 实例**：I0-I30，层级清晰
3. **子模块嵌套**：每个 slice 有子实例 I0
4. **Booth 编码可见**：xy = x & y 通过端口信号体现

---

## 对比：单文件 vs 多文件

| 设计 | 文件数 | 节点 | 边 |
|------|--------|------|-----|
| bs_mult.v (单) | 1 | 11 | 0 |
| bs_mult + all | 9 | 598 | 172 |

**结论**：使用完整文件集是正确分析设计的前提。

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18