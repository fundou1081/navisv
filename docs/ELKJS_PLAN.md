# navisv × elkjs 实施 PLAN

> 配套文档: [ELKJS_SPEC.md](./ELKJS_SPEC.md)
> 创建: 2026-08-05
> 预计总工时: ~9 小时，分 6 阶段

---

## 总览

```
Stage 1    ElkExporter 骨架 + 数据流转换           → 2h
Stage 2    HTML viewer + bundled elkjs              → 1.5h
Stage 2.5  Operator / Literal 节点 (菱形 + 虚线)    → 1.5h (插队, 2026-08-05)
Stage 2.6  AST 驱动的具体运算符符号 (!, +, <=)      → 1h (插队, 2026-08-05)
Stage 2.7  真实 ELK layered + 清晰边渲染            → 1h (插队, 2026-08-06)
Stage 2.8  PORT_IN/OUT 锚点 (FIRST/LAST)           → 0.5h (插队, 2026-08-06)
Stage 2.9  过滤 CLOCK/RESET/FF-update 边            → 1h (插队, 2026-08-06)
Stage 3    CLI + 3 视图                            → 2h
Stage 4    交互层 (搜索/高亮/CDC toggle)           → 1.5h (2026-08-06)
Stage 5    真实 RTL 测试                           → 0.5h (2026-08-06) — 受 slang-netlist 限制
Stage 6    examples + README + push                → 0.5h (2026-08-06)
Stage 6    examples + README + push                → 1h
```

每阶段结束 = 一个 git commit + 一个可工作的演示。

---

## Stage 2.5: Operator / Literal 节点 (2026-08-05)

**背景**: 用户反馈「我希望有 运算符 节点，能在图里看出来代码的逻辑，数据流」
**位置**: 在 Stage 2 之后、Stage 3 之前插队

### 任务
- [x] `navisv/graph/graph_builder.py`: 加 `preserve_operators=False` 参数 (默认 False, 保持向后兼容)
- [x] `navisv/graph/graph_builder.py`: 加 `_add_intermediate_nodes()` 方法
  - Assignment / Conditional / Case / Merge → kind='Operator', label='<=' / 'if' / 'case' / 'merge'
  - Constant → kind='Literal', label=node.value (e.g. "4'b0")
  - graph 节点 path: `op_<id>` / `const_<id>`
- [x] `navisv/graph/graph_builder.py`: 改 `_add_edges()` — preserve_operators=True 时用 op_<id>/const_<id> 而不 collapse
- [x] `navisv/graph/elk_exporter.py`: KIND_COLORS 加 Operator/Literal; KIND_SIZES 定义小尺寸
- [x] `navisv/graph/elk_exporter.py`: `_node_to_elk()` 加 `shape="diamond"` 提示 + properties 加 operator_kind/value
- [x] `navisv/data/elk_viewer.js`: Operator → `<polygon>` 菱形; Literal → 虚线小矩形
- [x] `navisv/data/elk_viewer.css`: Operator / Literal 样式
- [x] viewer legend 加 Operator / Literal 条目
- [x] `tests/test_elk_exporter.py`: 17 个新测试 (TestOperatorNode / TestLiteralNode / TestKindColorsExtended / TestViewerRendersOperatorAndLiteral / TestGraphBuilderPreserveOperators)

### 验收
- counter.sv: 4 nodes / 3 edges → 11 nodes / 16 edges
- 6 个 Operator (2 `if` + 2 `<=` + 2 `merge`)
- 1 个 Literal (`4'b0`)
- HTML 含 `<polygon>` (Operator 菱形) + `stroke-dasharray` (Literal 虚线)
- legend 含 Operator/Literal
- 47 + 17 = 64 tests pass (elk_exporter), 303 pass (全 navisv), 0 regression

### 限制 / 待办
- Operator 显示的 label 是 netlist kind (`if`/`<=`/`merge`)，不是具体运算符符号 (`+`/`-`/`==`/`&&`/`!`)。pyslang 集成留到 Stage 4+ 或单独路线图。
- 用户还可能想看: 位选/片选 (`[7:0]`)、类型转换 (`int'()`)、三元 (`?:`) — 都需要 pyslang AST。

### Commit
```
feat(elk): Stage 2.5 — Operator / Literal nodes (diamond + dashed rect)
```

---

