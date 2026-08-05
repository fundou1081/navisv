# navisv × elkjs 交互式可视化 — SPEC

> 状态: Draft v1 (2026-08-05)
> 目标: 用 elkjs (Eclipse Layout Kernel, JS 版) 替换/补充现有 DOT+Mermaid 静态输出，让 navisv 用户能交互式探索代码、数据流、控制流。

---

## 1. 设计原则

| 原则 | 含义 |
|------|------|
| **离线可用** | bundled elkjs.js (~2MB) 嵌入 HTML，单文件可分享，不依赖 CDN |
| **零 Python 依赖** | navisv 不引入 jinja2 等新依赖，HTML 模板用 f-string |
| **保留 DOT/Mermaid** | 不同场景适合不同格式，老接口不废弃 |
| **Python 只产 JSON+HTML** | 布局和渲染在浏览器跑 elkjs，Python 端不调 JS 引擎 |
| **可分享** | 一个 `.html` 文件 = 整张图 + 交互，离线能开 |

---

## 2. 视图类型 (4 种)

elkjs 强在不同算法适配不同语义，navisv 把"一刀切 DOT"拆成多视图：

| 视图 | CLI flag | elkjs 算法 | 数据来源 | 用途 |
|------|---------|-----------|---------|------|
| **数据流** | `--view dataflow` (default) | `layered` (DOWN) | `GraphBuilder` + `path_tracer` | 看信号怎么从 A 流到 B |
| **控制流** | `--view controlflow` | `mrtree` | `ast_parser` (always/if/case) | 看 always 块怎么分支 |
| **模块层级** | `--view modules` | `stress` (force) | `ast_parser` instances | 看 RTL 整体结构 |
| **CDC 高亮** | `--cdc-highlight` (任意视图) | `layered` + 边色 | `_get_cdc_edge_pairs` | 跨时钟域边单独着色 |

**MVP 范围**：Stage 3 实现 `dataflow` + `controlflow` + `modules` 三视图。`cdc-highlight` 作为 toggle，在 dataflow 上叠加。

---

## 3. 数据格式 (elkjs 原生 JSON)

navisv Python 端产出 elkjs 输入格式：

```json
{
  "id": "root",
  "layoutOptions": {
    "elk.algorithm": "layered",
    "elk.direction": "DOWN",
    "elk.spacing.nodeNode": "40",
    "elk.layered.spacing.nodeNodeBetweenLayers": "50",
    "elk.portConstraints": "FIXED_SIDE"
  },
  "children": [
    {
      "id": "alu.add_inst",
      "labels": [{"text": "alu (alu.sv:42)"}],
      "width": 180, "height": 60,
      "ports": [
        {"id": "in.a",  "layoutOptions": {"portConstraints.fixedSide": "WEST"}},
        {"id": "in.b",  "layoutOptions": {"portConstraints.fixedSide": "WEST"}},
        {"id": "out.r", "layoutOptions": {"portConstraints.fixedSide": "EAST"}}
      ],
      "children": [  // compound node：模块嵌套
        {"id": "alu.add_inst.reg_q", "labels": [{"text": "reg_q"}]}
      ]
    }
  ],
  "edges": [
    {
      "id": "e1",
      "sources": ["alu.add_inst.in.a"],
      "targets": ["alu.add_inst.reg_q"],
      "labels": [{"text": "always_ff @(posedge clk)"}],
      "layoutOptions": { "elk.edge.color": "#e74c3c" }
    }
  ]
}
```

### 3.1 必须用上的 elkjs 特性

1. **`ports` + `portConstraints`** — 输入端口固定在节点西边 (WEST)、输出在东边 (EAST)，数据流方向一目了然
2. **`compound children`** — 模块作为父节点，内部信号嵌套显示（DOT 用 cluster 模拟，elkjs 是原生）
3. **`layoutOptions` per edge** — 单条边单独着色（CDC 高亮用）
4. **`labels`** — 节点/边可附加多行文本（源码摘要 + 行号）
5. **`properties`** (扩展) — 嵌入 navisv 自定义数据 (节点类型、文件路径、源码片段) 给交互层用

### 3.2 properties 扩展 (交互层用)

每个节点和边带额外数据，嵌入 HTML 后浏览器交互层读取：

