# navisv × elkjs 实施 PLAN

> 配套文档: [ELKJS_SPEC.md](./ELKJS_SPEC.md)
> 创建: 2026-08-05
> 预计总工时: ~9 小时，分 6 阶段

---

## 总览

```
Stage 1  ElkExporter 骨架 + 数据流转换  → 2h
Stage 2  HTML viewer + bundled elkjs    → 1.5h
Stage 3  CLI + 3 视图                    → 2h
Stage 4  交互层 (搜索/高亮/CDC toggle)   → 1.5h
Stage 5  真实 RTL 测试                   → 1h
Stage 6  examples + README + push        → 1h
```

每阶段结束 = 一个 git commit + 一个可工作的演示。

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