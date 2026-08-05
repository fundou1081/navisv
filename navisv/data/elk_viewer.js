/* elk_viewer.js — navisv × elkjs 交互式渲染器
 *
 * 用法: 由 elk_html_template.py 嵌入到生成的 HTML 中。
 * 输入: GRAPH_DATA (navisv ElkExporter 输出的 elkjs JSON)
 * 输出: 渲染到 #graph 容器的 SVG,带颜色/箭头/端口
 *
 * 设计目标:
 *   Stage 2: ELK.layout() → SVG, 端口对齐, 颜色按 properties
 *            节点/边可点击 (info 面板在 <div id="info"> 显示)
 *            简单的 CSS hover 高亮
 *   Stage 4: 搜索框 (按名字过滤节点)
 *            节点类型过滤器 (Port/State/Operator/Literal 复选框)
 *            CDC toggle (高亮/隐藏跨时钟域边)
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------
  // Utility: 找节点或端口 (elkjs 把 source/target 拆到节点或子端口)
  // ---------------------------------------------------------------------
  function findEndpoint(layouted, id) {
    for (const c of layouted.children) {
      if (c.id === id) return { node: c, port: null };
      if (c.ports) {
        for (const p of c.ports) {
          if (p.id === id) return { node: c, port: p };
        }
      }
    }
    return null;
  }

  function endpointXY(endpoint, offX, offY) {
    if (!endpoint) return null;
    const { node, port } = endpoint;
    if (port) {
      return {
        x: node.x + port.x + port.width / 2 + offX,
        y: node.y + port.y + port.height / 2 + offY,
      };
    }
    return {
      x: node.x + node.width / 2 + offX,
      y: node.y + node.height / 2 + offY,
    };
  }

  // ---------------------------------------------------------------------
  // 主渲染函数
  // ---------------------------------------------------------------------
  function render(graphData) {
    return ELK.layout(graphData).then(function (layouted) {
      const w = Math.max(layouted.width || 600, 600);
      const h = Math.max(layouted.height || 400, 400);
      const off = 20;

      let svg =
        '<svg width="' + (w + off * 2) + '" height="' + (h + off * 2) +
        '" xmlns="http://www.w3.org/2000/svg" id="graph-svg">';

      // arrow marker
      svg +=
        '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5"' +
        ' markerWidth="6" markerHeight="6" orient="auto">' +
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#2c3e50"/></marker></defs>';

      // (Stage 7) pan/zoom transform group — all content is inside this group
      svg += '<g id="graph-view" transform="translate(0,0) scale(1)">';

      // 边
      (layouted.edges || []).forEach(function (edge) {
        const s = findEndpoint(layouted, edge.sources[0]);
        const t = findEndpoint(layouted, edge.targets[0]);
        const sp = endpointXY(s, off, off);
        const tp = endpointXY(t, off, off);
        if (!sp || !tp) return;
        const color =
          (edge.properties && edge.properties.color) || '#2c3e50';
        const lbl =
          edge.labels && edge.labels[0] ? edge.labels[0].text : '';
        svg +=
          '<line class="edge" x1="' + sp.x + '" y1="' + sp.y +
          '" x2="' + tp.x + '" y2="' + tp.y +
          '" stroke="' + color + '" stroke-width="1.8" marker-end="url(#arr)"' +
          ' data-edge-id="' + edge.id + '"/>';
        if (lbl) {
          const mx = (sp.x + tp.x) / 2;
          const my = (sp.y + tp.y) / 2;
          svg +=
            '<text class="edge-label" x="' + mx + '" y="' + (my - 4) +
            '" text-anchor="middle">' + escapeHtml(lbl) + '</text>';
        }
      });

      // 节点
      (layouted.children || []).forEach(function (node) {
        const x = node.x + off;
        const y = node.y + off;
        const color =
          (node.properties && node.properties.color) || '#34495e';
        const kind = (node.properties && node.properties.kind) || '';
        const lbl =
          node.labels && node.labels[0] ? node.labels[0].text : node.id;
        const isOperator = (kind === 'Operator');
        const isLiteral = (kind === 'Literal');

        svg += '<g class="node node-' + kind.toLowerCase() +
               '" data-node-id="' + node.id + '">';

        if (isOperator) {
          // 菱形: 中心点 (x+w/2, y+h/2),四个角点
          const cx = x + node.width / 2;
          const cy = y + node.height / 2;
          const pts = [
            [cx, y],               // top
            [x + node.width, cy],  // right
            [cx, y + node.height], // bottom
            [x, cy]                // left
          ].map(function (p) { return p.join(','); }).join(' ');
          svg +=
            '<polygon class="node-shape operator" points="' + pts +
            '" fill="white" stroke="' + color + '" stroke-width="2"/>' +
            '<text class="node-label" x="' + cx + '" y="' + (cy + 4) +
            '">' + escapeHtml(lbl) + '</text>';
        } else if (isLiteral) {
          // 小矩形,颜色淡
          svg +=
            '<rect class="node-shape literal" x="' + x + '" y="' + y +
            '" width="' + node.width + '" height="' + node.height +
            '" rx="4" fill="#ecf0f1" stroke="' + color +
            '" stroke-width="1.5" stroke-dasharray="3,2"/>' +
            '<text class="node-label literal" x="' + (x + node.width / 2) +
            '" y="' + (y + node.height / 2 + 4) + '">' +
            escapeHtml(lbl) + '</text>';
        } else {
          svg +=
            '<rect class="node-rect" x="' + x + '" y="' + y +
            '" width="' + node.width + '" height="' + node.height +
            '" rx="6" fill="white" stroke="' + color + '" stroke-width="2"/>' +
            '<text class="node-label" x="' + (x + node.width / 2) +
            '" y="' + (y + node.height / 2 + 4) + '">' +
            escapeHtml(lbl) + '</text>';
        }
        if (node.ports) {
          node.ports.forEach(function (port) {
            const side =
              (port.layoutOptions &&
                port.layoutOptions.portConstraints &&
                port.layoutOptions.portConstraints.fixedSide) ||
              'WEST';
            let px, py;
            if (side === 'WEST') {
              px = x;
              py = y + node.height / 2;
            } else {
              px = x + node.width;
              py = y + node.height / 2;
            }
            svg +=
              '<circle class="port" cx="' + px + '" cy="' + py +
              '" r="3.5" fill="white" stroke="' + color +
              '" stroke-width="2"/>';
          });
        }
        svg += '</g>';
      });

      // Legend (固定右上角) - 包含 Operator / Literal (Stage 2.5)
      svg += '<g class="legend" transform="translate(' + (off + 10) + ',' + (off + 10) + ')">';
      svg +=
        '<rect x="0" y="0" width="190" height="118" fill="white"' +
        ' stroke="#bdc3c7" rx="4" opacity="0.95"/>';
      svg += '<text class="legend-title" x="10" y="18">Legend</text>';
      // State
      svg +=
        '<rect x="10" y="28" width="14" height="10" fill="white"' +
        ' stroke="#27ae60" stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="37">State (Reg)</text>';
      // Port
      svg +=
        '<rect x="10" y="44" width="14" height="10" fill="white"' +
        ' stroke="#3498db" stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="53">Port (in/out)</text>';
      // Operator (菱形)
      svg +=
        '<polygon points="10,72 17,64 24,72 17,80" fill="white"' +
        ' stroke="#e67e22" stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="72">Operator (if/&lt;=)</text>';
      // Literal (虚线)
      svg +=
        '<rect x="10" y="88" width="14" height="10" fill="#ecf0f1"' +
        ' stroke="#7f8c8d" stroke-width="1.5" stroke-dasharray="2,2"/>' +
        '<text class="legend-text" x="30" y="97">Literal (4&#39;h1)</text>';
      // AlwaysFF (边)
      svg +=
        '<line x1="10" y1="108" x2="24" y2="108" stroke="#16a085"' +
        ' stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="111">AlwaysFF</text>';
      svg += '</g>';

      svg += '</g>';  // close #graph-view
      svg += '</svg>';

      const container = document.getElementById('graph');
      if (container) container.innerHTML = svg;

      // 点击交互: 节点 / 边 → 显示到 #info
      setupClickHandlers(layouted);

      // (Stage 7) pan/zoom 交互
      setupPanZoom();
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // ---------------------------------------------------------------------
  // (Stage 7) Pan / Zoom
  //  - wheel 滚轮: 以鼠标位置为原点缩放
  //  - drag 背景: 平移 (节点/边 不触发, 用 target 检测)
  //  - 工具栏按钮: zoom-in / zoom-out / reset
  //  - 显示当前 zoom % 在 #zoom-level
  // ---------------------------------------------------------------------
  let viewState = { scale: 1, tx: 0, ty: 0 };
  let isPanning = false;
  let panStart = { x: 0, y: 0, tx: 0, ty: 0 };

  function applyViewTransform() {
    const g = document.getElementById('graph-view');
    if (!g) return;
    g.setAttribute(
      'transform',
      'translate(' + viewState.tx + ',' + viewState.ty + ') ' +
      'scale(' + viewState.scale + ')'
    );
    const zl = document.getElementById('zoom-level');
    if (zl) zl.textContent = Math.round(viewState.scale * 100) + '%';
  }

  function clampScale(s) {
    return Math.max(0.1, Math.min(5, s));
  }

  function zoomAt(factor, cx, cy) {
    const newScale = clampScale(viewState.scale * factor);
    const actualFactor = newScale / viewState.scale;
    // 保持缩放原点 (cx, cy) 不动
    viewState.tx = cx - (cx - viewState.tx) * actualFactor;
    viewState.ty = cy - (cy - viewState.ty) * actualFactor;
    viewState.scale = newScale;
    applyViewTransform();
  }

  function resetView() {
    viewState = { scale: 1, tx: 0, ty: 0 };
    applyViewTransform();
  }

  function setupPanZoom() {
    const svg = document.getElementById('graph-svg');
    if (!svg) return;

    // wheel 缩放 (用 ctrlKey 修饰避免和浏览器原生冲突, 但这里直接拦截)
    svg.addEventListener('wheel', function (e) {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      zoomAt(factor, cx, cy);
    }, { passive: false });

    // drag pan — 鼠标按下在 SVG 背景时触发 (不在节点/边)
    svg.addEventListener('mousedown', function (e) {
      // 只在背景 (svg 本身) 触发; 节点/边 会阻止 mousedown
      if (e.target.closest('.node, .edge, .port, .legend')) return;
      isPanning = true;
      panStart = { x: e.clientX, y: e.clientY, tx: viewState.tx, ty: viewState.ty };
      svg.classList.add('panning');
      e.preventDefault();
    });

    window.addEventListener('mousemove', function (e) {
      if (!isPanning) return;
      viewState.tx = panStart.tx + (e.clientX - panStart.x);
      viewState.ty = panStart.ty + (e.clientY - panStart.y);
      applyViewTransform();
    });

    window.addEventListener('mouseup', function () {
      if (isPanning) {
        isPanning = false;
        svg.classList.remove('panning');
      }
    });

    // 工具栏按钮
    const zoomIn = document.getElementById('zoom-in');
    if (zoomIn) zoomIn.addEventListener('click', function () {
      const rect = svg.getBoundingClientRect();
      zoomAt(1.25, rect.width / 2, rect.height / 2);
    });
    const zoomOut = document.getElementById('zoom-out');
    if (zoomOut) zoomOut.addEventListener('click', function () {
      const rect = svg.getBoundingClientRect();
      zoomAt(1 / 1.25, rect.width / 2, rect.height / 2);
    });
    const reset = document.getElementById('reset-view');
    if (reset) reset.addEventListener('click', resetView);

    // 初始同步 zoom-level 显示
    applyViewTransform();
  }

  function setupClickHandlers(layouted) {
    const info = document.getElementById('info');
    if (!info) return;

    document.querySelectorAll('.node').forEach(function (g) {
      g.addEventListener('click', function () {
        const id = g.dataset.nodeId;
        const node = (layouted.children || []).find(function (c) {
          return c.id === id;
        });
        if (!node) return;
        const p = node.properties || {};
        info.textContent =
          'Node: ' + id + '\n' +
          'Kind: ' + (p.kind || 'N/A') + '\n' +
          'Direction: ' + (p.direction || 'N/A') + '\n' +
          'Module: ' + (p.module || 'N/A') + '\n' +
          'File: ' + (p.file || 'N/A') + '\n' +
          'Line: ' + (p.line || 'N/A') + '\n' +
          'Timing: ' + (p.timing || 'N/A');
      });
    });

    document.querySelectorAll('.edge').forEach(function (line) {
      line.addEventListener('click', function () {
        const id = line.dataset.edgeId;
        const edge = (layouted.edges || []).find(function (e) {
          return e.id === id;
        });
        if (!edge) return;
        const p = edge.properties || {};
        info.textContent =
          'Edge: ' + id + '\n' +
          'Timing: ' + (p.timing || 'N/A') + '\n' +
          'Edge kind: ' + (p.edge_kind || 'N/A') + '\n' +
          'Condition: ' + (p.condition || '(none)') + '\n' +
          'Condition kind: ' + (p.condition_kind || 'N/A') + '\n' +
          'Control signals: ' +
          ((p.condition_signals || []).join(', ') || '(none)') + '\n' +
          'CDC: ' + (p.cdc ? 'YES' : 'no') + '\n' +
          'Path count: ' + (p.path_count || 1);
      });
    });
  }

  // ---------------------------------------------------------------------
  // (Stage 4) 交互层: 搜索 / 节点类型过滤器 / CDC toggle
  // ---------------------------------------------------------------------
  let currentLayouted = null;  // 保存最近渲染的 layouted 给 filters 用

  function getNodeKind(node) {
    return (node.properties && node.properties.kind) || '';
  }

  function getNodeLabel(node) {
    return (node.labels && node.labels[0] && node.labels[0].text) || node.id || '';
  }

  function applyFilters() {
    if (!currentLayouted) return;
    const query = (document.getElementById('search-input') || {}).value || '';
    const q = query.trim().toLowerCase();
    const showPort = (document.getElementById('show-port') || {}).checked;
    const showState = (document.getElementById('show-state') || {}).checked;
    const showOperator = (document.getElementById('show-operator') || {}).checked;
    const showLiteral = (document.getElementById('show-literal') || {}).checked;
    const cdcOn = (document.getElementById('toggle-cdc') || {}).dataset.on === 'true';

    let matchCount = 0;
    let visibleCount = 0;
    let totalNodes = 0;

    // 按节点过滤
    document.querySelectorAll('.node').forEach(function (g) {
      totalNodes++;
      const id = g.dataset.nodeId;
      const node = (currentLayouted.children || []).find(function (c) { return c.id === id; });
      if (!node) return;
      const kind = getNodeKind(node);
      const label = getNodeLabel(node);

      // kind 过滤
      let visible = true;
      if (kind === 'Port' && !showPort) visible = false;
      else if (kind === 'State' && !showState) visible = false;
      else if (kind === 'Operator' && !showOperator) visible = false;
      else if (kind === 'Literal' && !showLiteral) visible = false;

      // search 过滤 (case-insensitive substring match on label + id)
      const isMatch = !q || label.toLowerCase().indexOf(q) >= 0 || id.toLowerCase().indexOf(q) >= 0;
      if (q && isMatch) matchCount++;

      g.classList.toggle('dimmed', !visible);
      g.classList.toggle('hidden', !visible);
      g.classList.toggle('highlighted', q && isMatch && visible);
      if (visible) visibleCount++;
    });

    // 边过滤: CDC toggle + 隐含节点过滤 (两端有 hidden 节点的边也隐藏)
    const visibleNodes = new Set();
    document.querySelectorAll('.node:not(.hidden)').forEach(function (g) {
      visibleNodes.add(g.dataset.nodeId);
    });

    document.querySelectorAll('.edge').forEach(function (line) {
      const id = line.dataset.edgeId;
      const edge = (currentLayouted.edges || []).find(function (e) { return e.id === id; });
      if (!edge) return;
      const isCdc = edge.properties && edge.properties.cdc;

      // CDC toggle: CDC on 时高亮 (增加 stroke-width), off 时 dim (透明度降低)
      line.classList.toggle('cdc-highlighted', cdcOn && !!isCdc);
      line.classList.toggle('cdc-dimmed', !cdcOn && !!isCdc);

      // 两端节点都隐藏时, 边也隐藏
      const src = edge.sources && edge.sources[0];
      const tgt = edge.targets && edge.targets[0];
      const endpointsVisible = visibleNodes.has(src) || visibleNodes.has(tgt);
      line.classList.toggle('hidden', !endpointsVisible);
    });

    // 匹配计数
    const mc = document.getElementById('match-count');
    if (mc) {
      if (q) {
        mc.textContent = `${matchCount}/${totalNodes} match`;
      } else {
        mc.textContent = `${visibleCount}/${totalNodes} visible`;
      }
    }
  }

  function bindFilterControls() {
    const search = document.getElementById('search-input');
    if (search) search.addEventListener('input', applyFilters);

    ['show-port', 'show-state', 'show-operator', 'show-literal'].forEach(function (id) {
      const cb = document.getElementById(id);
      if (cb) cb.addEventListener('change', applyFilters);
    });

    const cdcBtn = document.getElementById('toggle-cdc');
    if (cdcBtn) {
      cdcBtn.addEventListener('click', function () {
        const on = cdcBtn.dataset.on === 'true';
        cdcBtn.dataset.on = on ? 'false' : 'true';
        cdcBtn.textContent = 'CDC: ' + (on ? 'off' : 'on');
        cdcBtn.classList.toggle('active', !on);
        applyFilters();
      });
    }
  }

  // 启动 (GRAPH_DATA 由模板嵌入)
  if (typeof GRAPH_DATA !== 'undefined') {
    render(GRAPH_DATA).then(function (layouted) {
      currentLayouted = layouted;
      bindFilterControls();
      applyFilters();  // 初始化时也跑一遍 (确保 cdc-dimmed 等初始状态)
    }).catch(function (err) {
      const container = document.getElementById('graph');
      if (container) {
        container.innerHTML =
          '<pre style="color:red">Layout error: ' +
          escapeHtml(err.message) + '</pre>';
      }
      console.error(err);
    });
  } else {
    console.error('[elk_viewer] GRAPH_DATA not found');
  }
})();