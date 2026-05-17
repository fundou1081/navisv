# navisv 开发计划 v0.8

> 版本：v0.8
> 日期：2026-05-17
> 状态：已确认，待执行

---

## 总体目标

基于 slang-netlist 和 networkx，实现一个面向 AI Agent 的 SystemVerilog 语义导航中间件。首个可用版本将支持信号全貌查询（SignalProfileApp），并跑通从网表到自然语言答案的完整链路。

---

## 开发阶段

### Phase 0：原型验证 (1–2 天)

**目标**：证明 DesignGraph 构建 + QueryService.find_path + SignalProfileApp 的链路在真实设计上可行。

**任务**：
1. 在 examples/ 下搭建最小原型脚本，使用 slang-netlist 解析 OpenTitan I2C 模块
2. 实现简化版 DesignGraph：节点创建、从 getDrivers() 构建边（暂不加入 StatementExplorer 属性）
3. 实现 QueryService.find_path 和 SignalProfileApp 骨架，输出结构化结果和一段自然语言占位文本
4. 手动验证输出是否合理（驱动、负载列表正确性）

**产出**：examples/prototype_i2c.py，确认链路可行。

**依赖**：slang-netlist 能正确解析 I2C 模块并返回 driver/load 数据。

**状态**：✅ 已完成

---

### Phase 1：Graph Layer 完整实现 (3–5 天)

**目标**：实现完整的 DesignGraph，包含边属性增强和 class 支持。

**任务**：
1. 实现 schema.py 中 SignalNode、SignalEdge 数据类
2. 完成 design_graph.py：
   - 构建节点（标签、位宽、模块等自动填充）
   - 从 slang.getDrivers() 构建所有 drives 边，初始 timing='unknown'
3. 实现 statement_explorer.py：遍历 always/assign，匹配已有边并填充 timing、qualifier、source_location。处理 is_partial 标记
4. 实现 class_explorer.py：补充 class 内方法调用边，遵循 slang 优先原则
5. 实现 DesignGraph 最小接口：nodes()、edges()、predecessors()、successors()、edge_attr()、node_attr()、subgraph()

**产出**：navisv/graph/ 模块完整，可通过单元测试验证节点/边属性。

**测试**：使用 I2C 模块和人工构造的小型 SV 代码覆盖各类赋值语句、拼接、class。

**依赖**：pyslang 用于 statement walk。

**状态**：⚠️ 部分完成（基础实现，tags/位宽自动填充未完成）

---

### Phase 2：Query Layer 实现 (2–3 天)

**目标**：实现所有原子查询方法。

**任务**：
1. 定义 query/models.py 中 DriverInfo、LoadInfo、PathInfo 等简单数据类
2. 实现 query/service.py：
   - get_drivers()、get_loads()：基于 predecessors/successors，组装 DriverInfo/LoadInfo
   - find_path()：优先调用 slang PathFinder，失败回退 networkx 最短路径
   - fanin_cone()、fanout_cone()：BFS 遍历，限制深度
   - search_signals()：基于信号名正则匹配和 tags 过滤
   - scc_analysis()：调用 networkx.strongly_connected_components()
3. 所有方法返回纯结构化数据，不生成自然语言

**产出**：navisv/query/ 完整，每个方法有单元测试。

**测试**：使用 Phase 1 构建的图进行查询验证。

**状态**：✅ 已完成

---

### Phase 3：App Layer 首批实现 (3–4 天)

**目标**：实现四个核心 App，并形成自然语言模板。

**任务**：
1. 实现 apps/base.py：BaseApp 基类和 AppResponse
2. 实现 SignalProfileApp：组合 drivers/loads/fanin 等，输出信号身份证
3. 实现 ImpactAnalysisApp：fanout 锥 + 组合环路检测 + 跨模块过滤
4. 实现 FindSignalsApp：模糊查找，使用 search_signals
5. 实现 RelationshipApp：共同源/负载分析 + 路径查找
6. 每个 App 实现 _build_summary() 模板方法，生成自然语言（可使用简单的 f"..." 模板）

**产出**：navisv/apps/ 中 4 个核心 App，附带使用示例。

**测试**：在 I2C 上运行每个 App，人工评估 summary 可读性。

**状态**：⚠️ 1/4 完成（SignalProfileApp 已实现）

---

### Phase 4：CLI 集成与 AI Agent 接口 (1–2 天)

**目标**：提供命令行入口和 AI Agent 调用示例。

**任务**：
1. 实现 cli.py：支持 navisv profile \<signal\> 等命令
2. 创建 examples/agent_integration.py：演示如何将 App 输出喂给 LLM 进行进一步推理
3. 编写 DEVELOPMENT.md 贡献指南和铁律文档

**产出**：可用的 CLI 工具和 Agent 集成示例。

**状态**：❌ 未开始

---

### Phase 5：测试、文档与实验性 App (2–3 天)

**目标**：完善测试覆盖，补充实验性功能。

**任务**：
1. 补充 tests/ 下集成测试，基于小规模 SystemVerilog 用例和 I2C
2. 实现实验性 App：FsmDetectApp、ProtocolInferApp，返回 experimental=True
3. 编写 examples/ 中所有 App 的演示脚本
4. 更新 README.md，包含安装、快速开始、架构概览

**产出**：可发布的 v0.8 版本原型。

**状态**：❌ 未开始

---

## 测试策略

**单元测试**：每个 Graph / Query / App 模块独立测试，mock 底层数据。

**回归测试**：使用固定的小型 SV 设计作为黄金参考，验证查询结果一致性。

**性能探查**：Phase 2 后对 I2C 模块进行 profiling，记录 fanout_cone 等耗时，决定 Phase 2 是否需要缓存。

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| slang-netlist 解析 I2C 失败或 driver 不完整 | 原型阶段卡住 | 准备备用设计（如 example 16）；联系 slang 社区 |
| StatementExplorer 的 RHS 提取 is_partial 占比过高 | 边属性质量差 | 设定阈值 20%，超标时降低对应 App 置信度 |
| networkx 在大设计上性能不足 | Query 响应慢 | 限制 fanin/fanout 深度，增加缓存（Phase 2 末）|
| 自然语言摘要过于机械 | Agent 体验差 | 在 examples/agent_integration.py 中与 LLM 联调，优化模板，未来允许 App 接入 LLM 生成摘要（可选）|

---

## 里程碑

| 里程碑 | 说明 | 状态 |
|--------|------|------|
| M0 | 原型验证通过（Phase 0 完成）| ✅ 已完成 |
| M1 | Graph + Query 层可用，能查询 I2C 设计的 driver/load（Phase 1–2）| ✅ 已完成 |
| M2 | 核心 App 可用，能给出信号身份证和影响分析（Phase 3）| ⚠️ 进行中 |
| M3 | v0.8 发布，含 CLI、文档、实验性 App（Phase 4–5）| ❌ 未开始 |

---

## 下一步行动

1. **完成 Phase 3 其余 3 个核心 App**：ImpactAnalysisApp、FindSignalsApp、RelationshipApp
2. **补充测试文件**：test_design_graph.py、test_query_service.py、test_signal_profile.py
3. **实现 Phase 4 CLI + Agent 接口**：cli.py、examples/agent_integration.py
4. **完成 Phase 5**：测试、文档、实验性 App

---

*开发计划版本：v0.8*
*最后更新：2026-05-17*