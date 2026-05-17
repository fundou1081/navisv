# navisv 产品需求文档

**产品代号**：Navigator for SystemVerilog Debug  
**语义延伸**：Semantic Navigator Over SystemVerilog，专为 AI 调试代理设计的结构化网表导航层。

---

## 1. 背景与问题

在 SystemVerilog 验证与调试中，AI Agent 面临严重的"盲目探索"问题：

- 面对海量源码，无法快速定位信号的真实驱动/负载关系。
- 缺乏结构化的语义理解，只能进行文本级匹配，无法回答高层次调试问题。
- 现有工具（如 slang-netlist）能提供精确的 driver/load 提取，但输出为原始网表关系，对 AI Agent 而言仍需大量手工解释和链路推理。

**核心痛点**：AI Agent 不是缺少信息，而是缺少"导航地图"。

---

## 2. 产品定位

navisv 是构建在 slang-netlist 之上的**语义导航中间件**。

它将低层网表关系（driver/load）转化为面向具体调试场景的结构化答案，让 AI Agent 能够直接提出场景化问题，并沿着明确的信号路径高效探索，彻底告别盲目搜索。

**技术栈定位**：

```
底层：slang-netlist 精确网表
中层：图算法与语义抽象
上层：场景化导航命令
```

---

## 3. 目标用户

| 用户 | 角色 | 使用方式 |
|------|------|----------|
| AI 调试 Agent | 主要用户 | 通过命令行接口或 API 调用，获取场景化导航信息 |
| 验证工程师 | 间接用户 | 通过 Agent 间接使用，或直接调用命令进行人工辅助调试 |

---

## 4. 核心功能完整列表

---

### 一、Debug 与信号追踪（解决 AI 盲目探索）

#### `sample-condition` — 采样条件分析

| 项目 | 说明 |
|------|------|
| **功能** | 给出信号可安全采样的时钟/使能条件 |
| **输入** | 信号路径 |
| **核心能力** | 分析驱动逻辑，提取有效窗口 |
| **典型 AI 用例** | 避免采样 X 态或亚稳态 |
| **典型问题** | `这个信号何时有效？` |

```
{
  "signal": "top.axi4s_bus.data_vld",
  "clock_domain": "aclk",
  "enable_conditions": ["axi4s_bus.xfer_en", "axi4s_bus.tid == tid_q"],
  "valid_window": "xfer_en 期间，与 aclk 同步",
  "sampling_edge": "posedge aclk",
  "reset_values": ["1'b0 @ negedge rst_n"],
  "next_hops": [
    {"signal": "axi4s_bus.xfer_en", "command_hint": "sample-condition", "reason": "使能条件本身也需要验证有效窗口"},
    {"signal": "top.rst_n", "command_hint": "trace-cone", "reason": "检查复位释放后的初始有效时间"}
  ]
}
```

#### `usage` — 信号使用链追踪

| 项目 | 说明 |
|------|------|
| **功能** | 显示信号被下游如何使用（作为条件、赋值、接口连接） |
| **输入** | 信号路径 |
| **核心能力** | 追踪负载类型（条件、赋值、接口等） |
| **典型 AI 用例** | 理解信号影响力 |
| **典型问题** | `这个信号影响了哪些逻辑？` |

```
{
  "signal": "top.cipher_fsm.state_q",
  "fans": [
    {"path": "top.aes_core.round_key_sel", "use": "mux sel"},
    {"path": "top.key_expand.ctrl_en", "use": "组合逻辑输入"},
    {"path": "top.output_reg[31:0].d", "use": "data path"},
    {"path": "top.fsm_intrpt", "use": "条件生成"}
  ],
  "use_classification": {
    "mux_sel": 1,
    "combinational_input": 1,
    "sequential_input": 1,
    "condition": 1
  },
  "next_hops": [
    {"signal": "top.aes_core.round_key_sel", "command_hint": "usage", "reason": "向下追踪 state_q 在 mux 中的具体作用"},
    {"signal": "top.fsm_intrpt", "command_hint": "trace-cone", "reason": "追踪中断条件触发的完整路径"}
  ]
}
```

