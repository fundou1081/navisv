"""elk_html_template.py - 生成 navisv × elkjs 自包含 HTML viewer

设计目标 (来自 ELKJS_SPEC.md §5):
- 单文件 HTML (含 bundled elkjs.js + 嵌入 JSON + 嵌入 CSS + 嵌入 JS)
- 离线可用 (不依赖 CDN)
- 浏览器打开即用 (file:// 协议)
- 自描述: 含 title/toolbar/info panel

Stage 2 范围: 最小可工作的 viewer (ELK.layout → SVG, 节点/边点击 → info)
Stage 4 会扩展: 搜索 / 视图切换 / CDC toggle / 缩放 / 拖拽
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# 资源加载: bundled elkjs.js + viewer.js + viewer.css
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"


def _read_data_file(name: str) -> str:
    """读取 navisv/data/ 下的资源文件"""
    path = _DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Required data file missing: {path}. "
            f"Run scripts/install_elkjs.sh or copy elk.bundled.js to {path}"
        )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML 模板 (f-string, 零 Python 依赖)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<div id="header">
  <h1>🧭 navisv × elkjs <span class="badge">{view}</span></h1>
  <span class="meta">{meta}</span>
</div>
<!-- (Stage 4) 交互工具栏: 搜索 / 节点类型过滤 / CDC toggle -->
<!-- (Stage 7) 加 zoom/pan 控件 (zoom-in/zoom-out/reset + zoom-level) -->
<div id="toolbar">
  <input type="search" id="search-input" placeholder="🔍 Search nodes (case-insensitive)..." autocomplete="off">
  <span class="filter-group">
    <label class="filter-label"><input type="checkbox" id="show-port" checked> Port</label>
    <label class="filter-label"><input type="checkbox" id="show-state" checked> State</label>
    <label class="filter-label"><input type="checkbox" id="show-operator" checked> Operator</label>
    <label class="filter-label"><input type="checkbox" id="show-literal" checked> Literal</label>
  </span>
  <button type="button" id="toggle-cdc" class="toggle-button" data-on="false">CDC: off</button>
  <button type="button" id="zoom-out" class="zoom-btn" title="Zoom out">−</button>
  <span id="zoom-level">100%</span>
  <button type="button" id="zoom-in" class="zoom-btn" title="Zoom in">+</button>
  <button type="button" id="reset-view" class="zoom-btn reset" title="Reset view">Reset</button>
  <!-- (Stage 16) 主题切换: Light / Dark / Auto -->
  <select id="theme-select" class="theme-select" title="Color theme">
    <option value="auto">🌓 Auto</option>
    <option value="light">☀️ Light</option>
    <option value="dark">🌙 Dark</option>
  </select>
  <!-- (Stage 18) 分享 URL: 复制带状态的链接 -->
  <button type="button" id="share-url" class="zoom-btn share-btn" title="Copy shareable URL with current view state">🔗 Share</button>
  <!-- (Stage 10) 多格式导出菜单: SVG / PNG / JSON / Mermaid -->
  <div class="dropdown" id="export-dropdown">
    <button type="button" id="export-btn" class="zoom-btn export-trigger" title="Export current view">Export ▼</button>
    <div class="dropdown-content" id="export-menu" hidden>
      <button type="button" class="export-item" data-format="svg">📄 SVG (vector)</button>
      <button type="button" class="export-item" data-format="png">🖼 PNG (image)</button>
      <button type="button" class="export-item" data-format="json">&#123; &#125; JSON (elk layout)</button>
      <button type="button" class="export-item" data-format="mermaid">🧜 Mermaid (markdown)</button>
    </div>
  </div>
  <span class="match-count" id="match-count"></span>
</div>
<div id="graph"><div style="padding:40px;color:#7f8c8d;">Rendering graph...</div></div>
<!-- (Stage 9) 节点/边详情侧边栏: 右侧 320px, 默认隐藏 -->
<aside id="sidebar" class="sidebar-closed" aria-label="Node details">
  <div class="sidebar-header">
    <span class="sidebar-title" id="sidebar-title">Details</span>
    <button type="button" id="sidebar-close" class="sidebar-close" title="Close sidebar">×</button>
  </div>
  <div class="sidebar-body" id="sidebar-body">
    <p class="sidebar-empty">Click any node or edge to see details.</p>
  </div>
</aside>
<div id="info">Click any node or edge to see details.</div>
<!-- (Stage 18) Share 复制成功 toast 提示 -->
<div id="toast" class="toast" hidden>✅ URL copied to clipboard</div>

<!-- (Stage 12) 快捷键帮助面板: 按 ? 弹窗显示所有快捷键 -->
<div id="help-modal" class="modal-overlay" hidden role="dialog" aria-label="Keyboard shortcuts">
  <div class="modal-content">
    <div class="modal-header">
      <span class="modal-title">⌨ Keyboard Shortcuts</span>
      <button type="button" id="help-close" class="modal-close" title="Close">×</button>
    </div>
    <div class="modal-body">
      <table class="shortcut-table">
        <thead>
          <tr><th>Key</th><th>Action</th></tr>
        </thead>
        <tbody>
          <tr><td><kbd>Cmd</kbd>+<kbd>F</kbd> / <kbd>Ctrl</kbd>+<kbd>F</kbd></td><td>Focus search</td></tr>
          <tr><td><kbd>Esc</kbd></td><td>Close sidebar / clear search</td></tr>
          <tr><td><kbd>+</kbd> / <kbd>=</kbd></td><td>Zoom in</td></tr>
          <tr><td><kbd>−</kbd></td><td>Zoom out</td></tr>
          <tr><td><kbd>0</kbd></td><td>Reset view</td></tr>
          <tr><td><kbd>C</kbd></td><td>Toggle CDC highlight</td></tr>
          <tr><td><kbd>1</kbd></td><td>Toggle Port nodes</td></tr>
          <tr><td><kbd>2</kbd></td><td>Toggle State nodes</td></tr>
          <tr><td><kbd>3</kbd></td><td>Toggle Operator nodes</td></tr>
          <tr><td><kbd>4</kbd></td><td>Toggle Literal nodes</td></tr>
          <tr><td><kbd>?</kbd> / <kbd>/</kbd></td><td>Show this help</td></tr>
        </tbody>
      </table>
      <p class="modal-hint">Tip: shortcuts are disabled when typing in search input.</p>
    </div>
  </div>
</div>

<script>
{elkjs_script}
</script>
<script>
{viewer_script}
</script>
<script>
const GRAPH_DATA = {graph_json};
</script>
</body>
</html>
"""