## Stage 2.6: AST 驱动的具体运算符符号 (2026-08-05)

**背景**: 用户反馈「operator 要显示具体符号，先改这个」

Stage 2.5 的 Operator label 仍是 netlist kind (`if`/`<=`/`merge`)。
用户期待看到具体运算符（`!`、`+`、`&&` 等）。

### 任务
- [x] `navisv/graph/graph_builder.py`: 加 `AST_OP_TO_SYMBOL` 映射表 (~40 entries)
  - BinaryOp: Add/Sub/Mul/Div/Mod, Equality/Inequality, LogicalAnd/Or, BitwiseAnd/Or/Xor, ShiftLeft/Right, GreaterThan/LessThan
  - UnaryOp: LogicalNot/BitwiseNot/Plus/Minus/PreIncrement/PostIncrement
  - ConditionalOp → `?:`
- [x] `navisv/graph/graph_builder.py`: `_build_ast_expression_index()` walk AST
  - 收集 expression 节点 (Conditional/BinaryOp/UnaryOp/ConditionalOp/Assignment/Conversion/IntegerLiteral)
  - 按 (file, line) 索引, 行内按 col 排序
- [x] `navisv/graph/graph_builder.py`: `_match_netlist_to_ast()`
  - 按 (file, line) + col 临近匹配
  - kind 过滤 (Conditional ↔ Conditional, Assignment ↔ Assignment, Constant ↔ Conversion/IntegerLiteral)
  - Merge fallback
- [x] `navisv/graph/graph_builder.py`: `_find_first_operator()` 严格 walk
  - Conditional 只看 `conditions[*].expr`, 不进 ifTrue/ifFalse (避免跨语句吸到嵌套 BinaryOp)
  - Assignment 只看 `right`, 不看 left (NamedValue)
  - Conversion 看 operand
- [x] `navisv/graph/graph_builder.py`: `_add_intermediate_nodes()` 用 AST 匹配覆盖 netlist kind fallback
- [x] `navisv/parsers/netlist_parser.py`: 加 `file_table` 属性 (从 netlist.fileTable 读取)
- [x] `tests/test_elk_exporter.py`: +15 个新测试 (TestASTOpSymbolMap / TestGraphBuilderStage26Counter / TestFindFirstOperatorHelper)

### 验收
- counter.sv:
  - op_5 (`if !rst_n`): `if` → **`!`** ✅
  - op_6 (`count <= 0`): `<=` → `<=` (RHS 是字面值, fallback)
  - op_8 (`if enable`): `if` → `if` (condition 是 NamedValue, fallback)
  - op_9 (`count <= count+1`): `<=` → **`+`** ✅
  - const_7: `4'b0` → `4'b0` ✅
  - op_10/op_11 (Merge): `merge` → `merge` (fallback)
- 79 elk_exporter tests pass, 318 navisv tests pass, 0 regression
- PNG 渲染 5 个 Operator 菱形 + 1 Literal, 标签 `!` `+` `<=` `if` `merge` `4'b0`

### 关键 bugfix
第一次实现时 `_find_first_operator()` walk 了所有 children, 把嵌套 if 块里 Assignment 的 BinaryOp Add "吸"到外面 Conditional 节点上, 导致 op_5/op_8 都显示 `+`。
**修复**: 严格按 `conditions[*].expr` / `right` 字段 walk, 不跨语句边界。

### 限制 / 待办
- Merge fallback `merge` (无 AST 对应)
- 只看第一个 operator, 不展开深层嵌套
- 三元 `?:` / 位选 `[7:0]` / 类型转换 `int'()` 待 pyslang 或更精细 walk

### Commit
```
feat(elk): Stage 2.6 — operator labels show specific symbols (!, +, <=, if)
```

---

## Stage 2.7: 真实 ELK Layered Layout + 清晰边渲染 (2026-08-06)

**背景**: 用户反馈「这个图有些抽象，连接关系看不清，混淆」

Stage 2.6 的 PNG 用手写 BFS 布局, 节点散乱 + 边穿越混乱。Stage 2.7 引入真 ELK layered 算法 + orthogonal edge routing。

### 任务
- [x] `navisv/tools/run_elk.js`: Node.js 调 ELK.bundled.js 跑真 layered layout
  - `elk.algorithm = 'layered'`, `elk.direction = 'RIGHT'`, `elk.edgeRouting = 'ORTHOGONAL'`
  - 接受 `--direction={DOWN|RIGHT|UP|LEFT}` 参数