```json
{
  "id": "alu.reg_q",
  "labels": [{"text": "reg_q"}],
  "properties": {
    "kind": "reg",                         // "reg" | "wire" | "input" | "output" | "instance" | "module"
    "file": "alu.sv",
    "line": 42,
    "source": "logic [7:0] reg_q;",        // 源码片段（≤200 chars）
    "scope": "alu"
  }
}
```

---

## 4. Python API 设计

新文件：`navisv/graph/elk_exporter.py`

```python
# navisv/graph/elk_exporter.py
from typing import Literal, Optional, Dict, Any
from pathlib import Path

ViewType = Literal["dataflow", "controlflow", "modules"]

class ElkExporter:
    """Convert navisv graphs to elkjs input JSON + emit interactive HTML."""

    def __init__(self, view: ViewType = "dataflow"):
        self.view = view
        self.cdc_highlight = False

    def from_graph_builder(self, gb: "GraphBuilder") -> "ElkExporter":
        """Load graph from GraphBuilder (dataflow)."""
        ...

    def from_ast(self, ast: dict, design: str) -> "ElkExporter":
        """Load graph from AST (controlflow or modules)."""
        ...

    def to_elk_json(self) -> Dict[str, Any]:
        """Convert to elkjs JSON format."""
        ...

    def export_html(self, output_path: str, embed_source: bool = True) -> Path:
        """Generate self-contained HTML viewer.

        Single file with:
          - bundled elkjs.js
          - embedded JSON
          - embedded CSS + interaction JS
        """
        ...

    def export_json(self, output_path: str) -> Path:
        """Generate .json only (for elkjs.live / other tools)."""
        ...
```

### 4.1 CLI 接口

```
navisv elk <file.sv> [options]

  --view {dataflow,controlflow,modules}   视图类型 (default: dataflow)
  --cdc-highlight                          高亮 CDC 边
  --scope, -s <hier.path>                  聚焦子模块 (e.g. top.cpu.alu)
  --include-internal                       modules 视图显示内部信号
  --max-nodes <N>                          大图截断 (default: 500)
  --output, -o <file.html>                 输出 HTML (必填)
  --json-only                              只输出 .json，不生成 HTML
```

### 4.2 Python API (供 agent 使用)

```python
from navisv.graph.elk_exporter import ElkExporter

exporter = ElkExporter(view="dataflow").from_graph_builder(gb)
exporter.export_html("/tmp/alu.html")
```

---

## 5. HTML Viewer 规格

### 5.1 文件结构 (单文件)

```
navisv.html
├── <head>
│   ├── meta + title
│   ├── <style>  (CSS, ~3KB)
│   └── <script src="elk.bundled.js">  (~2MB)
└── <body>
    ├── <div id="toolbar">
    │   ├── search box
    │   ├── view selector
    │   ├── CDC toggle
    │   └── zoom controls
    ├── <div id="graph">  (SVG 容器)
    └── <div id="sidebar">  (选中节点时显示源码)
    └── <script>
        ├── const GRAPH_DATA = { ... };   // 嵌入 JSON
        ├── ELK.layout(...)
        ├── renderSVG(...)
        └── setupInteraction(...)
```

### 5.2 交互功能 (MVP)

| 功能 | 实现 | 优先级 |
|------|------|--------|
| 节点点击 → 高亮上下游 + 侧栏源码 | SVG event + JSON `properties` | P0 |
| 边 hover → tooltip 显示条件/时序 | SVG title element | P0 |
| 搜索信号名 → 跳转 + 高亮 | JS string match + 缩放 | P0 |
| 视图切换 (dataflow/controlflow/modules) | 重渲染（不同 JSON） | P1 |
| CDC toggle | 改边颜色 class | P1 |
| 缩放/拖拽 | elkjs 自带 pan/zoom | P0 |
| 大图性能 (1k+ 节点) | elkjs SVG + 节点虚拟化 | P2 |

### 5.3 视觉规范