def build_html(
    elk_json: Dict[str, Any],
    title: str = "navisv × elkjs",
    view: str = "dataflow",
    meta: str = "",
) -> str:
    """组装完整 HTML 字符串

    Args:
        elk_json: ElkExporter.to_elk_json() 输出
        title: 浏览器标签标题
        view: 视图名 (dataflow/controlflow/modules), 显示在 toolbar badge
        meta: 副标题元信息 (e.g. "5 nodes · 4 edges")

    Returns:
        完整 HTML 字符串 (含 bundled elkjs.js 1.6MB)
    """
    import json as _json

    elkjs_script = _read_data_file("elk.bundled.js")
    viewer_script = _read_data_file("elk_viewer.js")
    css = _read_data_file("elk_viewer.css")
    graph_json = _json.dumps(elk_json)

    return _HTML_TEMPLATE.format(
        title=title,
        view=view,
        meta=meta or f"view: {view}",
        css=css,
        elkjs_script=elkjs_script,
        viewer_script=viewer_script,
        graph_json=graph_json,
    )


def meta_from_json(elk_json: Dict[str, Any], view: str) -> str:
    """从 elk JSON 自动生成 meta 字符串 (节点/边数 + 视图)"""
    n_nodes = len(elk_json.get("children", []))
    n_edges = len(elk_json.get("edges", []))
    return f"view: {view} · {n_nodes} nodes · {n_edges} edges · click for details"