# navisv 验证覆盖率与风险分析

本文档介绍 navisv 新增的四个验证分析功能：**时序关系分析**、**SVA对齐检查**、**验证覆盖率地图**、**信号风险分析**。

## 功能总览

| 命令 | 功能 | 核心价值 |
|------|------|----------|
| `navisv temporal` | 时序关系分析 | 自动发现信号间的时序约束（组合延迟、寄存器延迟） |
| `navisv sva-align` | SVA 时序对齐 | 检查 SVA 是否与RTL 时序一致 |
| `navisv verify-map` | 验证覆盖地图 | 叠加 SVA + Coverage，识别未验证的信号 |
| `navisv risk` | 信号风险分析 | 基于图拓扑评估功能+时序复杂度，输出关键路径 |

---

## 1. temporal — 时序关系分析

### 功能

从 RTL 信号图中自动分析信号间的时序关系：**组合延迟路径**和**寄存器延迟路径**。

### 算法

1. **构建时序图**：解析每个信号的 `timing` 属性（`combinational`/`state`/`port`）
2. **BFS 传播延迟**：从源信号出发，按层级传播延迟
   - 组合逻辑：`out_delay = in_delay + 1`
   - 寄存器：`out_delay = in_delay + 1`（时钟周期）
3. **收集时序路径**：目标信号的所有上游路径及总延迟

### CLI

```bash
navisv temporal <file.sv> [src] [dst] [--depth N]

# 示例：分析单条路径
navisv temporal uart_controller.sv uart_rx_d1 uart_tx_o

# 示例：批量分析（省略 src/dst）
navisv temporal uart_controller.sv --depth 3
```

### 输出格式

**Text (默认)：**
```
时序关系 (延迟从大到小):
  uart_tx_o           总延迟=15  组合=6  寄存器=9  时钟域=uart_clk_i
    ← parity_bit      组合+1
    ← check_bit       组合+1
    ← curr_state     组合+1
    ← tik_count      寄存器+1
    ...
```

**JSON：**
```json
{
  "module": "uart_controller",
  "timing_paths": [
    {
      "target": "uart_tx_o",
      "total_delay": 15,
      "combinational_delay": 6,
      "register_delay": 9,
      "clock_domain": "uart_clk_i",
      "path": ["uart_rx_d1", "...", "parity_bit", "uart_tx_o"]
    }
  ]
}
```

---

## 2. sva-align — SVA 时序对齐检查

### 功能

分析 RTL 时序图与 SVA assertions 的一致性，发现以下问题：

| 问题类型 | 描述 |
|----------|------|
| **时序过松** | SVA 要求的延迟比 RTL 实际长 → 假pass |
| **时序过严** | SVA 要求的延迟比 RTL 实际短 → 假fail |
| **缺少SVA** | 关键信号路径没有 assertion |

### CLI

```bash
navisv sva-align <file.sv> [--min-latency N] [--limit N]

# 示例
navisv sva-align top.sv -l 2 -n 20
```

### 输出格式

**Text：**
```
=== SVA 时序对齐检查 ===
总 SVA: 24  匹配: 18  警告: 4  错误: 2

警告 (RTL 比 SVA 快，可能假fail):
  tx_valid: RTL=2 cycle  SVA=3 cycle  差=-1
  rx_ready: RTL=1 cycle  SVA=2 cycle  差=-1

错误 (RTL 比 SVA 慢，可能假pass):
  data_valid: RTL=5 cycle  SVA=3 cycle  差=+2
```

---

## 3. verify-map — 验证覆盖率地图

### 功能

在信号关系图上叠加 **SVA 覆盖** 和 **CoverGroup 覆盖**，直观展示：
- 🔵 **双覆盖**：同时有 SVA 和 CoverGroup
- 🟡 **仅SVA**：只有 assertion
- 🔷 **仅CG**：只有 covergroup
- 🔴 **未覆盖**：没有任何验证

### CLI

```bash
navisv verify-map <file.sv> [-m MODULE] [-n LIMIT] [-f text|json|dot|mermaid|all] [-o OUTPUT]

# 示例：输出所有格式
navisv verify-map uart_controller.sv -f all -o /tmp/verify

# 示例：只显示未覆盖信号
navisv verify-map uart_controller.sv -n 30
```

### 节点颜色规则

| 颜色 | 覆盖状态 |
|------|----------|
| 🟢 绿色 | SVA + CG 双覆盖 |
| 🟡 黄色 | 仅 SVA |
| 🔵 蓝色 | 仅 CG |
| 🔴 红色 | 未覆盖 |

### 边类型

| 边类型 | 样式 |
|--------|------|
| 组合逻辑 | 蓝色虚线 |
| 寄存器 | 红色实线 |
| 条件控制 | 橙色实线 |

---

## 4. risk — 信号风险/复杂度分析

### 功能

基于有向信号图的拓扑指标，自动评估每个信号的风险等级，从**功能逻辑复杂度**和**时序复杂度**两个维度打分。

### 评分体系

**功能逻辑复杂度 (0-100)：**

| 指标 | 权重 | 说明 |
|------|------|------|
| 入度 | 0-30 | 多源驱动风险 |
| 出度 | 0-25 | 扇出过大大驱动能力 |
| Fan-in 锥 | 0-15 | 上游影响范围 |
| Fan-out 锥 | 0-15 | 下游影响范围 |
| Betweenness | 0-15 | 路径枢纽程度 |
| 位宽 | 0-15 | 位级bug风险 |

**时序复杂度 (0-100)：**

