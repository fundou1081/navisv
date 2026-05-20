# navisv P3 Feature Plan

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

### 2. Design Hierarchy Navigation
- **目标**: 支持模块层次结构的导航
- **输入**: 模块路径、DesignGraph
- **输出**: 模块内的信号列表、子模块列表
- **判断逻辑**:
  - 利用 slang 的 module hierarchy
  - 提取模块内的所有信号
  - 支持跨模块路径追踪
- **应用场景**: SOC 设计分析、IP 核分析

### 3. Timing Report Generator
- **目标**: 生成完整的时序分析报告
- **输入**: DesignGraph、配置选项
- **输出**: 格式化报告（text/markdown/json）
- **判断逻辑**:
  - 按 clock domain 分组
  - 列出所有寄存器及其 timing 属性
  - 标记跨时钟域路径
  - 生成诊断摘要
- **应用场景**: 设计 review、签出检查

### 4. DOT Graph Visualization
- **目标**: 支持导出 DOT 格式用于可视化
- **输入**: 信号路径、子图范围
- **输出**: DOT 文件或 SVG/PNG 图片
- **判断逻辑**:
  - 利用 networkx DOT 生成
  - 支持节点/边属性标注
  - 支持子图聚类
- **应用场景**: 设计文档、调试可视化

---

## 优先级

| Feature | Priority | 预计工作量 |
|---------|----------|-----------|
| 多信号批量分析 API | P3-1 | 小 |
| Design Hierarchy Navigation | P3-2 | 中 |
| Timing Report Generator | P3-3 | 中 |
| DOT Graph Visualization | P3-4 | 中 |

---

## 状态

- [ ] 多信号批量分析 API
- [ ] Design Hierarchy Navigation
- [ ] Timing Report Generator
- [ ] DOT Graph Visualization