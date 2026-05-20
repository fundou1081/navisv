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
| fan-out 分析增强 | P2-1 | 中 | 待做 |
| 条件覆盖率 | P2-2 | 中 | 待做 |
| 路径分析增强 | P2-3 | 中 | 待做 |
| 多信号批量分析 API | P3-1 | 小 | 待做 |
| Timing Report Generator | P3-3 | 中 | 待做 |
| DOT Graph Visualization | P3-4 | 中 | 待做 |

---

## 状态

- [ ] fan-out 分析增强
- [ ] 条件覆盖率
- [ ] 路径分析增强
- [ ] 多信号批量分析 API
- [ ] Timing Report Generator
- [ ] DOT Graph Visualization