#### `related` — 相关信号发现

| 项目 | 说明 |
|------|------|
| **功能** | 发现强相关信号（扇入/扇出、命名模式、同源驱动） |
| **输入** | 信号路径 |
| **核心能力** | 扇入/扇出分析、命名模式匹配、共同驱动源检测 |
| **典型 AI 用例** | 找到一起变化的信号，加速根因分析 |
| **典型问题** | `还有哪些信号和它一起变化？` |

```
{
  "signal": "top.spi_device.cmd_st_e",
  "related": [
    {"path": "top.spi_device.cmdparse_en", "score": 0.95, "reason": "同 FSM 状态位，共同 always_ff 驱动"},
    {"path": "top.spi_device.bcnt_q[7:0]", "score": 0.78, "reason": "cmd_st 触发 bcnt 计数"},
    {"path": "top.spi_device.sdo_bus", "score": 0.65, "reason": "cmd_st 决定 sdo 数据源选择"}
  ],
  "cluster_hint": "CMD_PARSER cluster，建议 Agent 整体追踪",
  "next_hops": [
    {"signal": "top.spi_device.cmdparse_en", "command_hint": "related", "reason": "查看 cmdparse_en 的完整相关信号"},
    {"signal": "top.spi_device.bcnt_q", "command_hint": "paths", "reason": "追踪 bcnt 计数在数据通路中的作用"}
  ]
}
```

#### `trace-cone` — 逻辑锥生成

| 项目 | 说明 |
|------|------|
| **功能** | 生成组合/时序逻辑锥，用于回溯或前向追踪 |
| **输入** | 信号路径 |
| **核心能力** | 前向/后向图遍历 |
| **典型 AI 用例** | 回答"值从哪里来，到哪里去" |
| **典型问题** | `这个值从哪里来？到哪里去？` |

```
{
  "signal": "top.usb_token_pid_q[7:0]",
  "fanin_cone": {
    "depth": 3,
    "paths": [
      ["top.usb_rx_pid", "top.pid_check.pid_v", "top.token_pid_q"],
      ["top.usb_rx_data", "top.token_pid_q"]
    ]
  },
  "fanout_cone": {
    "depth": 5,
    "loads": [
      ["top.token_pid_q → usb_setup Detector → device_addr_match"],
      ["top.token_pid_q → usb_in_fsm → in_ready"]
    ]
  },
  "next_hops": [
    {"signal": "top.pid_check.pid_v", "command_hint": "trace-cone", "reason": "继续向后追踪 pid_v 的 driver"},
    {"signal": "top.usb_in_fsm", "command_hint": "fsm-detect", "reason": "查看 in_fsm 是否需要补全验证"}
  ]
}
```

#### `paths` — 控制/数据路径提取

| 项目 | 说明 |
|------|------|
| **功能** | 提取 control path 与 data path 上的关键节点 |
| **输入** | 信号路径 |
| **核心能力** | 区分控制流与数据流路径 |
| **典型 AI 用例** | 理解处理流水线 |
| **典型问题** | `这条数据流经哪些控制/数据通路？` |

```
{
  "signal": "top.kmac_out_bus[31:0]",
  "data_paths": [
    {"path": ["kmac_core.result_reg", "kmac_out_reg", "top.out_bus"], "type": "data"},
    {"path": ["kmac_core.result_vld", "kmac_out_vld", "top.out_vld"], "type": "valid"}
  ],
  "control_paths": [
    {"path": ["kmac_fsm.idle", "kmac_fsm.process", "kmac_fsm.done"], "type": "control"}
  ],
  "key_nodes": ["kmac_fsm.state_q", "kmac_out_sel", "kmac_core.result_vld"],
  "next_hops": [
    {"signal": "kmac_fsm.state_q", "command_hint": "trace-cone", "reason": "建议从 state_q 开始反向追踪驱动源"},
    {"signal": "kmac_out_sel", "command_hint": "usage", "reason": "检查 out_sel 如何影响数据通路"}
  ]
}
```

#### `gen-coverage` — 覆盖点自动生成