| 元素 | 样式 |
|------|------|
| 输入端口 | 西边 (left)，蓝色 (#3498db) |
| 输出端口 | 东边 (right)，橙色 (#e67e22) |
| 模块节点 (compound) | 浅灰背景 (#ecf0f1)，粗边框 |
| 寄存器 reg | 矩形，绿边 (#27ae60) |
| 线网 wire | 圆角矩形，灰边 (#95a5a6) |
| 组合边 | 黑色 (#2c3e50) |
| 时序边 | 蓝色 (#2980b9) |
| CDC 边 | 红色 (#e74c3c)，加粗 |

---

## 6. 与现有可视化的关系

| 命令 | 现状 | 未来 |
|------|------|------|
| `navisv dot <file>` | Graphviz DOT 输出 | **保留**（专业报告、PNG 嵌入） |
| `navisv mermaid <file>` | Mermaid 输出 | **保留**（粘文档、轻量分享） |
| `navisv elk <file>` | ❌ 不存在 | **新增**（交互探索） |
| `--format dot/mermaid` | 多命令支持 | **保留**，新增 `--format elk` 选项 |

DOT 和 Mermaid 各自场景：
- DOT: 论文/正式报告的高清 PNG
- Mermaid: GitHub README、飞书文档快速嵌入
- elk: 调试阶段交互探索

---

## 7. 不做什么 (Out of Scope)

- ❌ 服务化（不启动 HTTP server，本地 file:// 即可）
- ❌ 实时协作（多人编辑同一图）
- ❌ 图的 diff/版本对比（v1 单图）
- ❌ 嵌入 sv_query（navisv 独立项目，跨项目集成留到 v2）
- ❌ 导出为图片（用户在浏览器里截图就行）
- ❌ 流式/渐进式渲染（elkjs 单次 layout 够用）

---

## 8. 验收标准 (Definition of Done)

- [ ] `navisv elk design.sv -o /tmp/x.html` 在 Safari/Chrome 打开能渲染
- [ ] dataflow / controlflow / modules 三视图各自能用
- [ ] 点击节点弹出源码（来自 embedded source map）
- [ ] 搜索信号名能跳转
- [ ] CDC 高亮 toggle 生效
- [ ] picorv32 (9133 行) 生成 ≤30s，HTML 打开 ≤5s
- [ ] 单 HTML 文件 ≤2.5MB（含 bundled elkjs）
- [ ] 12 个现有测试不回归
- [ ] 新增 ≥5 个测试（elk_exporter 单元测试 + 端到端）

---

## 9. 文件清单

### 新增

```
navisv/graph/elk_exporter.py                  # 核心 (~400 行)
navisv/graph/elk_view_dataflow.py             # dataflow 视图 (~150 行)
navisv/graph/elk_view_controlflow.py          # controlflow 视图 (~150 行)
navisv/graph/elk_view_modules.py              # modules 视图 (~120 行)
navisv/graph/elk_html_template.py             # HTML 模板 (~300 行)
navisv/data/elk.bundled.js                    # bundled elkjs (~2MB, copy 自 my_proj/elkjs/examples/node_modules/elkjs/lib/)
navisv/data/elk_viewer.js                     # 交互层 JS (~5KB)
navisv/data/elk_viewer.css                    # 样式 (~2KB)

tests/test_elk_exporter.py                    # 单元测试
tests/test_elk_html.py                        # HTML 生成测试
tests/test_elk_e2e.py                         # 端到端 (picorv32 + 简单计数器)

examples/elk_dataflow.py
examples/elk_controlflow.py
examples/elk_modules.py
```

### 修改

```
navisv/cli.py                                 # 加 `navisv elk` 子命令
navisv/graph/__init__.py                      # 导出 ElkExporter
README.md                                     # 加 elk 可视化章节
docs/ELKJS_PLAN.md                            # 实施计划（独立文档）
```

---

## 10. 风险与缓解

| 风险 | 缓解 |
|------|------|
| bundled elkjs.js 文件大 (2MB) | 用 min 版本；只在用户调用 elk 命令时才嵌入 |
| 大 RTL (10k+ 行) 渲染慢 | elkjs 默认 `< 5s`，加 `--max-nodes` 截断 + node 虚拟化 |
| 浏览器兼容 (Safari/Chrome/Firefox) | elkjs 官方支持现代浏览器；CI 用 playwright smoke test |
| 用户机器没浏览器 | 文档说"需要 Chrome/Safari/Firefox 70+" |
| Layout 算法选错导致图难看 | dataflow 默认 `layered`，controlflow `mrtree`，modules `stress`；用户可 `--elk-algorithm` 覆盖 |
| 跨平台 (Mac/Linux/Win) | HTML 是平台无关的；只在 Python 端写文件，不引入 OS 差异 |