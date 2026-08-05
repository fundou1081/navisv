/* elk_viewer.js — navisv × elkjs 最小交互式渲染器
 *
 * 用法: 由 elk_html_template.py 嵌入到生成的 HTML 中。
 * 输入: GRAPH_DATA (navisv ElkExporter 输出的 elkjs JSON)
 * 输出: 渲染到 #graph 容器的 SVG,带颜色/箭头/端口
 *
 * 设计目标 (Stage 2 范围):
 *   - ELK.layout() → SVG, 端口对齐, 颜色按 properties
 *   - 节点/边可点击 (info 面板在 <div id="info"> 显示)
 *   - 简单的 CSS hover 高亮
 *
 * Stage 4 会扩展: 搜索/视图切换/CDC toggle/缩放/拖拽
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
        '" xmlns="http://www.w3.org/2000/svg">';

      // arrow marker
      svg +=
        '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5"' +
        ' markerWidth="6" markerHeight="6" orient="auto">' +
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#2c3e50"/></marker></defs>';

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
        const lbl =
          node.labels && node.labels[0] ? node.labels[0].text : node.id;
        svg +=
          '<g class="node" data-node-id="' + node.id + '">' +
          '<rect class="node-rect" x="' + x + '" y="' + y +
          '" width="' + node.width + '" height="' + node.height +
          '" rx="6" fill="white" stroke="' + color + '" stroke-width="2"/>' +
          '<text class="node-label" x="' + (x + node.width / 2) +
          '" y="' + (y + node.height / 2 + 4) + '">' +
          escapeHtml(lbl) + '</text>';
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

      // Legend (固定右上角)
      svg += '<g class="legend" transform="translate(' + (off + 10) + ',' + (off + 10) + ')">';
      svg +=
        '<rect x="0" y="0" width="180" height="76" fill="white"' +
        ' stroke="#bdc3c7" rx="4" opacity="0.95"/>';
      svg += '<text class="legend-title" x="10" y="18">Legend</text>';
      svg +=
        '<rect x="10" y="28" width="14" height="10" fill="white"' +
        ' stroke="#27ae60" stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="37">State (Reg)</text>';
      svg +=
        '<rect x="10" y="44" width="14" height="10" fill="white"' +
        ' stroke="#3498db" stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="53">Port (in/out)</text>';
      svg +=
        '<line x1="10" y1="64" x2="24" y2="64" stroke="#16a085"' +
        ' stroke-width="2"/>' +
        '<text class="legend-text" x="30" y="67">AlwaysFF</text>';
      svg += '</g>';

      svg += '</svg>';

      const container = document.getElementById('graph');
      if (container) container.innerHTML = svg;

      // 点击交互: 节点 / 边 → 显示到 #info
      setupClickHandlers(layouted);
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
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

  // 启动 (GRAPH_DATA 由模板嵌入)
  if (typeof GRAPH_DATA !== 'undefined') {
    render(GRAPH_DATA).catch(function (err) {
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