| 项目 | 说明 |
|------|------|
| **功能** | 为指定信号生成 covergroup 骨架 |
| **输入** | 信号路径 + 合法值域 |
| **核心能力** | 值域分析、交叉覆盖识别 |
| **典型 AI 用例** | 精准写 coverage，不漏边界 |
| **典型问题** | `如何为这个信号写 coverage？` |

```
{
  "signal": "top.dma_ctrl.blen_q[2:0]",
  "coverage_plan": {
    "toggle": ["blen_q[0]", "blen_q[1]", "blen_q[2]"],
    "boundary": [
      {"value": 0, "name": "idle"},
      {"value": 1, "name": "single beat"},
      {"value": 7, "name": "max burst"}
    ],
    "cross": [
      {"name": "blen_x_dir", "with": "top.dma_ctrl.dir_q", "description": "blen x dir cross coverage"}
    ],
    "illegal": [{"value": "blen_q > 7", "description": "burst length exceeds max"}]
  },
  "covergroup_template": "covergroup cg_blen @(posedge clk);\n  option.per_instance = 1;\n  cp_blen: coverpoint blen_q { bins idle = {0}; ... }\nendgroup",
  "next_hops": [
    {"signal": "top.dma_ctrl.dir_q", "command_hint": "gen-coverage", "reason": "与 dir_q 做交叉覆盖"},
    {"signal": "top.dma_ctrl.blen_q", "command_hint": "constraints", "reason": "检查 blen_q 是否有协议级约束需要一起覆盖"}
  ]
}
```

---

### 二、代码修改影响分析

#### `impact` — 修改影响范围评估

| 项目 | 说明 |
|------|------|
| **功能** | 评估信号/模块修改的影响范围 |
| **输入** | 信号或模块名 |
| **核心能力** | 扇出锥生成，标注受影响的时序/控制/数据路径 |
| **典型 AI 用例** | 改动前预判风险 |
| **典型问题** | `改这个信号会波及哪些地方？` |

```
{
  "target": "top.kmac_fsm.state_q",
  "impact_analysis": {
    "sequential_fans": [
      {"path": "top.aes_core.round_key_sel", "type": "时序", "severity": "high"}
    ],
    "combinational_fans": [
      {"path": "top.key_expand.ctrl_en", "type": "组合", "severity": "medium"}
    ],
    "data_path_fans": [
      {"path": "top.output_reg", "type": "数据", "severity": "high"}
    ],
    "control_path_fans": [
      {"path": "top.kmac_done_intrpt", "type": "控制", "severity": "high"}
    ]
  },
  "affected_modules": ["kmac_core", "key_expand", "output_reg"],
  "affected_coverage": ["cg_fsm_state", "cg_kmac_done"],
  "regression_hints": ["kmac_seq::fsm_transition_seq", "kmac_scoreboard::check_state_consistency"],
  "next_hops": [
    {"signal": "top.output_reg", "command_hint": "blast-radius", "reason": "评估 output_reg 被影响的完整范围"},
    {"command_hint": "grade", "reason": "评估当前 kmac_fsm 结构质量是否需要重构"}
  ]
}
```

#### `blast-radius` — 删除/改动波及区域模拟

| 项目 | 说明 |
|------|------|
| **功能** | 模拟删除/改动某信号的波及区域 |
| **输入** | 信号路径 |
| **核心能力** | 双向 BFS，量化受影响模块、信号、覆盖点 |
| **典型 AI 用例** | 确定回归测试范围 |
| **典型问题** | `如果删掉这个信号，会有什么问题？` |