| 指标 | 权重 | 说明 |
|------|------|------|
| 寄存器 | 0-20 | 有状态存储 |
| 时钟域 | 0-30 | 跨时钟域风险 |
| 寄存器链深度 | 0-25 | 经过几级寄存器 |
| 时序 fan-in | 0-15 | 上游时序路径数 |
| 时序 fan-out | 0-10 | 下游时序路径数 |

**综合得分：**
```
total = max(func, timing) + 0.3 × min(func, timing)
```

### 风险等级

| 等级 | 分数 | 颜色 | 含义 |
|------|------|------|------|
| critical | ≥80 | 🔴 | 高功能+高时序，需重点关注 |
| high | ≥60 | 🟠 | 单维度高，需验证覆盖 |
| medium | ≥40 | 🟡 | 中等复杂度 |
| low | <40 | 🟢 | 低风险 |

### CLI

```bash
navisv risk <file.sv> [-m MODULE] [-n LIMIT] [-f text|json|dot|mermaid|all] [-o OUTPUT]

# 示例：文本报告
navisv risk uart_controller.sv

# 示例：输出所有格式
navisv risk uart_controller.sv -f all -o /tmp/risk

# 示例：只看高风险信号
navisv risk uart_controller.sv -n 20
```

### 输出内容

**Text 报告：**
```
=== 信号风险分析: uart_controller ===

图指标:
  节点: 229  边: 490
  强连通分量: 148 (最大: 69)
  最大入度: 19  最大出度: 22

风险分布:
  🔴 critical: 5
  🟠 high:    18
  🟡 medium:  26
  🟢 low:     180

Top 5 高风险信号:
  reg_data_o           综合=88.0  功能=70.0  时序=60.0  入度=13
    因素: 高入度(13), 8-bit, 寄存器
  parity_rcvd          综合=83.5  功能=45.0  时序=70.0
    因素: 寄存器链(7级), 时钟域(1)
  next_state           综合=82.5  功能=75.0  时序=25.0
    因素: 入度=19(最高), 出度=14, FSM核心

二维分布矩阵:
  功能/时序          <40    40-60    >=60
  ------------------------------------
  低(<40)            183       7        7
  中(40-60)           13       6        8
  高(>=60)             3       1        1

时序关键路径 (Top 3):
  1: uart_rst_n → stop_bit_1_done → curr_state → data → check_bit → parity_bit → uart_tx_o (深度=8)
  2: uart_rst_n → stop_bit_1_done → curr_state → data → check_bit → parity_bit (深度=7)
```

**JSON（Agent 读取）：**
```json
{
  "module": "uart_controller",
  "graph_metrics": {
    "nodes": 229,
    "edges": 490,
    "is_dag": false,
    "scc_count": 148,
    "scc_max_size": 69
  },
  "summary": {
    "total_nodes": 229,
    "critical_nodes": 5,
    "high_risk_nodes": 18,
    "medium_risk_nodes": 26,
    "low_risk_nodes": 180
  },
  "nodes": [
    {
      "signal": "reg_data_o",
      "full_path": "uart_controller.reg_data_o",
      "func_complexity": 70.0,
      "timing_complexity": 60.0,
      "total_score": 88.0,
      "risk_level": "critical",
      "in_degree": 13,
      "out_degree": 5,
      "fanin": 23,
      "fanout": 18,
      "bit_width": 8,
      "func_factors": ["高入度(13)", "8-bit", "寄存器"],
      "timing_factors": ["寄存器", "寄存器链(3级)"]
    }
  ],
  "critical_paths": [
    {
      "path": ["uart_rst_n_i", "stop_bit_1_done", "curr_state", "data", "check_bit", "parity_bit", "uart_tx_o"],
      "depth": 8,
      "source": "uart_rst_n_i",
      "target": "uart_tx_o"
    }
  ]
}
```

---

## 全局选项

所有命令共享以下全局选项：

```bash
--format {text|json|dot|mermaid|all}, -f {text|json|dot|mermaid|all}
    text   - 默认，人类可读文本
    json   - 结构化 JSON（Agent 精确读取）
    dot    - Graphviz DOT 图
    mermaid - Mermaid 图（可直接粘贴到 GitHub/Typora）
    all    - 同时输出所有格式

--output OUTPUT, -o OUTPUT
    输出文件路径
    all 模式下：指定目录或文件名前缀
    示例：-o /tmp/risk  → /tmp/risk.json, /tmp/risk.mmd, /tmp/risk.dot

--include INCLUDE, -I INCLUDE
    include 目录（与 --format 同级选项）
```

---

## 实际测试结果

### UART-Implementation (229节点)

| 指标 | 值 |
|------|-----|
| 节点/边 | 229N 488E |
| critical | 5 |
| high | 18 |
| 关键路径深度 | 8 级 |
| Top 风险 | reg_data_o (88.0), parity_rcvd (83.5), next_state (82.5) |

### OpenTitan UART (2290节点, 40文件)

| 指标 | 值 |
|------|-----|
| 节点/边 | 2290N 7055E |
| critical | 0 |
| high | 17 |
| 关键路径深度 | 4 级 |
| Top 风险 | reg2hw (76.5), rdata_q (74.0), rx_valid_q (71.5) |

### 准确性问题修复记录

**问题**：入度虚高（时钟/复位边被计为数据边）、CDC 误报（rst_ni 被当独立时钟域）

**修复**：引入 `_data_graph` 纯数据图，排除 `PosEdge`/`NegEdge` 边

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| rdata_q 入度 | 10 | 8 ✓ |
| CDC 误报 | 110 | 0 ✓ |