- [x] `navisv/tools/render_svg.py`: 把 ELK 输出 JSON 渲染成 SVG
  - **Inline stroke 属性** (避开 rsvg-convert CSS quirk — Stage 2.6 踩过坑)
  - 4 个 arrow markers (blue/red/purple/gray) 在 `<defs>`
  - 节点按 kind 渲染 (Operator=菱形, Literal=虚线矩形, etc.)
  - 边按时序着色 (combinational=蓝, sequential=红, clock=紫)
  - 两栏 legend (节点 + 边)
- [x] `navisv/tools/elk_layout.py`: Python wrapper
  - `run_elk_layout(elk_json, direction)` — subprocess 调 Node.js + 读输出
  - `run_layout_and_render(elk_json, svg_path, ...)` — one-shot
  - CLI: `python -m navisv.tools.elk_layout <in.json> <out.svg> --direction=RIGHT`
- [x] `navisv/tools/__init__.py`: 包初始化
- [x] `tests/test_render_svg.py`: +31 个测试
  - TestStripFileTag (4) — label 去 file.sv:N 后缀
  - TestRenderMarkers (3) — `<defs>` 4 个箭头
  - TestRenderNode (7) — Port/State/Operator/Literal 形状 + offset + file tag 去除
  - TestRenderEdge (5) — combinational/sequential 颜色 + inline stroke + bend points
  - TestComputeBBox (2) — 节点 + 边范围
  - TestRenderSvgEndToEnd (5) — render_svg() 完整流程 + HTML escape
  - TestRunElkLayout (4) — Node.js subprocess + direction
  - TestStage27EndToEnd (1) — counter.sv 端到端

### 验收
- counter.sv 端到端: 11 节点 + 15 边清晰可见, 水平 flow, orthogonal routing
- PNG: 74KB, 1322x469, 节点位置合理, 箭头清晰, legend 完整
- 31 render_svg tests pass, 349 navisv tests pass, 0 regression

### 关键 bugfix
1. **CSS class 不被 rsvg-convert 解析** — Stage 2.6 PNG 只有箭头看不到边。改用 inline stroke + stroke-width, 边立刻可见
2. **测试 fixture 错位** — fixture edges 含 `sections` (ELK 输出), 但 ELK input 不能含 sections。拆为 2 个 fixture: input vs output
3. **HTML escape** — SVG text 中 `<` → `&lt;`, `'` → `&#x27;`, 测试 assertion 用转义后形式

### Commit
```
feat(elk): Stage 2.7 — real ELK layered layout + clear edge rendering
```

---

## Stage 2.8: PORT_IN/OUT 锚点 (FIRST/LAST) (2026-08-06)

**背景**: 借鉴 sv_query `DATAFLOW_VIZ_SPEC.md` §1 的绘图要求 (方豆要求「只参考里面最终的绘图要求」).

`PORT_IN` 节点应固定在最左层, `PORT_OUT` 节点应固定在最右层。让数据流方向 100% 清晰。

### 任务
- [x] `navisv/graph/elk_exporter.py`: `_node_to_elk()` 给 Port/Input/Output/Inout 加 `layoutOptions.elk.layered.layering.layerConstraint`
  - `direction ∈ {input, inout, In}` → `FIRST`
  - 其他 → `LAST`
- [x] `tests/test_elk_exporter.py`: +8 个测试
  - TestPortLayerConstraint (5): 单元 (input/output/inout variants, State 无 constraint, portConstraints.fixedSide 共存)
  - TestStage28EndToEnd (3): counter.sv e2e (三个 input port 都 FIRST, count State 无 constraint, ELK 输出 x 在最左)

### 验收
- counter.sv PNG: 三个 input port 垂直对齐在左列, count State 在右, 数据流方向清晰
- 87 elk_exporter tests pass (37+10+17+15+8), 357 navisv tests pass (零回归)
- 改动只有 2 个文件 (elk_exporter.py + test), 改动量小, 效果大

### Bugfix
第一次写错: 只匹配 `input`/`inout`, 但 slang-netlist 输出 direction 是 `In`/`Out` (首字母大写)。三个 input port 都被设成 LAST。修复: 加 `In` 到 first set。