```
{
  "target": "top.i2c_host.scl_fsm_q",
  "blast_radius": {
    "fanout_nodes": 12,
    "fanin_nodes": 3,
    "affected_modules": ["i2c_host", "i2c_target"],
    "affected_signals": ["scl_oe", "scl_out_fsm", "scl_stretch_q", "host_timeout"],
    "broken_paths": ["scl_fsm_q -> scl_oe -> scl_pad (open-drain)", "scl_fsm_q -> scl_stretch_q -> host_timeout"]
  },
  "regression_test_scope": {
    "must_test": ["i2c_host_fsm_transitions", "clock_stretch_behavior", "host_timeout"],
    "suggested_test": ["i2c_basic_seq", "i2c_target_ack_seq"]
  },
  "next_hops": [
    {"command_hint": "grade", "reason": "评估 i2c_host 结构稳定性"},
    {"command_hint": "path-profile", "reason": "检查 scl_fsm 到 pad 的完整 clock domain 路径"}
  ]
}
```

---

### 三、架构与早期设计（图算法驱动，提供客观数据）

#### `fsm-detect` — 隐藏状态机发现

| 项目 | 说明 |
|------|------|
| **功能** | 自动发现隐藏状态机 |
| **输入** | 模块或顶层 |
| **核心能力** | 信号依赖图 + 强连通分量（SCC）检测、反馈环识别 |
| **典型 AI 用例** | 补全未文档化 FSM，保证验证完整性 |
| **典型问题** | `这个模块里有哪些状态机？` |

```
{
  "module": "top.aes_core",
  "detected_fsms": [
    {
      "name": "cipher_fsm (inferred)",
      "state_bits": ["state_q[2:0]"],
      "scc_members": ["state_q", "round_cnt", "key_sel_q"],
      "control_signals": ["cipher_op", "key_init_sel", "state_sel"],
      "next_state_logic": ["state_q[1:0] = next_state_logic.q"],
      "feedback_cycles": 1,
      "coverage_gaps": ["未发现 state_q[2:0] 的 cross coverage", "缺少 idle->error 转换覆盖"]
    },
    {
      "name": "key_expand_fsm (inferred)",
      "state_bits": ["key_expand_rdy", "key_expand_busy"],
      "scc_members": ["key_expand_rdy"],
      "control_signals": ["key_expand_en"],
      "coverage_gaps": []
    }
  ],
  "next_hops": [
    {"command_hint": "grade", "reason": "评估 cipher_fsm 结构稳定性"},
    {"command_hint": "gen-coverage", "reason": "为发现的 FSM 补全覆盖点模板"}
  ]
}
```

#### `stability` — 架构稳定性评分

| 项目 | 说明 |
|------|------|
| **功能** | 架构稳定性/脆弱性评分 |
| **输入** | 模块名 |
| **核心能力** | 扇出宽度、耦合密度、影响半径计算 |
| **典型 AI 用例** | 识别高风险模块，指导重构优先级 |
| **典型问题** | `这个模块结构稳定吗？` |

```
{
  "module": "top.dma_ctrl",
  "stability_score": 6.2,
  "dimensions": {
    "fanout_width": {"score": 7.5, "label": "高", "description": "dma_ctrl 驱动 23 个下游信号"},
    "coupling_density": {"score": 5.1, "label": "中", "description": "平均每信号被 4.2 个上游信号驱动"},
    "influence_radius": {"score": 4.8, "label": "中", "description": "修改影响扩散至 5 个子模块"},
    "change_frequency": {"score": 8.0, "label": "高", "description": "历史修改频率 top 15%"}
  },
  "risk_flags": [
    "高扇出宽度：修改dma_ctrl可能导致级联影响",
    "高变化频率：该模块是频繁改动热点"
  ],
  "refactor_suggestions": [
    "建议拆分：将地址生成逻辑（addr_gen）与传输控制（xfer_ctrl）分离",
    "建议降耦：引入 arbiter 减少直接驱动关系"
  ],
  "next_hops": [
    {"command_hint": "stability", "reason": "对比拆分后的 addr_gen 模块稳定性"},
    {"command_hint": "path-profile", "reason": "分析 xfer_ctrl 的关键路径"}
  ]
}
```

#### `path-profile` — 关键路径与时钟域分析

| 项目 | 说明 |
|------|------|
| **功能** | 关键路径与时钟域分析 |
| **输入** | 时钟信号或模块 |
| **核心能力** | 组合逻辑深度计算、CDC 路径识别、同步器检查 |
| **典型 AI 用例** | 早期预警时序/跨时钟域问题 |
| **典型问题** | `这条时钟域路径安全吗？` |

