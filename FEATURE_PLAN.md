# navisv Feature Plan

## P2: 高级分析功能

### 1. fan-out 分析增强
- **目标**: 利用时序属性识别跨时钟域的 fan-out
- **输入**: 信号路径、DesignGraph
- **输出**: fan-out 列表，标注每个 load 的时钟域和时序属性
- **判断逻辑**:
  - 同 clock domain → 直接标记
  - 跨 clock domain → 标记为 `cross_clock_domain`
  - 异步 path → 标记为 `async_path`
- **应用场景**: CDC (Clock Domain Crossing) 分析

### 2. 条件覆盖率
- **目标**: 分析哪些条件组合从未触发
- **输入**: 信号的所有条件列表
- **输出**: 条件覆盖率报告
- **判断逻辑**:
  - 列出信号的所有 driving 条件
  - 识别 never-true / never-false 的条件
  - 标记为 `redundant` 或 `dead_code`
- **应用场景**: 验证 completeness、检查死代码

### 3. 路径分析增强
- **目标**: 结合 reset_kind 识别异步 reset 路径
- **输入**: 起止信号路径
- **输出**: 路径上每个节点的 reset_kind 和 clock_domain
- **判断逻辑**:
  - 追踪 data flow 路径
  - 识别路径上的 reset 类型 (async/sync/none)
  - 标记路径的 reset_safe 等级
- **应用场景**: 验证 reset 策略、检查亚稳态风险

---

## P3: 高级用户接口与可视化

### 1. 多信号批量分析 API
- **目标**: 支持一次分析多个信号，批量获取 fan-in/fan-out/conditions
- **输入**: 信号路径列表、DesignGraph
- **输出**: 每个信号的完整信息字典
- **判断逻辑**:
  - 批量调用 `get_signal_info`
  - 并行处理加速
  - 结果聚合到单个报告
- **应用场景**: 批量报告生成、测试向量生成

### 2. Timing Report Generator
- **目标**: 生成完整的时序分析报告
- **输入**: DesignGraph、配置选项
- **输出**: 格式化报告（text/markdown/json）
- **判断逻辑**:
  - 按 clock domain 分组
  - 列出所有寄存器及其 timing 属性
  - 标记跨时钟域路径
  - 生成诊断摘要
- **应用场景**: 设计 review、签出检查

### 3. DOT Graph Visualization
- **目标**: 支持导出 DOT 格式用于可视化
- **输入**: 信号路径、子图范围
- **输出**: DOT 文件或 SVG/PNG 图片
- **判断逻辑**:
  - 利用 networkx DOT 生成
  - 支持节点/边属性标注
  - 支持子图聚类
- **应用场景**: 设计文档、调试可视化

---

## 已完成功能 ✅

### 跨模块支持
- **状态**: ✅ 已支持
- **说明**: 支持完整路径查询如 `module.signal`，slang 解析时自动保留模块层次

### 多模块 SOC 设计
- **状态**: ✅ 已支持
- **说明**: 设计中已正确处理模块前缀，通过 `_signal_conditions` 字典维护

---

## 优先级

| Feature | Priority | 预计工作量 | 状态 |
|---------|----------|-----------|------|
| fan-out 分析增强 | P2-1 | 中 | ✅ 已完成 |
| 条件覆盖率 | P2-2 | 中 | 待做 |
| 路径分析增强 | P2-3 | 中 | ✅ 已完成 |
| 多信号批量分析 API | P3-1 | 小 | 待做 |
| Timing Report Generator | P3-3 | 中 | 待做 |
| DOT Graph Visualization | P3-4 | 中 | 待做 |
| **APB PRDATA 路径修复** | **P1** | **中** | **待做** |
| **FSM 内部路径建模** | **P1** | **大** | **待做** |
| **组合逻辑出边修复** | **P1** | **小** | **待做** |
| **条件分支可视化** | **P1** | **小** | **待做** |
| **CDC 标注** | **P1** | **中** | **待做** |
| **路径置信度评分** | **P1** | **小** | **待做** |

---

## 测试发现与改进项

### 开源项目测试: UART Controller