### Commit
```
feat(elk): Stage 2.8 — port FIRST/LAST layer constraint (from sv_query)
```

---

## Stage 3: CLI + 3 视图 (2026-08-06)

**背景**: 之前的 Stages 1-2.9 都只能通过 Python API 调用, 没在 CLI 暴露。`navisv elk` 是用户主要的调用入口。

### 任务
- [x] `cli.py`: 加 `elk` 子命令 (`add_parser('elk', help='ELK layered 可视化 (HTML/SVG/PNG)')`)
  - 10 个选项: file, --view, --output, --filter-clock-reset, --max-nodes, --scope, --cdc-highlight, --direction, --include, --preserve-operators
- [x] `cli.py`: 加 `run_elk()` 函数 (跟 run_dot/run_mermaid 同 pattern, ~110 行)
  - DesignDriver(cache=False) → GraphBuilder → ElkExporter → ELK layout → render
  - 输出路由按后缀 (.html/.svg/.png/.json)
  - 元数据报告 (children/edges/filtered_edges/orphan_nodes_removed)
- [x] `cli.py`: 加 `elif args.command == 'elk': run_elk(args)` dispatcher
- [x] `tests/test_cli_elk.py`: +14 个 CLI 集成测试 (subprocess 调 `cli.py elk`)
  - argparse (2): --help + main --help 包含 elk
  - dataflow view (6): HTML/SVG/PNG/JSON 输出 + metadata + no-filter-clock-reset
  - other views (3): controlflow / modules / direction DOWN
  - error handling (2): missing file + invalid view
  - E2E (1): 真实 counter.sv 端到端

### 验收
- `navisv elk tests/fixtures/elk_counter.sv` → `elk_counter.elk.html` (1.6MB, bundled elkjs)
- `navisv elk <file> -o out.svg` → SVG (dataflow, filter_clock_reset 默认开)
- `navisv elk <file> -o out.png` → PNG (rsvg-convert 1600px)
- `navisv elk <file> --view controlflow` → controlflow (filter 自动关)
- `navisv elk <file> --no-filter-clock-reset` → 跟 Stage 2.7 行为一致
- 14 CLI tests pass, 382 navisv tests total pass (零回归)

### Bugfix
1. `DesignDriver(cache=True)` 返回 `DesignGraph` (module hierarchy, 4 节点), 不是 `GraphBuilder` (dataflow)。ELK 需要 dataflow → `cache=False`
2. `render_svg()` 不接受 `direction=` 参数 (TypeError "unexpected keyword argument 'direction'") → 移除
3. 测试 helper `_run_cli()` 必须传 'elk' 子命令 (subprocess.run 不继承 pytest cwd)
4. 默认输出文件名是 `<basename>.elk.html` (e.g. `elk_counter.elk.html` for `tests/fixtures/elk_counter.sv`)

### Commit
```
feat(elk): Stage 3 — CLI navisv elk <file.sv> with 3 views (dataflow/controlflow/modules)
```

---

## Stage 1: ElkExporter 骨架 + DataFlowGraph → elk JSON (2h)

**目标**: Python 端能产出 elkjs 兼容的 JSON 字符串，先不生成 HTML。

### 任务
- [ ] 创建 `navisv/graph/elk_exporter.py`
- [ ] 实现 `ElkExporter` 类骨架（dataclass 风格）
- [ ] 实现 `from_graph_builder(gb: GraphBuilder)` 加载数据流
- [ ] 实现 `to_elk_json()` 基础转换（节点 → children，边 → edges）
- [ ] 实现 `_node_to_elk()` / `_edge_to_elk()` 内部辅助
- [ ] 加 `properties` 字段（kind/file/line/source/scope）
- [ ] 单元测试: `tests/test_elk_exporter.py`
  - 最小 SV → GraphBuilder → ElkExporter → JSON dict → snapshot
  - 验证 JSON 含 children/edges/ports/properties

### 验收
```python
from navisv.graph.graph_builder import GraphBuilder
from navisv.graph.elk_exporter import ElkExporter

gb = GraphBuilder(...)
gb.add_node(...)
gb.add_edge(...)

exporter = ElkExporter(view="dataflow").from_graph_builder(gb)
json_data = exporter.to_elk_json()
assert "children" in json_data
assert "edges" in json_data
```