```
{
  "clock_domain": "pclk",
  "critical_paths": [
    {"path": ["pclk", "usb_fsm.state_q", "usb_mux.sel", "data_reg.d"], "depth": 3, "slack": "critical"},
    {"path": ["pclk", "token_pid_q", "pid_check.pid_v", "addr_match.d"], "depth": 3, "slack": "normal"}
  ],
  "cdc_paths": [
    {"path": ["aclk", "tx_fsm.state_q", "->", "pclk", "tx_data_reg.d"], "type": "async", "protection": "2-flop synchronizer"},
    {"path": ["pclk", "cfg_reg.q", "->", "aclk", "cfg_bridge.d"], "type": "sync_fifo", "protection": "FIFO"}
  ],
  "synchronizer_gaps": [
    {"signal": "usb_intrpt", "type": "pulse sync", "protection": "none", "risk": "high"}
  ],
  "next_hops": [
    {"command_hint": "stability", "reason": "检查 usb_fsm 所在模块的稳定性"},
    {"command_hint": "fsm-detect", "reason": "检查 tx_fsm 状态机是否完整"}
  ]
}
```

#### `protocol-infer` — 端口协议自动推断

| 项目 | 说明 |
|------|------|
| **功能** | 端口协议自动推断 |
| **输入** | 端口列表 |
| **核心能力** | 握手模式识别（valid/ready, req/ack）、数据有效窗口提取 |
| **典型 AI 用例** | 生成 UVM interface 或 sequence 约束模板 |
| **典型问题** | `这个接口的协议是什么？` |

```
{
  "interface": "top.axi4s_m",
  "inferred_protocol": "AXI4-Stream (master)",
  "signals": {
    "tvalid": {"role": "valid", "driven_by": "always_ff @(posedge aclk)"},
    "tready": {"role": "ready", "driven_by": "slave"},
    "tdata": {"role": "data", "width": 32, "bounds": "[31:0]"},
    "tlast": {"role": "eom", "driven_by": "tlast_gen"}
  },
  "handshake_pattern": "valid-ready (two-way handshake)",
  "data_valid_window": {
    "start": "tvalid assertion",
    "end": "tvalid & tready握手完成",
    "duration": "1 cycle (combinational path)"
  },
  "generated_artifacts": {
    "uvm_interface": "axils_m_if.sv",
    "sequence_constraint": "axi4s_master_seq::build_phase",
    "monitor_template": "axi4s_monitor::build_phase"
  },
  "next_hops": [
    {"command_hint": "constraints", "reason": "为 AXI4S 端口提取协议级约束"},
    {"command_hint": "gen-coverage", "reason": "生成 AXI4S protocol coverage"}
  ]
}
```

---

### 四、设计与验证任务辅助

#### `constraints` — 信号合法约束提取

| 项目 | 说明 |
|------|------|
| **功能** | 提取信号合法约束与关联规则 |
| **输入** | 信号 + 场景 |
| **核心能力** | 驱动逻辑分析、关联信号约束关系挖掘 |
| **典型 AI 用例** | 精准写 sequence 约束，避免无效激励 |
| **典型问题** | `这个信号的合法取值范围是什么？` |

```
{
  "signal": "top.dma_ctrl.blen_q[2:0]",
  "constraints": {
    "intrinsic": [
      {"expr": "blen_q inside {[1:7]}", "source": "hw_constraint (RTL)"},
      {"expr": "blen_q > 0", "source": "implied by protocol"}
    ],
    "context_dependent": [
      {"condition": "xfer_size == BYTE", "valid_range": "[1:1]"},
      {"condition": "xfer_size == WORD", "valid_range": "[1:4]"},
      {"condition": "xfer_size == DWORD", "valid_range": "[1:8]"}
    ],
    "correlated_signals": [
      {"signal": "dir_q", "relation": "blen * dir determines beat count"}
    ]
  },
  "sequence_hints": [
    "避免 blen_q == 0 (protocol violation)",
    "建议与 dir_q 做 cross 约束"
  ],
  "next_hops": [
    {"signal": "top.dma_ctrl.dir_q", "command_hint": "constraints", "reason": "查看 dir_q 的约束关系"},
    {"command_hint": "gen-coverage", "reason": "基于约束生成覆盖点"}
  ]
}
```