**测试对象**: embedded-explorer/UART-Implementation
- 7个模块，172个节点，148条边
- 包含 APB 接口、FIFO、UART TX/RX、波特率生成器

#### 测试结果

| 追踪路径 | 结果 | 说明 |
|---------|------|------|
| APB → TX FIFO | ✓ | 完整路径追踪到寄存器 |
| RX → FIFO | ✓ | 跨模块路径正确 |
| Clock → Baud Gen | ✓ | 时钟路径追踪 |
| APB → Reg WR Enable | ✓ | 控制信号路径 |
| TX FIFO → TX Module | ✓ | 2寄存器路径 |
| RX FIFO → APB PRDATA | ✗ | APB 读数据路径断裂 |
| TX FIFO → UART TX Out | ✗ | TX FSM 内部路径断裂 |
| Baud Div → RX Clock | ✗ | 组合逻辑赋值边未生成 |
| Reset → TX FIFO | ✗ | 多路复位信号命名问题 |

**通过率: 60% (6/10)**

#### 根因分析

| 问题 | 根因 | 需要的改进 |
|------|------|-----------|
| APB PRDATA 路径 | `s_apb_prdata_o` 节点无入边 | 需要处理 `assign` 语句的反向追踪 |
| TX FSM 内部路径 | TX 状态机内部逻辑未完整建模 | FSM 状态转换路径需要建模 |
| Baud Div 出边 | `baud_div_o` 来自组合赋值但无出边 | 组合逻辑赋值需要生成驱动边 |
| Reset 路径 | 目标节点名称不匹配 (`_rst_n` vs `_presetn`) | 复位信号命名规范和匹配逻辑 |

#### Agent Debug 场景评估

**✓ 有帮助的场景:**
- 追踪数据流根因: `s_apb_pwdata_i → ... → tx_fifo_wr_data → TX`
- 识别关键寄存器: 路径上经过几个寄存器
- 时钟域识别: 标注路径所属时钟域

**✗ 不足之处:**

| 需求 | 当前状态 | 优先级 |
|------|---------|--------|
| 条件分支信息 | 只记录了 `condition`，未在路径中体现 | **高** |
| 跨时钟域识别 | 未标注 CDC 路径 | **高** |
| FSM 内部追踪 | TX/RX FSM 内部状态机路径断裂 | **高** |
| 时序约束信息 | 缺失 setup/hold 路径 | 中 |

### 改进任务清单

#### P1: 关键路径修复 (必须)

- [x] **APB PRDATA 路径**: 为 `assign` 语句生成反向驱动边，使读数据路径可追踪 ✅
- [x] **FSM 内部路径**: 完善 always 块内的状态转换路径建模 ✅
- [x] **组合逻辑出边**: 修复组合赋值信号的出边生成逻辑 ✅

#### P1: Agent 可用性增强

- [x] **条件分支可视化**: 在路径中标注 `condition` 分支信息 ✅
- [x] **CDC 标注**: 自动识别并标注跨时钟域路径 ✅
- [x] **路径置信度**: 增加 `path_confidence` 分数 (0-1) ✅

#### P2: 高级分析 (后续)

- [ ] **条件覆盖率**: 分析哪些条件组合从未触发 (已在 P2-2)
- [ ] **Timing Report**: 生成完整时序分析报告 (已在 P3-3)
- [ ] **DOT 可视化**: 支持导出可视化图形 (已在 P3-4)

---

## 状态

- [x] fan-out 分析增强 (P2-1)
- [x] 条件覆盖率 (P2-2) - ✅ 已完成 (get_condition_coverage)
- [x] 路径分析增强 (P2-3)
- [ ] 多信号批量分析 API (P3-1)
- [ ] Timing Report Generator (P3-3)
- [x] DOT Graph Visualization (P3-4) - ✅ 已完成 (export_to_dot)
- [ ] APB PRDATA 路径修复 (P1)
- [ ] FSM 内部路径建模 (P1)
- [ ] 组合逻辑出边修复 (P1)
- [ ] 条件分支可视化 (P1)
- [ ] CDC 标注 (P1)
- [ ] 路径置信度评分 (P1)