### Commit
```
feat(elk): Stage 1 — ElkExporter skeleton + dataflow JSON conversion
```

---

## Stage 2: HTML viewer + bundled elkjs (1.5h)

**目标**: 生成自包含 HTML，浏览器打开能看到静态布局图。

### 任务
- [ ] 复制 `~/my_proj/elkjs/examples/node_modules/elkjs/lib/elk.bundled.js` 到 `navisv/data/elk.bundled.js`
- [ ] 创建 `navisv/graph/elk_html_template.py` (f-string 模板)
  - `<head>` + `<style>` + `<script src="elk.bundled.js">`
  - `<body>` 骨架 (toolbar / graph / sidebar)
  - 嵌入 JSON 的 `<script>`
- [ ] 创建 `navisv/data/elk_viewer.js` (交互层骨架)
  - `ELK.layout(GRAPH_DATA).then(renderSVG)`
  - 最小 renderSVG 函数（elkjs 标准输出 → SVG 字符串）
- [ ] 实现 `ElkExporter.export_html(output_path)`
- [ ] 单元测试: `tests/test_elk_html.py`
  - 生成 HTML → 检查含 `elk.bundled.js` 引用 + `GRAPH_DATA` 嵌入 + 必要 DOM

### 验收
```bash
python3 -c "
from navisv.graph.graph_builder import GraphBuilder
from navisv.graph.elk_exporter import ElkExporter
gb = GraphBuilder.from_design('tests/fixtures/counter.sv')
ElkExporter(view='dataflow').from_graph_builder(gb).export_html('/tmp/c.html')
"
open /tmp/c.html  # 浏览器看到图
```

### Commit
```
feat(elk): Stage 2 — HTML viewer template + bundled elkjs.js
```

---

## Stage 3: CLI + 3 视图 (2h)

**目标**: `navisv elk design.sv --view {dataflow,controlflow,modules}` 全部能用。

### 任务
- [ ] 在 `cli.py` 加 `elk` 子命令
  - 解析 `--view`, `--cdc-highlight`, `--scope`, `--max-nodes`, `--output`, `--json-only`
  - 调用对应 view builder
- [ ] 创建 `navisv/graph/elk_view_dataflow.py` (复用 Stage 1)
- [ ] 创建 `navisv/graph/elk_view_controlflow.py`
  - 用 `ast_parser` 提取 always/if/case
  - elkjs `mrtree` 或 `layered` 算法
- [ ] 创建 `navisv/graph/elk_view_modules.py`
  - 用 `ast_parser` instance tree
  - elkjs `stress` (force) 算法
- [ ] 实现 view dispatch (按 `--view` 选择 builder)
- [ ] 测试: `tests/test_elk_e2e.py`
  - 用 `tests/fixtures/counter.sv` 跑 3 个 view
  - 验证 HTML 生成 + 大小合理

### 验收
```bash
navisv elk tests/fixtures/counter.sv --view dataflow -o /tmp/df.html
navisv elk tests/fixtures/counter.sv --view controlflow -o /tmp/cf.html
navisv elk tests/fixtures/counter.sv --view modules -o /tmp/m.html
# 三个 HTML 都能在浏览器打开
```

### Commit
```
feat(elk): Stage 3 — CLI navisv elk + 3 views (dataflow/controlflow/modules)
```

---

## Stage 4: 交互层 (1.5h)

**目标**: 节点点击、边 hover、搜索、CDC toggle 全部生效。

### 任务
- [ ] 在 `navisv/data/elk_viewer.js` 加交互
  - 节点 click → 高亮上下游 (`properties.kind` 决定路径)
  - 节点 click → 侧栏显示源码 (从 `properties.source`)
  - 边 hover → tooltip (从 `properties` 提取条件)
  - 搜索框 → 输入信号名 → 跳转 + 高亮
  - CDC toggle → 切换 `.cdc` CSS class
  - 缩放/拖拽 (elkjs 自带)
- [ ] 在 `navisv/data/elk_viewer.css` 加样式
  - 输入端口蓝、输出端口橙
  - reg/wire 节点不同形状
  - CDC 边红色加粗
  - 选中节点高亮
- [ ] 更新 `elk_html_template.py` 嵌入新版 CSS+JS
- [ ] 测试: 手动跑 picorv32，截图（可选）