#### `assert` — SVA 断言模板推荐

| 项目 | 说明 |
|------|------|
| **功能** | 推荐 SVA 断言模板 |
| **输入** | 信号 + 断言类型 |
| **核心能力** | 采样时钟选择、前置条件提取、安全/活性断言骨架生成 |
| **典型 AI 用例** | 高价值 checker 自动生成 |
| **典型问题** | `需要写什么断言来检查这个信号？` |

```
{
  "signal": "top.i2c_host.scl_fsm_q",
  "assertion_type": "safety + liveness",
  "sampling_clock": "sys_clk",
  "templates": [
    {
      "type": "safety",
      "name": "scl_fsm_no_stuck_at",
      "body": "property p_scl_fsm_no_stuck;\n  @(posedge sys_clk) $changed(scl_fsm_q) or $past(rst_n == 1'b0);\nendproperty",
      "reason": "防止状态机卡死"
    },
    {
      "type": "liveness",
      "name": "scl_fsm_progress",
      "body": "property p_scl_fsm_progress;\n  disable iff (!rst_n);\n  @(posedge sys_clk) s_f_active |-> ##[1:100] s_done;\nendproperty",
      "reason": "确保传输最终完成"
    }
  ],
  "required_prerequisites": ["rst_n", "sys_clk"],
  "next_hops": [
    {"command_hint": "gen-coverage", "reason": "为断言覆盖不到的路径补充 coverage"},
    {"command_hint": "usage", "reason": "检查 scl_fsm 所有负载是否被断言覆盖"}
  ]
}
```

#### `grade` — 设计结构质量客观评价

| 项目 | 说明 |
|------|------|
| **功能** | 设计结构质量客观评价 |
| **输入** | 模块名 |
| **核心能力** | 逻辑深度、扇出、CDC 安全等量化指标计算 |
| **典型 AI 用例** | 代码审查、设计比较、重构收益评估 |
| **典型问题** | `这个模块的结构质量怎么样？` |

```
{
  "module": "top.usb_device",
  "overall_score": 7.4,
  "dimensions": {
    "logic_depth": {"score": 8.0, "label": "优", "description": "最大组合路径深度 12 级，在可接受范围"},
    "fanout": {"score": 6.5, "label": "良", "description": "最大扇出 18，超过推荐值 15"},
    "cdc_safety": {"score": 7.0, "label": "良", "description": "3 条 CDC 路径，2 条有同步器保护"},
    "coupling": {"score": 7.5, "label": "良", "description": "模块内聚性较好，跨模块依赖适中"},
    "fsm_complexity": {"score": 8.0, "label": "优", "description": "FSM 状态数 8，转移逻辑清晰"}
  },
  "risk_flags": [
    "fanout 偏高：某些信号驱动 18+ 下游，可能导致布线拥塞",
    "1 条 CDC 路径无同步器保护"
  ],
  "comparison": {
    "vs_top_module_avg": "+1.2 (优于平均)",
    "vs_opentitan_avg": "-0.3 (略低于平均)"
  },
  "next_hops": [
    {"command_hint": "stability", "reason": "查看整体模块稳定性排名"},
    {"command_hint": "path-profile", "reason": "检查高扇出信号的关键路径"}
  ]
}
```

---

## 5. 统一输出与导航增强

### 结构化输出

所有命令输出统一 JSON 格式：

```json
{
  "result": { ... },
  "explanation": "自然语言解释（Agent 可朗读）",
  "next_hops": [
    {
      "signal": "...",
      "command_hint": "related",
      "reason": "...",
      "score": 0.95
    }
  ],
  "metadata": {
    "signal": "...",
    "module": "...",
    "query_time_ms": 42,
    "graph_stats": {"nodes": 1234, "edges": 5678, "depth": 5}
  }
}
```