### 验收
- 浏览器打开生成的 HTML
- 点击 "alu.add_inst" 节点 → 侧栏弹出源码
- 搜索 "reg_q" → 跳到该节点
- toggle CDC → 红色边出现/消失

### Commit
```
feat(elk): Stage 4 — interaction layer (click/hover/search/CDC toggle)
```

---

## Stage 5: 真实 RTL 测试 (1h)

**目标**: 在 picorv32 (9133 行) 上验证大图性能。

### 任务
- [ ] 下载/确认 picorv32.f 路径 (~/my_dv_proj/picorv32/)
- [ ] 跑 `navisv elk picorv32.v --view dataflow -o /tmp/pico.html`
  - 计时：生成时间 ≤30s
  - HTML 大小 ≤2.5MB
- [ ] 跑 controlflow + modules 视图
- [ ] 在浏览器手动验证：
  - 大图（数千节点）能渲染（elkjs 可能要等几秒）
  - 搜索响应快
  - 缩放流畅
- [ ] 加 `--max-nodes 500` 默认截断保护
- [ ] 简单计数器 fixture 加到 `tests/fixtures/`

### 验收
```bash
time navisv elk ~/my_dv_proj/picorv32/picorv32.v --view dataflow -o /tmp/pico.html
# real < 30s
# file size < 2.5MB
```

### Commit
```
feat(elk): Stage 5 — real RTL validation (picorv32, counter)
```

---

## Stage 6: examples + README + push (1h)

**目标**: 项目可被发现、可演示、可分享。

### 任务
- [ ] 创建 `examples/elk_dataflow.py`
- [ ] 创建 `examples/elk_controlflow.py`
- [ ] 创建 `examples/elk_modules.py`
- [ ] 更新 `README.md`
  - 加 "🆕 Interactive Visualization (elkjs)" 章节
  - 加 `navisv elk` 用法示例
  - 加 1-2 张截图（手动截浏览器）
- [ ] 加 `docs/ELKJS_SPEC.md` / `docs/ELKJS_PLAN.md` 索引
- [ ] git commit + push 到 origin
- [ ] 跑全部测试，确认无回归

### 验收
- README 看得到 elkjs 可视化介绍
- examples/ 有 3 个独立脚本可跑
- git log 显示 6 个清晰 stage commit
- 12 原有测试 + 5+ 新测试全过

### Commit
```
docs(elk): Stage 6 — examples + README update
```

---

## 长程任务跟踪

| 阶段 | 状态 | 完成时间 | Commit | 备注 |
|------|------|---------|--------|------|
| 1 — 骨架 + dataflow | ⏳ | — | — | 下一阶段 |
| 2 — HTML + bundled | ⏸️ | — | — | 待 stage 1 |
| 3 — CLI + 3 视图 | ⏸️ | — | — | 待 stage 2 |
| 4 — 交互层 | ⏸️ | — | — | 待 stage 3 |
| 5 — RTL 测试 | ⏸️ | — | — | 待 stage 4 |
| 6 — docs + push | ⏸️ | — | — | 待 stage 5 |

每阶段完成后更新此表 + 在 `memory/2026-08-05.md` 写日记。

---

## 跨阶段注意事项

1. **每阶段独立 commit**，方便 review 和回滚
2. **测试先行**：每阶段先写测试再写实现（除 stage 2 模板外）
3. **commit 前必跑测试**：`pytest tests/test_elk*.py -v`
4. **bundled elkjs 是大文件** (2MB)，用 git LFS？或者 .gitignore + install 脚本拉？看情况
5. **不要碰 cli.py 现有逻辑**，只在末尾加 `elif args.command == 'elk':` 分支
6. **保留 DOT/Mermaid**，不要标 deprecated

---

## 备用方案

如果 elkjs 在某个阶段卡住：

| 卡点 | 备选 |
|------|------|
| bundled.js 太大 | 用 elkjs 的 `lib/elk-api.min.js` (无 worker, ~700KB) |
| mrtree 算法效果差 | 改 `layered` |
| stress 算法太慢 | 改 `force` |
| Safari 渲染问题 | 文档标注"推荐 Chrome/Firefox" |
| 大 RTL 太慢 | 默认 `--max-nodes 500` + 加节点虚拟化 |

如果整个 elkjs 路线失败，回退方案：保留现有 DOT/Mermaid，不影响 navisv 主流程。