### 下一步导航建议

每个命令结果必须包含 ≥1 条 `next_hops`，引导 Agent 持续深入而不盲目探索。

### 范围裁剪

支持按模块、层级或半径限制输出规模：

```bash
navisv trace-cone top.data_vld --depth 5 --module aes_core
navisv impact top.fsm_state --radius 3 --exclude-sim
```

---

## 6. 工作流程

```
[设计源码 (*.sv)]
        ↓
 slang-netlist (C++ 核心引擎)
   - SystemVerilog 解析
   - 网表生成
   - 精确的 driver / load 关系计算
   - PathFinder / DriverTracker / NetlistGraph
        ↓
   navisv (语义导航层)
   - 关系图的语义标注
   - 路径抽象与场景模板
   - 图算法（DFS/BFS/SCC/CDC）
   - Agent 友好的 API / CLI
   - next-hop 建议生成
        ↓
  AI Agent / 验证工程师
```

**分工原则**：

- slang-netlist：负责底层精确信息，不感知场景语义
- navisv：负责语义抽象，面向调试场景组织信息

---

## 7. 技术约束与依赖

| 约束项 | 要求 |
|--------|------|
| 强依赖 | slang-netlist 必须可用，能够从同一设计数据库提取 driver/load/extract |
| 规模支持 | 需支持千万门级设计；大图输出需限制范围或支持层级裁剪 |
| 输出格式 | JSON / 结构化文本，优先支持流式交付 |
| 可组合性 | 命令可管道化（`trace-cone ... \| related ... \| paths ...`） |
| 集成方式 | 跨平台 CLI + Python API，AI Agent 可通过 stdin/stdout/API 调用 |
| 性能目标 | 百毫秒级单次场景查询（常见模块），流式输出首帧 < 50ms |

---

## 8. 错误处理规范

| 场景 | 返回 |
|------|------|
| 信号不存在 | `{"error": "signal_not_found", "candidates": [...]}`（提供模糊匹配候选） |
| 无 driver/load | `{"result": [], "explanation": "no drivers/loads found", "next_hops": [...]}` |
| 图为空 | `{"error": "empty_graph", "reason": "..."}` |
| 超时 | `{"error": "timeout", "hint": "--depth 3 --module xxx"}` |

---

## 9. 实施路线建议

### Phase 1（MVP）：核心 Debug 命令

| 命令 | 优先级 | 依赖 |
|------|--------|------|
| `trace-cone` | P0 | slang-netlist PathFinder |
| `usage` | P0 | slang-netlist getDrivers + load 追踪 |
| `sample-condition` | P1 | 源码文本分析 + timing extraction |
| `related` | P1 | fan-in/out 分析 |

### Phase 2：影响分析 + 架构命令

| 命令 | 优先级 | 依赖 |
|------|--------|------|
| `impact` | P1 | trace-cone + fanout 锥生成 |
| `blast-radius` | P2 | 双向 BFS |
| `fsm-detect` | P1 | SCC 检测 |
| `stability` | P2 | 多维评分指标 |
| `path-profile` | P2 | 组合深度 + CDC 检测 |
| `gen-coverage` | P1 | 值域分析 + 源码约束提取 |

### Phase 3：验证任务 + 规模化

| 命令 | 优先级 | 依赖 |
|------|--------|------|
| `constraints` | P2 | Python 层 constraint walk |
| `assert` | P2 | SVA 模板生成 |
| `protocol-infer` | P2 | 握手模式识别 |
| `grade` | P3 | 多维量化指标 |
| 流式输出 | 基础设施 | 支持大图流式返回 |
| 范围裁剪 | 基础设施 | depth limit / module scope |

---

## 10. 命名与愿景

**navisv** = "导航（navi）+ SystemVerilog（sv）"

**愿景**：让每一个 AI 调试代理在 SystemVerilog 的世界里，从此有路可循。

> *"Sense the netlist, navigate the design."*

**完整定位**：从 Debug 到 Architecture，让 AI 每一步都有客观路标。

---

*文档版本：v0.2*  
*创建日期：2026-05-16*